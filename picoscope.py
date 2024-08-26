#TODO: update documentation here
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
from time import sleep
from picosdk.ps2000a import ps2000a as ps
import numpy as np
import math
from picosdk.functions import adc2mV, assert_pico_ok
import mux

# Explanation of measurement process:
# 1) Picoscope object created using experimental parameters. This establishes the connection to the picoscope
#   -> This is only run once per experiment
#   i) openPicoscope establishes connection with the instrument. This can take a second or two
# 2) For every data point within an experiment:
#   a) Picoscope.RunPicoMeasurement is called. This sorts the measurement calls based on mode and direction and calls autoRange().
#      Multiple measurements can be made at a single point if either mode or direction is set to 'both'
#      It then formats the returned data into a dict suitable for use with Database.writeData()
#   b) Picoscope.autoRange() determines whether to directly call Picoscope.runRapidBlock() or to use autoRangeFinder, calculateOffset, or optimizeGain
#       i) voltageRangeFinder() is used for mode = Transmission measurements. If finds the smallest picoscope voltage range
#          that does not cut off data. It does this by repeatedly calling runRapidBlock with different voltage ranges
#       ii) calculateOffset() is used for mode = Echo measurements. It determines the picoscope analog offset voltage that
#           centers the data around 0 V. It does this by calling runRapidBlock once and averaging the first ~50 points and setting them to zero
#       iii) optimizeGain() is used for mode = Echo measurements. It determines the optimal gain setting on the pulser to
#           get the signal maximum close to +/- 1 V without going over. It does this by repeatedly calling runRapidBlock with different gain settings
#   c) Picoscope.runRapidBlock sets up a measurement based on the input parameters and gathers the data from an individual measurement using the picoscope rapid block mode
#       i) if a multiplexer is being used, it is set to the appropriate configuration using mux.setMuxConfiguration
#       ii) setupPicoMeasurement is used to set the picoscope channels and triggers to the correct settings, as well as the pulser gain for mode = echo
#      Data is returned as two equal length numpy arrays (voltage, time)
# 3) closePicoscope is called when the experiment is finished

# Control of picoscope handled by a custom class
# Connection data is stored as class variables and connection/setup/running are handled by class functions
class Picoscope():

    # initializing object requires experimental parameters as input
    # optionally takes a pulser object as an input. This is only used when mode = echo or both and autoRange = True
    def __init__(self, params: dict, pulser = None):

        self.params = params
        self.pulser = pulser

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
    # 4) Set trigger
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
    def setupPicoMeasurement(self, mode, direction):

        #Retrieve important parameters for later use
        cHandle = self.cHandle
        measureDelay = self.params['measureDelay']
        voltageRange = self.params['voltageRange']
        self.samples = self.params['samples']
        measureTime = self.params['measureTime']

        # set mode-dependent parameters: voltageIndex and voltageOffset
        # voltageIndex: get voltage indices from input voltage ranges for transmission measurement
        #   pulse-echo should be set to 1 V (index = 6) since the signal is optimized by pulser gain instead
        # voltageOffset: 0 for transmission, params['echoOffsetDirection'] for echo
        # pulser gain is also set for pulse-echo measurements
        if mode == 'transmission':
            self.voltageIndex = self.voltageIndexFromRange(voltageRange)
            self.voltageOffset = ctypes.c_float(0)
        elif mode == 'echo':
            self.voltageIndex = 6
            if direction == 'forward':
                self.voltageOffset = ctypes.c_float(self.params['voltageOffsetForward'])
                self.pulser.setGain(self.params['gainForward'])
            else:
                self.voltageOffset = ctypes.c_float(self.params['voltageOffsetReverse'])
                self.pulser.setGain(self.params['gainReverse'])

        # calculate and save measurement parameters (timebase, timeinterval, samples, delayintervals)
        # Calculate timebase and timeInterval (in ns) by making a call to a helper function
        self.timebase, self.timeInterval = self.timebaseFromDurationSamples(self.samples, measureTime)

        # Convert delay time (in us) to delay samples
        self.delayIntervals = math.floor((measureDelay * 1000) / self.timeInterval)

        # set channels and triggers
        setErrorCheck = self.setChannels()
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

    # helper function to run ps2000aSetChannel with the data on channel A and trigger on B
    # return -1 and print error message for all other input
    def setChannels(self):

        # input for ps2000aSetChannel is as follows:
        # handle = chandle
        # channel = 0 for A, 1 for B
        # enabled = 1
        # coupling type = ps2000a_DC = 1
        # range = voltageIndex
        # analogue offset = 0 V
        # todo: look into analog offset for pulse-echo measurements
        self.setChA = ps.ps2000aSetChannel(self.cHandle, 0, 1, 1, self.voltageIndex, self.voltageOffset)
        self.setChB = ps.ps2000aSetChannel(self.cHandle, 1, 1, 1, 6, 0)
        # Input for ps2000aSetTrigger is as follow:
        # cHandle = cHandle
        # Enable = 1
        # Source = 0 for A, 1 for B
        # Note on threshold: must be greater than 1024. 10000 chosen because it works, but this will vary depending on the voltage range
        # Threshold = 10000 ADC counts
        # Direction = ps2000a_Above = 0
        # Delay = delayIntervals
        # autoTrigger_ms = 1
        self.trigger = ps.ps2000aSetSimpleTrigger(self.cHandle, 1, 1, 10000, 0, self.delayIntervals, 10)

        #error check setting channels
        if self.setChA != 0 or self.setChB != 0 or self.trigger != 0:
            print("Picoscope setChannels error: an error occurred run ps2000aSetChannel or ps2000aSetSimpleTrigger. Try restarting the program or checking the picoscope connection.")
            assert_pico_ok(self.setChA)
            assert_pico_ok(self.setChB)
            assert_pico_ok(self.trigger)
        return 0

    # runPicoMeasurement runs a rapidblock measurement on the picoscope and returns the waveform data
    # Runs measurement based on parameters in self.params. Inputs a multiplexer object, a direction, and a mode
    #   If no multiplexer is used (multiplexer = None) these inputs are ignored. Otherwise, the multiplexer is configured
    #   before running the experiment
    # Returns an array of voltages and an array of times
    def runRapidBlock(self, multiplexer = None, mode = 'transmission', direction = 'forward'):

        # configure multiplexer, if applicable
        if multiplexer != None:
            multiplexer.setMuxConfiguration(mode, direction)
            # add 1 ms sleep to ensure switches have changed
            sleep(0.001)

        # run setup first
        self.setupPicoMeasurement(mode, direction)

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
            # print("Error: Problem setting number of captures on picoscope: " + self.setCaptures)
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
        # bufferMeanB = np.mean(bufferArrayChannelB, axis = 0)

        # Make sure the picoscope is stopped
        self.stop = ps.ps2000aStop(self.cHandle)
        assert_pico_ok(self.stop)

        # # Convert waveform values from ADC to mV
        # # First find the maxADC value
        maxADC = ctypes.c_int16()
        self.maximumValue = ps.ps2000aMaximumValue(self.cHandle, ctypes.byref(maxADC))
        assert_pico_ok(self.maximumValue)

        # Then convert the mean data array from ADC to mV using the sdk function
        buffermVA = np.array(adc2mV(bufferMeanA, self.voltageIndex, maxADC))
        # buffermVB = np.array(adc2mV(bufferMeanB, self.voltageIndexT, maxADC))

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
        return buffermVA, waveTime

    # a wrapper for the runRapidBlock() and multiplexer functions that manages measurements based on direction and collectionMode
    # uses the experimental parameters saved as self.params
    # inputs a multiplexer object if params['multiplexer'] = True, otherwise defaults to None
    # outputs a dict with keys labeling the data and values being arrays of time or voltage data
    # this data dict can be fed directly into Database.writeData(dict) to save data
    def runPicoMeasurement(self, multiplexer = None):

        # if a multiplexer is not provided, assume default mode = transmission and direction = forward
        if multiplexer != None:
            collectionMode = self.params['collectionMode']
            direction = self.params['collectionDirection']
        else:
            collectionMode = 'transmission'
            direction = 'forward'

        returnDict = {}

        # match all cases of collectionMode and direction
        # while some of these are redundant and could be combined, it is better to separate them for clarity
        match collectionMode:
            case 'transmission':
                match direction:
                    case 'forward':
                        # we will break the naming conventions for the transmission forward case to maintain backward compatibility
                        voltage, waveTime = self.autoRange(multiplexer, collectionMode, direction)
                        returnDict['voltage'] = voltage
                        returnDict['time'] = waveTime
                        return returnDict
                    case 'reverse':
                        voltage, waveTime = self.autoRange(multiplexer, collectionMode, direction)
                        returnDict['voltage_transmission_reverse'] = voltage
                        returnDict['time'] = waveTime
                        return returnDict
                    case 'both':
                        voltagef, waveTimef = self.autoRange(multiplexer, collectionMode, 'forward')
                        voltager, waveTimer = self.autoRange(multiplexer, collectionMode, 'reverse')
                        returnDict['voltage_transmission_forward'] = voltagef
                        returnDict['voltage_transmission_reverse'] = voltager
                        returnDict['time'] = waveTimef  # waveTime is constant for either measurement, so choice is arbitrary
                        return returnDict
                    case _:
                        print(
                            "Invalid collection direction. Make sure collectionDirection is set to 'forward', 'reverse', or 'both' and retry.")
                        return None
            case 'echo':
                match direction:
                    case 'forward':
                        voltage, waveTime = self.autoRange(multiplexer, collectionMode, direction)
                        returnDict['voltage_echo_forward'] = voltage
                        returnDict['time'] = waveTime
                        return returnDict
                    case 'reverse':
                        voltage, waveTime = self.autoRange(multiplexer, collectionMode, direction)
                        returnDict['voltage_echo_reverse'] = voltage
                        returnDict['time'] = waveTime
                        return returnDict
                    case 'both':
                        voltagef, waveTimef = self.autoRange(multiplexer, collectionMode, 'forward')
                        voltager, waveTimer = self.autoRange(multiplexer, collectionMode, 'reverse')
                        returnDict['voltage_echo_forward'] = voltagef
                        returnDict['voltage_echo_reverse'] = voltager
                        returnDict['time'] = waveTimef
                        return returnDict
                    case _:
                        print(
                            "Invalid collection direction. Make sure collectionDirection is set to 'forward', 'reverse', or 'both' and retry.")
                        return None
            case 'both':
                match direction:
                    case 'forward':
                        voltaget, waveTimet = self.autoRange(multiplexer, 'transmission', direction)
                        voltagee, waveTimer = self.autoRange(multiplexer, 'echo', direction)
                        returnDict['voltage_echo_forward'] = voltagee
                        returnDict['voltage_transmission_forward'] = voltaget
                        returnDict['time'] = waveTimet
                        return returnDict
                    case 'reverse':
                        voltaget, waveTimet = self.autoRange(multiplexer, 'transmission', direction)
                        voltagee, waveTimer = self.autoRange(multiplexer, 'echo', direction)
                        returnDict['voltage_echo_reverse'] = voltagee
                        returnDict['voltage_transmission_reverse'] = voltaget
                        returnDict['time'] = waveTimet
                        return returnDict
                    case 'both':
                        voltagetf, waveTimetf = self.autoRange(multiplexer, 'transmission', 'forward')
                        voltageef, waveTimeef = self.autoRange(multiplexer, 'echo', 'forward')
                        voltagetr, waveTimetr = self.autoRange(multiplexer, 'transmission', 'reverse')
                        voltageer, waveTimeer = self.autoRange(multiplexer, 'echo', 'reverse')
                        returnDict['voltage_transmission_forward'] = voltagetf
                        returnDict['voltage_echo_forward'] = voltageef
                        returnDict['voltage_transmission_reverse'] = voltagetr
                        returnDict['voltage_echo_reverse'] = voltageer
                        returnDict['time'] = waveTimetf
                        return returnDict
                    case _:
                        print(
                            "Invalid collection direction. Make sure collectionDirection is set to 'forward', 'reverse', or 'both' and retry.")
                        return None
            case _:
                print(
                    "Invalid collection mode. Make sure collectionMode is set to 'transmission', 'echo', or 'both' and retry.")
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
            # print("Actual measurement duration for calculated timebase is " + str(numberOfSamples * actualInterval / 1000) + " us.")
            return timebase, actualInterval

        #Handle case  where estimated interval is 8 ns to 30 seconds
        elif estimatedInterval < 30000000000:

            #Repeat above protocol but use second formula on p28 of API
            #Large numbers convert between seconds and nanoseconds and back again
            timebase = math.floor((125000000 * (estimatedInterval * (10**-9))) + 2)
            actualInterval = (10**9) * (timebase - 2) / 125000000
            # print("Actual measurement duration for calculated timebase is " + str(numberOfSamples * actualInterval / 1000) + " us.")
            return timebase, actualInterval

        #Finally handle weird case where really long time interval is requested
        else:
            print("Warning: Requested time interval is too long for picoscope. Use a stopwatch instead.")
            return (2**32)-1, 34000000000

    # a wrapper function to call the appropriate auto range function (if any)
    def autoRange(self, multiplexer, mode, direction):

        autoRangeTrans = self.params['autoRange']
        autoRangeEcho = self.params['autoRangeEcho']

        if (mode == 'transmission' and not autoRangeTrans) or (mode == 'echo' and not autoRangeEcho):
            return self.runRapidBlock(multiplexer, mode, direction)

        elif mode == 'transmission':
            return self.voltageRangeFinder(multiplexer, direction)

        elif mode == 'echo':
            return self.optimizeEchoRange(multiplexer, direction)
        else:
            print("Picoscope.autoRange(): unable to run auto range function. An incorrect mode (" + str(mode) + ") was likely specified during execution.\nRunning without auto range...")
            return self.runRapidBlock(multiplexer, mode, direction)

    # helper function that calculates the baseline of a given voltage array for the purposes of specifying a new voltage offset
    # inputs measurement direction string, the voltage array, and the number of points to average to calculate the baseline from
    # the beginning of the voltage array
    # offset calculated by finding the mean of the first pointsToAverage points within the voltage array
    # Updates the values of the class variables self.baseline and self.params['voltageOffsetForward/Reverse'
    # returns the calculated offset
    def calculateVoltageOffset(self, direction : str, voltage, pointsToAverage = 50):

        # baseline is added to the measured values in picoscope, so -1* is needed to center at 0
        baseline = -1* np.mean(voltage[0:pointsToAverage])/1000

        # set the new voltageOffset based on its change from the old one
        # must be converted to mV
        if direction == 'forward':
            newOffset = self.params['voltageOffsetForward'] + baseline
            self.baseline = baseline
            self.params['voltageOffsetForward'] = newOffset
        elif direction == 'reverse':
            newOffset = self.params['voltageOffsetReverse'] + baseline
            self.baseline = baseline
            self.params['voltageOffsetReverse'] = newOffset
        else:
            print("Picoscope.measureVoltageOffset: invalid direction (" + str(
                direction) + "). Check Pico.RunPicoMeasurement call to debug.")
            return -1

        return baseline

    # function that finds acceptable gain and baseline correction values for pulse-echo measurements
    # First determines the optimal voltage offset
    # Next determines whether the gain should be changed.
    #   If yes, a gain optimization protocol is run
    #       Since this can change the baseline, it rechecks if the offset is outside of tolerance. If yes, the whole protocol is
    #       recursively rerun. If the baseline is acceptable, the voltage, time with optimal gain is returned
    #   If the gain is acceptable, the voltage, time from the baseline optimization is returned
    # inputs:
    #   multiplexer object and experiment direction
    #   baselineTolerance: amount of V the baseline can drift from 0 before the baseline is recalculated
    #   baselinePoints: number of points in the beginning of the wave to average when calculating baseline
    #   minV, maxV: the target range in mV of the wave maximum. If it is outside this range, gain and baseline are remeasured until within tolerance
    # outputs the voltage, time arrays collected at the optimal conditions
    def optimizeEchoRange(self, multiplexer, direction : str, baselineTolerance=0.05, baselinePoints=50, minV=400, maxV=920):

        # run initial measurement, calculate new offset (this will alter the offset of the next measurement in a scan/repeat pulse)
        voltage, time = self.optimizeOffset(multiplexer,  direction, baselineTolerance, baselinePoints)

        # determine whether to run optimizeGain i.e. the offset wave is outside of [minV, maxV]
        voltageMax = np.max(abs(voltage))
        if voltageMax < minV or voltageMax > maxV:
            voltageG, timeG = self.optimizeGain(multiplexer, direction, minV, maxV)

            # if the offset is now outside of tolerance, the whole protocol should be rerun
            # this will rerun the offset optimization and, if needed, the gain optimization
            # note conversion from V to mV
            if abs(self.baseline) > baselineTolerance:
                return self.optimizeEchoRange(multiplexer, direction, baselineTolerance, baselinePoints, minV, maxV)

            # otherwise the new measurement is good
            return voltageG, timeG

        # gain did not need to be optimized, return values from offset optimization
        return voltage, time

    # function that recursively runs runRapidBlock until the calculated baseline is within a set tolerance
    # inputs:
    #   multiplexer object and experiment direction
    #   baselineTolerance: amount of mV the baseline can drift from 0 before the baseline is recalculated
    #   baselinePoints: number of points in the beginning of the wave to average when calculating baseline
    # returns the voltage, time arrays collected within the baselineTolerance
    def optimizeOffset(self, multiplexer, direction, baselineTolerance, baselinePoints):

        # run initial measurement and update offsets
        voltage, time = self.runRapidBlock(multiplexer, 'echo', direction)
        self.calculateVoltageOffset(direction, voltage, baselinePoints)

        # base case: offset is within tolerance, so return the data
        if abs(self.baseline) < baselineTolerance:
            return voltage, time

        # recursive case: offset is outside of tolerance, so rerun the function
        else:
            return self.optimizeOffset(multiplexer, direction, baselineTolerance, baselinePoints)
        # todo: handle error where requested offset is out of possible ranges

    # maximizes the echo signal by changing the gain on the pulser
    # The pulser limits the signal to +/- 1 V. Gain settings are -120 to 840
    # optimizeGain takes the direction, and a target min and max voltage as arguments
    # it runs the measurement until the maximum of the signal is above the minV and below maxV
    # Also alters the baseline offset as a function of the new gain
    # Returns the voltage, time at the optimal setting
    def optimizeGain(self, multiplexer, direction, minV = 400, maxV = 920):

        if direction == 'forward':
            gain = self.params['gainForward']
            offset = self.params['voltageOffsetForward']
        else:
            gain = self.params['gainReverse']
            offset = self.params['voltageOffsetReverse']

        self.pulser.setGain(gain)
        voltage, time = self.runRapidBlock(multiplexer, 'echo', direction)

        # adjust offset as well for next measurement
        self.calculateVoltageOffset(direction, voltage)

        absMax = np.max(abs(voltage))

        # base case 1: minV <= absMax <= maxV -> success! return values
        if absMax <= maxV and absMax >= minV:
            return voltage, time

        # base case 2: absMax > maxV and gain = minGain: print warning and return values
        elif absMax > maxV and gain == self.pulser.minGain:
            print("Picoscope.optimizeGain Warning: signal voltage exceeds tolerance and gain is set to minimum. Voltage returned, but values are likely to be cut off.")
            return voltage, time

        # base case 3: absMax < minV and gain = maxGain: print warning and return values
        elif absMax < minV and gain == self.pulser.maxGain:
            print("Picoscope.optimizeGain Warning: signal voltage is below threshold and gain is set to max. Voltage returned, but may have low signal to noise.")
            return voltage, time

        # recursion case: absMax not within [minV, maxV]: set a new gain guess, rerun
        elif absMax < minV or absMax > maxV:
            newGain = self.guessGain(gain, absMax, minV, maxV)
            if direction == 'forward':
                self.params['gainForward'] = newGain
            else:
                self.params['gainReverse'] = newGain
            return self.optimizeGain(multiplexer, direction, minV, maxV)

        # this case should not be possible
        else:
            print("HOW DID YOU GET HERE? THIS SHOULD NOT BE HOW NUMBERS WORK.\n"
                  "Also you should notify Sam and show him the parameters.")
            return -1

    # helper function to guess a reasonable new value for gain based on the current settings and measurement
    def guessGain(self, currentGain, measuredV, minV, maxV):

        # gain values are tenth of decibels (so hundredths of a power of ten)
        # using MeasuredVoltage = ActualVoltage * (10**currentGain/100) and using that to calculate gain needed to reach minV
        # NewGain = 100log10(MinV/MeasuredV) + CurrentGain
        # 50 is added to this value ensure the new value is slightly over minV since this method seems to systematically underestimate
        if measuredV < minV:
            newGain = (100 * np.log10(minV/measuredV)) + currentGain + 50
        # for voltages over the maximum, it is harder to generate an accurate guess since the value is cut off above 1 V
        # for now just guess -10 dB
        else:
            newGain = currentGain - 100

        # make sure the new gain does not exceed the gain limits
        if newGain > self.pulser.maxGain:
            return self.pulser.maxGain
        elif newGain < self.pulser.minGain:
            return self.pulser.minGain
        else:
            # gain needs to be an int, so ceil is used
            return math.ceil(newGain)


    # Recursively determines the minimum voltage range needed to capture data at the current location
    # Returns the waveform data at the proper range
    # Inputs a multiplexer object and direction. If no multiplexer is used, default to None
    # This should only add extra time if the voltage range has changed from the previous pixel
    # NOTE: this is only defined for transmission measurements. mode is implicitly 'transmission' when this is called
    def voltageRangeFinder(self, multiplexer = None, direction = 'forward'):

        # hardcoded voltage limits
        voltageLimits = np.array([0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20])

        # hardcoded tolerance limit - change limit if max is within 5%
        tolerance = 0.95
        voltageTolerances = tolerance * voltageLimits

        currentLimit = self.params['voltageRange']
        currentTolerance = tolerance * currentLimit

        # collect initial waveform and find maximum. Convert to mV
        voltage, time = self.runRapidBlock(multiplexer, 'transmission', direction)
        maxV = np.max(voltage)/1000

        # base case 1 : currentLimit == lowest limit and max < current limit. return waveform
        if currentLimit == voltageLimits[0] and maxV < currentLimit:
            return voltage, time

        # base case 2 : currentLimit == highest limit and max > highest tolerance. return waveform and print a warning
        elif currentLimit == voltageLimits[-1] and maxV >= currentTolerance:
            print(
                "Warning: voltageRangeFinder- waveform voltage exceeds oscilloscope maximum. Peaks are likely to be cutoff.")
            return voltage, time

        # base case 3 : max < current limit. set voltage range to be lowest range within tolerance, rerun measurement and return waveform
        elif maxV <= currentTolerance:

            # return index of first (lowest) tolerance that is >= maxV
            # taking [0][0] of the result is safe since maxV < currentTolerance implies the condition is met at least once
            rangeIndex = np.nonzero(voltageTolerances >= maxV)[0][0]
            limit = voltageLimits[rangeIndex]

            # if that tolerance is the current tolerance, return waveform, params
            if limit == currentLimit:
                return voltage, time

            # if not, setup a new measurement with the tighter voltage limit and return that data
            else:
                self.params['voltageRange'] = limit
                return self.runRapidBlock(multiplexer, 'transmission', direction)

        # recursion case : max > current tolerance. try again at the next highest voltage limit
        else:

            # get the index of the current limit
            rangeIndex = np.nonzero(voltageLimits == currentLimit)[0][0]

            # just for safety, check that range index is not the last index. this shouldn't be possible, but just in case I'm missing an edge case
            if rangeIndex == len(voltageLimits) - 1:
                return voltage, time

            # move to the next higher voltage limit and try again
            else:
                self.params['voltageRange'] = voltageLimits[rangeIndex + 1]
                return self.voltageRangeFinder(multiplexer, direction)
            
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
                    try:
                        # first try to handle case of forward transmission only, which uses 'voltage' as the key for backward compatibility
                        return np.max(waveDict['voltage'])/1000
                    except KeyError:
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
