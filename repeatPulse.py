import json
import picosdkRapidblockPulse as pico
import ultratekPulser as pulser
import time
import tqdm


def repeatPulse(params):

    # initialize time
    startTime = time.time()
    endTime = startTime + params['experimentTime']

    # initialize progress bar
    pbar = tqdm.tqdm(total=params['experimentTime'])

    # Connect to picoscope, ender, pulser
    picoConnection = pico.openPicoscope()
    pulserConnection = pulser.openPulser(params['pulserPort'])

    #Calculate numberOfScans
    params['numberOfScans'] = math.ceil(params['experimentTime'] / params['pulseInterval'])

    # generate filename for current scan json
    scanFileName = params['experimentFolder'] + params['experimentName']

    # Setup picoscope
    picoConnection = pico.setupPicoMeasurement(picoConnection,
                                               params['measureDelay'],
                                               params['voltageRange'],
                                               params['samples'],
                                               params['measureTime'])

    # Turn on pulser
    pulser.pulserOn(pulserConnection)

    #start pulse collection loop. Run until end of experiment
    while time.time() < endTime:

        # record scan start time
        pulseStartTime = time.time()

        # collect data
        waveform = pico.runPicoMeasurement(picoConnection, params['waves'])

        # Make data pretty for json
        waveformList = []
        waveformList.append(list(waveform[0]))
        waveformList.append(list(waveform[1]))

        timeString = "Time: " + str(time.time())

        metaDataList = [timeString]

        # #clear old plot and plot current data
        # plt.plot(waveform[0], waveform[1])
        # plt.show()

        # TODO: check formatting, add other data (i.e. scan position, time)

        # write data
        with open(scanFileName, 'a') as file:
            json.dump(waveformList, file)
            file.write('\n')
            json.dump(metaDataList, file)
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
