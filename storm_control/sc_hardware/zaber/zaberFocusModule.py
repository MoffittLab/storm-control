#!/usr/bin/env python
"""
HAL module for controlling a zaber z focus leveraging both coarse and fine focusing.

Jeff 09/21
Hazen 05/18
"""
import math
from PyQt5 import QtCore

import storm_control.sc_library.halExceptions as halExceptions

import storm_control.hal4000.halLib.halMessage as halMessage

import storm_control.sc_hardware.baseClasses.hardwareModule as hardwareModule
import storm_control.sc_hardware.baseClasses.stageZModule as stageZModule
import storm_control.sc_hardware.baseClasses.lockModule as lockModule

import storm_control.sc_hardware.zaber.zaberZ as zaber


class ZaberCoarseFocusBufferedFunctionality(stageZModule.ZStageFunctionalityBuffered):
    """
    This functionality interfaces with the coarse focusing module, i.e. the focus lock. As a buffered functionality it contains a device mutex
    """
    def __init__(self, **kwds):
        super().__init__(**kwds)
        self.minimum = self.getMinimum()
        self.maximum = self.getMaximum()

    def zMoveTo(self, z_pos):
        self.z_stage.zMoveCoarse(z_pos)
        self.z_position = z_pos
        return z_pos


class ZaberFineFocusBufferedFunctionality(stageZModule.ZStageFunctionalityBuffered):
    """
    This functionality interfaces with the fine focusing module, i.e. the focus lock. As a buffered functionality it contains a device mutex
    """
    zStagePosition = QtCore.pyqtSignal(float)

    def __init__(self, stage = None, parameters = None, **kwds):
        super().__init__(**kwds)
        self.stage = stage

    def zMoveTo(self, z_pos):
        self.z_stage.zMoveFine(z_pos)
        self.z_position = z_pos
        return z_pos

    def goRelative(self, z_delta):
        z_pos = self.z_position + z_delta
        self.goAbsolute(z_pos)

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
        
		# Create the coarse movement functionality
        settings = configuration.get("coarse_focus")
        print(settings)
        self.coarse_functionality = ZaberCoarseFocusBufferedFunctionality(device_mutex = self.controller_mutex, 
																		  z_stage = self.stage,
                                                                          parameters=settings)
        
        print(self.coarse_functionality)
        print(self.coarse_functionality.__dict__)

		# Create the fine movement functionality
        settings = configuration.get("coarse_focus")
        self.fine_functionality = ZaberFineFocusBufferedFunctionality(device_mutex = self.controller_mutex, 
																	  stage = self.stage,
                                                                      parameters=settings)
		
		# Create a list of the functionalities for ease of indexing 
        self.functionalities[self.module_name + ".coarse_focus"] = self.coarse_functionality
        self.functionalities[self.module_name + ".fine_focus"] = self.fine_functionality

        print("------------------------------------------------------------------------------------------------")
        print(self.functionalities)

    def getFunctionality(self, message):
        print("------------------------------------------------------------------------------------------------")
        print(message)
        
        if message.getData()["name"] in self.functionalities:
            print("Found functionality")
            fn = self.functionalities[message.getData()["name"]]
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"functionality" : fn}))
                    
    def processMessage(self, message):
        if message.isType("get functionality"):
            self.getFunctionality(message)
        if message.isType("stop film"):  # Add the current z_coarse position to the parameters that are written
            message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                              data = {"parameters" : self.view.getParameters()}))
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
