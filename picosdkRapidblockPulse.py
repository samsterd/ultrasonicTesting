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
class picosdkRapidblockPulse():

    # initializing object requires experimental parameters as input
    def __init__(self,params: dict):

        measureDelay = params['measureDelay']
        voltageRangeT = params['voltageRangeT']
        voltageRangeP = params['voltageRangeP']
        samples = params['samples']
        measureTime = params['measureTime']
        self.openPicoscope()
        self.setupPicoMeasurement(measureDelay, voltageRangeT, voltageRangeP, samples, measureTime)

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

    def setupPicoMeasurement(self, measureDelay = 3, voltageRangeT = 1, voltageRangeP = 1,samples = 512, measureTime = 10):

        #Retrieve cHandle and make sure it is properly assigned
        cHandle = self.cHandle

        #Raise error if cHandle == 0 or -1
        # (this was not implemented...)

        #Calculate voltage range for channel B (channel A is the trigger and will be kept constant)
        #voltageLimits taken from API ps2000aSetChannel() documentation, they are hard coded in the picoscope
        voltageLimits = [0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20]

        # checking the voltage range for transmission
        #get the first voltage that is above the voltageRange input
        try:
            voltageLimitT = next(v for v in voltageLimits if v >= voltageRangeT)
        # next raises StopIteration if the criteria is not met. In that case print a warning and use the maximum range
        except StopIteration:
            print("Warning: Input voltageRange is greater than the maximum Picoscope range (" + str(voltageLimits[-1]) + " V). Voltage range is set to the maximum value, but be careful not to overload the scope!")
            voltageLimitT = voltageLimits[-1]

        #now get the index of the voltageLimit, which is what actually gets passed to the scope
        # Note that this is 1-indexed rather than 0, so +1 is added
        voltageIndexT =voltageLimits.index(voltageLimitT) + 1
        self.voltageIndexT = voltageIndexT

        # checking the voltage range for pulse-echo
        # get the first voltage that is above the voltageRange input
        try:
            voltageLimitP = next(v for v in voltageLimits if v >= voltageRangeP)
        # next raises StopIteration if the criteria is not met. In that case print a warning and use the maximum range
        except StopIteration:
            print("Warning: Input voltageRange is greater than the maximum Picoscope range (" + str(voltageLimits[-1]) + " V). Voltage range is set to the maximum value, but be careful not to overload the scope!")
            voltageLimitP = voltageLimits[-1]

        # now get the index of the voltageLimit, which is what actually gets passed to the scope
        # Note that this is 1-indexed rather than 0, so +1 is added
        voltageIndexP = voltageLimits.index(voltageLimitP) + 1
        self.voltageIndexP = voltageIndexP
        #Channel A is used for pulse-echo
        #edit the voltageRange def for setchanel could get input as like channel B

        # Set up channel A. Channel A is the trigger channel and is not exposed to the user for now
        # handle = chandle
        # channel = ps2000a_CHANNEL_A = 0
        # enabled = 1
        # coupling type = ps2000a_DC = 1
        # range = ps2000a_1V = 6==>voltageIndexP
        # analogue offset = 0 V
        setChA = ps.ps2000aSetChannel(cHandle, 0, 1, 1, voltageIndexP, 0)

        #Error check channel A
        if setChA == "PICO_OK":
            self.setChA = setChA
        else:
            # print("Error: Problem connecting to picoscope channel A: " + setChA)
            #Raise error and break
            assert_pico_ok(setChA)

        #Setup channel B. B records the transducer data and its range is set by the user
        # handle = chandle
        # channel = ps2000a_CHANNEL_B = 1
        # enabled = 1
        # coupling type = ps2000a_DC = 1
        # range = ps2000a_1V = voltageIndexT
        # analogue offset = 0 V
        setChB = ps.ps2000aSetChannel(cHandle, 1, 1, 1, voltageIndexT, 0)

        #Error check channel B
        if setChB == "PICO_OK":
            self.setChB = setChB
        else:
            # print("Error: Problem connecting to picoscope channel B: " + setChB)
            #Raise error and break
            assert_pico_ok(setChB)

        # calculate and save measurement parameters (timebase, timeinterval, samples, delayintervals)
        # Calculate timebase and timeInterval (in ns) by making a call to a helper function
        self.timebase, self.timeInterval = self.timebaseFromDurationSamples(samples, measureTime)
        self.samples = samples

        # Convert delay time (in us) to delay samples
        self.delayIntervals = math.floor((measureDelay * 1000) / self.timeInterval)

            # Setup trigger on channel A
            # cHandle = cHandle
            # Enable = 1
            # Source = ps2000a_channel_A = 0
            # Note on threshold: must be greater than 1024. 10000 chosen because it works, but this will vary depending on the voltage range
            # Threshold = 10000 ADC counts
            # Direction = ps2000a_Above = 0
            # Delay = delayIntervals
            # autoTrigger_ms = 1
        trigger = ps.ps2000aSetSimpleTrigger(cHandle, 1, 0, 10000, 0, self.delayIntervals, 100)
        #
        # # Set up channel A. Channel A is the trigger channel and is not exposed to the user for now
        # # handle = chandle
        # # channel = ps2000a_CHANNEL_A = 0
        # # enabled = 0 Off
        # # coupling type = ps2000a_DC = 1
        # # range = ps2000a_1V = 6 --> (upated)voltageIndex
        # # analogue offset = 0 V
        # setChA = ps.ps2000aSetChannel(cHandle, 0, 1, 1, voltageIndex, 0)
        #
        # #Error check channel A
        # if setChA == "PICO_OK":
        #     self.picoData["setChA"] = setChA
        # else:
        #     # print("Error: Problem connecting to picoscope channel A: " + setChA)
        #     #Raise error and break
        #     assert_pico_ok(setChA)
        #
        # #Setup channel B. B records the transducer data and its range is set by the user
        # # handle = chandle
        # # channel = ps2000a_CHANNEL_B = 1
        # # enabled = 1
        # # coupling type = ps2000a_DC = 1
        # # range = ps2000a_1V = voltageIndex
        # # analogue offset = 0 V
        # setChB = ps.ps2000aSetChannel(cHandle, 1, 1, 1, voltageIndex, 0)
        #
        # #Error check channel B
        # if setChB == "PICO_OK":
        #     self.picoData["setChB"] = setChB
        # else:
        #     # print("Error: Problem connecting to picoscope channel B: " + setChB)
        #     #Raise error and break
        #     assert_pico_ok(setChB)

        # Calculate timebase and timeInterval (in ns) by making a call to a helper function
        # timebase, timeInterval = self.timebaseFromDurationSamples(samples, measureTime)
        # #Record timebase, timeInterval and numberOfSamples in picoData
        # self.picoData["timebase"] = timebase
        # self.picoData["timeInterval"] = timeInterval
        # self.picoData["samples"] = samples
        #
        # # Convert delay time (in us) to delay samples
        # delayIntervals = math.floor((measureDelay * 1000) / timeInterval)
        # self.picoData["delayIntervals"] = delayIntervals

        # Setup trigger on channel B
        # cHandle = cHandle
        # Enable = 1
        # Source = ps2000a_channel_B = 0
        # Note on threshold: must be greater than 1024. 10000 chosen because it works, but this will vary depending on the voltage range
        # Threshold = 10000 ADC counts
        # Direction = ps2000a_Above = 0
        # Delay = delayIntervals
        # autoTrigger_ms = 1
        # trigger = ps.ps2000aSetSimpleTrigger(cHandle, 1, 1, 10000, 0, delayIntervals, 100)

        # Error check trigger
        if trigger == "PICO_OK":
            self.trigger = trigger
        else:
            # print("Error: Problem setting trigger on channel A: " + trigger)
            #Raise error and break
            assert_pico_ok(self.trigger)

        # TODO: separate everything below (running the measurement) into a separate function?
        #  #add getTimebase2 call so that memory can be allocated properly
        # actually, this may need to be added to the run call rather than the set up call - i don't know if the ctypes memory allocation moves between functions?
        # self.class_picoData = self.picoData

    # runPicoMeasurement runs a rapidblock measurement on the picoscope and returns the waveform data
    #   Inputs are the picoData dict. Note that setupPicoMeasurement must have been run or the dict will not have necessary fields informed and errors will occur
    #   Second input is the number of waveforms to collect in rapid block. Choosing a larger number will result in more waves to average,
    #       but may use up memory. The Picoscope2208B has 64MS buffer memory w/ 2 channels, meaning it can store ~64000 waves with 1000 samples/wave
    #   Returns a numpy array of the average of the numberOfWaves
    def runPicoMeasurement(self, numberOfWaves = 64, collectionMode = 'transmission'):

        #TODO: add error checking here, need to assert that all necessary self.picoData fields are informed
        #these include: cHandle, timebase, numberOfSamples, all channel and trigger statuses
        #Gather important parameters from self.picoData dict
        cHandle = self.cHandle
        timebase = self.timebase
        samples = self.samples

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

        # return data based on experiment type
        match collectionMode:
            case 'transmission':
                return buffermVB, waveTime
            case 'pulse-echo':
                return buffermVA, waveTime
            case 'both':
                return buffermVA, buffermVB, waveTime
            case _:
                print("Invalid collection mode. Make sure collectionMode is set to 'transmission', 'pulse-echo', or 'both' and retry.")
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
    def voltageRangeFinder(self, params : dict):

        # hardcoded voltage limits
        voltageLimits = np.array([0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20])

        # hardcoded tolerance limit - change limit if max is within 5%
        tolerance = 0.95
        voltageTolerances = tolerance * voltageLimits

        currentLimit = params['voltageRangeT']
        currentTolerance = tolerance * currentLimit

        # collect initial waveform
        waveform = self.runPicoMeasurement(params['waves'],params['collectionMode'])

        # find max of the waveform, divide by 1000 to convert to V
        maxV = np.max(abs(waveform[0])) / 1000

        # base case 1 : currentLimit == lowest limit and max < current limit. return waveform
        if currentLimit == voltageLimits[0] and maxV < currentLimit:
            return waveform, params

        # base case 2 : currentLimit == highest limit and max > highest tolerance. return waveform and print a warning
        elif currentLimit == voltageLimits[-1] and maxV >= currentTolerance:
            print(
                "Warning: voltageRangeFinder- waveform voltage exceeds oscilloscope maximum. Peaks are likely to be cutoff.")
            return waveform, params

        # base case 3 : max < current limit. set voltage range to be lowest range within tolerance, rerun measurement and return waveform, params
        elif maxV <= currentTolerance:

            # return index of first (lowest) tolerance that is >= maxV
            # taking [0][0] of the result is safe since maxV < currentTolerance implies the condition is met at least once
            rangeIndex = np.nonzero(voltageTolerances >= maxV)[0][0]
            limit = voltageLimits[rangeIndex]

            # if that tolerance is the current tolerance, return waveform, params
            if limit == currentLimit:
                return waveform, params

            # if not, setup a new measurement with the tighter voltage limit and return that data
            else:
                params['voltageRangeT'] = limit
                self.setupPicoMeasurement(
                    params['measureDelay'],
                    params['voltageRangeT'],
                    params['voltageRangeP'],
                    params['samples'],
                    params['measureTime'])
                waveform = self.runPicoMeasurement(params['waves'],params['collectionMode'])
                return waveform, params

        # recursion case : max > current tolerance. try again at the next highest voltage limit
        else:

            # get the index of the current limit
            rangeIndex = np.nonzero(voltageLimits == currentLimit)[0][0]

            # just for safety, check that range index is not the last index. this shouldn't be possible, but just in case I'm missing a case
            if rangeIndex == len(voltageLimits) - 1:
                return waveform, params

            # move to the next higher voltage limit and try again
            else:
                params['voltageRangeT'] = voltageLimits[rangeIndex + 1]
                self.setupPicoMeasurement(params['measureDelay'],
                                                           params['voltageRangeT'],
                                                           params['voltageRangeP'],
                                                           params['samples'],
                                                           params['measureTime'])
                return self.voltageRangeFinder(params)





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
