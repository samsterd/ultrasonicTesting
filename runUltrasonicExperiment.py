import ultrasonicScan as scan
import multiscan
import scanSetupFunctions as setup
import repeatPulse

###################################################################
#################  Operating Instructions  ########################
###################################################################
# 1) Decide which experiment you want to perform (move the transducers, take a single pulse,
# collect a 2D scan, or collect multiple 2D scans)
#
# 2) fill out the relevant parameters for each experiment
#
# 3) run this script. On PyCharm, simply pless Shift + F10 or click the green play button at the top right


experimentParams = {
    # What do you want to do?
    #'move' = move the transducers
    #'single pulse' = perform a single test pulse
    #'repeat pulse' = repeat a pulse at a single location for a certain time at a certain frequency
    #'single scan' = perform a single 2D scan
    #'multi scan' = repeat a 2D scan with a set frequency
    #Once you have selected, fill out the values in the parameter list in the correct section
    #NOTE: ONLY CHANGE THE VALUES AFTER THE COLON ON EACH LINE
    'experiment' : 'single pulse',

    #####################################################################
    ################# 'move' parameters #################################
    ### Only applies when 'experiment' == 'move' ########################
    #####################################################################

    'axis': 'X',                                     # Axis to move ender
    'distance': -3,                                  # Distance in mm to move ender

    #################################################################################
    ###################### Picoscope Parameters #####################################
    #### Applies to 'single pulse', 'single scan', and 'multi scan' experiments #####
    #################################################################################

    'measureTime' : 1,                               # Approx measurement time, in us
    'measureDelay' : 13.5,                           # Approx delay after trigger to start measuring, in us
    'voltageRange' : 0.1,                            # Picoscope data range
    'waves' : 1000,                                  # Number of waves to collect and average
    'samples': 500,                                  # Number of data points per wave

    ################################################################################
    ########################### Saving Names ##########################################
    ##### Applies to 'single scan', 'multi scan', and 'repeat pulse' experiment ####
    ################################################################################

    'experimentFolder': 'data',                     # Name of folder to dump data
    'experimentName' : 'testdb01',                 # File name for single scan and repeat pulse experiment. Will be appended with .json
    'experimentBaseName' : 'test_multiscan_data',   # Base filename for multi scan experiment, which will have the scan # appended to it
    'saveFormat' : 'sqlite',                        # Format to save data. Options are sqlite or json. Sqlite is recommended

    ################################################################################
    ####################### Scan Parameters ########################################
    ####### Applies to 'single scan' and 'multi scan' experiment ###################
    ################################################################################

    'primaryAxis' : 'X',                            # First axis of motion for the scan. 'X' is recommended
    'secondaryAxis' : 'Z',                          # Second axis of motion for the scan. 'Z' is recommended
    'primaryAxisRange' : 4,                         # Distance in mm to scan on the primary axis
    'primaryAxisStep' : 0.1,                        # Distance in mm between each scan on the primary axis
    'secondaryAxisRange' : 4,                       # Distance in mm to scan on the secondary axis
    'secondaryAxisStep' : -0.1,                     # Distance in mm between each scan on the secondary axis

    ################################################################################
    ################ Repeat Measure Parameters #####################################
    ###### Applies to 'multi scan' and 'repeat pulse' experiments ##################
    ################################################################################

    'scanInterval' : 3600,                          # For multi scans: Minimum time between start of scans, in seconds.
    'numberOfScans' : 10,                           # For multi scans: Number of times to run the scan
    'pulseInterval' : 10,                           # For repeat pulse: Minimum time between pulse collection, in seconds
    'experimentTime' : 3600,                        # For repeat pulse: Time to collect data, in seconds

    #################################################################################
    ########################## Port Names ###########################################
    ######### Only change if instrument USB ports are changed! ######################
    #################################################################################
    'pulserPort' : '/dev/ttyUSB1',                          # Ultratek pulser port name
    'enderPort' : '/dev/ttyUSB0'                            # Ender port name
}

##########################################################################################

##########################################################################################

##########################################################################################
##########################################################################################
####################### END OF USER INPUT ################################################
##########################################################################################
##########################################################################################

##########################################################################################

##########################################################################################


# Function to choose experiment function based on parameters
def runExperiment(params : dict):

    # get the experiment from the input
    experiment = params['experiment']

    #run the appropriate experiment function
    # 'move' = move the transducers
    # 'single pulse' = perform a single test pulse
    # 'single scan' = perform a single 2D scan
    # 'multi scan' = repeat a 2D scan with a set frequency
    match experiment:
        case 'move':
            setup.repositionEnder(params)

        case 'single pulse':
            setup.singlePulseMeasure(params)

        case 'repeat pulse':
            repeatPulse.repeatPulse(params)

        case 'single scan':
            scan.runScan(params)

        case 'multi scan':
            multiscan.multiscan(params)

        #Match case where no matching expiment is input
        case _:
            print("No experiment matches input. Check the value of the 'experiment' parameter and ensure it is a valid experiment")
            print("Valid experiments are: 'move', 'single pulse', 'single scan', and 'multi scan'")

runExperiment(experimentParams)