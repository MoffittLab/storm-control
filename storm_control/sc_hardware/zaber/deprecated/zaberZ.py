#!/usr/bin/env python
"""
RS232 interface to a Zaber Z stage.

Hazen 04/17
Jeff 09/21
"""
import traceback

import storm_control.sc_hardware.serial.RS232 as RS232
import storm_control.sc_library.hdebug as hdebug

class ZaberZRS232(RS232.RS232):
    """
    ZaberZ stage RS232 interface class.
    """
    def __init__(self, **kwds):
        """
        Connect to the Zaber stage at the specified port.
        """
        self.live = True
        self.unit_to_um = kwds["unit_to_um"]
        self.um_to_unit = 1.0/self.unit_to_um
        self.x = 0.0
        self.y = 0.0
        self.stage_id = kwds["stage_id"]
        self.limits = kwds["limits_dict"]

        # We need to remove the keywords not needed for the RS232 super class initialization
        del kwds["stage_id"]
        del kwds["unit_to_um"]
        del kwds["limits_dict"]

        # RS232 stuff
        try:
            super().__init__(**kwds)
            test = self.commWithResp("/")
            if not test:
                self.live = False

        except (AttributeError, AssertionError):
            print(traceback.format_exc())
            self.live = False
            print("Zaber Z Stage is not connected? Stage is not on?")
            print("Failed to connect to the Zaber Z stage at ", kwds["port"])

    def goAbsolute(self, z):
        # Coerce values to stage limits
        coerced_value = False
        if z<self.limits["z_min"]:
            z=self.limits["z_min"]
            coerced_value = True
        if z>self.limits["z_max"]:
            z=self.limits["z_max"]
            coerced_value = True
        if coerced_value:
            print("Stage warning: Requested a move outside of programmed limits")
    
        # Convert um units to the stage step units and round to an integer
        z = int(round(z * self.um_to_unit))       
        
        # Send a command to move the z to the absolute position
        reponse = self.commWithResp("/" + str(self.stage_id) + " move abs " + str(z))
        
    def goRelative(self, z):
        # Convert um units to the stage step units and round to an integer
        z = int(round(z * self.um_to_unit))
        
        # Send a command to move in z a relative position
        self.writeline("/" + str(self.stage_id) + " move rel " + str(z))

    def getPosition(self):
        response = self.commWithResp("/" + str(self.stage_id) + " get pos")
        
        response = response.strip()
        response_parts = response.split(" ")
        try:
            sz = map(float, response_parts[5])
        except ValueError:
            return [None]
        return sz*self.unit_to_um

    def isStageMoving(self):
        response = self.commWithResp("/" + str(self.stage_id))
        
        # Parse the response
        response_parts = response.split(" ")

        # Handle an error response, or an empty response
        if not (response_parts[2] == "OK") or len(response_parts) < 2:
            print("STAGE ERROR: " + response)
            return "ERROR"        
        # Parse IDLE/BUSY
        if response_parts[3] == "IDLE":
            return "IDLE"
        else: # BUSY Case
            return "MOVING"

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
