#
# Copyright (C) 2018 Pico Technology Ltd. See LICENSE file for terms.
#
# ps2000a RAPID BLOCK MODE EXAMPLE
# This example opens a 3000a driver device, sets up one channel and a trigger then collects 10 block of data in rapid succession.
# This data is then plotted as mV against time in ns.

import ctypes
from picosdk.ps2000a import ps2000a as ps
import numpy as np
import matplotlib.pyplot as plt
import time
from picosdk.functions import adc2mV, assert_pico_ok

startTime = time.time()

# Create chandle and status ready for use
status = {}
chandle = ctypes.c_int16()

# Opens the device/s
status["openunit"] = ps.ps2000aOpenUnit(ctypes.byref(chandle), None)
assert_pico_ok(status["openunit"])

connectTime = time.time()
print("Connect Time")
print(connectTime - startTime)

# Set up channel A
# handle = chandle
# channel = ps2000a_CHANNEL_A = 0
# enabled = 1
# coupling type = ps2000a_DC = 1
# range = ps2000a_1V = 6
# analogue offset = 0 V
chARange = 6
status["setChA"] = ps.ps2000aSetChannel(chandle, 0, 1, 1, chARange, 0)
assert_pico_ok(status["setChA"])

# Sets up single trigger
# andle = chandle
# Enable = 1
# Source = ps2000a_channel_A = 0
# Threshold = 1024 ADC counts
# Direction = ps2000a_Falling = 3
# Delay = 0
# autoTrigger_ms = 1000
status["trigger"] = ps.ps2000aSetSimpleTrigger(chandle, 1, 0, 1024, 3, 0, 1)
assert_pico_ok(status["trigger"])

# Setting the number of sample to be collected
preTriggerSamples = 0
postTriggerSamples = 1000
maxsamples = preTriggerSamples + postTriggerSamples

# Gets timebase innfomation
# WARNING: When using this example it may not be possible to access all Timebases as all channels are enabled by default when opening the scope.
# To access these Timebases, set any unused analogue channels to off.
# handle = chandle
# Timebase = 2 = timebase
# Nosample = maxsamples
# TimeIntervalNanoseconds = ctypes.byref(timeIntervalns)
# MaxSamples = ctypes.byref(returnedMaxSamples)
# Segement index = 0
timebase = 3
timeIntervalns = ctypes.c_float()
returnedMaxSamples = ctypes.c_int16()
status["GetTimebase"] = ps.ps2000aGetTimebase2(chandle, timebase, maxsamples, ctypes.byref(timeIntervalns), 1, ctypes.byref(returnedMaxSamples), 0)
assert_pico_ok(status["GetTimebase"])

# Creates a overlow location for data
overflow = ctypes.c_int16()
# Creates converted types maxsamples
cmaxSamples = ctypes.c_int32(maxsamples)

# Handle = Chandle
# nSegments = 64
# nMaxSamples = ctypes.byref(cmaxSamples)

numberOfSamples = 1000

status["MemorySegments"] = ps.ps2000aMemorySegments(chandle, numberOfSamples, ctypes.byref(cmaxSamples))
assert_pico_ok(status["MemorySegments"])

# sets number of captures
status["SetNoOfCaptures"] = ps.ps2000aSetNoOfCaptures(chandle, numberOfSamples)
assert_pico_ok(status["SetNoOfCaptures"])

# Starts the block capture
# handle = chandle
# Number of prTriggerSamples
# Number of postTriggerSamples
# Timebase = 2 = 4ns (see Programmer's guide for more information on timebases)
# time indisposed ms = None (This is not needed within the example)
# Segment index = 0
# LpRead = None
# pParameter = None
status["runblock"] = ps.ps2000aRunBlock(chandle, preTriggerSamples, postTriggerSamples, timebase, 0, None, 0, None, None)
assert_pico_ok(status["runblock"])

# TODO: use a 2D array instead of dicts for performance
bufferAMax = {}
bufferAMin = {}

for sample in range(numberOfSamples):
    bufferAMax[sample] = (ctypes.c_int16 * maxsamples)()
    bufferAMin[sample] = (ctypes.c_int16 * maxsamples)() # used for downsampling which isn't in the scope of this example
    # Setting the data buffer location for data collection from channel A
    # handle = chandle
    # source = ps2000a_channel_A = 0
    # Buffer max = ctypes.byref(bufferAMax)
    # Buffer min = ctypes.byref(bufferAMin)
    # Buffer length = maxsamples
    # Segment index = sample
    # Ratio mode = ps2000a_Ratio_Mode_None = 0
    status["SetDataBuffers"] = ps.ps2000aSetDataBuffers(chandle, 0, ctypes.byref(bufferAMax[sample]), ctypes.byref(bufferAMin[sample]), maxsamples, sample, 0)

# Creates a overlow location for data
overflow = (ctypes.c_int16 * numberOfSamples)()
# Creates converted types maxsamples
cmaxSamples = ctypes.c_int32(maxsamples)

# Checks data collection to finish the capture
ready = ctypes.c_int16(0)
check = ctypes.c_int16(0)
while ready.value == check.value:
    status["isReady"] = ps.ps2000aIsReady(chandle, ctypes.byref(ready))

# handle = chandle
# noOfSamples = ctypes.byref(cmaxSamples)
# fromSegmentIndex = 0
# ToSegmentIndex = numberOfSamples - 1
# DownSampleRatio = 0
# DownSampleRatioMode = 0
# Overflow = ctypes.byref(overflow)

status["GetValuesBulk"] = ps.ps2000aGetValuesBulk(chandle, ctypes.byref(cmaxSamples), 0, numberOfSamples - 1, 0, 0, ctypes.byref(overflow))
assert_pico_ok(status["GetValuesBulk"])

# handle = chandle
# Times = Times = (ctypes.c_int16*numberOfSamples)() = ctypes.byref(Times)
# Timeunits = TimeUnits = ctypes.c_char() = ctypes.byref(TimeUnits)
# Fromsegmentindex = 0
# Tosegementindex = numberOfSamples - 1
Times = (ctypes.c_int64*numberOfSamples)()
TimeUnits = ctypes.c_char()
status["GetValuesTriggerTimeOffsetBulk"] = ps.ps2000aGetValuesTriggerTimeOffsetBulk64(chandle, ctypes.byref(Times), ctypes.byref(TimeUnits), 0, numberOfSamples - 1)
assert_pico_ok(status["GetValuesTriggerTimeOffsetBulk"])

measureTime = time.time()
print("Measure Time")
print(measureTime - connectTime)

# Finds the max ADC count
# handle = chandle
# Value = ctype.byref(maxADC)
maxADC = ctypes.c_int16()
status["maximumValue"] = ps.ps2000aMaximumValue(chandle, ctypes.byref(maxADC))
assert_pico_ok(status["maximumValue"])

buffermV = np.zeros((numberOfSamples, maxsamples))
# Converts ADC from channel A to mV
# Because adc2mV returns a python list, we can convert the values to a large array rather than use a dict of c-arrays
for sample in range(numberOfSamples):
    buffermV[sample, :] = np.array(adc2mV(bufferAMax[sample], chARange, maxADC))

# for averaging, use array.mean(axis = 0)
bufferMean = np.mean(buffermV, axis = 0)

# Creates the time data
# RENAME THIS VARIABLE, DONT HAVE Times AND times IN THE SAME SCRIPT
times = np.linspace(0, (cmaxSamples.value - 1) * timeIntervalns.value, cmaxSamples.value)

processTime = time.time()
print("Processing time")
print(processTime - measureTime)

# Plot the averaged data
plt.plot(times, bufferMean)
plt.xlabel('Time (ns)')
plt.ylabel('Voltage (mV)')
plt.show()

# Plots the data from channel A onto a graph
# plt.plot(time, adc2mVChAMax[:])
# plt.plot(time, adc2mVChAMax1[:])
# plt.plot(time, adc2mVChAMax2[:])
# plt.plot(time, adc2mVChAMax3[:])
# plt.plot(time, adc2mVChAMax4[:])
# plt.plot(time, adc2mVChAMax5[:])
# plt.plot(time, adc2mVChAMax6[:])
# plt.plot(time, adc2mVChAMax7[:])
# plt.plot(time, adc2mVChAMax8[:])
# plt.plot(time, adc2mVChAMax9[:])
# plt.xlabel('Time (ns)')
# plt.ylabel('Voltage (mV)')
# plt.show()



# Stops the scope
# Handle = chandle
status["stop"] = ps.ps2000aStop(chandle)
assert_pico_ok(status["stop"])

# Closes the unit
# Handle = chandle
status["close"] = ps.ps2000aCloseUnit(chandle)
assert_pico_ok(status["close"])

# Displays the staus returns
print(status)