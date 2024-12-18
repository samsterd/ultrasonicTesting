# A set of functions to run in order to set parameters for a scan
# This includes:
#   singlePulseMeasure - turns on pulser, takes a measurement with the picoscope at given parameters, outputs a plot
#   repositionEnder - connects to Ender, moves, and disconnects so that it can be positioned at the starting point of a scan
# This interface should be improved to better match setup protocols
import ultratekPulser as utp
import scanner as sc
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import time
import picoscope as picoscope
import mux


# Function to test collection parameters
# Inputs: instrument ports dict and parameter dict defined at top of script
# Outputs: Plot of pulse data received by the picoscope
# Outline: connects to pulser, picoscope, turns on pulser, sets up picoscope measurement, collects data, closes connections, plots data
def singlePulseMeasure(params):

    # if not using GUI, set matplotlib backend to 'Tk'
    # TODO: this is done for compatibility with the linux computer, but Qt5 SHOULD work there too...
    if params['gui'] == False:
        matplotlib.use('TkAgg')

    # connect to multiplexer, if applicable
    if params['multiplexer']:
        multiplexer = mux.Mux(params)
    else:
        multiplexer = None

    # Open connection to pulser
    pulser = utp.Pulser(params['pulserType'], pulserPort=params['pulserPort'], dllFile=params['dllFile'])

    # Connect to picoscope & Set up pico measurement
    pico = picoscope.Picoscope(params, pulser)

    # Adjust pulser pulsewidth
    pulser.setFrequency(params['transducerFrequency'])

    # Set the number of half cycles if using tone burst pulser
    if pulser.type == 'tone burst':
        pulser.setHalfCycles(params['halfCycles'])

    # Turn on the pulser
    pulser.pulserOn()

    waveDict = pico.runPicoMeasurement(multiplexer)

    # Turn off pulser
    pulser.pulserOff()

    # Close connection to pulser, picoscope, and multiplexer
    pulser.closePulser()
    pico.closePicoscope()
    if params['multiplexer']:
        multiplexer.closeMux()

    if params['gui']:
        return waveDict
    else:
        plotWaveDict(waveDict)

# helper function to plot the waveDict returned by runPicoMeasurement()
# handles arbitrary number of y-value keys, assumed x-axis is 'time'
def plotWaveDict(waveDict):

    time = waveDict['time']
    fig, ax = plt.subplots()
    for voltageKey in waveDict.keys():
        # this isn't the best way to only select voltage keys but it works for now
        if 'voltage' in voltageKey and 'Offset' not in voltageKey:
            ax.plot(time, waveDict[voltageKey], label = voltageKey)

    plt.xlabel('Time (us)')
    plt.ylabel('Voltage (mV)')
    plt.legend()
    plt.show()

# Helper function to connect to and move the scanner
# Inputs the parameters dict, which must contain the scannerPort, axis, and distance keys
def moveScanner(params):

    scanner = sc.Scanner(params)
    moveRes = scanner.move(params['axis'], params['distance'])
    scanner.close()
    return moveRes

# Recursively determines the minimum voltage range needed to capture data at the current location
# Returns the waveform data at the proper rang and the updated params dict
# This should only add extra time if the voltage range has changed from the previous pixel
# def voltageRangeFinder(params):
#
#     # hardcoded voltage limits
#     voltageLimits = np.array([0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20])
#
#     # hardcoded tolerance limit - change limit if max is within 5%
#     tolerance = 0.95
#     voltageTolerances = tolerance * voltageLimits
#
#     currentLimit = params['voltageRange']
#     currentTolerance = tolerance * currentLimit
#
#     # collect initial waveform
#     waveform = pico.runPicoMeasurement(params['waves'])
#
#     # find max of the waveform, divide by 1000 to convert to V
#     maxV = np.max(abs(waveform[0]))/1000
#
#     # base case 1 : currentLimit == lowest limit and max < current limit. return waveform
#     if currentLimit == voltageLimits[0] and maxV < currentLimit:
#         return waveform, params
#
#     # base case 2 : currentLimit == highest limit and max > highest tolerance. return waveform and print a warning
#     elif currentLimit == voltageLimits[-1] and maxV >= currentTolerance:
#         print("Warning: voltageRangeFinder- waveform voltage exceeds oscilloscope maximum. Peaks are likely to be cutoff.")
#         return waveform, params
#
#     # base case 3 : max < current limit. set voltage range to be lowest range within tolerance, rerun measurement and return waveform, params
#     elif maxV <= currentTolerance:
#
#         # return index of first (lowest) tolerance that is >= maxV
#         # taking [0][0] of the result is safe since maxV < currentTolerance implies the condition is met at least once
#         rangeIndex = np.nonzero(voltageTolerances >= maxV)[0][0]
#         limit = voltageLimits[rangeIndex]
#
#         # if that tolerance is the current tolerance, return waveform, params
#         if limit == currentLimit:
#             return waveform, params
#
#         # if not, setup a new measurement with the tighter voltage limit and return that data
#         else:
#             params['voltageRange'] = limit
#             picoConnection = pico.setupPicoMeasurement(
#                                                params['measureDelay'],
#                                                params['voltageRange'],
#                                                params['samples'],
#                                                params['measureTime'])
#             waveform = pico.runPicoMeasurement(params['waves'])
#             return waveform, params
#
#     # recursion case : max > current tolerance. try again at the next highest voltage limit
#     else:
#
#         # get the index of the current limit
#         rangeIndex = np.nonzero(voltageLimits == currentLimit)[0][0]
#
#         # just for safety, check that range index is not the last index. this shouldn't be possible, but just in case I'm missing a case
#         if rangeIndex == len(voltageLimits) - 1:
#             return waveform, params
#
#         # move to the next higher voltage limit and try again
#         else:
#             params['voltageRange'] = voltageLimits[rangeIndex + 1]
#             picoConnection = pico.setupPicoMeasurement(params['measureDelay'],
#                                                        params['voltageRange'],
#                                                        params['samples'],
#                                                        params['measureTime'])
#             return voltageRangeFinder(params)