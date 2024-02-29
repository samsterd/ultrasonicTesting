# Code to run multiple 2D scans on a timer
import time
import ultrasonicScan

scanParams = {
    #Data saving location
    'experimentBaseName' : 'at_testdata',  # Name for json file containing data, which will have the scan # appended to it
    'experimentFolder' : 'data',  # Name of folder to dump data

    #Scanning parameters
    'scanInterval' : 3600,         #Minimum time between start of scans, in seconds
    'numberOfScans' : 10           # Number of times to run the scan
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

def multiscan(params):

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

    return 0
