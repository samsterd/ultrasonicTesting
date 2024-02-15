# Interface to interact with Picoscope 2208B and collect rapid block data from a simple trigger
# Intended to replace pulse.py for ultrasonic testing
# General program flow:
# openPicoscope() -> connects to picoscope using picosdk through USB
# setupPicoMeasurement() -> takes experimental parameters and converts them to picoscope readable data, passes to scope
# collectPicoData() -> runs measurement, performs averaging, returns waveform data
# closePicoscope() -> ends connection to picoscope
# necessary data (i.e. oscilloscope handle, status) will be passed between functions as a dict called picoData
# picoData keys and values:
#   "cHandle" - c_int16 unique identifier of picoscope
#   "openUnit" - a dict containing the picoscope status returns

import ctypes
from picosdk.ps2000a import ps2000a as ps
import numpy as np
import matplotlib.pyplot as plt
import time
import math
from picosdk.functions import adc2mV, assert_pico_ok

# Function to open connection to a picoscope
# Takes no argument, it will connect to the first scope it finds if more than one is connected
# Returns a picoData dict with the cHandle and openUnit keys added
# TODO: add tests (check cHandle is generated, errors are properly raised)
def openPicoscope():

    #initialize dict for picoData
    initPicoData = {}

    #Create cHandle for referring to opened scope and add it to the data dict
    cHandle = ctypes.c_int16()

    #Open the unit with the cHandle ref. None for second argument means it will return the first scope found
    #The outcome of the operation is recorded in cHandle
    initPicoData["openUnit"] = ps.ps2000aOpenUnit(ctypes.byref(cHandle), None)

    #Print plain explanations of errors
    if cHandle == -1:
        print("Picoscope failed to open. Check that it is plugged in and not in use by another program.")
    elif cHandle == 0:
        print("No Picoscope found. Check that it is plugged in and not in use by another program.")

    #Raise errors and stop code
    assert_pico_ok(initPicoData["openUnit"])

    #Return picoData
    return initPicoData

# setupPicoMeasurement takes experimental parameters and picoData dict and converts it to picoscope-readable data
#   More specifically, this sets up a rapidBlock measurement with a simple trigger on channel A and ultrasonic data collected on channel B
# setupPicoMeasurement(delay, voltageRange, timeResolution, duration, numberToAverage, picoData)
#   picoData - dict containing picoscope info and statuses. Note that the "cHandle" key must be filled for this function to run!
#   delay - the delay, in microseconds, between receiving the trigger and starting data collection. Default is 3 us.
#   voltageRange - the maximum voltage, in V, to be read in the measurement. Default is 1 V
#       The oscilloscope has 10 discrete settings for voltage range. This script will choose the smallest range is larger than the input
#   numberOfSamples - the number of data points per waveform
#   duration - the duration of the measurement, in microseconds. Defaults to 10 us. The time interval between data points is duration / numberOfSamples
#       Note that minimum time interval for measurements with 2 channels is 2 ns
#   numberToAverage - the number of waveforms that are collected and averaged in each measurement. The default is 64
#       Higher values will increase signal to noise but at the cost of speed and memory

def setupPicoMeasurement(picoData, delay = 3, voltageRange = 1, numberOfSamples = 512, duration = 10):

    #Retrieve cHandle and make sure it is properly assigned
    cHandle = picoData["cHandle"]

    #Raise error if cHandle == 0 or -1

    #Calculate voltage range for channel B (channel A is the trigger and will be kept constant)
    #voltageLimits taken from API ps2000aSetChannel() documentation, they are hard coded in the picoscope
    voltageLimits = [0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20]

    #get the first voltage that is above the voltageRange input
    try:
        voltageLimit = next(v for v in voltageLimits if v >= voltageRange)
    # next raises StopIteration if the criteria is not met. In that case print a warning and use the maximum range
    except StopIteration:
        print("Warning: Input voltageRange is greater than the maximum Picoscope range (" + str(voltageLimits[-1]) + " V). Voltage range is set to the maximum value, but be careful not to overload the scope!")
        voltageLimit = voltageLimits[-1]

    #now get the index of the voltageLimit, which is what actually gets passed to the scope
    voltageIndex =voltageLimits.index(voltageLimit)

    # Set up channel A. Channel A is the trigger channel and is not exposed to the user for now
    # handle = chandle
    # channel = ps2000a_CHANNEL_A = 0
    # enabled = 1
    # coupling type = ps2000a_DC = 1
    # range = ps2000a_1V = 6
    # analogue offset = 0 V
    setChA = ps.ps2000aSetChannel(cHandle, 0, 1, 1, 6, 0)

    #Error check channel A
    if setChA == "PICO_OK":
        picoData["setChA"] = setChA
    else:
        print("Error: Problem connecting to picoscope channel A: " + setChA)
        #Raise error and break
        assert_pico_ok(setChA)

    #Setup channel B. B records the transducer data and its range is set by the user
    # handle = chandle
    # channel = ps2000a_CHANNEL_B = 1
    # enabled = 1
    # coupling type = ps2000a_DC = 1
    # range = ps2000a_1V = voltageIndex
    # analogue offset = 0 V
    setChB = ps.ps2000aSetChannel(cHandle, 1, 1, 1, voltageIndex, 0)

    #Error check channel B
    if setChB == "PICO_OK":
        picoData["setChB"] = setChB
    else:
        print("Error: Problem connecting to picoscope channel B: " + setChB)
        #Raise error and break
        assert_pico_ok(setChB)

    # Calculate timebase and timeInterval (in ns) by making a call to a helper function
    timebase, timeInterval = timebaseFromDurationSamples(numberOfSamples, duration)

    #TODO: add getTimebase2 call so that memory can be allocated properly
    #actually, this may need to be added to the run call rather than the set up call - i don't know if the ctypes memory allocation moves between functions?

    # Convert delay time (in us) to delay samples
    delaySamples = math.floor((delayTime * 1000) / timeInterval)

    # Setup trigger

    # Error check trigger

    # Return picoData

    return 0

#A helper function to calculation the oscilloscope timebase based on desired measurement duration and number of samples
# Inputs are the numberOfSamples and the desired duration (in us)
# Returns a timebase integer that most closely follows the input and the timeInterval that corresponds to. numberOfSamples will not change, but duration may be rounded depending on possible timebases
#Calculates based on formula in p28 of picoscope2000a API for a 1 GS/s scope with 2 channels
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
        timebase = math.floor(np.log2((10**9) * estimatedInterval))
        actualInterval = (2**timebase)
        print("Actual measurement duration for calculated timebase is " + str(numberOfSamples * actualInterval / 1000) + " us.")
        return timebase, actualInterval

    #Handle case  where estimated interval is 8 ns to 30 seconds
    elif estimatedInterval < 30000000000:

        #Repeat above protocol but use second formula on p28 of API
        timebase = math.floor((estimatedInterval * 125000000) + 2)
        actualInterval = (timebase - 2) / 125000000
        print("Actual measurement duration for calculated timebase is " + str(numberOfSamples * actualInterval / 1000) + " us.")
        return timebase, actualInterval

    #Finally handle weird case where really long time interval is requested
    else:
        print("Warning: Requested time interval is too long for picoscope. Use a stopwatch instead.")
        return (2**32)-1, 34000000000