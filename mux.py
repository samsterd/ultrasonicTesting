import serial

# class for controlling Cytec CXAR multiplexer
class Mux():

    # establish connection to port, gather data from import params, perform basic error checking
    # requires the experimentParams dict to run
    def __init__(self, params):
        """
        A class for controlling the Cytex CXAR multiplexer

        Methods:
            init(params : dict) : establish connection to the multiplexer, gather mux addresses from experimental params,
                define measurement directions, check that the addresses are safe for operation
            closeMux() : close all switches and end serial connection
            writeToMux(command : str) : encodes commands and sends to Mux. Reads response and checks for errors
            clearMux() : close all switches
            openSwitch(switch : tuple) : opens the switch specified by the input address
            closeSwitch(switch : tuple) : closes the switch specified by the input address
            openSwitches(switches : list of tuples) : opens multiple switches, first checking that the combination is safe
                Safe is defined here as no combination of switches is open that directly connects the pulser to the Picoscope
            setMuxConfiguration(mode : str, direction : str) : clears prior state, then opens a set of switches for a given
                experimental configuration (mode/direction)
            errorCheckAddresses(params : dict) : checks that the input list of addresses is safe and properly formatted.
                Safe is defined here as the pulser and Picoscope are not on the same module.

        Variables:
            picoMod (int) : module number that the Picoscope is connected to
            pulseMod (int) : module number that the pulser is connected to
            Switch addresses : every address is defined as a 2-tuple of ints  - (module #, switch #)
                rf : address of pulser RF output (i.e. the pulse-echo signal)
                t0p : transducer 0 pulser connection
                t0r : transducer 0 receiver connection (measure signal in transmission mode)
                t1p : transducer 1 pulser connection
                t1r : transducer 1 receiver connection (measure signal in transmission mode)
            Mode directions: a list of two switch addresses which define a mode (transmission/pulse-echo) and
            direction (forward/reverse) combination
                transForward : transmission from T0->T1
                transReverse : transmission from T1-> T0
                echoForward : pulse from T0, measure from RF
                echoReverse : pulse from T1, measure from RF
        """

        # create serial connection object for mux
        try:
            self.connection = serial.Serial(params['multiplexerPort'])
        except serial.SerialException as error:
            print(f"Error opening multiplexer: {error}")
            return -1

        # convert input module and switch definitions to (module, switch) addresses
        self.picoMod = params['picoModule']
        self.pulseMod = params['pulseModule']
        self.rf = (self.picoMod, params['rfSwitch'])
        self.t0p = (self.pulseMod, params['t0PulseSwitch'])
        self.t0r = (self.picoMod, params['t0ReceiveSwitch'])
        self.t1p = (self.pulseMod, params['t1PulseSwitch'])
        self.t1r = (self.picoMod, params['t1ReceiveSwitch'])

        # define mode/direction combinations in terms of switches that are on
        # self.tx and self.pico are added to all combinations since they are required to run an experiment
        # this data is used in self.setMuxConfiguration but is more convenient to define in __init__
        self.transForward = [self.t0p, self.t1r]
        self.transReverse = [self.t1p, self.t0r]
        self.echoForward = [self.t0p, self.rf]
        self.echoReverse = [self.t1p, self.rf]

        # ensure there are no dangerous or poorly formed address combinations in the input
        self.errorCheckAddresses(params)

        # set the multiplexer to answerback mode to ensure all commands are received
        self.writeToMux('A 1 73')

    def closeMux(self):
        """
        Close all switches and close serial connection

        Args:
            None
        Returns:
            int : 0 if operation is successful, -1 if a SerialException occurred
        """

        self.clearMux()
        try:
            self.connection.close()

        except serial.SerialException as error:
            print(f"Error closing multiplexer connection: {error}")
            return -1
        return 0

    def writeToMux(self, command: str):
        """
        Encodes and sends a command string to the multiplexer, then waits for a response and fails in a safe manner
        if an error message is returned.

        Args:
            command (str) : a string representing a command to the multiplexer. A carriage return will be appended and
                the string encoded in utf-8 before sending
        Returns:
            0 if operation is successful. If an error message is read from the multiplexer, all switches are closed and
            a MuxError is raised before writeToMux returns
        """

        self.connection.write((command + '\r').encode('utf-8'))

        response = int(self.connection.read_until('\r'.encode('utf-8')))

        if response != 0 and response != 1:
            # any response that is not 0 or 1 is an error code. Close all switches before raising error to fail in a safe state
            self.clearMux()
            raise MuxError("Multiplexer returned the error code '" + str(response) + "'. Experiment aborted. "
                                                                                     "See https://cytec-ate.com/quickstart/remote/ for documentation")
        else:
            return 0

    def clearMux(self):
        """
        Runs the 'C' command, which closes all switches.

        Args:
            None
        Returns:
            None
        """
        self.writeToMux('C')

    def openSwitch(self, switch):
        """
        Opens a specified switch by running the 'L# # #' command.

        Args:
            switch ( (int, int) tuple) : the module #, switch # address of the switch to open
        Returns:
            0 if operation is successful
        """
        if None in switch:
            raise MuxError("An address containing None was passed to openSwitch. This is not a valid address. Experiment aborted.\n"
                           "If this error appears during normal operation, please send your experimental parameters to Sam. "
                           "Congratulations! You have found an interesting edge case to the guardrails.")

        # convert switch address to command string
        commandString = "L0 " + str(switch[0]) + " " + str(switch[1])
        self.writeToMux(commandString)
        return 0

    # runs the 'U# # #' command, which closes the specified switch
    # inputs a switch address tuple
    def closeSwitch(self, switch):
        """
        Closes a specified switch by running the 'U# # #' command.

        Args:
            switch ( (int, int) tuple) : the module #, switch # address of the switch to close
        Returns:
            0 if operation is successful
        """
        if None in switch:
            raise MuxError("An address containing None was passed to closeSwitch. This is not a valid address. Experiment aborted.\n"
                           "If this error appears during normal operation, please send your experimental parameters to Sam. "
                           "Congratulations! You have found an interesting edge case to the guardrails.")

        # convert switch address to command string
        commandString = "U0 " + str(switch[0]) + " " + str(switch[1])
        self.writeToMux(commandString)
        return 0

    def openSwitches(self, switches):
        """
        Opens a list of switches in succession after first performing a safety check to ensure that the pulse and receive
        addresses of the same transducer are not input at the same time (this directly connects the pulser to picoscope
        and will break the picoscope)

        Args:
            switches (list of address tuples) : the list of switches to be opened
        Returns:
            0 if operation successful. Raises a MuxError if an unsafe list of switches is entered
        """

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

    def setMuxConfiguration(self, mode : str, direction : str):
        """
        Changes the state of the multplexer to match the given collection mode (transmission or pulse-echo) and
        direction (forward or reverse).

        Args:
            mode (str): type of measurement (either 'transmission' or 'echo')
            direction (str): designates which transducer sends the pulse (either 'forward' or 'reverse')
        Returns:
            -1 if invalid inputs are entered
            0 if operation is successful
        """

        self.clearMux() # first make sure no other switches are open
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

    # helper function to

    def errorCheckAddresses(self, params):
        """
        A helper function to check that input mux addresses will not cause errors. Raises an exception if the picoscope
        and pulser tx channel are on the same module or if the experiment specified in params requires a component that
        has a (None, None) address.

        Args:
            params (dict) : experimental parameters dict
        Returns:
            0 if no errors are raised
        """

        # check that the receiving and pulsing transducer switches are on separate modules
        if self.t0r[0] != None and (self.t0r[0] == self.t0p[0] or self.t0r[0] == self.t1p[0]):
            raise MuxError("Unsafe combination of multiplexer addresses detected. Please ensure that the t0ReceiveSwitch is"
                           " not on the same module as any transducer pulse address.")
        if self.t1r[0] != None and (self.t1r[0] == self.t0p[0] or self.t1r[0] == self.t1p[0]):
            raise MuxError("Unsafe combination of multiplexer addresses detected. Please ensure that the t1ReceiveSwitch is"
                           " not on the same module as any transducer pulse address.")

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
        #todo: maybe delete this test? there should be duplicates in address list, so check this another way
        # addressSet = set(addressList)
        # if len(addressSet) != len(addressList):
        #     raise MuxError("The input list of addresses contains duplicates. Please ensure no two addresses share the same "
        #                    "(module, switch) numbers and try again.\n"
        #                    "If you are getting this error but there are no duplicate numbers, check that the addresses with (None, None) match the input experiment mode and direction.")

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

class MuxError(Exception):
    """
    An error class for issues relating to the multiplexer configuration and operation
    """
    pass