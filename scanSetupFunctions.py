# A set of functions to run in order to set parameters for a scan
# This includes:
#   singlePulseMeasure - turns on pulser, takes a measurement with the picoscope at given parameters, outputs a plot
#   repositionEnder - connects to Ender, moves, and disconnects so that it can be positioned at the starting point of a scan
# This interface should be improved to better match setup protocols

import picosdkRapidblockPulse as pico
import ultratekPulser as utp
import enderControl as ender
import matplotlib.pyplot as plt
import numpy as np
import time


# Function to test collection parameters
# Inputs: instrument ports dict and parameter dict defined at top of script
# Outputs: Plot of pulse data received by the picoscope
# Outline: connects to pulser, picoscope, turns on pulser, sets up picoscope measurement, collects data, closes connections, plots data
def singlePulseMeasure(params):

    # Connect to picoscope
    picoConnection = pico.openPicoscope()

    # Open connection to pulser
    pulser = utp.Pulser(params['pulserType'], pulserPort = params['pulserPort'], dllFile = params['dllFile'])

    # Adjust pulser pulsewidth
    pulser.setFrequency(params['transducerFrequency'])

    # Set the number of half cycles if using tone burst pulser
    if pulser.type == 'tone burst':
        pulser.setHalfCycles(params['halfCycles'])

    # Turn on the pulser
    pulser.pulserOn()

    # Set up pico measurement
    picoConnection = pico.setupPicoMeasurement(picoConnection,
                                               params['measureDelay'],
                                               params['voltageRange'],
                                               params['samples'],
                                               params['measureTime'])

    # Run pico measurement
    voltages, times = pico.runPicoMeasurement(picoConnection, params['waves'])

    # Turn off pulser
    pulser.pulserOff()

    # Close connection to pulser and picoscope
    pulser.closePulser()
    pico.closePicoscope(picoConnection)

    # Plot data
    plt.plot(times, voltages)
    plt.xlabel('Time (us)')
    plt.ylabel('Voltage (mV)')
    plt.show()

# Helper function to connect and move the Ender
# Inputs: instrumentPorts dict, the axis to move, and the distance
def repositionEnder(params):

    # Connect to Ender
    enderConnection = ender.openEnder(params['enderPort'])

    # Move ender
    ender.moveEnder(enderConnection, params['axis'], params['distance'])

    # Close connection
    ender.closeEnder(enderConnection)
