# Script to run a 2D ultrasonic scan

import picosdkRapidblockPulse as pico
import ultratekPulser as pulser
import enderControl as ender
import math
import matplotlib.pyplot as plt
import json

scanParams = {
    #Data saving location
    'experimentName' : 'scan_test',  # Name for json file containing data
    'experimentFolder' : 'files/ultrasound',  # Name of folder to dump data

    #Scanning parameters
    'primaryAxis' : 'X',              #First axis of motion for the scan
    'secondaryAxis' : 'Z',            #Second axis of motion for the scan
    'primaryAxisRange' : '10',         #Distance in mm to scan on the primary axis
    'primaryAxisStep' : '1',           #Distance in mm between each scan on the primary axis
    'secondaryAxisRange' : '10',       #Distance in mm to scan on the secondary axis
    'secondaryAxisStep' : '1',         #Distance in mm between each scan on the secondary axis

    #Picoscope collection parameters
    'measureTime' : 2,  # Approx measurement time, in us
    'measureDelay' : 15,  # Approx delay after trigger to start measuring, in us
    'voltageRange' : 0.1,  # Picoscope data range
    'waves' : 1000,  # Number of waves to collect and average
    'samples' : 1000,  # Number of data points per wave

    #Names of ports for instruments
    'pulserPort' : 'COM2',  # Ultratek pulser port name
    'enderPort' : 'COM3'  # Ender port name
}

# Runs a 2D scan, taking ultrasonic pulse data at every point, and saves to the specified folder
# Inputs: parameters specified above
def runScan(params):

    #setup save file
    filename = params['experimentFolder'] + params['experimentName'] + ".json"

    #connect to database?

    #Connect to picoscope, ender, pulser
    picoConnection = pico.openPicoscope()
    pulserConnection = pulser.openPulser(params['pulserPort'])
    enderConnection = ender.openEnder(params['enderPort'])

    #Setup picoscope
    picoConnection = pico.setupPicoMeasurement(picoConnection,
                                               params['measureDelay'],
                                               params['voltageRange'],
                                               params['samples'],
                                               params['measureTime'])

    #Turn on pulser
    pulser.pulserOn(pulserConnection)

    #Calculate number of steps on each axis
    #math.ceiling is used to ensure the result is an integer
    primaryAxisSteps = math.ceil(params['primaryAxisRange'] / params['primaryAxisStep'])
    secondaryAxisSteps = math.ceil(params['secondaryAxisRange'] / params['secondaryAxisStep'])

    #start scan
    for i in range(secondaryAxisSteps + 1):

        for j in range(primaryAxisSteps + 1):

            #collect data
            waveform = pico.runPicoMeasurement(picoConnection, params['waves'])

            #clear old plot and plot current data
            plt.clf()
            plt.plot(waveform[0], waveform[1])

            #TODO: check formatting, add other data (i.e. scan position, time)

            #write data
            with open(filename, 'a') as file:
                json.dump(waveform, file)
                file.write('\n')

            #TODO: get database saving working

            #Increment position along primary axis
            ender.moveEnder(enderConnection, params['primaryAxis'], params['primaryAxisStep'])

        # Move back to origin of primary axis
        ender.moveEnder(enderConnection, params['primaryAxis'], -1 * primaryAxisSteps * params['primaryAxisStep'])

        # Increment position on secondary axis
        ender.moveEnder(enderConnection, params['secondaryAxis'], params['secondaryAxisStep'])

    #Turn off pulser
    pulser.pulserOff(pulserConnection)

    #Close connection to pulser, picoscope, and ender
    pulser.closePulser(pulserConnection)
    ender.closeEnder(enderConnection)
    pico.closePicoscope(picoConnection)

    return 0

runScan(scanParams)