# Code for running pulser
# Each function has separate handling depending on whether pulserType = 'standard' or 'tone burst'
#   standard - communicates to Ultratek CompactPulser over serial connection using pyserial using ascii commands
#   tone burst - communicates to USBUT350 using MSL-LoadLib to access their 32 bit C SDK


import serial
import math
from msl.loadlib import Client64

# Pulser connections are implemented as a class
# both types of pulsers will have the same function names, but they will behave differently depending on their type
class Pulser():

    # pulserType is required. kwargs will be the port name for 'standard' or the dll file location for 'tone burst'
    def __init__(self, pulserType, **kwargs):

        # Inform the pulserType
        self.type = pulserType

        # Initialize connection to the pulser based on the type
        self.connection = self.openPulser(pulserType, kwargs)

    # creates the connection object based on the pulserType, either a pyserial instance or a win64 server
    def openPulser(self, pulserType, kwargs):

        if pulserType == 'standard':

            # Create a pyserial connection object
            # Note pyserial defaults match the ultratek connection parameters
            # For reference these are:
            # baudrate = 9600
            # bytesize = EIGHTBITS
            # parity = PARITY_NONE
            # stopbits = STOPBITS_ONE
            # xonxoff = False
            try:
                pulserSerial = serial.Serial(kwargs['pulserPort'])

            except serial.SerialException as error:
                print(f"Error opening pulser: {error}")
                return -1

            else:
                return pulserSerial

        elif pulserType == 'tone burst':

            # Create an instance of the win64 client for interacting with the 32-bit dll
            return usbut350Client(kwargs['dllFile'])

        else:

            print("pulserType not recognized. Make sure to set pulserType to either 'standard' or 'tone burst'")
            return -1

    # Function to send commands to the standard pulser by serial. Useful for turning things on/off or adjusting parameters
    # Inputs: string command to send
    # Function adds a carriage return to the command, encodes it to ascii, then sends to the pulser
    # TODO: add verification that message is received
    def writeToPulser(self, command):

        if self.type == 'standard':

            commandString = command + '\r'

            try:
                self.connection.write(commandString.encode('ascii'))

            except serial.SerialException as error:
                print(f"Error writing command to pulser: {error}")
                return -1

            else:
                return 0

        else:
            print("writeToPulser: pulserType is not Standard, serial commands not sent")
            return -1

    # Change the frequency of the pulser
    # Inputs a frequency in MHz
    def setFrequency(self, freq):

        if self.type == 'standard':
            # Calculate pulse width from frequency. First convert freq to period (in ns) then divide by 2 -> 500 / freq
            # math.floor is used to find the nearest integer
            pulseWidth = math.floor(500 / freq)

            # Convert the pulseWidth to the appropriate pulser command
            pulseWidthCommand = 'W' + str(pulseWidth)

            self.writeToPulser(pulseWidthCommand)

        elif self.type == "tone burst":

            # convert frequency to kHz
            # math.floor is used to round to nearest integer
            freqkhz = math.floor(freq * 1000)

            # send command
            self.connection.setFrequency(freqkhz)

    def setHalfCycles(self, halfCycles : int):

        if self.type == 'standard':

            # standard pulser does not have this attribute. Print warning message and continue
            print("pulser.setHalfCycles: pulserType 'standard' does not have attribute 'halfCycles'. Ignoring command.")

        elif self.type == 'tone burst':

            if 1 <= halfCycles and halfCycles <= 32:

                self.connection.setHalfCycles(halfCycles)

            else:
                print("pulser.setHalfCycles: parameter 'halfCycles' must be an integer between 1 and 32")

    # Turns the pulser on at maximum pulse repitition frequency (PRF)
    # Returns None
    def pulserOn(self):

        # Compact PUlser max PRF is 5000 Hz. P# command sets PRF to 10 * #, so P500 = 5000 Hz
        if self.type == 'standard':
            self.writeToPulser('P500')

        # Tone burst max PRF is 1000 Hz
        elif self.type == 'tone burst':
            self.connection.setPRF(1000)

    # Turns off pulser by setting pulse repetition frequency to 0
    # Returns None
    def pulserOff(self):

        if self.type == 'standard':
            self.writeToPulser('P0')

        elif self.type == 'tone burst':
            self.connection.setPRF(0)

    # Closes connection to pulser
    def closePulser(self):

        if self.type == 'standard':
            try:
                self.connection.close()

            except serial.SerialException as error:
                print(f"Error closing pulser connection: {error}")
                return -1

            else:
                return 0

        elif self.type == 'tone burst':
            return self.connection.shutdown_server32()
    def readGain(self):
        #start with self.writeToPulser('G?'), but then you need to read the value that comes out
        getValue = self.connection.read().decode('ascii')
        if "G" in getValue:
            getValue=getValue.replace('G','')
            getValue= int(getValue)
            return getValue

    def setGain(self, gainValue : int):
        #It needs to check that it is between -120 and 840 (the upper and lower limits on the pulser), 
        # give an error message if the input is invalid, otherwise run self.writeToPulser('G' + str(gainValue)
        if -120<= gainValue and gainValue<=840:
            self.writeToPulser('G' + str(gainValue))
        else:
            print("error: input is invalid")

# Set up class for calling tone burst functions using msl-loadlib 64 bit client
class usbut350Client(Client64):
    """Call a function in 'my_lib.dll' via the 'MyServer' wrapper."""

    def __init__(self, dllLocation):
        # Specify the name of the Python module to execute on the 32-bit server (i.e., 'my_server')
        super(usbut350Client, self).__init__(module32='usbut350Server', dllFile = dllLocation)

    def initialize(self, port = 0):
        return self.request32('initialize', port)

    def findPort(self):
        return self.request32('findPort')

    def setPRF(self, freq):
        return self.request32('setPRF', freq)

    def pulserOn(self):
        return self.request32('pulserOn')

    def pulserOff(self):
        return self.request32('pulserOff')

    def setFrequency(self, freq = 2250, polarity = 0):
        return self.request32('setFrequency', freq, polarity)

    def setHalfCycles(self, halfCycles = 16):
        return self.request32('setHalfCycles', halfCycles)

    # incomplete version, just sets to max voltage
    # TODO: implement actual selection
    def setVoltage(self):
        return self.request32('setVoltage')

import ultratekPulser as utp

pulser = utp.Pulser('standard', '/dev/tty/USB1')

print(pulser.readGain())