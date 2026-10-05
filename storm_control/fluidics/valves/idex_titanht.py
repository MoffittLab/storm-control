#!/usr/bin/python
# ----------------------------------------------------------------------------------------
# A basic class for UART control of a single IDEX/Rheodyne TitanHT valve (e.g. the
# HT2425 24 position / 25 port selector) driven directly by the TitanHT driver board.
#
# Protocol: IDEX document 2321382G, "UART/USB Communication Protocol for
# TitanEX/TitanEZ/TitanHP, TitanHT Driver Boards and MX Series II Modules"
#   - 8N1, no handshaking, default 19200 baud, TTL levels (use a MAX232 or FTDI adapter)
#   - every packet ends in <CR>; values are two ASCII hex digits
#   - P<hh>  move to position hh      -> <CR> on success, nothing on error
#   - M      home
#   - S      status -> position (01-..) or error code (63, 58, 4D, 42, 37, 2C)
#   - E/R/Q/D read last error / firmware rev / valve profile / command mode
#   - while moving the board answers any input with '*'
#   - TitanHT does not implement the +/- (directional) move commands
#
# Load from kilroy settings with:
#   <valve_class type="string">storm_control.fluidics.valves.idex_titanht</valve_class>
# ----------------------------------------------------------------------------------------

# ----------------------------------------------------------------------------------------
# Import
# ----------------------------------------------------------------------------------------
import time

from storm_control.fluidics.valves.valve import AbstractValve

# ----------------------------------------------------------------------------------------
# TitanHT Class Definition
# ----------------------------------------------------------------------------------------
class AValveChain(AbstractValve):

    error_codes = {0x63: "Valve failure (cannot home)",
                   0x58: "Non-volatile memory error",
                   0x4D: "Valve configuration or command mode error",
                   0x42: "Valve positioning error",
                   0x37: "Data integrity error",
                   0x2C: "Data CRC error"}

    def __init__(self, parameters = None):

        # Define attributes
        self.com_port = parameters.get("valves_com_port")
        self.verbose = parameters.get("verbose", True)
        self.baudrate = parameters.get("valves_baudrate", 19200)
        self.num_ports = parameters.get("valves_num_ports", 24) # Selectable positions (HT2425: 24 + common)
        self.simulate = parameters.get("num_simulated_valves", 0) > 0

        self.current_port = 0
        self.moving = False
        self.error = None

        # Create serial port (if not in simulation mode)
        if not self.simulate:
            import serial
            self.serial = serial.Serial(port = self.com_port,
                                        baudrate = self.baudrate,
                                        bytesize = serial.EIGHTBITS,
                                        parity = serial.PARITY_NONE,
                                        stopbits = serial.STOPBITS_ONE,
                                        timeout = 0.5)

        # Configure device
        self.initializeValve()

    # ------------------------------------------------------------------------------------
    # Change Port Position: direction is ignored (TitanHT always takes the shortest path)
    # ------------------------------------------------------------------------------------
    def changePort(self, valve_ID, port_ID, direction = 0, wait_until_done = False):
        if not self.isValidValve(valve_ID):
            return False
        if not self.isValidPort(valve_ID, port_ID):
            return False

        if self.simulate:
            self.current_port = port_ID
            return True

        response = self.inquire("P%02X" % (port_ID + 1))
        if response is None:
            print("TitanHT did not acknowledge move to port " + str(port_ID + 1))
            return False

        if wait_until_done:
            self.waitUntilNotMoving(valve_ID)
        return True

    # ------------------------------------------------------------------------------------
    # Close serial port
    # ------------------------------------------------------------------------------------
    def close(self):
        if not self.simulate:
            self.serial.close()
            if self.verbose:
                print("Closed TitanHT valve on " + str(self.com_port))

    # ------------------------------------------------------------------------------------
    # Default names for each port (port 0 = position 1)
    # ------------------------------------------------------------------------------------
    def getDefaultPortNames(self, valve_ID):
        return ["Port " + str(port_ID + 1) for port_ID in range(self.num_ports)]

    # ------------------------------------------------------------------------------------
    # Rotation is not selectable on the TitanHT
    # ------------------------------------------------------------------------------------
    def getRotationDirections(self, valve_ID):
        return ["Least distance"]

    # ------------------------------------------------------------------------------------
    # Return (status string, is moving) for the QtValveControl widget
    # ------------------------------------------------------------------------------------
    def getStatus(self, valve_ID):
        self.updateValveStatus()
        if self.error is not None:
            return ("Error: " + self.error, True)
        if self.moving:
            return ("Moving", True)
        return ("Port " + str(self.current_port + 1), False)

    # ------------------------------------------------------------------------------------
    # Configuration string displayed in the GUI
    # ------------------------------------------------------------------------------------
    def howIsValveConfigured(self, valve_ID):
        return "TitanHT " + str(self.num_ports) + " position"

    def howManyValves(self):
        return 1

    # ------------------------------------------------------------------------------------
    # Read firmware/mode, then home if the valve is not at a valid position
    # ------------------------------------------------------------------------------------
    def initializeValve(self):
        print("----------------------------------------------------------------------")
        if self.simulate:
            print("Simulating IDEX TitanHT valve with " + str(self.num_ports) + " positions")
            return True

        print("Opening IDEX TitanHT valve")
        print("   COM Port: " + str(self.com_port) + " @ " + str(self.baudrate) + " baud")
        self.serial.reset_input_buffer()

        firmware = self.inquire("R")
        if firmware is None:
            print("Error: no response from TitanHT valve")
            return False
        if self.verbose:
            print("   Firmware revision: " + chr(int(firmware, 16)))
            print("   Command mode: " + str(self.inquire("D")))
            print("   Valve profile: " + str(self.inquire("Q")))

        self.updateValveStatus()
        if self.error is not None:
            print("   Valve reports error (" + self.error + "); homing")
            self.resetChain()
        return True

    # ------------------------------------------------------------------------------------
    # Send a command and return the stripped response: "" for a bare <CR> acknowledge,
    # "*" if the valve is busy, None if there was no response
    # ------------------------------------------------------------------------------------
    def inquire(self, message):
        self.write(message)
        response = self.read()
        if response == "":
            return None
        return response.strip()

    def isValidPort(self, valve_ID, port_ID):
        if not (0 <= port_ID < self.num_ports):
            if self.verbose:
                print(str(port_ID) + " is not a valid port on the TitanHT")
            return False
        return True

    def isValidValve(self, valve_ID):
        if valve_ID != 0:
            if self.verbose:
                print(str(valve_ID) + " is not a valid valve (TitanHT is a single valve)")
            return False
        return True

    # ------------------------------------------------------------------------------------
    # Read until <CR>; returns "" on timeout
    # ------------------------------------------------------------------------------------
    def read(self):
        response = self.serial.read_until(b"\r").decode(errors = "replace")
        if self.verbose:
            print("TitanHT <- " + repr(response))
        return response

    # ------------------------------------------------------------------------------------
    # Home the valve (position 1)
    # ------------------------------------------------------------------------------------
    def resetChain(self):
        if self.simulate:
            self.current_port = 0
            return
        self.inquire("M")
        self.waitUntilNotMoving(0)

    # ------------------------------------------------------------------------------------
    # Query S and update current_port / moving / error
    # ------------------------------------------------------------------------------------
    def updateValveStatus(self):
        if self.simulate:
            return
        response = self.inquire("S")
        if response is None:
            self.error = "No response"
            return
        if "*" in response:
            self.moving = True
            return

        self.moving = False
        try:
            value = int(response, 16)
        except ValueError:
            self.error = "Unexpected response " + repr(response)
            return

        if value in self.error_codes:
            self.error = self.error_codes[value]
        else:
            self.error = None
            self.current_port = value - 1

    def waitUntilNotMoving(self, valve_ID, pause_time = 0.25, timeout = 30.0):
        start = time.time()
        self.updateValveStatus()
        while self.moving and (time.time() - start) < timeout:
            time.sleep(pause_time)
            self.updateValveStatus()

    def write(self, message):
        if self.verbose:
            print("TitanHT -> " + repr(message))
        self.serial.write((message + "\r").encode())
