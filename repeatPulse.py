import json
import picosdkRapidblockPulse as pico
import ultratekPulser as pulser
import time
import tqdm
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from database import Database


def repeatPulse(params):

    # Connect to picoscope, ender, pulser
    picoConnection = pico.openPicoscope()
    pulserConnection = pulser.openPulser(params['pulserPort'])

    # generate filename for current scan
    scanFileName = params['experimentFolder'] + params['experimentName']

    # if saveFormat is sqlite, initialize the database
    if params['saveFormat'] == 'sqlite':
        database = Database(params)

    # Setup picoscope
    picoConnection = pico.setupPicoMeasurement(picoConnection,
                                               params['measureDelay'],
                                               params['voltageRange'],
                                               params['samples'],
                                               params['measureTime'])

    # Turn on pulser
    pulser.pulserOn(pulserConnection)

    # initialize time
    experimentTime = params['experimentTime']
    startTime = time.time()
    endTime = startTime + experimentTime

    # initialize progress bar
    pbar = tqdm.tqdm(total=experimentTime)

    #start pulse collection loop. Run until end of experiment
    while time.time() < endTime:

        # record scan start time
        pulseStartTime = time.time()

        # collect data
        waveform = pico.runPicoMeasurement(picoConnection, params['waves'])

        # Make a data dict for saving
        waveData = {}

        waveData['voltage'] = list(waveform[0])
        waveData['time'] = list(waveform[1])

        waveData['time_collected'] = time.time()

        # save data as sqlite database
        if params['saveFormat'] == 'sqlite':
            query = database.parse_query(waveData)
            database.write(query)

        # save data as json
        else:
            with open(scanFileName, 'a') as file:
                json.dump(waveData, file)
                file.write('\n')

        # calculate time elapsed in this iteration
        iterationTime = time.time() - pulseStartTime

        # check difference between iteration time and experiment pulse interval
        waitTime = params['pulseInterval'] - iterationTime

        # If time spent on iteration is less than pulseInterval, wait until pulseInterval has elapsed
        if waitTime > 0:
            time.sleep(waitTime)

            #update progress bar
            pbar.update(params['pulseInterval'])

        # iterationTime is longer than pulse interval. Immediately repeat the iteration and update pbar the correct amount
        else:
            pbar.update(iterationTime)

    pbar.close()

    pulser.pulserOff(pulserConnection)
    pico.closePicoscope(picoConnection)