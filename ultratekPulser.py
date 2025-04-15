# Code for running pulser
# Each function has separate handling depending on whether pulserType = 'standard' or 'tone burst'
#   standard - communicates to Ultratek CompactPulser over serial connection using pyserial using ascii commands
#   tone burst - communicates to USBUT350 using MSL-LoadLib to access their 32 bit C SDK


import serial
import math
from msl.loadlib import Client64

class Pulser():

    # pulserType is required. kwargs will be the port name for 'standard' or the dll file location for 'tone burst'
    # todo: standardize returns, add more informative and consistent error handling, add error handling for pulserType and kwargs (maybe change from the kwargs requirement?)
    def __init__(self, pulserType, **kwargs):
        """
        A class for interacting with Ultratek ultrasonic pulsers. This class currently supports the CompactPulser (standard
        pulser type) and the USBUT tone burst pulser (tone burst pulser type), with different behaviors depending on which
        pulser is used.

        Methods:
            init(pulserType : str, kwargs) : sets values based on experiment parameters and initializes connection to instrument
                kwargs are used to establish the connection depending on the pulserType
                'pulserPort' is required for 'standard' type and is the USB port that the pulser is connected to
                'dllFile' is required for 'tone burst' type and is the file location of the USBUT dll file
            openPulser(pulserType : str, kwargs) : sets up the connection to the pulser
            writeToPulser(command : str) : sends a command string to the 'standard' pulser
            setFrequency(freq : int or float) : sets the frequency of the pulser (MHz)
            setHalfCycles(halfCycles : int) : sets the number of half cycles in a tone burst pulse
            pulserOn() : turns on the pulser by setting the pulse repetition frequency (PRF) to max
            pulserOff() : turns off the pulser by setting the PRF to 0
            closePulser() : closes connection to the pulser
            readGain() : reads the current gain of the pulser (standard pulser only)
            setGain(gainValue : int) : sets the gain of the pulser for pulse-echo measurements (standard pulser only)

        Class Variables:
            type (str) : 'standard' for CompactPulser, 'tone burst' for the tone burst pulser
                type is used as a switch in most class methods to implement the command in the proper way
                'standard' sends commands via the serial connection. 'tone burst' sends commands via an msl-loadlib server
                in order to interact with the tone burst pulser's 32 bit dll functions
            minGain (int) : minimum value the gain can be safely set to on the compact pulser
            maxGain (int) : maximum value the gain can be safely set to on the compact pulser
            connection (class) : the connection class used to communicate with the pulser.
                'standard' used the PySerial Serial object
                'tone burst' uses the msl-loadlib Client64 object
        """
        # Inform the pulserType
        self.type = pulserType

        # Fill in some constants
        self.minGain = -120
        # maxGain is set below pulser maximum (840) because signals get distorted above 600
        self.maxGain = 600

        # Initialize connection to the pulser based on the type
        self.connection = self.openPulser(pulserType, kwargs)

    def openPulser(self, pulserType, kwargs):
        """
        Creates the connection object based on the pulserType, either a pyserial instance or a win64 server.

        Args:
            pulserType (str) : 'standard' or 'tone burst'
            kwargs : required keyword arguments for establishing the connection, which depend on the pulserType
                pulserPort (str) : type == 'standard', the name of the USB port the pulser is connected to (i.e. 'COM3' or '/dev/ttyUSB0')
                dllFile (str) : type == 'tone burst', the location of the dll file (usually within the folders '...//USUTSDK//USBUTSDKC//USBUT.dll')

        Returns:
            connection class : Serial object for 'standard' (or -1 if an error occurred), usbut350Client for 'tone burst'
        """

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

     # TODO: add verification that message is received
    def writeToPulser(self, command):
        """
         Function to send commands to the standard pulser by serial. Formats and encodes input strings and sends them
         through the connection.

         Args:
             command (str) : the command string to be sent to the pulser. See the CompactPulser manual for a list of commands
                NOTE: do not add a carriage return to input strings, the function handles this automatically.
         Returns:
             int : 0 if successful, -1 if an error occurred. Errors are accompanied by printed messages
        """

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

    def setFrequency(self, freq):
        """
        Changes the frequency of ultrasound emitted by the pulser.

        Args:
            freq (int or float) : the frequency to set the pulser, in MHz

        Returns:
            None. The command is sent to the pulser and error handling is done through writeToPulser.
        """

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
        """
        Changes the number of half cycles in a tone burst.

        Args:
            halfCycles (int) : the number of half cycles to set. 1 <= halfCycles <= 32

        Returns:
            None. The command is sent to the pulser and error handling is done through usbut350Client.setHalfCycles
        """

        if self.type == 'standard':

            # standard pulser does not have this attribute. Print warning message and continue
            print("pulser.setHalfCycles: pulserType 'standard' does not have attribute 'halfCycles'. Ignoring command.")

        elif self.type == 'tone burst':

            if 1 <= halfCycles and halfCycles <= 32:

                self.connection.setHalfCycles(halfCycles)

            else:
                print("pulser.setHalfCycles: parameter 'halfCycles' must be an integer between 1 and 32")

    def pulserOn(self):
        """
        Sets the pulser to the maximum pulse repitition frequency (PRF) as the 'on' state. These values are 5000 Hz for
        'standard' and 1000 Hz for 'tone burst'

        Args:
            None

        Returns:
            None
        """

        #TODO: make PRF an experiment parameter
        # Compact PUlser max PRF is 5000 Hz. P# command sets PRF to 10 * #, so P500 = 5000 Hz
        if self.type == 'standard':
            self.writeToPulser('P500')

        # Tone burst max PRF is 1000 Hz
        elif self.type == 'tone burst':
            self.connection.setPRF(1000)

    def pulserOff(self):
        """
        Turns off pulser by setting pulse repetition frequency to 0.

        Args:
            None
        Returns:
            None
        """

        if self.type == 'standard':
            self.writeToPulser('P0')

        elif self.type == 'tone burst':
            self.connection.setPRF(0)

    def closePulser(self):
        """
        Closes the connection to the pulser. This ends the Serial connection for 'standard' and shuts down the 32-bit
        server for 'tone burst'

        Args:
            None
        Returns:
            None
        """

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

    #todo: error handling here is particularly bad
    def readGain(self):
        """
        Reads the gain setting of the 'standard' pulser for the RF output.
        This is used when optimizing settings for pulse-echo measurements.

        Args:
            None
        Returns:
            int : the current gain setting (-120 to 600), 0 if no gain was returned, -1 if type is 'tone burst'
        """

        if self.type == 'standard':

            #start with self.writeToPulser('G?'), but then you need to read the value that comes out
            self.writeToPulser('G?')
            getValue = self.connection.read_until('\r'.encode('ascii'))
            # print(getValue)
            getValue=str(getValue)
            if "G" in getValue:
                getValue=getValue.replace("'",'')
                getValue=getValue.replace('bG=','')
                getValue=getValue.replace('\\r','')
                return int(getValue)
            else:
                return 0
        else:
            print("readGain: gain setting is not supported on the tone burst pulser.")
            return -1

    def setGain(self, gainValue : int):
        """
        Sets the gain setting of the 'standard' pulser for the RF output.
        This is used when optimizing settings for pulse-echo measurements.

        Args:
            gainValue (int) : the gain value to set on the Pulser (in dB). Must be between self.minGain and self.maxGain

        Returns:
            None
        """

        if self.type == 'standard':

            #It needs to check that it is between minGain and maxGain (the upper and lower limits on the pulser),
            # give an error message if the input is invalid, otherwise run self.writeToPulser('G' + str(gainValue)
            if self.minGain<= gainValue and gainValue<=self.maxGain:
                self.writeToPulser('G' + str(gainValue))
            else:
                print("error: input is invalid")

        else:
            print("setGain: gain setting is not supported on the tone burst pulser.")

class usbut350Client(Client64):
    """Call a function in 'my_lib.dll' via the 'MyServer' wrapper."""

    def __init__(self, dllLocation):
        """
        A class for interacting with the tone burst pulser functions via msl-loadlib Client64 object
        This is needed because the tone burst dll files are in 32 bit C, but all modern Python will run on a 64 bit program
        In order to get around this, msl-loadlib creates a 32 bit server with the dll loaded and a 64 bit client to send
        our commands from. In this way 64 bit commands are sent, executed by the 32 bit server, and any results sent back
        to the 64 bit client to be read in Python.

        Methods:
            init(dllLocation : str) : initializes the 32 bit server. Requires the location of the 32-bit dll file for the
                tone burst pulser functions
            All other methods pass specific commands to the 32 bit server (more details in usbut350Server class within usbut350Server.py)
            Each of these methods is a wrapper for the Client64 request32 method:
                The first argument is a string naming the method to call in the Server32 (usbut350Server) object
                Extra args are passed in order after the function name string
            Methods are:
            initialize(port : int) : creates the USB connection to the pulser
            findPort() : finds the port number the tone burst pulser is connected to
            setPRF(freq : int) : sets the pulser repetition frequency (PRF) (Hz)
            pulserOn() : sets the PRF to max (1000 Hz)
            pulserOff() : sets the PRF to 0
            setFrequency(freq : int or float, polarity : int) : sets the ultrasound frequency. Polarity is 0 or 1 and
                determines whether the initial voltage is positive or negative.
            setHalfCycles(halfCycles : int) : sets the number of tone burst half cycles (from 1 to 32)
        """
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

