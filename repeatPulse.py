import json
import picosdkRapidblockPulse as pico
import ultratekPulser as pulser
import time
import tqdm
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt

#TODO: fix the plotting code. it doesn't work.
def repeatPulse(params):

    # Connect to picoscope, ender, pulser
    picoConnection = pico.openPicoscope()
    pulserConnection = pulser.openPulser(params['pulserPort'])

    # generate filename for current scan json
    scanFileName = params['experimentFolder'] + params['experimentName']

    # Set up plot
    fig, ax = plt.subplots()

    (wave, ) = ax.plot([params['measureDelay'] - 1, params['measureDelay'] + params['measureTime'] + 1],
                       [-1 * params['voltageRange'], params['voltageRange']], animated = True)
    plt.xlabel('Time (ns)')
    plt.ylabel('Intensity (mV)')
    plt.show(block = False)

    #test

    #Copy figure background to allow fast updating
    background = fig.canvas.copy_from_bbox(fig.boox)
    # Draw initial filler data
    ax.draw_artist(wave)
    # Show result
    fig.canvas.blit(fig.bbox)

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

        # Plot the data
        wavePlot.set_xdata(waveform[1])
        wavePlot.set_ydata(waveform[0])

        #draw updated plot
        #reset the background
        fig.canvas.restore_region(background)
        #update data
        wave.set_xdata(waveform[1])
        wave.set_ydata(waveform[0])
        #draw it
        ax.draw_artist(wave)
        #copy image to gui
        fig.canvas.blit(fig.bbox)
        #flush impending gui events
        fig.canvas.flush_events()
        plt.show(block = False)

        # Make data pretty for json
        waveformList = []
        waveformList.append(list(waveform[0]))
        waveformList.append(list(waveform[1]))

        timeString = "Time: " + str(time.time())

        metaDataList = [timeString]

        # #clear old plot and plot current data
        # plt.plot(waveform[0], waveform[1])
        # plt.show()

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

    pbar.close()

    pulser.pulserOff(pulserConnection)
    pico.closePicoscope(picoConnection)