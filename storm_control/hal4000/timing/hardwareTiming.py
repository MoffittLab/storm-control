#!/usr/bin/env python
"""
Handles hardware timing for a setup. This is a setup that doesn't
use a camera for the time base, but instead uses another source 
such as a counter on a DAQ card.

Note: In this case it is enforced that there are no master cameras.

Optionally the counter can output pulses whose high time is the camera
exposure time (for cameras configured in 'TriggerWidth' exposure mode),
and the counter can wait for an external start trigger, such as the
signal indicating that all the cameras are ready for a trigger.

Hazen 10/19
"""

from PyQt5 import QtCore

import storm_control.sc_library.halExceptions as halExceptions
import storm_control.sc_library.parameters as params

import storm_control.hal4000.halLib.halFunctionality as halFunctionality
import storm_control.hal4000.halLib.halMessage as halMessage
import storm_control.hal4000.halLib.halMessageBox as halMessageBox
import storm_control.hal4000.halLib.halModule as halModule


class HardwareTimingFrame(object):
    """
    This pretends to be a camera frame for the benefit of timing.timing.
    """
    def __init__(self, frame_number, **kwds):
        super().__init__(**kwds)
        
        self.frame_number = frame_number
        

class HardwareTimingFunctionality(halFunctionality.HalFunctionality):
    """
    This is tied to the source time base, such as a DAQ counter, so 
    that it emits a newFrame signal whenever the time base indicates
    the start of a new frame. 

    This pretends to be a camera functionality in order to work as
    expected with timing.timing.
    """
    newFrame = QtCore.pyqtSignal(object)
    startTimedOut = QtCore.pyqtSignal(str)
    stopped = QtCore.pyqtSignal()
    
    def __init__(self, counter_functionality = None, name = None, start_timeout = 0.0, **kwds):
        super().__init__(**kwds)

        self.counter_fn = counter_functionality
        self.exposure_time = None
        self.film_length = None
        self.fps = None
        self.name = name
        self.n_pulses = 0
        self.running = False

        self.counter_fn.setDoneFn(self.handleStopped)
        self.counter_fn.setSignalFn(self.handleNewFrame)

        #
        # If the counter waits for an external start trigger (i.e. all the
        # cameras reporting that they are ready) this timer catches the case
        # where the trigger never arrives, for example because a camera did
        # not start, so that HAL does not wait forever.
        #
        self.start_timer = QtCore.QTimer(self)
        self.start_timer.setSingleShot(True)
        self.start_timer.timeout.connect(self.handleStartTimeout)
        if self.counter_fn.hasTrigger() and (start_timeout > 0.0):
            self.start_timer.setInterval(int(1000.0 * start_timeout))
        else:
            self.start_timer = None

    def getCameraName(self):
        return self.name
    
    def getParameter(self, p_name):
        assert (p_name == "fps")
        return self.fps

    def handleNewFrame(self):
        #
        # The counter outputs two pulses per cycle, so only a
        # emit a newFrame signal every other cycle.
        #
        if ((self.n_pulses%2) == 0):
            frame = HardwareTimingFrame(int(self.n_pulses/2))
            self.newFrame.emit(frame)
        self.n_pulses += 1

    def handleStartTimeout(self):
        #
        # Note that handleNewFrame() is called from a DAQmx thread, so we
        # check the pulse count here rather than stopping the timer there.
        #
        if (self.n_pulses > 0):
            return
        self.counter_fn.stopOutput()
        msg = "Hardware timing start trigger not received after "
        msg += "{0:.1f} seconds. Check that all the cameras are ready.".format(0.001 * self.start_timer.interval())
        print(">> Warning", msg)
        self.stopped.emit()
        self.startTimedOut.emit(msg)

    def handleStopped(self):
        self.stopped.emit()

    def restartCounter(self):
        """
        Restart the counter so that new fps / exposure time settings take
        effect, if it is running (i.e. live mode).
        """
        if self.running:
            self.stopCounter()
            self.startCounter()

    def setExposureTime(self, exposure_time):
        """
        If this is not None the counter high time is set to the exposure
        time, otherwise the counter has a 50% duty cycle.
        """
        self.exposure_time = exposure_time

    def setFilmLength(self, film_length):
        self.film_length = film_length
        
    def setFPS(self, fps):
        self.fps = float(fps)
        
    def startCounter(self):
        self.n_pulses = 0
        self.counter_fn.setFrequency(self.fps)

        cycles = 0
        if self.film_length is not None:
            cycles = self.film_length

        if self.exposure_time is not None:
            self.counter_fn.pulseOutput(high_time = self.exposure_time,
                                        low_time = 1.0/self.fps - self.exposure_time,
                                        cycles = cycles)
        else:
            self.counter_fn.pwmOutput(duty_cycle = 0.5, cycles = cycles)

        if self.start_timer is not None:
            self.start_timer.start()
        self.running = True

    def stopCounter(self):
        if self.start_timer is not None:
            self.start_timer.stop()
        self.counter_fn.stopOutput()
        self.film_length = None
        self.running = False
    

class HardwareTiming(halModule.HalModule):
    """
    Hardware timing for a film.

    The actual timing is provided by a functionality that behaves like
    a nidaqModule.CTTaskFunctionality().
    """
    def __init__(self, module_params = None, qt_settings = None, **kwds):
        super().__init__(**kwds)
        self.film_settings = None
        self.hardware_timing_functionality = None

        self.configuration = module_params.get("configuration")
        self.allow_master = self.configuration.get("allow_master", False)

        # The minimum time (in seconds) that the counter output must be low
        # between pulses, for example so that the cameras can re-arm.
        self.min_low_time = self.configuration.get("min_low_time", 0.0)

        # The time (in seconds) to wait for an external start trigger before
        # giving up, zero means wait forever. Only used if the counter has
        # a start trigger.
        self.start_timeout = self.configuration.get("start_timeout", 10.0)

        # If 'exposure_time' is specified then the counter high time is the
        # exposure time, otherwise the counter has a 50% duty cycle.
        self.use_exposure_time = self.configuration.has("exposure_time")

        self.parameters = params.StormXMLObject()

        #
        # FIXME: The range would be better set by what the cameras allow
        #        based on their current configuration.
        #
        self.parameters.add(params.ParameterRangeFloat(description = "Frames per second",
                                                       name = "fps",
                                                       value = self.configuration.get("fps", 0.1),
                                                       min_value = self.configuration.get("fps_min", 0.001),
                                                       max_value = self.configuration.get("fps_max", 10000.0)))

        if self.use_exposure_time:
            self.exposure_time_max = self.configuration.get("exposure_time_max", 10.0)
            self.exposure_time_min = self.configuration.get("exposure_time_min", 1.0e-5)
            self.parameters.add(params.ParameterRangeFloat(description = "Exposure time (seconds)",
                                                           name = "exposure_time",
                                                           value = self.configuration.get("exposure_time"),
                                                           min_value = self.exposure_time_min,
                                                           max_value = self.exposure_time_max,
                                                           decimals = 5,
                                                           step = 0.001))
        self.setTiming(self.parameters.get("fps"),
                       self.parameters.get("exposure_time") if self.use_exposure_time else None)

    def maxExposureTime(self, fps):
        """
        The longest exposure time that leaves the counter low for at least
        min_low_time each frame at this frame rate.
        """
        max_exposure = min(1.0/fps - self.min_low_time, self.exposure_time_max)
        return max(max_exposure, self.exposure_time_min)

    def setTiming(self, fps, exposure_time):
        """
        Set the frame rate and exposure time. The frame rate takes priority,
        the exposure time is clipped so that it fits in a frame. The exposure
        time's maximum is also set to this limit so that the parameters editor
        won't accept a longer one.
        """
        self.parameters.setv("fps", fps)
        if self.use_exposure_time:
            max_exposure = self.maxExposureTime(self.parameters.get("fps"))
            if (exposure_time > max_exposure):
                print(">> Warning exposure time {0:.5f}s clipped to {1:.5f}s for {2:.3f} FPS.".format(exposure_time,
                                                                                                        max_exposure,
                                                                                                        self.parameters.get("fps")))
            p = self.parameters.getp("exposure_time")
            p.setMaximum(max_exposure)
            p.setv(exposure_time)

    def handleResponse(self, message, response):
        if message.isType("get functionality"):
            
            if (message.getData()["extra data"] == "counter"):
                htf = HardwareTimingFunctionality(counter_functionality = response.getData()["functionality"],
                                                  name = self.module_name,
                                                  start_timeout = self.start_timeout)
                htf.startTimedOut.connect(self.handleStartTimedOut)
                self.hardware_timing_functionality = htf
                self.hardware_timing_functionality.setFPS(self.parameters.get("fps"))
                if self.use_exposure_time:
                    self.hardware_timing_functionality.setExposureTime(self.parameters.get("exposure_time"))

                self.sendTimingConfiguration()

    def handleStartTimedOut(self, msg):
        halMessageBox.halMessageBoxInfo(msg, is_error = True)

    def sendTimingConfiguration(self):
        """
        Tell other modules, such as the camera parameters viewers, the
        current frame rate and exposure time. The exposure time is None
        if the counter has a 50% duty cycle.
        """
        exposure_time = None
        if self.use_exposure_time:
            exposure_time = self.parameters.get("exposure_time")
        timing = {"fps" : self.parameters.get("fps"),
                  "exposure_time" : exposure_time}
        self.sendMessage(halMessage.HalMessage(m_type = "configuration",
                                               data = {"properties" : {"hardware timing" : timing}}))

    def processMessage(self, message):

        if message.isType("configuration"):

            # Check for master cameras. If they exist this is an error in the setup
            # configuration.
            if ("is camera" in message.getData()["properties"]):
                if not self.allow_master:
                    m_data = message.getData()["properties"]
                    if m_data["is camera"] and m_data["is master"]:
                        raise halExceptions.HalException("Master camera detected in hardware timed setup!")

            # Check if we are the time base for the film.
            #
            # If we are and this is a fixed length film then
            # set the hardware counter appropriately.
            #
            elif message.sourceIs("timing"):
                timing_fn = message.getData()["properties"]["functionality"]
                if (timing_fn.getTimeBase() == self.module_name) and self.film_settings.isFixedLength():
                    self.hardware_timing_functionality.setFilmLength(self.film_settings.getFilmLength())

        elif message.isType("configure1"):

            # Broadcast initial parameters. These become the defaults that
            # parameters files are loaded on top of, so they keep the full
            # exposure time range rather than the limit for the current fps.
            initial = self.parameters.copy()
            if self.use_exposure_time:
                initial.getp("exposure_time").setMaximum(self.exposure_time_max)
            self.sendMessage(halMessage.HalMessage(m_type = "initial parameters",
                                                   data = {"parameters" : initial}))

            # Send 'configuration' message with information about this hardware timing
            # module. This module is always a master, but is not a camera.
            p_dict = {"module name" : self.module_name,
                      "is camera" : False,
                      "is master" : True}
            self.sendMessage(halMessage.HalMessage(m_type = "configuration",
                                                   data = {"properties" : p_dict}))
            
            # Get DAQ counter like functionality.
            self.sendMessage(halMessage.HalMessage(m_type = "get functionality",
                                                   data = {"name" : self.configuration.get("counter_fn_name"),
                                                           "extra data" : "counter"}))

        elif message.isType("current parameters"):
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"parameters" : self.parameters.copy()}))
            
        elif message.isType("get functionality"):
            if (message.getData()["name"] == self.module_name):
                message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                                  data = {"functionality" : self.hardware_timing_functionality}))

        elif message.isType("new parameters"):
            #
            # FIXME: We have a similar problem here as with timing.timing. We don't know
            #        the allowed FPS range for the cameras based on their new parameters
            #        at this point. By the time we do know at 'updated parameters' it is
            #        to late to change the allowed range that settings.settings will show
            #        in the parameter editor GUI.
            #
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"old parameters" : self.parameters.copy()}))
            p = message.getData()["parameters"].get(self.module_name)
            exposure_time = None
            if self.use_exposure_time:
                # Older parameters files won't have an exposure time.
                exposure_time = p.get("exposure_time", self.parameters.get("exposure_time"))
            self.setTiming(p.get("fps"), exposure_time)

            self.hardware_timing_functionality.setFPS(self.parameters.get("fps"))
            if self.use_exposure_time:
                self.hardware_timing_functionality.setExposureTime(self.parameters.get("exposure_time"))
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"new parameters" : self.parameters}))

        elif message.isType("start"):
            if self.hardware_timing_functionality is None:
                raise halExceptions.HalException("no counter functionality available for hardware timing.")

        elif message.isType("start camera"):
            # This message comes from film.film. This module behaves
            # like a master camera.
            if message.getData()["master"]:
                self.hardware_timing_functionality.startCounter()
                
        elif message.isType("start film"):
            # This message comes from film.film, we save the film settings
            # but don't actually do anything until we get a 'configuration'
            # message from timing.timing.
            self.film_settings = message.getData()["film settings"]

        elif message.isType("stop camera"):
            # This message comes from film.film. This module behaves
            # like a master camera.
            if message.getData()["master"]:
                self.hardware_timing_functionality.stopCounter()
                
        elif message.isType("stop film"):
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name, 
                                                              data = {"parameters" : self.parameters.copy()}))

        elif message.isType("updated parameters"):
            # The counter only reads fps / exposure time when it starts. Films
            # always start it, but in live mode it is already running, so
            # restart it to apply the new settings. Parameters can't change
            # during a film.
            if self.hardware_timing_functionality is not None:
                self.hardware_timing_functionality.restartCounter()
            self.sendTimingConfiguration()
                
                
                
