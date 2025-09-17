import json
import picoscope as picoscope
import ultratekPulser as utp
import time
import tqdm
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from database import Database
import pickleJar as pj
import mux


def repeatPulse(params):

    # Connect to picoscope, pulser
    pulser = utp.Pulser(params['pulserType'], pulserPort = params['pulserPort'], dllFile = params['dllFile'])
    pico = picoscope.Picoscope(params, pulser)

    # connect to multiplexer, if applicable
    if params['multiplexer']:
        multiplexer = mux.Mux(params)
    else:
        multiplexer = None

    # determine whether the files will be divided
    multipleFiles = params['dataPointsPerFile'] > 0
    fileIndex = 0

    # raise error if multipleFiles and not saving as sqlite. Honestly should probably stop supporting JSON
    if multipleFiles and params['saveFormat'] != 'sqlite':
        raise ValueError("repeatPulse saving error: multiple files is only supported for 'sqlite' save formats.")

    # generate filename for current scan
    if multipleFiles:
        params['fileName'] = params['experimentFolder'] + '//' + params['experimentName'] + '_0'
    else:
        params['fileName'] = params['experimentFolder'] + '//' + params['experimentName']

    # if saveFormat is sqlite, initialize the database
    #   NOTE FOR FUTURE: for multipleFiles = True, consider initializing all databases at once to avoid time overhead
    #   mid-measurement. Not sure if this will end up being important for most use cases, have not actually timed the process
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
        waveDict = pico.runPicoMeasurement(multiplexer)
        waveDict['time_collected'] = time.time()

        # create a new database if we are managing memory and collection index is too high
        if multipleFiles and collectionIndex > params['dataPointsPerFile']:
            # iterate fileIndex, reset collectionIndex
            fileIndex += 1
            collectionIndex = 0

            # close old db and create new one
            database.connection.close()
            del database # deleting old object to avoid any issues with old properties not being overwritten.
            params['fileName'] = params['experimentFolder'] + '//' + params['experimentName'] + '_' + str(fileIndex)
            database = Database(params)

        else:
            collectionIndex += 1

        waveDict['collection_index'] = collectionIndex

        # save data as sqlite database
        if params['saveFormat'] == 'sqlite':
            database.writeData(waveDict)

        # save data as json
        else:
            with open(params['fileName'], 'a') as file:
                json.dump(waveDict, file)
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

    # close instrument and database connections
    pulser.pulserOff()
    pulser.closePulser()
    pico.closePicoscope()
    if params['multiplexer']:
        multiplexer.closeMux()
    if params['saveFormat'] == 'sqlite':
        database.connection.close()