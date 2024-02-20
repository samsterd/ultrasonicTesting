# A set of functions to run in order to set parameters for a scan
# This includes:
#   singlePulseMeasure - turns on pulser, takes a measurement with the picoscope at given parameters, outputs a plot
#   repositionEnder - connects to Ender, moves, and disconnects so that it can be positioned at the starting point of a scan
# This interface should be improved to better match setup protocols

import picosdkRapidblockPulse as pico
import ultratekPulser as pulser
import enderControl as ender
import matplotlib.pyplot as plt
import numpy as np
import time

# Controls whether the script runs a pulse, moves the ender, or both
# Ender is moved before the pulse is run!
controlParams = {
    'moveEnder' : False,   # Should the Ender be moved when the script is executed
    'runPulse' : False     # Should a single pulse be collected when the script is executed
}

#Names of ports the pulser and ender are connected to
instrumentPorts = {
    'pulserPort' : 'COM2',#Ultratek pulser port name
    'enderPort' : 'COM3'  #Ender port name
}

#Parameters for moving the ender
enderParams = {
    'axis' : 'X',      #Axis to move ender
    'distance' : 1     #Distance in mm to move ender
}

#Parameters for collecting data with the picoscope
picoParams = {
    'measureTime' : 2,   #Approx measurement time, in us
    'measureDelay' : 15, #Approx delay after trigger to start measuring, in us
    'voltageRange' : 0.1,#Picoscope data range
    'waves' : 1000,      #Number of waves to collect and average
    'samples': 1000      #Number of data points per wave
}


# Function to test collection parameters
# Inputs: instrument ports dict and parameter dict defined at top of script
# Outputs: Plot of pulse data received by the picoscope
# Outline: connects to pulser, picoscope, turns on pulser, sets up picoscope measurement, collects data, closes connections, plots data
def singlePulseMeasure(ports, params):

    # Connect to pulser
    pulserConnection = pulser.openPulser(instrumentPorts['pulserPort'])

    # Connect to picoscope
    picoConnection = pico.openPicoscope()

    # Turn on the pulser
    pulser.pulserOn(pulserConnection)

    # Set up pico measurement
    picoConnection = pico.setupPicoMeasurement(picoConnection,
                                               picoParams['measureDelay'],
                                               picoParams['voltageRange'],
                                               picoParams['samples'],
                                               picoParams['measureTime'])

    # Run pico measurement
    times, voltages = pico.runPicoMeasurement(picoConnection, picoParams['waves'])

    # Turn off pulser
    pulser.pulserOff(pulserConnection)

    # Close connection to pulser and picoscope
    pulser.closePulser(pulserConnection)
    pico.closePicoscope(picoConnection)

    # Plot data
    plt.plot(times, voltages)
    plt.xlabel('Time (us)')
    plt.ylabel('Voltage (mV)')
    plt.show()

    return 0

# Helper function to connect and move the Ender
# Inputs: instrumentPorts dict, the axis to move, and the distance
def repositionEnder(ports, params):

    # Connect to Ender
    enderConnection = ender.openEnder(ports['enderPort'])

    # Move ender
    ender.moveEnder(enderConnection, params['axis'], params['distance'])

    # Close connection
    ender.closeEnder(enderConnection)

    return 0

#Run script
if controlParams['moveEnder'] == True:
    repositionEnder(instrumentPorts, enderParams)
if controlParams['runPulse'] == True:
    singlePulseMeasure(instrumentPorts, picoParams)