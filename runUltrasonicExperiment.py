import ultrasonicScan as scan
import multiscan
import scanSetupFunctions as setup
import repeatPulse
import gui

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
    # If you want to use the GUI, simply set 'gui' : True and the program will guide you through the rest of the setup
    'gui' : True,

    # What do you want to do?
    #'move' = move the transducers
    #'single pulse' = perform a single test pulse
    #'repeat pulse' = repeat a pulse at a single location for a given time and frequency
    #'single scan' = perform a single 2D scan
    #'multi scan' = repeat a 2D scan with a set frequency
    #Once you have selected, fill out the values in the parameter list in the correct section
    #NOTE: ONLY CHANGE THE VALUES AFTER THE COLON ON EACH LINE
    'experiment' : 'single pulse',

    #####################################################################
    ################# 'move' parameters #################################
    ### Only applies when 'experiment' == 'move' ########################
    #####################################################################

    'axis': 'X',                                     # Axis to move scanner
    'distance': -3,                                  # Distance in mm to move scanner

    #################################################################################
    ###################### Ultrasonic Parameters #####################################
    #### Applies to 'single pulse', 'single scan', and 'multi scan' experiments #####
    #################################################################################

    'transducerFrequency' : 50,                    # Central frequency of the ultrasonic transducer, in MHz. Current options are 2.25 or 50
    'pulserType' : 'standard',                       # Type of pulser. 'standard' is the single wave CompactPulser. 'tone burst' uses the USBUT350 tone burst pulser
    'measureTime' : 1,                               # Approx measurement time, in us. Note this can be changed by the picoscope time interval based on samples
                                                     #      Changes to the measureTime will be printed in the console when the script is run
    'measureDelay' : 4,                           # Approx delay after trigger to start measuring, in us
    'voltageRangeT' : 0.02,                            # For Transmission: Picoscope voltage range in V. Note this is the total range: 1 V = [-0.5 V, 0.5 V]
    'voltageRangeP': 1,                              #For Pulse-echo: Picoscope voltage range in V. Note this is the total range: 1 V = [-0.5 V, 0.5 V]

    # Allowed voltages = (0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20)
    'voltageAutoRange' : True,                      # Set the oscilloscope to rerun measurements where the voltage range of the wave has significantly changed
                                                     # This enables the tightest possible voltageRange to be used, increasing the accuracy of low intensity signals without cutting off high intensity ones
                                                     # NOTE: this can add significant overhead (2-3x increase in collection time) for each waveform where the range changes
    'waves' : 1000,                                  # Number of waves to collect and average
    'samples': 1000,                                  # Number of data points per wave
    'halfCycles' : 16,                               # Tone burst pulser only. Number of half-cycles in a tone burst pulse. Minimum 1, maximum 32
    'collectionMode': 'pulse-echo',                #transmission/pulse-echo/both

    ################################################################################
    ########################### Saving Names ##########################################
    ##### Applies to 'single scan', 'multi scan', and 'repeat pulse' experiment ####
    ################################################################################

    'experimentFolder': '/home/rpi-001/acoustics/',                     # Name of folder to dump data
    'experimentName' : 'autorangeTest2',                  # File name for single scan and repeat pulse experiment. Will be appended with .json or .sqlite3
    'experimentBaseName' : 'test_multiscan_data',   # Base filename for multi scan experiment, which will have the scan # appended to it
    'saveFormat' : 'sqlite',                        # Format to save data. Options are sqlite or json. Sqlite is highly recommended
    'postAnalysis' : False,                         # Option to run simple post-scan analysis and plotting: calculate max-min, STA/LTA, and Hilbert Envelope, save plots of data and dump CSVs of the raw metrics
                                                    # NOTE: this is only available if for single or multi scan experiments with saveFormat = 'sqlite'

    ################################################################################
    ####################### Scan Parameters ########################################
    ####### Applies to 'single scan' and 'multi scan' experiment ###################
    ################################################################################

    'primaryAxis' : 'X',                            # First axis of motion for the scan. 'X' is recommended
    'secondaryAxis' : 'Z',                          # Second axis of motion for the scan. 'Z' is recommended
    'primaryAxisRange' : 20,                         # Distance in mm to scan on the primary axis
    'primaryAxisStep' : 5,                        # Distance in mm between each scan on the primary axis
    'secondaryAxisRange' : 20,                       # Distance in mm to scan on the secondary axis
    'secondaryAxisStep' : -5,                     # Distance in mm between each scan on the secondary axis

    ################################################################################
    ################ Repeat Measure Parameters #####################################
    ###### Applies to 'multi scan' and 'repeat pulse' experiments ##################
    ################################################################################

    'scanInterval' : 3600,                          # For multi scans: Minimum time between start of scans, in seconds.
    'numberOfScans' : 10,                           # For multi scans: Number of times to run the scan
    'pulseInterval' : 1,                            # For repeat pulse: Minimum time between pulse collection, in seconds
    'experimentTime' : 5,                           # For repeat pulse: Time to collect data, in seconds

    #################################################################################
    ########################## Port Names ###########################################
    ######### Only change if instrument USB ports are changed! ######################
    #################################################################################
    'pulserPort' : '/dev/ttyUSB0',                          # Ultratek pulser port name
    'scannerPort' : '/dev/ttyUSB1',                         # Ender port name
    'dllFile' : 'C://USUTSDK//USBUTSDKC//USBUT.dll',        # Only used for 'pulserType' : 'tone burst'. Location of USBUT350 pulser SDK

    ##################################################################################
    ######################### Scanner Size Parameters ################################
    ##################################################################################
    'transducerHolderHeight' : 50,                            # Z-direction length of the transducer holder, in mm
    'scannerMaxDimensions' : (220, 220, 240)                # Maximum dimensions of the scanner.
                                                            # For the Ender-3 or other 3D printers this is the build volume
}

##########################################################################################

##########################################################################################

##########################################################################################
##########################################################################################
####################### END OF USER INPUT ################################################
################# DO NOT CHANGE BELOW THIS LINE ##########################################
##########################################################################################
##########################################################################################

##########################################################################################

##########################################################################################


# Function to choose experiment function based on parameters
def runExperiment(params : dict):

    if params['gui']:
        gui.startGUI(params)

    else:
        # get the experiment from the input
        experiment = params['experiment']

        #run the appropriate experiment function
        # 'move' = move the transducers
        # 'single pulse' = perform a single test pulse
        # 'single scan' = perform a single 2D scan
        # 'multi scan' = repeat a 2D scan with a set frequency
        match experiment:
            case 'move':
                setup.moveScanner(params)

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