# Script to run a 2D ultrasonic scan

import picosdkRapidblockPulse as pico
import ultratekPulser as pulser
import enderControl as ender
import math
import time
import matplotlib.pyplot as plt
import json
from tqdm import tqdm
from database import Database


# Runs a 2D scan, taking ultrasonic pulse data at every point, and saves to the specified folder
# Inputs: parameters specified above
def runScan(params):

    #setup save file
    params['fileName'] = params['experimentFolder'] + '//' + params['experimentName']

    #setup database if saving as sqlite
    if params['saveFormat'] == 'sqlite':
        database = Database(params)

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

    # Adjust pulser pulsewidth
    pulser.transducerFrequencyToPulseWidth(pulserConnection, params['transducerFrequency'])

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

            #Make a data dict for saving
            pixelData = {}

            #Add waveform data to pixelData
            pixelData['voltage'] = list(waveform[0])
            pixelData['time'] = list(waveform[1])

            #Add collection metadata
            pixelData['time_collected'] = time.time()

            #calculate location to add to file
            iLoc = i * params['secondaryAxisStep']
            jLoc = j * params['primaryAxisStep']

            iKey = params['secondaryAxis']
            jKey = params['primaryAxis']

            #add location to pixelData
            pixelData[iKey] = iLoc
            pixelData[jKey] = jLoc

            # save data as sqlite database
            if params['saveFormat'] == 'sqlite':
                query = database.parse_query(pixelData)
                database.write(query)

            # save format is json, so dump data, then dump metadata
            else:
                #write data to json for redundancy
                with open(params['fileName'], 'a') as file:
                    json.dump(pixelData, file)
                    file.write('\n')

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
