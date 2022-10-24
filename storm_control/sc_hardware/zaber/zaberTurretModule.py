#!/usr/bin/env python
"""
HAL module to interface with the Zaber Dichroic Cube Turret (X-FCR).

Jeffrey Moffitt 9/21
"""

import storm_control.hal4000.halLib.halMessage as halMessage

import storm_control.sc_hardware.baseClasses.hardwareModule as hardwareModule
import storm_control.sc_hardware.zaber.zaberTurret as zaberTurret

import storm_control.sc_library.halExceptions as halExceptions
import storm_control.sc_library.parameters as params


class ZaberTurretControl(object):
    """
    Control of the Zaber Dichroic Cube Turret. 
    """
    def __init__(self, turret = None, configuration = None, **kwds):
        super().__init__(**kwds)
        self.turret = turret

        # Confirm that the turret is active
        self.turret.checkIsDeviceOn()
        
        # Create a dictionary based on the configuration file
        #   This will define the names for each dichroic cube, and we will index them via these names
        self.turret_config = {}
        values = configuration.get("cube_names", None)
        
        # Confirm this required configuration was provided
        assert values is not None
        
        # Parse the configuration
        cube_names = values.split(",")
        for pos, cube_name in enumerate(cube_names):
            self.turret_config[cube_name] = pos + 1

        # This dichroic cube can hold only 6 entries
        assert len(cube_names) <= self.turret.max_num_positions

        # Create parameters
        self.parameters = params.StormXMLObject()

        # Create a Hal parameter that can be modified in the parameters editor to select cube
        values = sorted(self.turret_config.keys())
        self.parameters.add(params.ParameterSetString(description = "Turret positions",
                                                      name = "Dichroic_cube",
                                                      value = values[0],  # Start in the first position
                                                      allowed = values))

        self.newParameters(self.parameters, initialization = True)

    def getParameters(self):
        return self.parameters
    
    def newParameters(self, parameters, initialization = False):

        # Find the parameters that have changed (if not initializing the class)
        if initialization:
            changed_p_names = parameters.getAttrs()
        else:
            changed_p_names = params.difference(parameters, self.parameters)

        p = parameters
        for pname in changed_p_names:

            # Update our current parameters.
            self.parameters.setv(pname, p.get(pname))

            # Position the turret
            if (pname == "Dichroic_cube"):
                requested_position = self.turret_config[p.get("Dichroic_cube")]
                self.turret.changePosition(requested_position)
            else:
                print(">> Warning", str(pname), " is not a valid parameter for the Zaber dichroic cube turret")


class ZaberXFCR06CModule(hardwareModule.HardwareModule):

    def __init__(self, module_params = None, qt_settings = None, **kwds):
        super().__init__(**kwds)
        self.control = None
        self.turret = None

        configuration = module_params.get("configuration")
        self.turret = zaberTurret.ZaberXFCR06C(baudrate = configuration.get("baudrate"),
                                               port = configuration.get("port"))
        if self.turret.getStatus():
            self.control = ZaberTurretControl(turret = self.turret,
                                              configuration = configuration)

    def cleanUp(self, qt_settings):
        if self.control is not None:
            self.turret.shutDown()

    def processMessage(self, message):

        if self.control is None:
            return

        if message.isType("configure1"):
            self.sendMessage(halMessage.HalMessage(m_type = "initial parameters",
                                                   data = {"parameters" : self.control.getParameters()}))

        #
        # FIXME? Maybe we want do this at 'update parameters' as we don't
        #        do any error checking.
        #
        elif message.isType("new parameters"):
            hardwareModule.runHardwareTask(self,
                                           message,
                                           lambda : self.updateParameters(message))

    def updateParameters(self, message):
        message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                          data = {"old parameters" : self.control.getParameters().copy()}))
        p = message.getData()["parameters"].get(self.module_name)
        self.control.newParameters(p)
        message.addResponse(halMessage.HalMessageResponse(source = self.module_name,
                                                          data = {"new parameters" : self.control.getParameters()}))

#
# The MIT License
#
# Copyright (c) 2021 Moffitt Laboratory, Boston Children's Hospital, Harvard Medical School
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
