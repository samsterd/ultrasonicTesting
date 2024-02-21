# Script to run a 2D ultrasonic scan

import picosdkRapidblockPulse as pico
import ultratekPulser as pulser
import enderControl as ender
import math
import time
import matplotlib.pyplot as plt
import json
from tqdm import tqdm

#TODO:
#   return to start location after scan!
#   get formatting right
#   make scan plot live update
#   get database code from docker, implement it here
#   improve ui, especially on scanSetup
#   improve documentation

scanParams = {
    #Data saving location
    'experimentName' : 'at_testdata',  # Name for json file containing data
    'experimentFolder' : 'data',  # Name of folder to dump data

    #Scanning parameters
    'primaryAxis' : 'X',              #First axis of motion for the scan
    'secondaryAxis' : 'Z',            #Second axis of motion for the scan
    'primaryAxisRange' : 4,         #Distance in mm to scan on the primary axis
    'primaryAxisStep' : 0.1,           #Distance in mm between each scan on the primary axis
    'secondaryAxisRange' : 4,       #Distance in mm to scan on the secondary axis
    'secondaryAxisStep' : -0.1,         #Distance in mm between each scan on the secondary axis

    #Picoscope collection parameters
    'measureTime' : 1,   #Approx measurement time, in us
    'measureDelay' : 13.5, #Approx delay after trigger to start measuring, in us
    'voltageRange' : 0.1,#Picoscope data range
    'waves' : 1000,      #Number of waves to collect and average
    'samples': 500,      #Number of data points per wave

    #Names of ports for instruments
    'pulserPort' : 'COM5',  # Ultratek pulser port name
    'enderPort' : 'COM7'  # Ender port name
}

# Runs a 2D scan, taking ultrasonic pulse data at every point, and saves to the specified folder
# Inputs: parameters specified above
def runScan(params):

    #setup save file
    filename = params['experimentFolder'] + '\\' + params['experimentName'] + ".json"

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
    #+1 added at end to make the ranges inclusive of the ends
    primaryAxisSteps = math.ceil(params['primaryAxisRange'] / abs(params['primaryAxisStep'])) + 1
    secondaryAxisSteps = math.ceil(params['secondaryAxisRange'] / abs(params['secondaryAxisStep'])) + 1

    #start scan. tqdm adds progress bars
    for i in tqdm(range(secondaryAxisSteps)):

        for j in range(primaryAxisSteps):

            #collect data
            waveform = pico.runPicoMeasurement(picoConnection, params['waves'])

            #Make data pretty for json
            waveformList = []
            waveformList.append(list(waveform[0]))
            waveformList.append(list(waveform[1]))

            #calculate location to add to file
            iLoc = i * params['secondaryAxisStep']
            jLoc = j * params['primaryAxisStep']

            iString = params['secondaryAxis'] + ": " + str(iLoc)
            jString = params['primaryAxis'] + ": " + str(jLoc)

            timeString = "Time: " + str(time.time())

            metaDataList = [iString, jString, timeString]

            # #clear old plot and plot current data
            # plt.plot(waveform[0], waveform[1])
            # plt.show()

            #TODO: check formatting, add other data (i.e. scan position, time)

            #write data
            with open(filename, 'a') as file:
                json.dump(waveformList, file)
                json.dump(metaDataList, file)
                file.write('\n')

            #TODO: get database saving working

            #Increment position along primary axis
            ender.moveEnder(enderConnection, params['primaryAxis'], params['primaryAxisStep'])

        # Move back to origin of primary axis
        ender.moveEnder(enderConnection, params['primaryAxis'], -1 * primaryAxisSteps * params['primaryAxisStep'])

        # Increment position on secondary axis
        ender.moveEnder(enderConnection, params['secondaryAxis'], params['secondaryAxisStep'])

        # Wait 2 seconds for motion to finish
        time.sleep(2)

    #Return to the start position. Only needs to be done on the secondary axis since the parimary axis resets at the end of the loop
    ender.moveEnder(enderConnection, params['secondaryAxis'], -1 * secondaryAxisSteps * params['secondaryAxisStep'])

    #Turn off pulser
    pulser.pulserOff(pulserConnection)

    #Close connection to pulser, picoscope, and ender
    pulser.closePulser(pulserConnection)
    ender.closeEnder(enderConnection)
    pico.closePicoscope(picoConnection)

    return 0

runScan(scanParams)