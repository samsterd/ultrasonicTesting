# module to create a 32-bit server for interacting with the USB-UT350 tone burst pulser SDK
# Modified from the 'Access a 32-bit library in 64-bit Python' tutorial in the MSL-LoadLib documentation

from msl.loadlib import Server32

class usbut350Server(Server32):
    """Wrapper around a 32-bit C++ library 'USBUT.dll' that has an 'add' and 'version' function."""

    def __init__(self, host, port, dllFile = 'C://USUTSDK//USBUTSDKC//USBUT.dll', **kwargs):
        """
        A class for calling the 32-bit functions in the tone-burst pulser SDK using the msl-loadlib Server32 class.

        Methods:
            init(host : int, port : int, dllFile : string) : initializes the Server32 class, finds the usb port of the pulser
            initialize(port : int) : starts communication with pulser via serial
            findPort() : finds the USB port the pulser is plugged into
            setPRF(freq : int) : sets the pulser pulse repetition frequency in Hz
            pulserOff() : sets PRF to 0
            pulserOn() : sets PRF to 1000
            setFrequency(freq : int, polarity : 0 or 1) : sets the frequency and polarity of the tone burst pulse
            setHalfCycles(halfCycles : int) : sets the number of periods (half periods) in a tone burst pulse
            setVoltage() : sets the max voltage of a pulse. Currently just sets to the maximum value

        Variables:
            usbPort(string) : port the pulser is plugged into
            lib(ctypes.CDLL) : the DLL function library
                functions in the tone burst SDK are called using self.lib.USBUTParms(mode, *args)
                mode is an int which specifies the function to be called. Extra arguments depend on the mode
                More information about these functions is found in the tone burst pulser SDK documentation
        """

        # Load the 'my_lib' shared-library file using ctypes.CDLL
        # The Server32 class has a 'lib' property that is a reference to the ctypes.CDLL object
        # functions in the dll file are called using self.lib.USBUTParms(mode, args)
        super(usbut350Server, self).__init__(dllFile, 'cdll', host, port)

        self.usbPort = self.findPort()

        # Call the version function from the library
        # self.version = self.lib.version()


    def initialize(self, port = 0):
        """
        Starts communication with the pulser. Used to check if a connection was succesful

        Args:
            port(int) : an integer designating the USB port to try communicating through
        Returns:
            int : 1 if connection was successful
        """
        return self.lib.USBUTParms(5000, port)


    def findPort(self):
        """
        Identifies the port the tone burst pulser is connected to by calling initialize on the allowed port numbers (0-19).
        If no port is found, raises a RunetimeError

        Args:
            None
        Returns:
            int : port number of the tone burst pulser.
        """

        for i in range(19):
            if self.initialize(i) == 1:
                return i

        # USB port not found, raise an error
        raise RuntimeError("Unable to find USB port that USB-UT350 is connected to. Please verify the device is connected and its drivers are installed.")

    def setPRF(self, freq):
        """
        Set the pulse repetition frequency of the pulser in Hz

        Args:
            freq (int) : PRF. Allowed PRF is 0 to 1000
        Returns:
            int : return code. 1 if operation successful. If a value other than 1 is returned, a warning message is printed.
        """

        # int() used to ensure we aren't passing freq.0 due to accidental conversion to float upstream
        prf = self.lib.USBUTParms(1038, self.usbPort, int(freq))

        if prf != 1:
            print("setPRF not successful. Check connection to pulser.")

        return prf

    def pulserOff(self):
        """
        Turn off the pulser by setting PRF to 0

        Args:
            None
        Returns:
            int : return code from setPRF(). 1 if operation is successful.
        """

        return self.setPRF(0)

    def pulserOn(self):
        """
        Turn on the pulser by setting PRF to maximum (1000 Hz)

        Args:
            None
        Returns:
            int : return code from setPRF(). 1 if operation is successful.
        """

        return self.setPRF(1000)

    def setFrequency(self, freq = 2250, polarity = 0):
        """
        Set the frequency of the tone burst wave, from 20 kHz to 10 MHz. Also sets the polarity, which determines whether
        the first half cycle has a positive or negative voltage.

        Args:
            freq (int) : frequency, in kHz. Allowed values are 20 to 10,000
            polarity (int) : polarity. Allowed values are 0 (positive) or 1 (negative)
        Returns:
            int : return code. 1 if operation is successful
        """

        # freq must be rounded and converted back to an int due to prevent accidental passing of a float (freq.0)
        return self.lib.USBUTParms(1046, self.usbPort, int(round(freq)), polarity)

    def setHalfCycles(self, halfCycles = 16):
        """
        Set the number of half cycles (i.e. half of a sine period) in a single tone burst pulse

        Args:
            halfCycles (int) : number of half cycles. Allowed values are 2 to 32.
        Returns:
            int : return code. 1 if operation is successful
        """

        return self.lib.USBUTParms(1012, self.usbPort, halfCycles)

    def setVoltage(self):
        """
        Set the maximum voltage in a pulser. Currently sets it to the maximum allowed value.

        Args:
            None
        Returns:
            int : return code. 1 if operation is successful
        """

        return self.lib.USBUTParms(1011, self.usbPort, 255)