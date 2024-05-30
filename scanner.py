# set of functions for controlling the Ender-3 for ultrasonic scanning
# modified from test_ender functions

# Scanner control is implemented through the Scanner class
# Variables:
#   port - USB port address of scanner
#   serial - Pyserial Serial object for the connection to the scanner
#   minDimensions - 3-tuple of the minimum coordinates the scanner can safely move to. Equal to (0, 0, transducer holder height)
#   maxDimensions - 3-tuple of the max coordinates the scanner can move to. Determined by the printer volume. For Ender-3 it is (220, 220, 240)
# Functions:
#   init(parameters : dict) - initializes the connection to the scanner and other variables based on information passed in parameters dict
#                             parameters must include 'scannerPort', 'transducerHolderHeight', and 'scannerMaxDimensions'
#   write(command : str) - formats arbitrary strings and passes them through the serial connection
#   move(axis : str, distance : number) - moves along the specified axis and distance
#   currentPosition() - gets the current position from the scanner. Returns a 3-tuple of the (x, y, z) coordinates
#   safeMoveQ(axis : str, distance : number) - checks that a proposed move is within min/maxDimensions of scanner. Returns a Boolean
#   home() - runs the scanner homing protocol to calibrate its current position by moving to (0,0,0)
#            NOTE: DO NOT RUN THIS WITH THE TRANSDUCER HOLDER OR ANY EXPERIMENTAL MATERIALS ON THE SCANNER STAGE
#   cancel() - stops the current move action. Cannot cancel a home() command
#   close() - stops the current serial connection
# Also includes two helper functions
#   axisDistanceToArray(axis : str, distance : number) - converts an axis/distance pair into a len-3 numpy array corresponding to the move
#   validAxisQ(axis : str) - tests whether an input string is a valid axis

import serial
import numpy as np

# Scanner class controls the 3D motion of the gantry via pyserial. Tested on Ender-3 3D printer gantry, but should work
# with any gantry that operates on GCode
class Scanner():

    # establish connection via Serial object
    # the parameterDict must contain the keys 'scannerPort', 'transducerHolderHeight' and 'scannerMaxDimensions'
    def __init__(self, parameters : dict, baudRate = 115200):

        if 'scannerPort' not in parameters.keys() or 'transducerHolderHeight' not in parameters.keys() or 'scannerMaxDimensions' not in parameters.keys():
            raise KeyError("Scanner: input parameters does not contain enough information. "
                  "parameters must be a dict with keys \'scannerPort\', \'transducerHolderHeight\' and \'scannerMaxDimensions\'")

        self.port = parameters['scannerPort']
        self.minDimensions = (0, 0, parameters['transducerHolderHeight'])
        self.maxDimensions = parameters['scannerMaxDimensions']

        try:
            # Open serial port
            self.serial = serial.Serial(parameters['scannerPort'], baudRate)

        # catch errors in connection
        except serial.SerialException as error:
            print(f"Scanner.init: Error opening connection to scanner: {error}")

            # return -1 for error
            raise serial.SerialException

    # encode strings to the proper format and send to the scanner via serial
    def write(self, command):

        # commands need a space, carriage return, and newline to be accepted
        formattedCommand = command + " \r\n"

        try:
            self.serial.write(formattedCommand.encode('utf-8'))

        except serial.SerialException as error:
            print(f"Scanner.write: Error writing command to scanner: {error}")
            raise serial.SerialException

    # Writes a series of commands to perform relative movements with the scanner
    # Inputs the axis of motion as a string ('X','Y', or 'Z'), and the distance to move (in mm) (can be negative)
    # function translates the movement to GCode and passes it to the scanner
    def move(self, axis : str, distance):

        if not self.validAxisQ(axis):
            raise ValueError('Input axis is not \'X\', \'Y\', or \'Z\'')

        if not self.safeMoveQ(axis, distance):
            print("Scanner.move Error: input move is not safe. Check that there is enough space for the scanner to make the desired move.")
            return -1

        # make uppercase
        upperAxis = axis.upper()

        # Convert axis and distance inputs into the proper GCode
        motionCommand = "G1 " + upperAxis + str(distance)

        # Set ender units to millimeters
        unitRes = self.write("G21")

        # Set positioning to relative (not absolute)
        posRes = self.write("G91")

        # Disable endstops
        #TODO: figure out why this is necessary, update for safety
        popRes = self.write("M121")

        # Send motion command
        moveRes = self.write(motionCommand)

        # flush out the responses. It is unclear why 5 reads are needed for 4 commands, but testing has shown it is needed
        for i in range(5):
            self.serial.read_until()

    def currentPosition(self):

        # set to absolute positioning
        self.write("G90")
        self.serial.read_until()
        # gather the current position from the scanner
        self.write("M114")
        serialRead = self.serial.read_until()
        pos = serialRead.decode('utf-8')

        # output string is 'X:100.00 Y:0.00 Z:160.00 E:0.00 Count X:8000 Y:0 Z:64000'
        # need to format to return (X,Y,Z)
        splitPos = [coor.split(':') for coor in pos.split()]
        x = float(splitPos[0][1])
        y = float(splitPos[1][1])
        z = float(splitPos[2][1])

        return (x,y,z)

    # test whether a given move is safe based on the measurements of the scanner and transducer holder
    def safeMoveQ(self, axis, distance):

        if not self.validAxisQ(axis):
            raise ValueError('Input axis is not \'X\', \'Y\', or \'Z\'')

        # get the current position, destination position
        currentPos = np.array(self.currentPosition())
        movePos = self.axisDistanceToArray(axis, distance)
        destinationPos = currentPos + movePos

        # iterate through destinationPos and check vs max and min dimensions
        for i in range(3):
            if destinationPos[i] < self.minDimensions[i] or destinationPos[i] > self.maxDimensions[i]:
                return False

        return True

    # NOTE: DO NOT RUN WHILE THE TRANSDUCER HOLDER IS ATTACHED
    def home(self):
        self.write("G28")

    # NOTE: this will not cancel the home command, it can only cancel ongoing move commands
    def cancel(self):
        self.write("G80")

    def close(self):

        try:
           self.serial.close()

        except serial.SerialException as error:
            print(f"Scanner.close error: {error}")
            raise serial.SerialException

    # helper function to convert an axis, distance pair to a numpy array
    # i.e. 'X', 3 to [3,0,0] or 'Z', -5 to [0,0,-5]
    @classmethod
    def axisDistanceToArray(self, axis : str, distance):

        if not self.validAxisQ(axis):
            raise ValueError('Input axis is not \'X\', \'Y\', or \'Z\'')
        if axis.upper() == 'X':
            return np.array([distance, 0, 0])
        elif axis.upper() == 'Y':
            return np.array([0,distance,0])
        elif axis.upper() == 'Z':
            return np.array([0,0,distance])

    # helper function to check if a given input string is 'X', 'Y', or 'Z'
    @staticmethod
    def validAxisQ(axis : str):

        if axis.upper() in ['X', 'Y', 'Z']:
            return True
        else:
            return False
