import serial

# class for controlling Cytec CXAR multiplexer
class Mux():

    # establish connection to port, gather data from import params, perform basic error checking
    # requires the experimentParams dict to run
    def __init__(self, params):

        # create serial connection object for mux
        try:
            self.connection = serial.Serial(params['multiplexerPort'])
        except serial.SerialException as error:
            print(f"Error opening multiplexer: {error}")
            return -1

        # gather addresses
        self.tx = params['txAddress']
        self.pico = params['picoAddress']
        self.rf = params['rfAddress']
        self.t0p = params['t0PulseAddress']
        self.t0r = params['t0ReceiveAddress']
        self.t1p = params['t1PulseAddress']
        self.t1r = params['t1ReceiveAddress']

        # define mode/direction combinations in terms of switches that are on
        # self.tx and self.pico are added to all combinations since they are required to run an experiment
        # this data is used in self.setMuxConfiguration but is more convenient to define in __init__
        txPico = [self.tx, self.pico]
        self.transForward = [self.t0p, self.t1r] + txPico
        self.transReverse = [self.t1p, self.t0r] + txPico
        self.echoForward = [self.t0p, self.rf] + txPico
        self.echoReverse = [self.t1p, self.rf] + txPico

        # ensure there are no dangerous or poorly formed address combinations in the input
        self.errorCheckAddresses(params)

        # set the multiplexer to answerback mode to ensure all commands are received
        self.writeToMux('A 1 73')

    # close all switches and close serial connection
    def closeMux(self):

        self.clearMux()
        try:
            self.connection.close()

        except serial.SerialException as error:
            print(f"Error closing multiplexer connection: {error}")
            return -1
        return 0

    # Inputs a command string
    # Appends an \r, encodes the string and passes it to the multiplexer
    # Reads response and ensures no error codes were given (that is, response == 0 or 1)
    #   Raises an error and closes all switches if an error code occurs
    def writeToMux(self, command: str):

        self.connection.write((command + '\r').encode('utf-8'))

        response = int(self.connection.read_until('\r'.encode('utf-8')))

        if response != 0 and response != 1:
            self.clearMux()
            raise MuxError("Multiplexer returned the error code '" + str(response) + "'. Experiment aborted. "
                                                                                     "See https://cytec-ate.com/quickstart/remote/ for documentation")
        else:
            return 0

    # runs the 'C' command, which turns off all switches
    def clearMux(self):

        self.writeToMux('C')
        return 0

    # runs the 'L# # #' command, which opens the specified switch
    # inputs a switch address tuple
    def openSwitch(self, switch):

        if None in switch:
            raise MuxError("An address containing None was passed to openSwitch. This is not a valid address. Experiment aborted.\n"
                           "If this error appears during normal operation, please send your experimental parameters to Sam. Congratulations! You have found"
                           " an interesting edge case to the guardrails.")

        # convert switch address to command string
        commandString = "L0 " + str(switch[0]) + " " + str(switch[1])
        self.writeToMux(commandString)
        return 0

    # runs the 'U# # #' command, which closes the specified switch
    # inputs a switch address tuple
    def closeSwitch(self, switch):

        if None in switch:
            raise MuxError("An address containing None was passed to closeSwitch. This is not a valid address. Experiment aborted.\n"
                           "If this error appears during normal operation, please send your experimental parameters to Sam. Congratulations! You have found"
                           " an interesting edge case to the guardrails.")

        # convert switch address to command string
        commandString = "U0 " + str(switch[0]) + " " + str(switch[1])
        self.writeToMux(commandString)
        return 0

    # opens a list of switches in successions
    # inputs a list of switch address tuples
    # performs error checking on the list, ensuring that the pulse and receive addresses of the same transducer are not
    #   input at the same time (this directly connects the pulser to picoscope and will break the picoscope)
    #   If an unsafe combination is input, closes all switches and raises an error
    # then it runs openSwitch for each input switch
    def openSwitches(self, switches):

        # check for unsafe switch combinations
        t0Pulsing = False
        t0Receiving = False
        t1Pulsing = False
        t1Receiving = False
        for switch in switches:
            if switch == self.t0p: t0Pulsing = True
            if switch == self.t1p: t1Pulsing = True
            if switch == self.t0r: t0Receiving = True
            if switch == self.t1r: t1Receiving = True

        if t0Pulsing and t0Receiving:
            self.clearMux()
            raise MuxError("Unsafe combination of switch openings detected for Transducer 0. Experiment aborted.")
        elif t1Pulsing and t1Receiving:
            self.clearMux()
            raise MuxError("Unsafe combination of switch openings detected for Transducer 1. Experiment aborted.")

        # No unsafe combinations detected so open the switches
        for switch in switches:
            self.openSwitch(switch)
        return 0

    # Changes the state of the multplexer to match the given collection mode (transmission or pulse-echo) and direction (forward or reverse)
    # First clearMuxs the prior state, then opens all of the requested switches
    # Inputs the mode and direction strings, returns 0 when operation is complete
    def setMuxConfiguration(self, mode : str, direction : str):

        self.clearMux()
        if mode == 'transmission' and direction == 'forward':
            self.openSwitches(self.transForward)
        elif mode == 'transmission' and direction == 'reverse':
            self.openSwitches(self.transReverse)
        elif mode == 'echo' and direction == 'forward':
            self.openSwitches(self.echoForward)
        elif mode == 'echo' and direction == 'reverse':
            self.openSwitches(self.echoReverse)
        else:
            print("Mux.setMuxConfiguration: Invalid mode/direction input. Only valid values are mode = 'transmission' or 'echo' "
                  "and direction = 'forward' or 'reverse'.\nInputs were mode = " + mode + " and direction = " + direction + "\nAction was aborted.")
            return -1
        return 0

    # helper function to check that input mux addresses will not cause errors
    # Raises an exception if the picoscope and pulser tx channel are on the same module
    # or if the experiment specified in params requires a component that has a (None, None) address
    def errorCheckAddresses(self, params):

        # check that pulser and picoscope are not on the same module
        txMod = self.tx[0]
        picoMod = self.pico[0]
        if txMod == picoMod:
            raise MuxError("Unsafe combination of multiplexer addresses detected. Please ensure that the txAddress is"
                           " not on the same module as the picoAddress and retry.")

        # check that requested collectionMode and collectionDirection do not require a None address
        # can't think of a clever way to do it so we'll brute force it. It only needs to be done once per experiment so optimization isn't critical
        addressList = []
        mode = params['collectionMode']
        dir = params['collectionDirection']
        if (mode == 'transmission' or mode == 'both'):
            if (dir == 'forward' or dir == 'both'):
                addressList = addressList + self.transForward
            if (dir == 'reverse' or dir == 'both'):
                addressList = addressList + self.transReverse
        if (mode == 'pulse-echo' or mode == 'both'):
            if (dir == 'forward' or dir == 'both'):
                addressList = addressList + self.echoForward
            if (dir == 'reverse' or dir == 'both'):
                addressList = addressList + self.echoReverse

        # check for duplicate addresses
        addressSet = set(addressList)
        if len(addressSet) != len(addressList):
            raise MuxError("The input list of addresses contains duplicates. Please ensure no two addresses share the same "
                           "(module, switch) numbers and try again.")

        # iterate through the addressList and raise an error if any of them are improperly formed or None
        for addr in addressList:
            if None in addr:
                raise MuxError("The specified collectionMode and collectionDirection require a multiplexer address that contains a None value."
                               "Ensure that all required channels are plugged in and that the input addresses are correct and try again.")
            if len(addr) != 2:
                raise MuxError("An input address " + str(addr) + " has the incorrect length. Multiplexer addresses must be tuples of length 2.")
            for num in addr:
                if type(num) != int:
                    raise MuxError("An input address " + str(addr) + " is improperly formatted. All characters in an address must be integers or None.")
        return 0

# Create error class for issues relating to multiplexer configuration and operation
class MuxError(Exception):
    pass