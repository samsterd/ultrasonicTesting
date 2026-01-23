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
import copy

def repeatPulse(params):

    # Connect to picoscope, pulser
    pulser = utp.Pulser(params['pulserType'], pulserPort = params['pulserPort'], dllFile = params['dllFile'])
    pico = picoscope.Picoscope(params, pulser)

    # connect to multiplexer, if applicable
    if params['multiplexer']:
        multiplexer = mux.Mux(params)
    else:
        multiplexer = None

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
        waveDict = pico.runPicoMeasurement(multiplexer)

        waveDict['time_collected'] = time.time()
        waveDict['collection_index'] = collectionIndex
        collectionIndex += 1

        # CURRENTLY NOT SUPPORTED
        # if params['voltageAutoRange']:
        #     waveData['voltageRange'] = params['voltageRange']

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

def sweepParameters(initParams: dict, sweepParams: dict):
    """
    Execute multiple experiments in sequence while changing the value of a single parameter

    Args:
        initParams (dict) : initial params dict from runUltrasonicExperiment.py. All parameters from this dict are held
            constant EXCEPT the parameter specified by the key of sweepParams.
        sweepParams (dict) : dict describing the parameter to sweep. The key of sweepParams must be a key in initParams,
            and the value must be a list of valid values of that parameter
            NOTE: parameters involved in the instrument connections or data saving cannot be changed
            NOTE: if multiple parameters are swept, they will only be changed one at a time, with the unchanged sweepParams
                being held at their value in initParams
    Returns:
        None. Data is saved in a single file as specified in params
    """

    # error check inputs
    for key in sweepParams.keys():
        if key not in initParams.keys():
            raise ValueError("sweepParameters: all keys in sweepParams input must be valid experimental parameters.")

    # check that all swept values are lists
    listLens = []
    for val in sweepParams.values():
        if type(val) != list:
            raise ValueError("sweepParameters: all values in sweepParams must be lists.")

    # generate list of input parameters
    inputParams = []
    for key in sweepParams.keys():
        for keyVal in sweepParams[key]:
            inputCopy = copy.deepcopy(initParams)
            inputCopy[key] = keyVal
            inputParams.append(inputCopy)

    # Connect to picoscope, pulser
    pulser = utp.Pulser(initParams['pulserType'], pulserPort=initParams['pulserPort'], dllFile=initParams['dllFile'])
    # TODO: this line may need to be broken up between connecting and initializing parameters to allow collection times to be swept
    pico = picoscope.Picoscope(initParams, pulser)

    # connect to multiplexer, if applicable
    if initParams['multiplexer']:
        multiplexer = mux.Mux(initParams)
    else:
        multiplexer = None

    # generate filename for current scan
    initParams['fileName'] = initParams['experimentFolder'] + '//' + initParams['experimentName']

    # if saveFormat is sqlite, initialize the database
    if initParams['saveFormat'] == 'sqlite':
        database = Database(initParams)

    # Initialize the collection index which is used in the saved data table
    collectionIndex = 0

    # iterate through inputParams dicts, running experiments as normal
    #   Major difference between this experiment and repeatPulse is that the pulser is turned on and off every experiment
    #   in order to allow pulse parameters to be swept (i.e. change frequency between experiments)
    for i in tqdm(range(len(inputParams))):

        input = inputParams[i]

        # Adjust pulser pulsewidth
        pulser.setFrequency(input['transducerFrequency'])

        # Set the number of half cycles if using tone burst pulser
        if pulser.type == 'tone burst':
            pulser.setHalfCycles(input['halfCycles'])

        # Turn on the pulser
        pulser.pulserOn()

        # collect data
        waveDict = pico.runPicoMeasurement(multiplexer)

        waveDict['time_collected'] = time.time()
        waveDict['collection_index'] = collectionIndex
        collectionIndex += 1

        # save data as sqlite database
        if input['saveFormat'] == 'sqlite':
            database.writeData(waveDict)

        # save data as json
        else:
            with open(input['fileName'], 'a') as file:
                json.dump(waveDict, file)
                file.write('\n')

        pulser.pulserOff()

    pulser.closePulser()
    pico.closePicoscope()
    if initParams['multiplexer']:
        multiplexer.closeMux()
    if initParams['saveFormat'] == 'sqlite':
        database.connection.close()

    return 0

# todo: this necessitates writing a validParamsQ, validParamQ, list of params (also list of categorized params), etc function in order to validate each swept
#   experiment. Put these in scanSetupFunctions? Might also be a good time to consolidate functions into single file

# todo: implement sweepParameters as an experiment option on runExperiment. Add options to GUI (eventually)