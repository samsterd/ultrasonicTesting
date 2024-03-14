# module to create a 32-bit server for interacting with the USB-UT350 tone burst pulser SDK
# Modified from the 'Access a 32-bit library in 64-bit Python' tutorial in the MSL-LoadLib documentation

from msl.loadlib import Server32

class usbut350Server(Server32):
    """Wrapper around a 32-bit C++ library 'USBUT.dll' that has an 'add' and 'version' function."""

    def __init__(self, host, port, dllFile = 'C://USUTSDK//USBUTSDKC//USBUT.dll', **kwargs):
        # Load the 'my_lib' shared-library file using ctypes.CDLL
        super(usbut350Server, self).__init__(dllFile, 'cdll', host, port)

        # The Server32 class has a 'lib' property that is a reference to the ctypes.CDLL object
        self.usbPort = self.findPort()
        # Call the version function from the library
        # self.version = self.lib.version()

    # Functions for communicating with the pulser over USB
    #   All functions go through USBUTParms with the first MODE argument setting the function
    #   There are also two optional paramters after MODE
    # Initialize function to start communicating with the pulser
    def initialize(self, port = 0):
        return self.lib.USBUTParms(5000, port)

    # Finds what USB port the pulser is plugged into
    # Runs initialize while iterating through the allowed port numbers (0-19)
    # returns the port where initialize returns 1.
    def findPort(self):

        for i in range(19):
            if self.initialize(i) == 1:
                return i

        # USB port not found, raise an error
        raise RuntimeError("Unable to find USB port that USB-UT350 is connected to. Please verify the device is connected and its drivers are installed.")

    # Set the pulse repetition frequency of the pulser in Hz
    # 0 <= freq <= 1000
    # Returns 1 if succesful
    def setPRF(self, freq):

        prf = self.lib.USBUTParms(1038, self.usbPort, freq)

        if prf != 1:
            print("setPRF not successful. Check connection to pulser.")

        return prf

    # Turn off pulser by setting PRF to 0
    def pulserOff(self):

        return self.setPRF(0)

    # Turn pulser on to maximum frequency
    def pulserOn(self):

        return self.setPRF(1000)

    # Set the frequency of the tone burst
    # 20 < freq < 10,000 (values are in kHz)
    # Final option is polarity - 0 for positive, 1 for negative
    # Default is 2.25 MHz with positive polarity
    def setFrequency(self, freq = 2250, polarity = 0):

        return self.lib.USBUTParms(1046, self.usbPort, freq, polarity)

    def setHalfCycles(self, halfCycles = 16):

        return self.lib.USBUTParms(1012, self.usbPort, halfCycles)

    # For now this function just sets voltage to max
    # TODO: translate the formula in SDK to make this usable
    def setVoltage(self):

        return self.lib.USBUTParms(1011, self.usbPort, 255)