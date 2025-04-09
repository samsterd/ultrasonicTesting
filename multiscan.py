# Code to run multiple 2D scans on a timer
import time
import ultrasonicScan

def multiscan(params):
    """
    Execute multiple 2D scans over a set time interval

    Args:
        params (dict) : experiment params dict from runUltrasonicExperiment.py
    Returns:
        None. Data is saved in a separate file for each scan
    """

    #initialize time
    startTime = time.time()

    #start scan loop
    for scan in range(params['numberOfScans']):

        #record scan start time
        scanStartTime = time.time()

        #generate filename for current scan json
        scanFileName = params['experimentBaseName'] + '_' + str(scan)

        #overwrite experimentName in params with new filename
        params['experimentName'] = scanFileName

        #run the scan
        ultrasonicScan.runScan(params)

        #check every second whether the time interval has elapsed
        while time.time() < scanStartTime + params['scanInterval']:
            time.sleep(1)
