#!/usr/bin/env python
"""
A serial interface to the Zaber Dichroic Turret.

Jeffrey Moffitt 9/21
"""

import storm_control.sc_hardware.serial.RS232 as RS232

class ZaberXFCR06C(RS232.RS232):

    def __init__(self, **kwds):
        super().__init__(**kwds)
        self.max_num_positions = 6

    # Change the position of the turret
    def changePosition(self, requested_position):
        # Check to confirm the request is within limits
        assert requested_position <= self.max_num_positions
        assert requested_position > 0
        
        # Define the command string
        command_string = "/01 0 move index " + str(requested_position) + "\n"
        
        # Issue the command
        response = self.commandResponse(command_string)
        
        # Report a problem, if needed
        if not (response == "OK"):
            print("WARNING: Dichroic cube position may not have changed!")

    # Check to see if the device is valid
    def checkIsDeviceOn(self):
        # Check the device id
        device_id = self.commandResponse("/01 0 get device.id\n")
        assert device_id is not None
        print("......Zaber dichroic turret detected: Device " + str(device_id))

    def commandResponse(self, command, timeout = 0.1):
        
        # Clear buffer of old responses.
        self.tty.timeout = 0
        while (len(self.readline()) > 0):
            pass
        
        # Set timeout.
        self.tty.timeout = timeout

        # Send the command and wait timeout time for a response.
        self.writeline(command)
        response = self.readline()

        # Check that we got a message within the timeout.
        if (len(response) > 0):
            split_values = response.split(" ")
            if len(split_values) < 6:
                print(">> Warning unknown Zaber turret response: " + str(response))
                return None                
            # Handle the no error case
            if split_values[2] == "OK":
                return split_values[5]
            else:
                print(">> Turret error: " + split_values[5])
                return split_values[5]
            
        else:
            return None


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
