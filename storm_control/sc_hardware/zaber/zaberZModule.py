#!/usr/bin/env python
"""
HAL module for controlling a Zaber Z stage.  

Jeff 09/21
Hazen 04/17
"""

from PyQt5 import QtCore

import storm_control.hal4000.halLib.halMessage as halMessage

import storm_control.sc_hardware.baseClasses.stageModule as stageModule
import storm_control.sc_hardware.zaber.zaberZ as zaberZ


class ZaberXYStageFunctionality(stageModule.StageFunctionality):
    """
    These stages are nice because they respond quickly to commands
    and they also provide feedback about whether or not they are
    moving.
    """
    def __init__(self, update_interval = None, **kwds):
        super().__init__(**kwds)
        self.querying = False

        # Each time this timer fires we'll 'query' the stage for it's
        # current position.
        self.updateTimer = QtCore.QTimer()
        self.updateTimer.setInterval(update_interval)
        self.updateTimer.timeout.connect(self.handleUpdateTimer)
        self.updateTimer.start()

        # Connect to our own stagePosition signal in order to store
        # the current position.
        self.stagePosition.connect(self.handleStagePosition)
        
        # This thread will poll the serial port for responses from
        # the stage to the commands we're sending.
        self.polling_thread = ZaberPollingThread(device_mutex = self.device_mutex,
                                                      is_moving_signal = self.isMoving,
                                                      sleep_time = 100,
                                                      stage = self.stage,
                                                      stage_position_signal = self.stagePosition)
        self.polling_thread.startPolling()

    def canZero(self):
        return False # The zaber stages cannot be zeroed
       
    def canHome(self):
        return False # The zaber stages should not be homed.... objective damage

    def handleStagePosition(self, pos_dict):
        self.pos_dict = pos_dict
        self.querying = False

    def handleUpdateTimer(self):
        """
        Query the stage for its current position.
        """
        #
        # The purpose of the self.querying flag is to prevent build up of
        # position update requests. If there is already one in process there
        # is no point in starting another one.
        #
        if not self.querying:
            self.querying = True
            self.mustRun(task = self.stage.position)

    def wait(self):
        self.updateTimer.stop()
        self.polling_thread.stopPolling()
        super().wait()
        
        


class ZaberPollingThread(QtCore.QThread):
    """
    Handles polling the Zaber stage for responses to serial commands.
    """
    def __init__(self,
                 device_mutex = None,
                 is_moving_signal = None,
                 sleep_time = None,
                 stage = None,
                 stage_position_signal = None,
                 **kwds):
        super().__init__(**kwds)
        self.device_mutex = device_mutex
        self.is_moving_signal = is_moving_signal
        self.sleep_time = sleep_time         
        self.stage = stage
        self.stage_position_signal = stage_position_signal

    def run(self):
        self.running = True
        while(self.running):
            ### First poll the status: moving, not moving, or error
        
            # Lock the stage mutex
            self.device_mutex.lock()
            
            # Request the current status
            response = self.stage.isStageMoving()
            
            # Unlock the stage mutex
            self.device_mutex.unlock()
            
            if response == "MOVING":
                self.is_moving_signal.emit(True)
                
            elif response == "IDLE":
                self.is_moving_signal.emit(False)
            else:
                print("STAGE ERROR!!")

            ### Next poll the position
            # Lock the stage mutex
            self.device_mutex.lock()
            
            # Request the current status
            [sx,sy] = self.stage.getPosition()
            
            # Unlock the stage mutex
            self.device_mutex.unlock()

            if sx is not None:
                self.stage_position_signal.emit({"x" : sx, "y" : sy})

            # Sleep for ~ x milliseconds.
            self.msleep(self.sleep_time)

    def startPolling(self):
        self.start(QtCore.QThread.NormalPriority)

    def stopPolling(self):
        self.running = False
        self.wait()
        

class ZaberZStage(stageModule.StageModule):

    def __init__(self, module_params = None, qt_settings = None, **kwds):
        super().__init__(**kwds)

        # Extract configuration
        configuration = module_params.get("configuration")
        
        # Build the limits dictionary: These are hard coded limits for go_absolute commands
        limits_dict = {"z_min": configuration.get("x_min",0), 
                        "z_max": configuration.get("x_max", 120000)}
                        
        # Create the stage
        self.stage = zaber.ZaberZRS232(baudrate = configuration.get("baudrate"),
                                        port = configuration.get("port"), 
                                        unit_to_um = configuration.get("unit_to_um", 0.001),
                                        stage_id = configuration.get("stage_id", 1), 
                                        limits_dict = limits_dict)
        if self.stage.getStatus():            
            
            # Set (maximum) stage velocity.
            velocity = configuration.get("velocity", None)
            if not velocity is None:
                self.stage.setVelocity(velocity, velocity)
            
            # Create the stage functionality
            self.stage_functionality = ZaberStageFunctionality(device_mutex = QtCore.QMutex(),
                                                                    stage = self.stage,
                                                                    update_interval = 500)

        else:
            self.stage = None



#
# The MIT License
#
# Copyright (c) 2021 Moffitt Lab, Boston Children's Hospital, Harvard Medical School
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
