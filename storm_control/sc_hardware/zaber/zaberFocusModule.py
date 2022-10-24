#!/usr/bin/env python
"""
HAL module for controlling a zaber z focus leveraging both coarse and fine focusing.

Jeff 09/21
Hazen 05/18
"""
from PyQt5 import QtCore

import storm_control.sc_library.halExceptions as halExceptions

import storm_control.hal4000.halLib.halMessage as halMessage
import storm_control.sc_library.parameters as params

import storm_control.sc_hardware.baseClasses.hardwareModule as hardwareModule
import storm_control.sc_hardware.baseClasses.stageZModule as stageZModule
import storm_control.sc_hardware.baseClasses.lockModule as lockModule

import storm_control.sc_hardware.zaber.zaberZ as zaber
import numpy

class ZaberCoarseFocusBufferedFunctionality(stageZModule.ZStageFunctionalityBuffered):
    """
    This functionality interfaces with the coarse focusing module, i.e. the focus lock. As a buffered functionality it contains a device mutex
    """
    def __init__(self, **kwds):
        super().__init__(**kwds)
        self.minimum = self.getMinimum()
        self.maximum = self.getMaximum()
        
        # Start the class with the current hardware position of the stage (not zero)
        self.z_position = self.z_stage.zPositionCoarse()

    def zMoveTo(self, z_pos):
        self.z_stage.zMoveCoarse(z_pos)
        self.z_position = z_pos
        return z_pos
    
    def getPosition(self):
        return self.z_stage.zPositionCoarse()
    
class ZaberFineFocusBufferedFunctionality(hardwareModule.BufferedFunctionality, lockModule.ZStageFunctionalityMixin):
    """
    This functionality interfaces with the fine focusing module, i.e. the focus lock. As a buffered functionality it contains a device mutex
    """
    zStagePosition = QtCore.pyqtSignal(float)
    zScanConfigComplete = QtCore.pyqtSignal(object)
    def __init__(self, z_stage = None, **kwds):
        super().__init__(**kwds)
        self.minimum = self.getMinimum()
        self.maximum = self.getMaximum()
        self.z_stage = z_stage
        self.z_scan_mode = False
        self.z_pos_prior_to_scan = None
        self.module_name = "ZaberFineFocusBufferedFunctionality"
        self.recenter()
        
    def zMoveTo(self, z_pos):
        self.z_stage.zMoveFine(z_pos)
        self.z_position = z_pos
        return z_pos
    
    def restrictZPos(self,z_pos):
        #Ensure that all requested z positions are within the maximum and minimum range, working in units of microns
        if (z_pos < self.minimum):
            z_pos = self.minimum
        if (z_pos > self.maximum):
            z_pos = self.maximum
        return z_pos

    def goRelative(self, z_delta):
        self.z_position = self.z_position + z_delta
        self.goAbsolute(self.z_position)
        
    def goAbsolute(self, z_pos):
        z_pos = self.restrictZPos(z_pos)
        self.maybeRun(task = self.zMoveTo,
              args = [z_pos],
              ret_signal = self.zStagePosition,
              run_next = False)
        
    def getCurrentPosition(self):
        return self.z_stage.fine_position
    
    def haveHardwareTiming(self):
        return True
            
    def isInZScanMode(self):
        return self.z_stage.is_zscan
    
    def startZScan(self):
        #self.z_stage.startZScan()
        print("In startZScan")
        self.z_pos_prior_to_scan = self.getCurrentPosition()
        self.mustRun(task = self.z_stage.startZScan, 
                     ret_signal = self.zScanConfigComplete)
        print("Exciting startZScan")
    
    def configureZScan(self, z_pos):
        self.mustRun(task = self.z_stage.configureZScan,
                     args = [z_pos])
        #self.z_stage.configureZScan(z_pos)
        
    def completeZScan(self):
        print("Starting complete ZScan")
        # Add the complete Z scan to the must run queue
        self.mustRun(task = self.z_stage.completeZScan)
        # Add a move to the original location to the must run queue
        self.mustRun(task = self.zMoveTo,
              args = [self.z_pos_prior_to_scan],
              ret_signal = self.zStagePosition)
        
class ZaberZController(hardwareModule.HardwareModule):

    def __init__(self, module_params = None, qt_settings = None, **kwds):
        super().__init__(**kwds)
        self.controller_mutex = QtCore.QMutex()
        self.functionalities = {}

        configuration = module_params.get("configuration")
        self.stage = zaber.ZaberZRS232(baudrate = configuration.get("baudrate"),
									   port = configuration.get("port"), 
									   stage_id = configuration.get("stage_id", 1), 
									   unit_to_um = configuration.get("unit_to_um", 1000), 
									   limits_dict = {"z_min": configuration.get("z_min", 0), 
													  "z_max": configuration.get("z_maz", 100000)},
                                       debug = configuration.get("debug", False))
        
        # Create parameters
        self.parameters = params.StormXMLObject()
        self.parameters.add(params.ParameterString(description = "Relative z positions (um)",
                                                   name = "z_offsets",
                                                   value = ""))
        self.rel_z_values = None
        self.in_z_scan_mode = False
        
		# Create the coarse movement functionality
        settings = configuration.get("coarse_focus")
        self.coarse_functionality = ZaberCoarseFocusBufferedFunctionality(device_mutex = self.controller_mutex, 
																		  z_stage = self.stage,
                                                                          parameters=settings)
        
		# Create the fine movement functionality
        settings = configuration.get("fine_focus")
        self.fine_functionality = ZaberFineFocusBufferedFunctionality(device_mutex = self.controller_mutex, 
																	  z_stage = self.stage,
                                                                      parameters=settings)
        
        # Connect the configuration complete signal
        self.fine_functionality.zScanConfigComplete.connect(self.handleZScanConfigComplete)
        

		# Create a list of the functionalities for ease of indexing 
        self.functionalities[self.module_name + ".coarse_focus"] = self.coarse_functionality
        self.functionalities[self.module_name + ".fine_focus"] = self.fine_functionality

        # This message is sent by lockModes.lockMode to indicate that the stage should be placed in z scan mode 
        halMessage.addMessage("software config z scan",
                      validator = {"data" : {"is_locked" : [True, bool]},
                                   "resp" : None})
        
        
    def getFunctionality(self, message):
        if message.getData()["name"] in self.functionalities:
            fn = self.functionalities[message.getData()["name"]]
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"functionality" : fn}))
                    
    def newParameters(self, message):
        
        # Return the old parameters
        message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                          data = {"old parameters" : self.getParameters().copy()}))

        
        
        # Extract module specific parameters
        p = message.getData()["parameters"].get(self.module_name)
        self.parameters = p
        self.rel_z_values = numpy.array([])
        if (len(p.get("z_offsets")) > 0):
            self.rel_z_values = numpy.array(list(map(float, p.get("z_offsets").split(","))))
        
        self.fine_functionality.configureZScan(self.rel_z_values)
        
        # Respond with the new parameters
        message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                          data = {"new parameters" : self.getParameters()}))
        
    def getParameters(self):
        return self.parameters
    
    def handleResponses(self, message):
        # Handle the response from the focus lock (called with the 'start film' message)
        print("received a response")
        if message.isType("focus lock status"):
            print("Handling response from focus lock status")
            # Confirm just one response
            assert (len(message.getResponses()) == 1)
            
            # Loop over the one response and gather the name of the mode and it status
            for response in message.getResponses():
                lock_mode_name = response.getData()["mode_name"]
                is_locked = response.getData()["is_locked"]
                
            # If the mode is the z-scan mode appropriate for this module, and it is locked, configure z scane
            if (lock_mode_name == "Triggered Z Scan") and is_locked:
                self.fine_functionality.startZScan()  # NOTE: This will complete the loop by calling handleZScanConfigComplete
                print("I have successful configured the z scan")
                self.in_z_scan_mode = True
            else: # Tell film.Film that it can go
                print("Focus lock is not in a z-scan mode")
                self.sendMessage(halMessage.HalMessage(m_type = "ready to film"))
    
    def processMessage(self, message):
        
        if message.isType("configure1"):
            # Let film.film know that it needs to wait for us
            # to get ready before starting the cameras.
            self.sendMessage(halMessage.HalMessage(m_type = "wait for",
                                                   data = {"module names" : ["film"]}))
        elif message.isType("get functionality"):
            self.getFunctionality(message)
            
        elif message.isType("start film"):
            # Handle the case that there is no z_scan requested
            if self.rel_z_values is None:
                print("Bypass z-scan and just run")
                # Tell film.Film that this module is ready for filing to start
                self.sendMessage(halMessage.HalMessage(m_type = "ready to film"))
            else: 
                print("Sending request for focus lock status")
                # Check with the focus lock to get it status
                self.sendMessage(halMessage.HalMessage(m_type = "focus lock status"))
                        
        elif message.isType("stop film"):  
            # Add the current z_coarse position to the parameters that are written
            coarse_z_position = params.ParameterFloat(name = "coarse_z_position",
                                                      value = self.stage.coarse_position)
            in_z_scan_mode = params.ParameterSetBoolean(name = "z_scan_mode",
                                                        value = self.in_z_scan_mode)
            rel_pos = params.ParameterString(name = "relative_z_offsets", 
                                             value = self.parameters.get("z_offsets"))
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"acquisition" : [coarse_z_position,
                                                                                       in_z_scan_mode,
                                                                                       rel_pos]}))
            
            # Inform the fine functionality that it is done filming
            if self.fine_functionality.isInZScanMode():
                print("I am now going to clean up the zscan")
                self.fine_functionality.completeZScan()
            self.in_z_scan_mode = False
        
        elif message.isType("current parameters"):
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"parameters" : self.getParameters().copy()}))

        elif message.isType("new parameters"): # Handle the new parameters
            self.newParameters(message)
                        
    def handleZScanConfigComplete(self):
        # Handle the completion of a ZScanConfigurationComplete signal by telling film.Film that the module is ready
        self.sendMessage(halMessage.HalMessage(m_type = "ready to film"))

    def cleanUp(self, qt_settings):
        self.stage.shutDown()
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
