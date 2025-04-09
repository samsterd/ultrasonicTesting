import ultratekPulser as utp
import scanner as sc
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import time
import picoscope as picoscope
import mux

# A set of functions to run in order to set parameters for a scan
# This includes:
#   singlePulseMeasure - turns on pulser, takes a measurement with the picoscope at given parameters, outputs a plot
#   repositionEnder - connects to Ender, moves, and disconnects so that it can be positioned at the starting point of a scan
# This interface should be improved to better match setup protocols

def singlePulseMeasure(params):
    """
    Executes an ultrasonic pulse experiment and shows a plot of the results

    Args:
        params (dict) : experiment params dict from runUltrasonicExperiment.py
    Returns:
        None. Data is shown in a plot but not saved.
        todo: implement saving on single pulse experiments
    """

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

def plotWaveDict(waveDict):
    """
    Plots the ultrasonic waveform(s) output from runPicoMeasurement(). Multiple data sets in a single input will be
    overlaid on the same plot.

    Args:
        waveDict (dict) : the data dict output from runPicoMeasurement(). 'time' is used as the x-axis and any key
            containing 'voltage' will be used as plot data
    Returns:
        None. Displays a plot but returns nothing
    """

    time = waveDict['time']
    fig, ax = plt.subplots()
    for voltageKey in waveDict.keys():
        if 'voltage' in voltageKey and 'Offset' not in voltageKey:
            # Need to select voltage keys but not voltage_offset. This isn't the best way to only select voltage keys but it works for now
            ax.plot(time, waveDict[voltageKey], label = voltageKey)

    plt.xlabel('Time (us)')
    plt.ylabel('Voltage (mV)')
    plt.legend()
    plt.show()

def moveScanner(params):
    """
    Executes a move of the gantry / scanner.

    Args:
        params (dict) : experiment params dict from runUltrasonicExperiment.py
            Required keys: 'scannerPort', 'axis', 'distance'
    Returns:
        None
    """

    scanner = sc.Scanner(params)
    moveRes = scanner.move(params['axis'], params['distance'])
    scanner.close()