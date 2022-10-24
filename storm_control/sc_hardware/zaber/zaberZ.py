#!/usr/bin/env python
"""
RS232 interface to a Zaber Z stage.

Hazen 04/17
Jeff 09/21
"""
import traceback
import time

import storm_control.sc_hardware.serial.RS232 as RS232
import storm_control.sc_library.hdebug as hdebug

from timeit import default_timer as timer

class ZaberZRS232(RS232.RS232):
    """
    ZaberZ stage RS232 interface class.  This class allows for a coarse and fine z position, with the fine z position relative to the coarse position.
	This approach allows the stage to be used for coarse focusing and for the fine focusing of the autofocus system.
    """
    def __init__(self, **kwds):
        """
        Connect to the Zaber Z stage at the specified port.
        """
        self.live = True
        self.unit_to_um = kwds["unit_to_um"]
        self.um_to_unit = 1.0/self.unit_to_um
        self.stage_id = kwds["stage_id"]
        self.limits = kwds["limits_dict"]
        self.coarse_position = 0.0
        self.fine_position = 0.0
        self.is_zscan = False

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

		# Get the current coarse position
        self.coarse_position = self.getPosition()
        print("  Zaber z stage is starting at " + str(self.coarse_position))

	# Coerce the requested position
    def coerceToLimits(self, z):
		# Coerce values to stage limits
        coerced_value = False
        if z<self.limits["z_min"]:
            z=self.limits["z_min"]
            coerced_value = True
        if z>self.limits["z_max"]:
            z=self.limits["z_max"]
            coerced_value = True
        if coerced_value:
            print("Zaber Z Stage Warning: Requested a move outside of programmed limits")
        return z
    
	# Command a coarse position change AND update the coarse position
    def zMoveCoarse(self, z_in_um):
        if self.is_zscan:
            print("Ignoring move requests while in z scan mode")
            return
        
		# Coerce to limits
        z_in_um = self.coerceToLimits(z_in_um + self.fine_position)
		        
		# Convert z to units
        z_in_units = int(round(z_in_um * self.um_to_unit))       
		
		# Send a command to move the z to the absolute position
        response = self.commWithResp("/" + str(self.stage_id) + " move abs " + str(z_in_units))
        response_parts = response.split(" ")
		
        # Check to see if successful, and if so, store the requested coarse_position
        if response_parts[2] == "OK":
            self.coarse_position = z_in_um - self.fine_position
        else:
            print("Zaber Z Stage Warning: Coarse movement request not successful")
    
	# Command a fine position change
    def zMoveFine(self, z_in_um):

        if self.is_zscan:
            print("Ignoring move requests while in z scan mode")
            return

		# Coerce to limits
        z_in_um = self.coerceToLimits(z_in_um + self.coarse_position)
	
        # Convert z to units
        z_in_units = int(round(z_in_um * self.um_to_unit))       
        
		# Send a command to move the z to the absolute position
        response = self.commWithResp("/" + str(self.stage_id) + " move abs " + str(z_in_units))
        response_parts = response.split(" ")

        # Check to see if successful, and if so, store the requested fine_position
        if response_parts[2] == "OK":
            self.fine_position = z_in_um - self.coarse_position
        else:
            print("Zaber Z Stage Warning: Fine movement request not successful")
            	

            
	# Return the absolute position
    def getPosition(self):
        print("Starting getPosition")

        response = self.commWithResp("/" + str(self.stage_id) + " get pos")
        
        response = response.strip()
        response_parts = response.split(" ")
        try:
            sz = float(response_parts[5])
        except ValueError:
            return None
        
        print("...ending getPosition")

        return sz*self.unit_to_um
	
	# Return the coarse position
    def zPositionCoarse(self):
        return self.coarse_position
	
	# Return the fine position
    def zPositionFine(self):
        return self.fine_position

	# Return if the stage is moving
    def isStageMoving(self):
        print("Starting isStageMoving")
        response = self.commWithResp("/" + str(self.stage_id))
        
        # Parse the response
        response_parts = response.split(" ")
        print("...ending isStageMoving")

        # Handle an error response, or an empty response
        if not (response_parts[2] == "OK") or len(response_parts) < 2:
            print("STAGE ERROR: " + response)
            return "ERROR"        
        # Parse IDLE/BUSY
        if response_parts[3] == "IDLE":
            return "IDLE"
        else: # BUSY Case
            return "MOVING"
        
    def configureZScan(self, z_pos_in_um):
        print("Starting configureZScan")
        # Handle empty z case
        if len(z_pos_in_um)==0:
            print("No z positions provided")
            return
        
        # Convert offsets into absolute position units
        z_in_units = []
        for index, z_in_um in enumerate(z_pos_in_um):
            if len(z_in_units) == 0: # Use movement from current position
                temp_z = round(z_in_um*self.um_to_unit)
                z_in_units.append(temp_z)
            else: # Calculate movement from previous relative position
                temp_z = round( (z_in_um - z_pos_in_um[index-1]) * self.um_to_unit)
                z_in_units.append(temp_z)
                
        start_time = timer()
        print("Starting configuration of the z stage movement....")
            
        # Erase the previous buffer
        response = self.commWithResp("/stream 1 setup disable")
        response_parts = response.split(" ")
        if not (response_parts[2] == "OK") or len(response_parts) < 2:
            print("STAGE ERROR: " + response)
            #return "ERROR"        
        
        response = self.commWithResp("/stream buffer 1 erase")
        response_parts = response.split(" ")
        if not (response_parts[2] == "OK") or len(response_parts) < 2:
            print("STAGE ERROR: " + response)
            #return "ERROR"        

        # Configure a stream buffer
        response = self.commWithResp("/stream 1 setup store 1 1")
        response_parts = response.split(" ")
        if not (response_parts[2] == "OK") or len(response_parts) < 2:
            print("STAGE ERROR: " + response)
            return "ERROR"        

        # Loop over z positions to add relevant commands
        for z in z_in_units:
            # Wait for a low DI signal (completion of last frame)
            response = self.commWithResp("/stream 1 wait io di 1 == 0")
            response_parts = response.split(" ")
            if not (response_parts[2] == "OK") or len(response_parts) < 2:
                print("STAGE ERROR: " + response)
                return "ERROR"  
            
            # Wait for a high DI signal (start of next frame)
            response = self.commWithResp("/stream 1 wait io di 1 == 1")
            response_parts = response.split(" ")
            if not (response_parts[2] == "OK") or len(response_parts) < 2:
                print("STAGE ERROR: " + response)
                return "ERROR"        

            # Wait for a high DI signal (start of next frame)
            response = self.commWithResp("/stream 1 line rel " + str(z))
            response_parts = response.split(" ")
            if not (response_parts[2] == "OK") or len(response_parts) < 2:
                print("STAGE ERROR: " + response)
                return "ERROR"      
            
        end_time = timer()

        print("...completed a hardware triggered configuration with the following relative positions")
        print("...required " + str(end_time - start_time))
        print(z_in_units)
        print(z_pos_in_um)
        
    def startZScan(self):
        print("Starting startZScan")
        
        # Configure zscan mode
        self.is_zscan = True
        
        # For troubleshooting purposes, reset the stream
        response = self.commWithResp("/stream 1 setup disable")
        response_parts = response.split(" ")
        if not (response_parts[2] == "OK") or len(response_parts) < 2:
            print("STAGE ERROR: " + response)
            return "ERROR"  
        
        # Configure the live mode
        response = self.commWithResp("/stream 1 setup live 1")
        response_parts = response.split(" ")
        if not (response_parts[2] == "OK") or len(response_parts) < 2:
            print("STAGE ERROR: " + response)
            return "ERROR"  

        # Configure the live mode
        response = self.commWithResp("/stream 1 call 1")
        response_parts = response.split(" ")
        if not (response_parts[2] == "OK") or len(response_parts) < 2:
            print("STAGE ERROR: " + response)
            return "ERROR"  
        
        print("...ending startZScan")

            
    def completeZScan(self):
        print("Starting zaberZ.completeZScan")
        #response = self.commWithResp("/stream 1 info")
        response = self.commWithResp("/stream 1 setup disable")
        print("Disabled z scan")
        print(response)
        response_parts = response.split(" ")
        if not (response_parts[2] == "OK") or len(response_parts) < 2:
            print("STAGE ERROR: " + response)
            return "ERROR"  

        self.is_zscan = False

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
