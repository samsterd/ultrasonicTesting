import json
import picosdkRapidblockPulse as pico
import ultratekPulser as utp
import time
import tqdm
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from database import Database
import pickleJar as pj
import picosdkRapidblockPulse as picoRapid


def repeatPulse(params):

    # Connect to picoscope & Set up pico measurement
    pico = picoRapid.picosdkRapidblockPulse(params)
    # Connect to picoscope, ender, pulser
    # picoConnection = picoRapid.openPicoscope()
    pulser = utp.Pulser(params['pulserType'], pulserPort = params['pulserPort'], dllFile = params['dllFile'])

    # generate filename for current scan
    params['fileName'] = params['experimentFolder'] + '//' + params['experimentName']

    # if saveFormat is sqlite, initialize the database
    if params['saveFormat'] == 'sqlite':
        database = Database(params)

    # # Setup picoscope
    # picoConnection = pico.setupPicoMeasurement(picoConnection,
    #                                            params['measureDelay'],
    #                                            params['voltageRange'],
    #                                            params['samples'],
    #                                            params['measureTime'])
    # Adjust pulser pulsewidth
    pulser.setFrequency(params['transducerFrequency'])

    # Set the number of half cycles if using tone burst pulser
    if pulser.type == 'tone burst':
        pulser.setHalfCycles(params['halfCycles'])

    # Turn on the pulser
    pulser.pulserOn()

    # initialize time
    experimentTime = params['experimentTime']
    startTime = time.time()
    endTime = startTime + experimentTime

    # Initialize the collection index which is used in the saved data table
    collectionIndex = 0

    # initialize progress bar
    pbar = tqdm.tqdm(total=experimentTime)

    #start pulse collection loop. Run until end of experiment
    while time.time() < endTime:

        # record scan start time
        pulseStartTime = time.time()

        # collect data
        if params['voltageAutoRange']:
            waveform, params = pico.voltageRangeFinder(params)
        else:
            waveform = pico.runPicoMeasurement(params['waves'])

        # Make a data dict for saving
        waveData = {}

        waveData['voltage'] = list(waveform[0])
        waveData['time'] = list(waveform[1])

        waveData['time_collected'] = time.time()
        waveData['collection_index'] = collectionIndex
        collectionIndex += 1

        # CURRENTLY NOT SUPPORTED
        # if params['voltageAutoRange']:
        #     waveData['voltageRange'] = params['voltageRange']

        # save data as sqlite database
        if params['saveFormat'] == 'sqlite':
            query = database.parse_query(waveData)
            database.write(query)

        # save data as json
        else:
            with open(params['fileName'], 'a') as file:
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

    pulser.pulserOff()
    pulser.closePulser()
    pico.closePicoscope()