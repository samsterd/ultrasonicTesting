# UPGRADE PLAN
# Goal is to implement pulse-echo mode while also updating the code
# Install picoSDK locally
#   this part sucks
#   verify with hardware first before overhauling!
#
# First overhaul: set up oscilloscope class Picoscope
#   picoData dict should be stored as class variables(o)
#   functions should be class functions (o)
#   openPicoscope and setupPicoMeasurement should be taken over by the __init__ function(o)
#       __init__ should take the experimental params dict from runUltrasonicExperiment as an input(o)
#   runPicoMeasurement should be a class function that also takes the params dict as an argument(o)
#   closePicoscope should be implemented as a class function as well(o)
#   Replace all previous picoscope functions in other files with the new implementation, test it
#       these will be in scanSetupFunctions(o), repeatPulse(o), and ultrasonicScan(o)
#   wish list:
#       better error handling
#           currently sending errors through assert_pico_ok which raises assertion errors when something breaks
#           these should be handled through a popup window in the GUI in the executeExperiment windows
#       better handling of timebase/experiment time interconversion

# Next: refactor code to enable pulse-echo mode
#   need to read oscilloscope documentation to verify 300V pulse is safe!
#   rewire things
#       trigger goes to same channel, but need a BNC junction to connect pulser TX to transducer and picoscope
#   (if possible) collect data from the trigger channel A
#       allocate memory buffers for channel A data
#       allow option of collecting transmission, pulse-echo, or both
#   add pulse-echo to interface
#       add option to params dict
#       add to GUI (relevant experiment windows as well as executeExperiment functions)

# Interface to interact with Picoscope 2208B and collect rapid block data from a simple trigger
# Intended to replace pulse.py for ultrasonic testing
# General program flow:
# openPicoscope() -> connects to picoscope using picosdk through USB
# setupPicoMeasurement() -> takes experimental parameters and converts them to picoscope readable data, opens measurement channels and sets triggers
# runPicoMeasurement() -> runs rapidblock measurement, performs averaging, returns waveform data
# closePicoscope() -> ends connection to picoscope
# necessary data (i.e. oscilloscope handle, status) will be passed between functions as a dict called picoData
# picoData keys and values:
#   "cHandle" - c_int16 unique identifier of picoscope
#   "openUnit" - a dict containing the picoscope status returns

import ctypes
import time
from picosdk.ps2000a import ps2000a as ps
import numpy as np
import math
from picosdk.functions import adc2mV, assert_pico_ok
import matplotlib.pyplot as plt


# Control of picoscope handled by a custom class
# Connection data is stored as class variables and connection/setup/running are handled by class functions
# TODO: add tests (check cHandle is generated, errors are properly raised)
class Picoscope():

    # initializing object requires experimental parameters as input
    #TODO: setup function needs to be moved outside of init since it may need to be called multiple times
    def __init__(self,params: dict):

        self.params = params

        self.openPicoscope()
        # self.setupPicoMeasurement(measureDelay, voltageRangeT, voltageRangeP, samples, measureTime, collectionDirection)

    # opens connection to the picoscope, generates cHandle
    def openPicoscope(self):

        #initialize dict for picoData
        initPicoData = {}

        #Create cHandle for referring to opened scope
        self.cHandle = ctypes.c_int16()

        #Open the unit with the cHandle ref. None for second argument means it will return the first scope found
        #The outcome of the operation is recorded in cHandle
        self.openUnit = ps.ps2000aOpenUnit(ctypes.byref(self.cHandle), None)

        #Print plain explanations of errors
        if self.cHandle == -1:
            print("Picoscope failed to open. Check that it is plugged in and not in use by another program.")
        elif self.cHandle == 0:
            print("No Picoscope found. Check that it is plugged in and not in use by another program.")

        #Raise errors and stop code
        assert_pico_ok(self.openUnit)

    # setupPicoMeasurement takes experimental parameters and picoData dict and converts it to picoscope-readable data
    #   More specifically, this sets up a measurement with a simple trigger on channel A and ultrasonic data collected on channel B
    #       ps2000aSetChannel is run for both channels, the timebase is calculated, and ps2000aSetSimpleTrigger is run. Statuses are recorded in picoData
    # setupPicoMeasurement(delay, voltageRange, timeResolution, duration, numberToAverage, picoData)
    #   picoData - dict containing picoscope info and statuses. Note that the "cHandle" key must be filled for this function to run!
    #   measureDelay - the delay, in microseconds, between receiving the trigger and starting data collection. Default is 3 us.
    #   voltageRange - the maximum voltage, in V, to be read in the measurement. Default is 1 V
    #       The oscilloscope has 10 discrete settings for voltage range. This script will choose the smallest range is larger than the input
    #   samples - the number of data points per waveform
    #   measureTime - the duration of the measurement, in microseconds. Defaults to 10 us. The time interval between data points is duration / numberOfSamples
    #       Note that minimum time interval for measurements with 2 channels is 2 ns

    # * part of process that needs to be changed to run on arbitrary channels
    #SETUP PROCESS
    # 1) Set voltage limits (convert voltage to voltage index)
    # x*2) Run setchannel functions
    # 3) Calculate timebase, delay intervals
    # x*4) Set trigger
    #RUN PROCESS
    # 5) Create pointers/memory buffers
    #   a) Number of Samples
    #   b) overflow
    #   c) data buffers
    # 6) Divide memory segments, set number of captures, connect data buffers to pico memory
    # 7) Run rapid block
    # 8) Get values
    # 9) Post processing (mean, convert to voltage, generate time axis)
    # *10) Return, delete buffers
    #   a) will need to start return a list of voltages instead of a single voltage
    #   b) database code needs to handle a list of arrays passed into it. Add labels when multiple voltages returned. Add collection mode to params list
    # How to do it:
    #   have a 'directionality' parameter with options 'forward' 'reverse' 'both'
    #   use 'collectionMode' and 'directionality' to assign which channel is transmission and which is echo
    #       -for directionality == 'both' it needs to run twice - maybe have that as a wrapper to setup/run? or implement in experiment function at higher abstraction?
    #    (time setup function) make setup part of run, not init
    def setupPicoMeasurement(self,  direction = 'forward'):

        #Retrieve important parameters for later use
        cHandle = self.cHandle
        measureDelay = self.params['measureDelay']
        voltageRangeT = self.params['voltageRangeT']
        voltageRangeP = self.params['voltageRangeP']
        self.samples = self.params['samples']
        measureTime = self.params['measureTime']

        # get voltage indices from input voltage ranges
        self.voltageIndexT = self.voltageIndexFromRange(voltageRangeT)
        self.voltageIndexP = self.voltageIndexFromRange(voltageRangeP)

        # calculate and save measurement parameters (timebase, timeinterval, samples, delayintervals)
        # Calculate timebase and timeInterval (in ns) by making a call to a helper function
        self.timebase, self.timeInterval = self.timebaseFromDurationSamples(self.samples, measureTime)

        # Convert delay time (in us) to delay samples
        self.delayIntervals = math.floor((measureDelay * 1000) / self.timeInterval)

        # set channels and triggers based on collectionMode and direction
        setErrorCheck = self.setChannels(direction)
        if setErrorCheck == -1:
            assert_pico_ok(self.setChA)

    # helper function to convert an input voltage range to the index used in setChannel()
    def voltageIndexFromRange(self, voltageRange):

        # voltageLimits taken from API ps2000aSetChannel() documentation, they are hard coded in the picoscope
        voltageLimits = [0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20]

        try:
            # get the first voltage that is above the voltageRange input
            voltageLimit = next(v for v in voltageLimits if v >= voltageRange)
        # next raises StopIteration if the criteria is not met. In that case print a warning and use the maximum range
        except StopIteration:
            print("Warning: Input voltageRange is greater than the maximum Picoscope range (" + str(voltageLimits[-1]) + " V). Voltage range is set to the maximum value, but be careful not to overload the scope!")
            voltageLimit = voltageLimits[-1]

        # now get the index of the voltageLimit, which is what actually gets passed to the scope
        # Note that this is 1-indexed rather than 0, so +1 is added
        voltageIndex = voltageLimits.index(voltageLimit) + 1

        return voltageIndex

    # helper function to run ps2000aSetChannel appropriately depending on the input direction
    # Inputs direction, which is either 'forward' or 'reverse'
    # forward: A is pulser, B is transmission receiver
    # reverse: B is pulser, A is transmission receiver
    # trigger is set on the pulser channel
    # return -1 and print error message for all other input
    def setChannels(self, direction : str):

        # input for ps2000aSetChannel is as follows:
        # handle = chandle
        # channel = 0 for A, 1 for B
        # enabled = 1
        # coupling type = ps2000a_DC = 1
        # range = voltageIndex
        # analogue offset = 0 V
        # Input for ps2000aSetTrigger is as follow:
        # cHandle = cHandle
        # Enable = 1
        # Source = 0 for A, 1 for B
        # Note on threshold: must be greater than 1024. 10000 chosen because it works, but this will vary depending on the voltage range
        # Threshold = 10000 ADC counts
        # Direction = ps2000a_Above = 0
        # Delay = delayIntervals
        # autoTrigger_ms = 1
        if direction == 'forward':
            self.setChA = ps.ps2000aSetChannel(self.cHandle, 0, 1, 1, self.voltageIndexP, 0)
            self.setChB = ps.ps2000aSetChannel(self.cHandle, 1, 1, 1, self.voltageIndexT, 0)
            self.trigger = ps.ps2000aSetSimpleTrigger(self.cHandle, 1, 0, 10000, 0, self.delayIntervals, 10)
        elif direction == 'reverse':
            self.setChA = ps.ps2000aSetChannel(self.cHandle, 0, 1, 1, self.voltageIndexT, 0)
            self.setChB = ps.ps2000aSetChannel(self.cHandle, 1, 1, 1, self.voltageIndexP, 0)
            self.trigger = ps.ps2000aSetSimpleTrigger(self.cHandle, 1, 1, 10000, 0, self.delayIntervals, 10)
        else:
            print("Picoscope setChannels error: input direction is \"" + direction + "\" but only \"forward\" and \"reverse\" are accepted.")
            return -1

        #error check setting channels
        if self.setChA != 'PICO_OK' or self.setChB != 'PICO_OK' or self.trigger != 'PICO_OK':
            print("Picoscope setChannels error: an error occurred run ps2000aSetChannel or ps2000aSetSimpleTrigger. Try restarting the program or checking the picoscope connection.")
            assert_pico_ok(self.setChA)
            assert_pico_ok(self.setChB)
            assert_pico_ok(self.trigger)
        return 0

    # runPicoMeasurement runs a rapidblock measurement on the picoscope and returns the waveform data
    #   Inputs are the picoData dict. Note that setupPicoMeasurement must have been run or the dict will not have necessary fields informed and errors will occur
    #   Second input is the number of waveforms to collect in rapid block. Choosing a larger number will result in more waves to average,
    #       but may use up memory. The Picoscope2208B has 64MS buffer memory w/ 2 channels, meaning it can store ~64000 waves with 1000 samples/wave
    #   Returns a numpy array of the average of the numberOfWaves
    def runRapidBlock(self,  direction = 'forward'):

        # run setup first
        self.setupPicoMeasurement(direction)

        #TODO: add error checking here, need to assert that all necessary self.picoData fields are informed
        #these include: cHandle, timebase, numberOfSamples, all channel and trigger statuses
        #Gather important parameters from self.picoData dict
        cHandle = self.cHandle
        timebase = self.timebase
        samples = self.samples
        numberOfWaves = self.params['waves']

        #Create a c type for numberOfSamples that can be passed to the ps2000a functions
        cNumberOfSamples = ctypes.c_int32(self.samples)

        #Create overflow . Note: overflow is a flag for whether overvoltage occured on a given channel during measurement
        #For 2 channel measurements, each channel needs an overflow flag so we allocate 2 * numberOfWaves
        overflow = (ctypes.c_int16 * numberOfWaves )()

        #Divide picoscope memory into segments for rapidblock capture(Important)
        memorySegments = ps.ps2000aMemorySegments(self.cHandle, numberOfWaves, ctypes.byref(cNumberOfSamples))
        assert_pico_ok(memorySegments)

        #Set the number of captures (=wavesToCollect) on the picoscope
        self.setCaptures = ps.ps2000aSetNoOfCaptures(self.cHandle, numberOfWaves)

        #Error check set captures
        if self.setCaptures == "PICO_OK":
            pass
        else:
            print("Error: Problem setting number of captures on picoscope: " + self.setCaptures)
            assert_pico_ok(self.setCaptures)

        #Set up memory buffers to receive data from channel B
        bufferArrayChannelB = np.empty((numberOfWaves, self.samples), dtype = ctypes.c_int16)
        #Convert bufferArrayChannelB to a ctype
        bufferArrayChannelBCtype = np.ctypeslib.as_ctypes(bufferArrayChannelB)

        #Set up memory buffers for channel A.
        bufferArrayChannelA = np.empty((numberOfWaves, self.samples), dtype = ctypes.c_int16)
        bufferArrayChannelACtype = np.ctypeslib.as_ctypes(bufferArrayChannelA)

        # bufferArrayChannelBPointer = bufferArrayChannelB.ctypes.data_as(c_int16_pointer)
        for wave in range(numberOfWaves):
            # bufferArrayChannelB[wave] = (ctypes.c_int16 * numberOfSamples)()
            # dataPointer = bufferArrayChannelB[wave].ctypes.data_as(c_int16_pointer)
            # Setting the data buffer location for data collection from channel B
            # handle = chandle
            # source = ps2000a_channel_B = 1
            # Buffer location = ctypes.byref(bufferArrayChannelB[wave])
            # Buffer length = numberOfSampless
            # Segment index = wave
            # Ratio mode = ps2000a_Ratio_Mode_None = 0 (we are not downsampling)
            waveC = ctypes.c_uint32(wave)
            dataBufferB = ps.ps2000aSetDataBuffer(self.cHandle, 1, ctypes.byref(bufferArrayChannelBCtype[wave]), self.samples, waveC, 0)
            assert_pico_ok(dataBufferB)
            dataBufferA = ps.ps2000aSetDataBuffer(self.cHandle, 0, ctypes.byref(bufferArrayChannelACtype[wave]), self.samples, waveC, 0)
            assert_pico_ok(dataBufferA)

        # Start block capture
        # handle = cHandle
        # Number of prTriggerSamples = 0
        # Number of postTriggerSamples = numberOfSamples
        # Timebase = timebase
        # Oversample is not used (0)
        # time indisposed ms = None (This is not needed)
        # Segment index = 0 (start at beginning of memory)
        # LpReady = None (not used)
        # pParameter = None (not used)
        self.runblock = ps.ps2000aRunBlock(self.cHandle, 0, self.samples, self.timebase, 0, None, 0, None, None)
        #TODO: add better error handling
        assert_pico_ok(self.runblock)

        #Wait until data collection is finished
        ready = ctypes.c_int16(0)
        check = ctypes.c_int16(0)
        while ready.value == check.value:
            ps.ps2000aIsReady(self.cHandle, ctypes.byref(ready))

        # Retrieve values from picoscope
        # handle = cHandle
        # noOfSamples = ctypes.byref(cNumberOfSamples)
        # fromSegmentIndex = 0
        # ToSegmentIndex = numberOfWaves - 1
        # DownSampleRatio = 0
        # DownSampleRatioMode = 0
        # Overflow = ctypes.byref(overflow)
        self.getValuesBulk = ps.ps2000aGetValuesBulk(self.cHandle, ctypes.byref(cNumberOfSamples), 0, (numberOfWaves)-1, 0, 0, ctypes.byref(overflow))
        assert_pico_ok( self.getValuesBulk)

        #Calculate the average of the waveform values stored in the buffer
        bufferMeanA = np.mean(bufferArrayChannelA, axis = 0)
        bufferMeanB = np.mean(bufferArrayChannelB, axis = 0)

        # Make sure the picoscope is stopped
        self.stop = ps.ps2000aStop(self.cHandle)
        assert_pico_ok(self.stop)

        # # Convert waveform values from ADC to mV
        # # First find the maxADC value
        maxADC = ctypes.c_int16()
        self.maximumValue = ps.ps2000aMaximumValue(self.cHandle, ctypes.byref(maxADC))
        assert_pico_ok(self.maximumValue)

        # Then convert the mean data array from ADC to mV using the sdk function
        buffermVA = np.array(adc2mV(bufferMeanA, self.voltageIndexP, maxADC))
        buffermVB = np.array(adc2mV(bufferMeanB, self.voltageIndexT, maxADC))

        #Create the time data (i.e. the x-axis) using the time intervals, numberOfSamples, and delay time
        timeInterval = self.timeInterval
        startTime = self.delayIntervals * timeInterval
        stopTime = startTime + (timeInterval * (self.samples - 1))
        waveTime = np.linspace(startTime, stopTime, self.samples)

        #Might need to free up memory for longer scans by deleting the buffer arrays
        # this is probably handled by python garbage collection and is unnecessary
        del bufferArrayChannelB
        del bufferArrayChannelA

        # return data all data
        return buffermVA, buffermVB, waveTime

    # a wrapper for the runRapidBlock() function that manages calls and returns
    # uses the experimental parameters saved as self.params, so it requires no inputs
    # outputs a dict with keys labeling the data and values being arrays of time or voltage data
    # todo: create a wrapper function for the runpico function
    # needs to take in parameters, run self.runRapidBlock() appropriately (i.e. double for direction = 'both')
    # then sort how the data is returned based on collectionMode and collectionDirection
    # return all data as a list of arrays and also add a list of strings that label the data?
    def runPicoMeasurement(self):

        collectionMode = self.params['collectionMode']
        direction = self.params['collectionDirection']
        returnDict = {}

        # match all cases of collectionMode and direction
        # while some of these are redundant and could be combined, it is better to separate them for clarity
        match collectionMode:
            case 'transmission':
                match direction:
                    case 'forward':
                        buffermVA, buffermVB, waveTime = self.runRapidBlock(direction)
                        returnDict['voltage_transmission_forward'] = buffermVB
                        returnDict['time'] = waveTime
                        return returnDict
                    case 'reverse':
                        buffermVA, buffermVB, waveTime = self.runRapidBlock(direction)
                        returnDict['voltage_transmission_reverse'] = buffermVA
                        returnDict['time'] = waveTime
                        return returnDict
                    case 'both':
                        buffermVAf, buffermVBf, waveTimef = self.runRapidBlock('forward')
                        buffermVAr, buffermVBr, waveTimer = self.runRapidBlock('reverse')
                        returnDict['voltage_transmission_forward'] = buffermVBf
                        returnDict['voltage_transmission_reverse'] = buffermVAr
                        returnDict['time'] = waveTimef  # waveTime is constant for either measurement, so choice is arbitrary
                        return returnDict
                    case _:
                        print(
                            "Invalid collection direction. Make sure collectionDirection is set to 'forward', 'reverse', or 'both' and retry.")
                        return None
            case 'pulse-echo':
                match direction:
                    case 'forward':
                        buffermVA, buffermVB, waveTime = self.runRapidBlock(direction)
                        returnDict['voltage_echo_forward'] = buffermVA
                        returnDict['time'] = waveTime
                        return returnDict
                    case 'reverse':
                        buffermVA, buffermVB, waveTime = self.runRapidBlock(direction)
                        returnDict['voltage_echo_reverse'] = buffermVB
                        returnDict['time'] = waveTime
                        return returnDict
                    case 'both':
                        buffermVAf, buffermVBf, waveTimef = self.runRapidBlock('forward')
                        buffermVAr, buffermVBr, waveTimer = self.runRapidBlock('reverse')
                        returnDict['voltage_echo_forward'] = buffermVAf
                        returnDict['voltage_echo_reverse'] = buffermVBr
                        returnDict['time'] = waveTimef
                        return returnDict
                    case _:
                        print(
                            "Invalid collection direction. Make sure collectionDirection is set to 'forward', 'reverse', or 'both' and retry.")
                        return None
            case 'both':
                match direction:
                    case 'forward':
                        buffermVA, buffermVB, waveTime = self.runRapidBlock(direction)
                        returnDict['voltage_echo_forward'] = buffermVA
                        returnDict['voltage_transmission_forward'] = buffermVB
                        returnDict['time'] = waveTime
                        return returnDict
                    case 'reverse':
                        buffermVA, buffermVB, waveTime = self.runRapidBlock(direction)
                        returnDict['voltage_echo_reverse'] = buffermVB
                        returnDict['voltage_transmission_reverse'] = buffermVA
                        returnDict['time'] = waveTime
                        return returnDict
                    case 'both':
                        buffermVAf, buffermVBf, waveTimef = self.runRapidBlock('forward')
                        buffermVAr, buffermVBr, waveTimer = self.runRapidBlock('reverse')
                        returnDict['voltage_echo_forward'] = buffermVAf
                        returnDict['voltage_transmission_forward'] = buffermVBf
                        returnDict['voltage_echo_reverse'] = buffermVBr
                        returnDict['voltage_transmission_reverse'] = buffermVAr
                        returnDict['time'] = waveTimef
                        return returnDict
                    case _:
                        print(
                            "Invalid collection direction. Make sure collectionDirection is set to 'forward', 'reverse', or 'both' and retry.")
                        return None
            case _:
                print(
                    "Invalid collection mode. Make sure collectionMode is set to 'transmission', 'pulse-echo', or 'both' and retry.")
                return None, None


    #ends the connection to the picoscope
    #Input: picoData with the cHandle field filled
    #Returns picoData with the "close" field informed
    def closePicoscope(self):
        self.close = ps.ps2000aCloseUnit(self.cHandle)
        assert_pico_ok(self.close)

    #A helper function to calculation the oscilloscope timebase based on desired measurement duration and number of samples
    # Inputs are the numberOfSamples and the desired duration (in us)
    # Returns a timebase integer that most closely follows the input and the timeInterval that corresponds to. numberOfSamples will not change, but duration may be rounded depending on possible timebases
    #Calculates based on formula in p28 of picoscope2000a API for a 1 GS/s scope with 2 channels
    @staticmethod
    def timebaseFromDurationSamples(numberOfSamples, duration):

        #First calculate a naive time interval (in ns) of measurement based on the inputs
        estimatedInterval = duration * 1000 / numberOfSamples

        #First handle cases where specified timeInterval is shorter than possible so the minimum timebase is used
        if estimatedInterval < 2:
            actualInterval = 2
            print("Warning: Requested time interval is too short for picoscope. Defaulting to minimum timebase for 2 channels (2 ns)")
            print("Actual measurement duration for this timebase is " + str(numberOfSamples * actualInterval / 1000) + " us.")
            return 1, actualInterval

        #Next handle intervals less than 8 ns, which use a different formula
        elif estimatedInterval < 8:

            #calculate the nearest timebase using the formulate base = floor(log2 (10**9 * interval))
            #math.floor is used instead of np.floor to make it return an int not a float
            timebase = math.floor(np.log2(estimatedInterval))
            actualInterval = (2**timebase)
            print("Actual measurement duration for calculated timebase is " + str(numberOfSamples * actualInterval / 1000) + " us.")
            return timebase, actualInterval

        #Handle case  where estimated interval is 8 ns to 30 seconds
        elif estimatedInterval < 30000000000:

            #Repeat above protocol but use second formula on p28 of API
            #Large numbers convert between seconds and nanoseconds and back again
            timebase = math.floor((125000000 * (estimatedInterval * (10**-9))) + 2)
            actualInterval = (10**9) * (timebase - 2) / 125000000
            print("Actual measurement duration for calculated timebase is " + str(numberOfSamples * actualInterval / 1000) + " us.")
            return timebase, actualInterval

        #Finally handle weird case where really long time interval is requested
        else:
            print("Warning: Requested time interval is too long for picoscope. Use a stopwatch instead.")
            return (2**32)-1, 34000000000

    # Recursively determines the minimum voltage range needed to capture data at the current location
    # Returns the waveform data at the proper rang and the updated params dict
    # This should only add extra time if the voltage range has changed from the previous pixel
    # NOTE: this only works for the transmission voltage currently
    def voltageRangeFinder(self):

        # hardcoded voltage limits
        voltageLimits = np.array([0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20])

        # hardcoded tolerance limit - change limit if max is within 5%
        tolerance = 0.95
        voltageTolerances = tolerance * voltageLimits

        currentLimit = self.params['voltageRangeT']
        currentTolerance = tolerance * currentLimit

        # collect initial waveform and find maximum
        waveDict = self.runPicoMeasurement()
        maxV = self.transmissionMaximum(waveDict)

        # base case 1 : currentLimit == lowest limit and max < current limit. return waveform
        if currentLimit == voltageLimits[0] and maxV < currentLimit:
            return waveDict

        # base case 2 : currentLimit == highest limit and max > highest tolerance. return waveform and print a warning
        elif currentLimit == voltageLimits[-1] and maxV >= currentTolerance:
            print(
                "Warning: voltageRangeFinder- waveform voltage exceeds oscilloscope maximum. Peaks are likely to be cutoff.")
            return waveDict

        # base case 3 : max < current limit. set voltage range to be lowest range within tolerance, rerun measurement and return waveform, params
        elif maxV <= currentTolerance:

            # return index of first (lowest) tolerance that is >= maxV
            # taking [0][0] of the result is safe since maxV < currentTolerance implies the condition is met at least once
            rangeIndex = np.nonzero(voltageTolerances >= maxV)[0][0]
            limit = voltageLimits[rangeIndex]

            # if that tolerance is the current tolerance, return waveform, params
            if limit == currentLimit:
                return waveDict

            # if not, setup a new measurement with the tighter voltage limit and return that data
            else:
                self.params['voltageRangeT'] = limit
                waveform = self.runPicoMeasurement()
                return waveform

        # recursion case : max > current tolerance. try again at the next highest voltage limit
        else:

            # get the index of the current limit
            rangeIndex = np.nonzero(voltageLimits == currentLimit)[0][0]

            # just for safety, check that range index is not the last index. this shouldn't be possible, but just in case I'm missing a case
            if rangeIndex == len(voltageLimits) - 1:
                return waveDict

            # move to the next higher voltage limit and try again
            else:
                self.params['voltageRangeT'] = voltageLimits[rangeIndex + 1]
                return self.voltageRangeFinder()
            
    # helper function that finds the maximum voltage from transmission data
    # inputs the dict returned from running runPicoMeasurement()
    # returns the max value in mV
    def transmissionMaximum(self, waveDict):
        
        # determine the key string for the transmission voltage
        mode = self.params['collectionMode']
        direction = self.params['collectionDirection']
        
        if mode == 'pulse-echo':
            return -1 # no transmission data collected
        
        else:
            match direction:
                case 'forward':
                    return np.max(waveDict['voltage_transmission_forward'])/1000
                case 'reverse':
                    return np.max(waveDict['voltage_transmission_reverse'])/1000
                case 'both':
                    return np.max(np.array([
                        np.max(waveDict['voltage_transmission_forward'])/1000,
                        np.max(waveDict['voltage_transmission_reverse'])/1000
                    ]))
                case _:
                    print("transmissionMaximum error: not able to identify transmission data. Unclear how this happened. Check "
                          "collectionMode and collectionDirection and try again.")
                    return -1





############################################
####Example scripts########
#Collect ultrasonic pulses in water with 5 MHz transducers
# testData = {}
# testData = openPicoscope()
# testData = setupPicoMeasurement(testData, 15, 0.1, 1000, 1 )
# startMeasure = time.time()
# testY, testX = runPicoMeasurement(testData, 1000)
# stopMeasure = time.time()
# print(str(stopMeasure - startMeasure))
# plt.plot(testX, testY)
# plt.show()
# closePicoscope(testData)

# # #test collecting multiple data sets from one setup
# testData = {}
# testData = openPicoscope()
# testData = setupPicoMeasurement(testData, 3, 0.1, 1000, 10 )
# startMeasure = time.time()
# testY, testX = runPicoMeasurement(testData, 8)
# stopMeasure = time.time()
# print(str(stopMeasure - startMeasure))
# plt.plot(testX, testY)
# startMeasure = time.time()
# testY1, testX1 = runPicoMeasurement(testData, 5000)
# stopMeasure = time.time()
# print(str(1000 * (stopMeasure - startMeasure)))
# # plt.plot(testX1, testY1)
# # plt.show()
# closePicoscope(testData)
#
# #get timing data
# sampleSizes = [1, 8, 64, 100, 1000, 5000]
# timingData = {}
# testData = openPicoscope()
# testData = setupPicoMeasurement(testData, 3, 0.1, 1000, 10)
# # Do one initial measurement because the first has a large overhead
# runPicoMeasurement(testData, 8)
# for i in sampleSizes:
#     timeList = np.array([])
#     for j in range(50):
#         startMeasure = time.time()
#         runPicoMeasurement(testData, i)
#         stopMeasure = time.time()
#         timeList = np.append(timeList, 1000 * (stopMeasure - startMeasure))
#     print("Timing data for " + str(i) + " samples: " + str(np.mean(timeList)) + " +/- " + str(np.std(timeList)) + " ms")
#     timingData[i] = timeList
# closePicoscope(testData)
