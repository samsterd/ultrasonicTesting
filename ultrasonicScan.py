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
#   get formatting right - save scan parameters somewhere!
#   make scan plot live update
#   make scan snake/raster instead of line by line
#   add tiny sleep between collections to prevent collection while moving
#   get database code from docker, implement it here
#   improve ui, especially on scanSetup
#   improve documentation


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

            #write data
            with open(filename, 'a') as file:
                json.dump(waveformList, file)
                file.write('\n')
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
