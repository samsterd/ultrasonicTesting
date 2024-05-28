# set of functions for controlling the Ender-3 for ultrasonic scanning
# modified from test_ender functions

# Overhaul goals:
#   turn everything into gantry class
#   update experiment functions to work off of Scanner class
#   add guardrails / limits based on absolute positioning
#       gather absolute pos function
#       initialize limits
#       add check to every move
#           TIME IT AND CHECK FOR INCREASED OVERHEAD
#           Needs to be negligible increase in move time, otherwise check on every scan instead

# Functions:
#   openEnder(port)
#   writeToEnder(serialConnection, command)
#   moveEnder(serialConnection, axis, distance)
#   closeEnder(serialConnection)

import serial

# Scanner class controls the 3D motion of the gantry via pyserial. Tested on Ender-3 3D printer gantry, but should work
# with any gantry that operates on GCode
class Scanner():

    # establish connection via Serial object
    def __init__(self, port, baudRate = 115200):

        try:
            # Open serial port
            self.serial = serial.Serial(port, baudRate)

        # catch errors in connection
        except serial.SerialException as error:
            print(f"Scanner.init: Error opening connection to scanner: {error}")

            # return -1 for error
            return -1

    # encode strings to the proper format and send to the scanner via serial
    def write(self, command):

        # commands need a space, carriage return, and newline to be accepted
        formattedCommand = command + " \r\n"

        try:
            self.serial.write(formattedCommand.encode('utf-8'))

        except serial.SerialException as error:
            print(f"Scanner.write: Error writing command to scanner: {error}")
            return -1

    # Writes a series of commands to perform relative movements with the scanner
    # Inputs the axis of motion as a string ('X','Y', or 'Z'), and the distance to move (in mm) (can be negative)
    # function translates the movement to GCode and passes it to the scanner
    def move(self, axis : str, distance):

        if axis not in ['X', 'x', 'Y', 'y', 'Z', 'z']:
            print("Scanner.move error: invalid axis input. Axis must be one of the strings \'X\', \'Y\', or \'Z\'. Movement aborted.")
            return -1

        # Convert axis and distance inputs into the proper GCode
        motionCommand = "G1 " + axis + str(distance)

        # Set ender units to millimeters
        unitRes = self.write("G21")
        if unitRes == -1:
            print("Scanner.move: error sending code G21 to scanner. Movement aborted.")
            return -1

        # Set positioning to relative (not absolute)
        posRes = self.write("G91")
        if posRes == -1:
            print("Scanner.move: error sending code G91 to scanner. Movement aborted.")
            return -1

        # Disable endstops
        #TODO: figure out why this is necessary, update for safety
        popRes = self.write("M121")
        if popRes == -1:
            print("Scanner.move: error sending code M121 to scanner. Movement aborted.")
            return -1

        # Send motion command
        moveRes = self.write(motionCommand)
        if moveRes == -1:
            print("Scanner.move: error sending code " + motionCommand + " to scanner. Movement aborted.")
            return -1

    def close(self):

        try:
           self.serial.close()

        except serial.SerialException as error:
            print(f"Scanner.close error: {error}")
            return -1