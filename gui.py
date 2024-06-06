#todo: clean up imports!!!
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
# from PyQt5.QtWidgets import QFileDialog
import sys
import scanSetupFunctions as setup
import ultrasonicScan as scan
import multiscan
import repeatPulse
import scanner as sc
from serial import SerialException
import time
import os
import json

#TODO:
# xmake an initial experiment select window
# xmake the move window
# xfigure out how to transition windows
# xdefine windows for other experiments
# xmove files to gui.py, integrate gui start into run script
# xdefine control flow of experiment!
#      xIt might be better to make buttons for moving from any window to any other relevant window?
# xIMPLEMENT EVERYTHING AS QSTACKEDWIDGET()
# xfix control flow to include timeWindow (forgot about that)
# xcreate an experiment window that summarizes parameters and has option to abort or run
# xcreate executeExperiment for every experiment
#   xon move: change button to Moving..., make unclickable for duration
#   add progress bars?
# add reading parameter json file to __init__
# figure out mouseover notes
# xgather parameters from widgets
# define initialization/setup experiment
#   save ports etc in a json file?
# clean up imports
# put main loop somewhere better?
# fill in option defaults based on values in params dict
# implement a back button
# xupdate addWidgets to put them in a hardcoded index determined by self.windowIndices
# before merging: check linux compatibility
# Once merged: update the SOP on notion
#
# todo: setup function
#   example move
#       need to add safeMoveQ override flag
#   run homing function
#   prompt to measure transducer holder height, input it
#   prompt to verify gantry dimensions
#   move into a more reasonable position
#   enter port or dll file
#   run single pulse
#       edit pulse display to add inputs for these if experimentType == setup
#       may need to add error handling depending on whether exception gets raised on failure

# windowType = init, move, pulse, save, scan, time, experiment, 'scannerSetup'  'homing', 'dimensions'
# windowIndex = {init : 0, move : 1, pul
# experimentType = init, "Move", "Single Pulse Measurement", "Repeat Pulse Measurement", "Single Scan", "Multiple Scans", "Setup"])
#
# algorithm:
# start on init window
# when next button is pressed, determine the next window to display based on current windowtype, experimenttype, and other info entered
# create functions for each type of window

class MainWindow(QMainWindow):

    def __init__(self, params,  *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        self.setWindowTitle("Ultrasound Experiment")
        self.params = params

        self.windowType = 'init'
        self.experimentType = 'init'
        # create a dict to convert window types to indices
        self.windowIndices = {'init' : 0, 'move' : 1, 'pulse' : 2, 'save' : 3, 'scan' : 4, 'time' : 5, 'experiment' : 6,
                              'scannerSetup' : 7, 'homing' : 8, 'dimensions' : 9}

        # add widgets to stackedwidget in order defined by windowIndices
        # note that a filler temp widget is created for the experiment window since that needs to be made after the parameters are chosen
        self.mainWidget = QStackedWidget()
        self.mainWidget.insertWidget(self.windowIndices['init'],self.initWindow())
        self.mainWidget.insertWidget(self.windowIndices['move'], self.moveWindow())
        self.mainWidget.insertWidget(self.windowIndices['pulse'], self.pulseWindow())
        self.mainWidget.insertWidget(self.windowIndices['save'], self.saveWindow())
        self.mainWidget.insertWidget(self.windowIndices['scan'], self.scanWindow())
        self.mainWidget.insertWidget(self.windowIndices['time'], self.timeWindow())
        self.mainWidget.insertWidget(self.windowIndices['experiment'], QWidget())
        self.mainWidget.insertWidget(self.windowIndices['scannerSetup'], self.scannerSetupWindow())
        self.mainWidget.insertWidget(self.windowIndices['homing'], self.homingWindow())
        self.mainWidget.insertWidget(self.windowIndices['dimensions'], self.measureDimensionsWindow())

        # self.mainWidget.addWidget(self.experimentWindow())
        self.mainWidget.setCurrentIndex(0)

        self.setCentralWidget(self.mainWidget)

        # this is done after setting up the initial page so a warning dialog can properly display on top
        self.readSetupJSON()


    ################################################################################
    ################ NEXT BUTTON CONTROL FLOW ######################################
    #################################################################################

    # this function handles control flow of the gui. uses the current window and experiment type to set the next window
    def nextButtonClicked(self):

        # Handle initialization case first
        if self.windowType == 'init':

            # grab the experiment type from the combobox
            self.experimentType = self.experimentSelect.currentText()

            # remake all windows to re-initialize parameters and ensure that widgets are not disappearing
            self.remakeWindowsExceptInitAndExperiment()

            if self.experimentType == 'Repeat Pulse Measurement':
                self.switchWindow('pulse')

            elif self.experimentType == 'Setup':
                self.switchWindow('scannerSetup')

            else:
                self.switchWindow('move')

        # next handle changes from move window
        elif self.windowType == 'move':

            if self.experimentType == 'Move':
                self.switchWindow('init')

            # in all other cases, go to pulse menu
            else:
                self.switchWindow('pulse')

        elif self.windowType == 'pulse':

            if self.experimentType == 'Single Pulse Measurement':
                self.switchWindow('init')

            # this is the end of the setup experiment so the results must be recorded in set_parameters.json
            elif self.experimentType == 'Setup':
                self.writeSetupJSON()
                self.WarningDialog("Updated setup_parameters.json with setup results.")
                self.switchWindow('init')

            elif self.experimentType == 'Single Scan':
                self.switchWindow('scan')

            else:
                self.switchWindow('time')

        elif self.windowType == 'time':

            if self.experimentType == 'Repeat Pulse Measurement':
                self.switchWindow('save')

            else:
                self.switchWindow('scan')

        elif self.windowType == 'scan':

            self.switchWindow('save')

        elif self.windowType == 'save':

            self.switchWindow('experiment')

        # setup window progression
        elif self.windowType == 'scannerSetup':

            self.switchWindow('homing')

        elif self.windowType == 'homing':

            self.switchWindow('dimensions')

        elif self.windowType == 'dimensions':

            self.switchWindow('pulse')

        # all unhandled cases (including experiment) go back to the init window
        else:

            self.switchWindow('init')

####################################################################################
############### WINDOW DEFINITIONS #################################################
####################################################################################

    # init window is where experiment type is specified
    def initWindow(self):

        self.experimentSelect = QComboBox()
        self.experimentSelect.addItems(
            ["Move", "Single Pulse Measurement", "Repeat Pulse Measurement", "Single Scan", "Multiple Scans", "Setup"])
        self.experimentSelectLabel = QLabel("Select Experiment Type: ")
        # self.input.textChanged.connect(self.label.setText)

        self.nextButtonInit = QPushButton("Next")
        self.nextButtonInit.clicked.connect(self.nextButtonClicked)

        layout = QGridLayout()
        layout.addWidget(self.experimentSelectLabel, 0, 0)
        layout.addWidget(self.experimentSelect, 0, 1)
        layout.addWidget(self.nextButtonInit, 1, 1)

        widget = QWidget()
        widget.setLayout(layout)

        return widget

    # move window specifies move parameters
    def moveWindow(self):

        self.moveLabel = QLabel("Define movement parameters:")

        self.moveAxisLabel = QLabel("Axis: ")
        self.moveAxis = QComboBox()
        self.moveAxis.addItems(['X', 'Y', 'Z'])

        self.distanceLabel = QLabel("Distance (mm):")
        self.distance = QLineEdit("1")
        self.distance.setValidator(QDoubleValidator(0.1, 100, 1))

        self.moveButtonLabel = QLabel("Execute Move:")
        self.moveButton = QPushButton("MOVE")
        self.moveButton.clicked.connect(self.executeMove)

        self.nextButtonMove = QPushButton("Next")
        self.nextButtonMove.clicked.connect(self.nextButtonClicked)

        layout = QGridLayout()
        layout.addWidget(self.moveLabel, 0,0)
        layout.addWidget(self.moveAxisLabel, 1, 0)
        layout.addWidget(self.moveAxis, 1, 1)
        layout.addWidget(self.distanceLabel, 2, 0)
        layout.addWidget(self.distance, 2, 1)
        layout.addWidget(self.moveButtonLabel, 3, 0)
        layout.addWidget(self.moveButton, 3, 1)
        layout.addWidget(self.nextButtonMove, 4, 1)

        widget = QWidget()
        widget.setLayout(layout)

        return widget


    # pulse window specifies scope and pulser paramters
    def pulseWindow(self):

        if self.experimentType == 'Setup':
            self.pulseLabel = QLabel("Run a test pulse to verify the pulser and oscilloscope connection.\n")
        else:
            self.pulseLabel = QLabel("Define ultrasonic pulse and collection parameters:")

        self.transducerFrequencyLabel = QLabel("Central frequency of ultrasonic transducer (MHz):")
        self.transducerFrequency = QLineEdit("2.25")
        self.transducerFrequency.setValidator(QDoubleValidator(0.01, 100, 3))

        self.pulserType = QLabel("Type of ultrasonic pulser:")
        self.pulser = QComboBox()
        self.pulser.addItems(["Standard", "Tone Burst"])

        self.measureTimeLabel = QLabel("Approximate measurement time (us):\n"
                                       "Note: this can be changed by the Picoscope time interval selection.\n"
                                       "If the measure time is changed, it will be printed in the console.")
        self.measureTime = QLineEdit("20")
        self.measureTime.setValidator(QDoubleValidator(0.001, 1000, 3))

        self.measureDelayLabel = QLabel("Delay after trigger pulse is received before measurement starts (us):")
        self.measureDelay = QLineEdit("10")
        self.measureDelay.setValidator(QDoubleValidator(0.001, 1000, 3))

        self.voltageRangeLabel = QLabel("Voltage range on the oscilloscope (V)")
        self.voltageRange = QComboBox()
        self.voltageRange.addItems(["0.02", "0.05", "0.1", "0.2", "0.5", "1", "2", "5", "10", "20"])

        self.voltageAutoRangeLabel = QLabel("Automatically find the optimal voltage range during a measurement:\n"
                                            "Note: this can increase scan collection time, but prevents measurement artifacts due to large amplitude changes.")
        self.voltageAutoRange = QCheckBox()
        self.voltageAutoRange.setChecked(True)

        self.samplesLabel = QLabel("Number of data points per wave (Measure time / number of data points = time resolution):")
        self.samples = QLineEdit("1000")
        self.samples.setValidator(QIntValidator(1, 10000))

        self.wavesLabel = QLabel("Number of waveforms to average per measurement:")
        self.waves = QLineEdit("1000")
        self.waves.setValidator(QIntValidator(1, 10000))

        self.halfCyclesLabel = QLabel("For tone burst pulser only: number of half cycles per tone burst:")
        self.halfCycles = QLineEdit("2")
        self.halfCycles.setValidator(QIntValidator(1,32))

        # add port information for setup
        if self.experimentType == 'Setup':
            self.pulserPortLabel = QLabel("USB Port of Pulser (COM# or /dev/ttyUSB#) (Compact Pulser Only):")
            self.pulserPort = QLineEdit("COM5")
            self.dllFileLabel = QLabel("Location of SDK DLL File (Tone Burst Pulser Only):")
            self.dllFile = QLineEdit("C://USUTSDK//USDBUTSDKC//USBUT.dll")

        self.executePulseButton = QPushButton("Execute Pulse")
        self.executePulseButton.clicked.connect(self.executeSinglePulse)

        self.returnToMoveButton = QPushButton("Return To Move")
        self.returnToMoveButton.clicked.connect(self.returnToMove)

        self.nextButtonPulse = QPushButton("Next")
        self.nextButtonPulse.clicked.connect(self.nextButtonClicked)

        layout = QGridLayout()
        layout.addWidget(self.pulseLabel, 0, 0)
        layout.addWidget(self.transducerFrequencyLabel, 1, 0)
        layout.addWidget(self.transducerFrequency, 1, 1)
        layout.addWidget(self.pulserType, 2, 0)
        layout.addWidget(self.pulser, 2, 1)
        layout.addWidget(self.measureTimeLabel, 3, 0)
        layout.addWidget(self.measureTime, 3, 1)
        layout.addWidget(self.measureDelayLabel, 4, 0)
        layout.addWidget(self.measureDelay, 4, 1)
        layout.addWidget(self.voltageRangeLabel, 5, 0)
        layout.addWidget(self.voltageRange, 5, 1)
        layout.addWidget(self.voltageAutoRangeLabel, 6, 0)
        layout.addWidget(self.voltageAutoRange, 6, 1)
        layout.addWidget(self.samplesLabel, 7, 0)
        layout.addWidget(self.samples, 7, 1)
        layout.addWidget(self.wavesLabel, 8, 0)
        layout.addWidget(self.waves, 8, 1)
        layout.addWidget(self.halfCyclesLabel, 9, 0)
        layout.addWidget(self.halfCycles, 9, 1)
        if self.experimentType == 'Setup':
            layout.addWidget(self.pulserPortLabel, 10, 0)
            layout.addWidget(self.pulserPort, 10, 1)
            layout.addWidget(self.dllFileLabel, 11, 0)
            layout.addWidget(self.dllFile, 11, 1)
            layout.addWidget(self.executePulseButton, 12, 1)
            layout.addWidget(self.returnToMoveButton, 13, 1)
            layout.addWidget(self.nextButtonPulse, 14, 1)
        else:
            layout.addWidget(self.executePulseButton, 10, 1)
            layout.addWidget(self.returnToMoveButton, 11, 1)
            layout.addWidget(self.nextButtonPulse, 12, 1)

        widget = QWidget()
        widget.setLayout(layout)
        return widget

    # time specifies times for repeat pulse and multi scan
    def timeWindow(self):

        self.timeLabel = QLabel("Define experiment time parameters for Repeat Pulse or Multi Scan:")

        self.scanIntervalLabel = QLabel("Minimum time between starting scans (s):")
        self.scanInterval = QLineEdit("1800")
        self.scanInterval.setValidator(QIntValidator(1, 500000))

        self.numberOfScansLabel = QLabel("Number of scans to run:")
        self.numberOfScans = QLineEdit("10")
        self.numberOfScans.setValidator(QIntValidator(1, 10000))

        self.multiScanTimeExplanation = QLabel("Note: the minimum duration of a multi scan experiment is the time between scans times number of scans.\n"
                                               "If the actual time per scan is greater than the minimum time between scans, the next scan will\n"
                                               "start immediately after the previous and the total experiment time will be greater than the minimum.")

        self.pulseIntervalLabel = QLabel("Pulse interval (s):")
        self.pulseInterval = QLineEdit("1")
        self.pulseInterval.setValidator(QDoubleValidator(0.0001, 100000, 4))

        self.experimentTimeLabel = QLabel("Experiment time (s):")
        self.experimentTime = QLineEdit("10")
        self.experimentTime.setValidator(QDoubleValidator(0.1, 10000000, 1))

        self.nextButtonTime = QPushButton("Next")
        self.nextButtonTime.clicked.connect(self.nextButtonClicked)

        layout = QGridLayout()
        layout.addWidget(self.timeLabel, 0, 0)

        if self.experimentType == 'Repeat Pulse Measurement':

            layout.addWidget(self.pulseIntervalLabel, 1, 0)
            layout.addWidget(self.pulseInterval, 1, 1)
            layout.addWidget(self.experimentTimeLabel, 2, 0)
            layout.addWidget(self.experimentTime, 2, 1)

        elif self.experimentType == 'Multiple Scans':

            layout.addWidget(self.scanIntervalLabel, 1, 0)
            layout.addWidget(self.scanInterval, 1, 1)
            layout.addWidget(self.numberOfScansLabel, 2, 0)
            layout.addWidget(self.numberOfScans, 2, 1)
            layout.addWidget(self.multiScanTimeExplanation, 3, 0)

        layout.addWidget(self.nextButtonTime, 4, 1)

        widget = QWidget()
        widget.setLayout(layout)
        return widget

    # scan specifies scan length
    def scanWindow(self):

        self.scanLabel = QLabel("Define length parameters of the scan:")

        self.primaryAxisLabel = QLabel("Primary scan axis:")
        self.primaryAxis = QComboBox()
        self.primaryAxis.addItems(['X', 'Y', 'Z'])

        self.primaryAxisRangeLabel = QLabel("Primary axis range (mm):")
        self.primaryAxisRange = QLineEdit("10")
        self.primaryAxisRange.setValidator(QDoubleValidator(0.1, 100, 1))

        self.primaryAxisStepLabel = QLabel("Primary axis step size (mm):")
        self.primaryAxisStep = QLineEdit("0.5")
        self.primaryAxisStep.setValidator(QDoubleValidator(0.1, 100, 1))

        self.secondaryAxisLabel = QLabel("Secondary scan axis:")
        self.secondaryAxis = QComboBox()
        self.secondaryAxis.addItems(['X', 'Y', 'Z'])

        self.secondaryAxisRangeLabel = QLabel("Secondary axis range (mm):")
        self.secondaryAxisRange = QLineEdit("10")
        self.secondaryAxisRange.setValidator(QDoubleValidator(0.1, 100, 1))

        self.secondaryAxisStepLabel = QLabel("Secondary axis step size (mm):")
        self.secondaryAxisStep = QLineEdit("0.5")
        self.secondaryAxisStep.setValidator(QDoubleValidator(0.1, 100, 1))

        self.nextButtonTime = QPushButton("Next")
        self.nextButtonTime.clicked.connect(self.nextButtonClicked)

        layout = QGridLayout()
        layout.addWidget(self.scanLabel, 0, 0)
        layout.addWidget(self.primaryAxisLabel, 1, 0)
        layout.addWidget(self.primaryAxis, 1, 1)
        layout.addWidget(self.primaryAxisRangeLabel, 2, 0)
        layout.addWidget(self.primaryAxisRange, 2, 1)
        layout.addWidget(self.primaryAxisStepLabel, 3, 0)
        layout.addWidget(self.primaryAxisStep, 3, 1)
        layout.addWidget(self.secondaryAxisLabel, 4, 0)
        layout.addWidget(self.secondaryAxis, 4, 1)
        layout.addWidget(self.secondaryAxisRangeLabel, 5, 0)
        layout.addWidget(self.secondaryAxisRange, 5, 1)
        layout.addWidget(self.secondaryAxisStepLabel, 6, 0)
        layout.addWidget(self.secondaryAxisStep, 6, 1)
        layout.addWidget(self.nextButtonTime, 7, 1)
        # todo: add a safety check and a dialog box if the scan dimensions are invalid

        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def saveWindow(self):

        self.saveLabel = QLabel("Define saving parameters:")

        self.experimentFolderLabel = QLabel("Save directory:")
        self.experimentFolderName = QLabel("No Folder Selected")
        self.experimentFolderButton = QPushButton("Select Directory")
        # todo: dialog box repeats before accepting selection. still works, so it is a low priority for debugging
        self.experimentFolderButton.clicked.connect(self.dirButtonClicked)

        self.experimentNameLabel = QLabel("Name of experiment:")
        self.experimentName = QLineEdit("sample_name")

        self.saveFormatLabel = QLabel("Save format:")
        self.saveFormat = QComboBox()
        self.saveFormat.addItems(["SQLite3 (recommended)", "JSON"])

        self.pickleDataLabel = QLabel("Pickle data after collection:")
        self.pickleData = QCheckBox()
        self.pickleData.setChecked(False)

        self.nextButtonSave = QPushButton("Next")
        self.nextButtonSave.clicked.connect(self.nextButtonClicked)

        layout = QGridLayout()
        layout.addWidget(self.saveLabel, 0, 0)
        layout.addWidget(self.experimentFolderLabel, 1, 0)
        layout.addWidget(self.experimentFolderName, 1, 1)
        layout.addWidget(self.experimentFolderButton, 2, 1)
        layout.addWidget(self.experimentNameLabel, 3, 0)
        layout.addWidget(self.experimentName, 3, 1)
        layout.addWidget(self.saveFormatLabel, 4, 0)
        layout.addWidget(self.saveFormat, 4, 1)
        layout.addWidget(self.pickleDataLabel, 5, 0)
        layout.addWidget(self.pickleData, 5, 1)
        layout.addWidget(self.nextButtonSave, 6, 1)

        widget = QWidget()
        widget.setLayout(layout)
        return widget

    # this window summarizes all of the experimental parameters and gives the option to start the experiment or abort back to init
    # its going to be long and tedious...
    def experimentWindow(self):

        self.experimentLabel = QLabel("Double check experimental parameters and run experiment:")
        layout = QGridLayout()
        layout.addWidget(self.experimentLabel, 0, 0)

        self.pulseParametersLabel = QLabel("Ultrasound Parameters:")
        layout.addWidget(self.pulseParametersLabel, 1, 0)
        layout.addWidget(self.transducerFrequencyLabel, 2, 0)
        layout.addWidget(self.transducerFrequency, 2, 1)
        layout.addWidget(self.pulserType, 3, 0)
        layout.addWidget(self.pulser, 3, 1)
        layout.addWidget(self.measureTimeLabel, 4, 0)
        layout.addWidget(self.measureTime, 4, 1)
        layout.addWidget(self.measureDelayLabel, 5, 0)
        layout.addWidget(self.measureDelay, 5, 1)
        layout.addWidget(self.voltageRangeLabel, 6, 0)
        layout.addWidget(self.voltageRange, 6, 1)
        layout.addWidget(self.voltageAutoRangeLabel, 7, 0)
        layout.addWidget(self.voltageAutoRange, 7, 1)
        layout.addWidget(self.samplesLabel, 8, 0)
        layout.addWidget(self.samples, 8, 1)
        layout.addWidget(self.wavesLabel, 9, 0)
        layout.addWidget(self.waves, 9, 1)
        layout.addWidget(self.halfCyclesLabel, 10, 0)
        layout.addWidget(self.halfCycles, 10, 1)

        self.saveParametersLabel = QLabel("Save Parameters:")
        layout.addWidget(self.saveParametersLabel, 11, 0)
        layout.addWidget(self.experimentFolderLabel, 12, 0)
        layout.addWidget(self.experimentFolderName, 12, 1)
        layout.addWidget(self.experimentFolderButton, 13, 1)
        layout.addWidget(self.experimentNameLabel, 14, 0)
        layout.addWidget(self.experimentName, 14, 1)
        layout.addWidget(self.saveFormatLabel, 15, 0)
        layout.addWidget(self.saveFormat, 15, 1)
        layout.addWidget(self.pickleDataLabel, 16, 0)
        layout.addWidget(self.pickleData, 16, 1)

        if self.experimentType == 'Repeat Pulse Measurement':

            self.repeatPulseLabel = QLabel("Repeat Pulse Parameters:")
            layout.addWidget(self.repeatPulseLabel, 17, 0)
            layout.addWidget(self.pulseIntervalLabel, 18, 0)
            layout.addWidget(self.pulseInterval, 18, 1)
            layout.addWidget(self.experimentTimeLabel, 19, 0)
            layout.addWidget(self.experimentTime, 19, 1)

            self.executeRepeatPulseButton = QPushButton("Execute Repeat Pulse")
            self.executeRepeatPulseButton.clicked.connect(self.executeRepeatPulse)
            self.cancelButton = QPushButton("Cancel (Return To Start)")
            self.cancelButton.clicked.connect(self.nextButtonClicked)

            layout.addWidget(self.executeRepeatPulseButton, 20, 1)
            layout.addWidget(self.cancelButton, 21, 1)

        if self.experimentType == 'Single Scan' or self.experimentType == 'Multiple Scans':

            self.scanLabel = QLabel("Scan Parameters:")
            layout.addWidget(self.scanLabel, 17, 0)
            layout.addWidget(self.primaryAxisLabel, 18, 0)
            layout.addWidget(self.primaryAxis, 18, 1)
            layout.addWidget(self.primaryAxisRangeLabel, 19, 0)
            layout.addWidget(self.primaryAxisRange, 19, 1)
            layout.addWidget(self.primaryAxisStepLabel, 20, 0)
            layout.addWidget(self.primaryAxisStep, 20, 1)
            layout.addWidget(self.secondaryAxisLabel, 21, 0)
            layout.addWidget(self.secondaryAxis, 21, 1)
            layout.addWidget(self.secondaryAxisRangeLabel, 22, 0)
            layout.addWidget(self.secondaryAxisRange, 22, 1)
            layout.addWidget(self.secondaryAxisStepLabel, 23, 0)
            layout.addWidget(self.secondaryAxisStep, 23, 1)

        if self.experimentType == 'Single Scan':

            self.executeSingleScanButton = QPushButton("Execute Scan")
            self.executeSingleScanButton.clicked.connect(self.executeSingleScan)
            self.cancelButton = QPushButton("Cancel (Return To Start)")
            self.cancelButton.clicked.connect(self.nextButtonClicked)

            layout.addWidget(self.executeSingleScanButton, 24, 1)
            layout.addWidget(self.cancelButton, 25, 1)

        if self.experimentType == 'Multiple Scans':

            self.multiScanTimeLabel = QLabel("Multiple Scan Times:")
            layout.addWidget(self.multiScanTimeLabel, 24, 0)
            layout.addWidget(self.scanIntervalLabel, 25, 0)
            layout.addWidget(self.scanInterval, 25, 1)
            layout.addWidget(self.numberOfScansLabel, 26, 0)
            layout.addWidget(self.numberOfScans, 26, 1)
            layout.addWidget(self.multiScanTimeExplanation, 27, 0)

            self.executeMultiScanButton = QPushButton("Execute Scans")
            self.executeMultiScanButton.clicked.connect(self.executeMultiScan)
            self.cancelButton = QPushButton("Cancel (Return To Start)")
            self.cancelButton.clicked.connect(self.nextButtonClicked)

            layout.addWidget(self.executeMultiScanButton, 28, 1)
            layout.addWidget(self.cancelButton, 29, 1)

        widget = QWidget()
        widget.setLayout(layout)
        return widget

    ############## SETUP WINDOWS #########################################
    # Setup experiment consists of the following phases:
    # 1) Set the USB port for the scanner. Verify by attempting to move
    # 2) Prompt the user to disconnect everything from the printer head and run the homing function
    # 3) Prompt the user to measure the transducer holder height and verify the scanner dimensions
    # 4) Prompt the user to move the scanner to a more centered position
    # 5) Run a modified single pulse experiment with the pulser port / dll file option exposed
    # 6) Dump collected info into a json file
    def scannerSetupWindow(self):

        self.scannerConnectionInstructions = QLabel("First determine the USB port that the scanner is plugged into.\n"
                                                    "The port will be verified by doing a short move 5mm to the left or right.\n"
                                                    "If you do not see the scanner move, try a different port")
        self.scannerPortLabel = QLabel("USB Port Name. On Windows this will be COM# and on Linus /dev/ttyUSB#:")
        self.scannerPort = QLineEdit("COM1")

        self.testMoveDirectionLabel = QLabel("Direction of test move:")
        self.testMoveDirection = QComboBox()
        self.testMoveDirection.addItems(["Left", "Right"])

        self.executeTestMoveButton = QPushButton("Execute Test Move")
        self.executeTestMoveButton.clicked.connect(self.executeTestMove)

        self.scannerConnectionNextButton = QPushButton("Next")
        self.scannerConnectionNextButton.clicked.connect(self.nextButtonClicked)

        layout = QGridLayout()
        layout.addWidget(self.scannerConnectionInstructions, 0, 0)
        layout.addWidget(self.scannerPortLabel, 1, 0)
        layout.addWidget(self.scannerPort, 1, 1)
        layout.addWidget(self.testMoveDirectionLabel, 2, 0)
        layout.addWidget(self.testMoveDirection, 2, 1)
        layout.addWidget(self.executeTestMoveButton, 3, 1)
        layout.addWidget(self.scannerConnectionNextButton, 4, 1)

        widget = QWidget()
        widget.setLayout(layout)

        return widget

    def homingWindow(self):

        self.scannerHomingInstructions = QLabel("Homing the scanner calibrates its position. This must be done at least once\n"
                                                "in order for the scanner to be moved safely.")
        self.scannerHomingWarning = QLabel("WARNING: REMOVE THE TRANSDUCER HOLDER FROM THE SCANNER HEAD BEFORE HOMING.\n"
                                           "FAILURE TO DO SO MAY RESULT IN DAMAGE TO THE HOLDER OR THE SCANNER!")
        self.homingButton = QPushButton("Run Homing Protocol")
        self.homingButton.clicked.connect(self.executeHoming)
        self.homingNextButton = QPushButton("Next")
        self.homingNextButton.clicked.connect(self.nextButtonClicked)

        layout = QGridLayout()
        layout.addWidget(self.scannerHomingInstructions)
        layout.addWidget(self.scannerHomingWarning)
        layout.addWidget(self.homingButton)
        layout.addWidget(self.homingNextButton)

        widget = QWidget()
        widget.setLayout(layout)

        return widget

    def measureDimensionsWindow(self):

        self.measureDimensionsInstructions = QLabel("Measure the transducer holder height and verify the scanning dimensions.\n"
                                                    "This information is used to prevent unsafe moves of the scanner.")
        self.transducerHeightLabel = QLabel("Transducer holder height (mm):")
        self.transducerHeight = QLineEdit("50")
        self.transducerHeight.setValidator(QDoubleValidator(1, 200, 1))

        self.scannerWidthLabel = QLabel("Scanner Width (X-Axis) (mm):")
        self.scannerWidth = QLineEdit("220")
        self.scannerWidth.setValidator(QDoubleValidator(1, 1000, 1))

        self.scannerLengthLabel = QLabel("Scanner Length (Y-Axis) (mm):")
        self.scannerLength = QLineEdit("220")
        self.scannerLength.setValidator(QDoubleValidator(1, 1000, 1))

        self.scannerHeightLabel = QLabel("Scanner Height (Z-Axis) (mm):")
        self.scannerHeight = QLineEdit("240")
        self.scannerHeight.setValidator(QDoubleValidator(1, 1000, 1))

        self.scannerDimensionsNextButton = QPushButton("Next")
        self.scannerDimensionsNextButton.clicked.connect(self.nextButtonClicked)

        layout = QGridLayout()
        layout.addWidget(self.measureDimensionsInstructions, 0, 0)
        layout.addWidget(self.transducerHeightLabel, 1, 0)
        layout.addWidget(self.transducerHeight, 1, 1)
        layout.addWidget(self.scannerWidthLabel, 2, 0)
        layout.addWidget(self.scannerWidth, 2, 1)
        layout.addWidget(self.scannerLengthLabel, 3, 0)
        layout.addWidget(self.scannerLength, 3, 1)
        layout.addWidget(self.scannerHeightLabel, 4, 0)
        layout.addWidget(self.scannerHeight, 4, 1)
        layout.addWidget(self.scannerDimensionsNextButton, 5, 1)

        widget = QWidget()
        widget.setLayout(layout)

        return widget


    #########################################################################
    ################# DIALOG BOXES #########################################
    #######################################################################

    # create warning message subclass
    class WarningDialog(QDialog):
        def __init__(self, warningMessage : str, parent = None):
            super().__init__()

            self.setWindowTitle("Warning!")

            QBtn = QDialogButtonBox.Ok

            self.warningButtonBox = QDialogButtonBox(QBtn)
            self.warningButtonBox.clicked.connect(self.close)

            self.layout = QVBoxLayout()
            message = QLabel(warningMessage)
            self.layout.addWidget(message)
            self.layout.addWidget(self.warningButtonBox)
            self.setLayout(self.layout)
            self.exec()

    def dirButtonClicked(self):

        dlg = QFileDialog(self)
        dlg.setFileMode(QFileDialog.Directory)
        dlg.exec()
        file = str(dlg.getExistingDirectory(self, "Select Directory"))
        self.experimentFolderName.setText(file)

    #######################################################################3
    ############## HELPER FUNCTIONS ########################################
    ########################################################################

    # inputs the name of the target window. grabs the stacked widget index of the window and changes the index of the stacked widget
    # also updates the self.windowType field to destinationWindow
    def switchWindow(self, destinationWindow : str):

        self.windowType = destinationWindow
        destinationIndex = self.windowIndices[destinationWindow]

        # the experiment window must be remade right before it is shown to be properly formatted and filled with the chosen values
        if destinationWindow == 'experiment':
            self.remakeWindow('experiment')

        self.mainWidget.setCurrentIndex(destinationIndex)

    # inputs a windowType. removes that window's current widget, remakes the widget and inserts it back in its old place
    # this is used when a window changes in response to the inputs in a previous window
    def remakeWindow(self, window):

        # get index of window
        index = self.windowIndices[window]

        # get the widget at that index and remove it
        self.mainWidget.removeWidget(self.mainWidget.widget(index))

        # run the correct window function
        newWidget = self.runWindowFunction(window)

        # insert that widget into the correct index
        self.mainWidget.insertWidget(index, newWidget)

    # helper function to remake all windows except the init one
    # this re-initializes parameters and prevents widgets from disappearing after the experiment window is displayed
    def remakeWindowsExceptInitAndExperiment(self):

        for window in self.windowIndices.keys():
            if window != 'init' and window != 'experiment':
                self.remakeWindow(window)

    # takes a windowType string and runs the corresponding window widget creation function
    def runWindowFunction(self, windowType):

        match windowType:
            case 'init':
                return self.initWindow()
            case 'move':
                return self.moveWindow()
            case 'pulse':
                return self.pulseWindow()
            case 'save':
                return self.saveWindow()
            case 'scan':
                return self.scanWindow()
            case 'time':
                return self.timeWindow()
            case 'experiment':
                return self.experimentWindow()
            case 'scannerSetup':
                return self.scannerSetupWindow()
            case 'homing':
                return self.homingWindow()
            case 'dimensions':
                return self.measureDimensionsWindow()

    # returnToMove is made as a separate function to connect to the returnToMoveButton because directly calling switchWindow
    # on the button clicked event causes problems with immediately executing the window change
    def returnToMove(self):
        self.switchWindow('move')

    # a function that reads setup_parameters.json and pulls in the relevant values
    # it will display a warning dialog if the file is not found or improperly formatted
    def readSetupJSON(self):

        currentDir = os.path.dirname(os.path.realpath(__file__))
        jsonFile = os.path.join(currentDir,'setup_parameters.json')

        if not os.path.isfile(jsonFile):
            self.WarningDialog("setup_parameters.json file not found. Either run the Setup experiment or\n"
                               "check that all necessary parameters are correct in runUltrasonicExperiment.py.")

        else:
            # load the file
            with open(jsonFile, 'r+') as f:
                jsonData = json.load(f)

            # copy the data into the params dict
            for key in jsonData.keys():
                self.params[key] = jsonData[key]

    # takes the data taken from the Setup experiment and writes it to a json file
    def writeSetupJSON(self):

        # gather data from widgets
        jsonDict = {}
        jsonDict['pulserPort'] = self.pulserPort.text()
        jsonDict['scannerPort'] = self.scannerPort.text()
        jsonDict['dllFile'] = self.dllFile.text()
        jsonDict['transducerHolderHeight'] = float(self.transducerHeight.text())
        jsonDict['scannerMaxDimensions'] = (float(self.scannerWidth.text()),
                                            float(self.scannerLength.text()),
                                            float(self.scannerHeight.text()))

        # if the previous file exists, overwrite it
        currentDir = os.path.dirname(os.path.realpath(__file__))
        jsonFile = os.path.join(currentDir,'setup_parameters.json')
        with open(jsonFile, "w") as f:
            json.dump(jsonDict, f)

    ############################################################################
    ######### EXECUTE EXPERIMENT FUNCTIONS ###################################
    #########################################################################

    # execute a physical move the gantry
    def executeMove(self):

        # change status of button while move is executing
        self.moveButton.setText("MOVING...")
        self.moveButton.setEnabled(False)
        self.moveButton.repaint()

        # gather the input parameters from widgets
        self.params['axis'] = self.moveAxis.currentText()
        self.params['distance'] = float(self.distance.text())

        # execute the move
        # moveRes = setup.moveScanner(self.params)
        #
        # # show a dialog box if move is invalid
        # if moveRes == -1:
        #     self.WarningDialog("Specified move is unsafe and will not execute. Check the move parameters and the position of the\n"
        #                        "transducer holder and try again. If you are sure the move should be safe, hit Abort and run the Setup experiment\n"
        #                        "to ensure the size parameters are correct and the gantry has been homed.")

        # wait a short time before unlocking the button
        time.sleep(0.5)

        # change button back to normal
        self.moveButton.setText("MOVE")
        self.moveButton.setEnabled(True)

    # a special constrained version of move for testing the USB port connection
    # this enables calling scanner.move() with checkMoveSafety = False and allows special error handling for timeouts
    def executeTestMove(self):

        # change status of button while move is executing
        self.executeTestMoveButton.setText("MOVING...")
        self.executeTestMoveButton.setEnabled(False)
        self.executeTestMoveButton.repaint()

        # gather parameters
        self.params['pulserPort'] = self.scannerPort.text()
        direction = self.testMoveDirection.currentText()
        # set move direction and axis. It is constrained to move left or right so axis = 'x'
        self.params['axis'] = 'X'
        if direction == "Left":
            self.params['distance'] = -5
        else:
            self.params['distance'] = 5

        # need to add filler info for 'transducerHolderHeight' and 'scannerMaxDimensions'
        self.params['transducerHolderHeight'] = 50
        self.params['scannerMaxDimensions'] = (220, 220, 240)

        print('test move')
        # try:
        #     scanner = sc.Scanner(self.params)
        # except SerialException:
        #     self.WarningDialog("Serial port exception raised. Try a different port.")
        #
        # scanner.move(self.params['axis'], self.params['distance'], checkMoveSafety = False)
        # scanner.close()

        # change button back to normal
        self.executeTestMoveButton.setText("MOVE")
        self.executeTestMoveButton.setEnabled(True)

    def executeHoming(self):

        print('test homing')
        # scanner = sc.Scanner(self.params)
        # scanner.home()
        # scanner.close()

    def executeSinglePulse(self):

        # change status of button while experiment is running
        self.executePulseButton.setText("Running Pulse...")
        self.executePulseButton.setEnabled(False)
        self.executePulseButton.repaint()

        # gather parameters
        self.params['transducerFrequency'] = float(self.transducerFrequency.text())
        self.params['pulserType'] = self.pulser.currentText()
        self.params['measureTime'] = float(self.measureTime.text())
        self.params['measureDelay'] = float(self.measureDelay.text())
        self.params['voltageRange'] = float(self.voltageRange.currentText())
        self.params['voltageAutoRange'] = self.voltageAutoRange.isChecked()
        self.params['waves'] = int(self.waves.text())
        self.params['samples'] = int(self.samples.text())
        self.params['halfCycles'] = int(self.halfCycles.text())

        if self.experimentType == 'Setup':
            self.params['pulserPort'] = self.pulserPort.text()
            self.params['dllFile'] = self.dllFile.text()

        # todo: add error handling
        # setup.singlePulseMeasure(self.params)

        # change button back to normal
        self.executePulseButton.setText("Execute Pulse")
        self.executePulseButton.setEnabled(True)

    def executeRepeatPulse(self):

        # change status of button while experiment is running
        self.executeRepeatPulseButton.setText("Experiment Running...")
        self.executeRepeatPulseButton.setEnabled(False)
        self.executeRepeatPulseButton.repaint()

        # gather parameters
        self.params['transducerFrequency'] = float(self.transducerFrequency.text())
        self.params['pulserType'] = self.pulser.currentText()
        self.params['measureTime'] = float(self.measureTime.text())
        self.params['measureDelay'] = float(self.measureDelay.text())
        self.params['voltageRange'] = float(self.voltageRange.currentText())
        self.params['voltageAutoRange'] = self.voltageAutoRange.isChecked()
        self.params['waves'] = int(self.waves.text())
        self.params['samples'] = int(self.samples.text())
        self.params['halfCycles'] = int(self.halfCycles.text())

        self.params['experimentFolder'] = self.experimentFolderName.text()
        self.params['experimentName'] = self.experimentName.text()
        self.params['experimentBaseName'] = self.experimentName.text()
        self.params['saveFormat'] = self.saveFormat.currentText()
        self.params['pickleData'] = self.pickleData.isChecked()

        self.params['pulseInterval'] = float(self.pulseInterval.text())
        self.params['experimentTime'] = float(self.experimentTime.text())

        # run experiment
        #repeatPulse.repeatPulse(self.params)

        # change button back to normal
        self.executeRepeatPulseButton.setText("Execute Repeat Pulse")
        self.executeRepeatPulseButton.setEnabled(True)

    def executeSingleScan(self):

        # change status of button while experiment is running
        self.executeSingleScanButton.setText("Scan Running...")
        self.executeSingleScanButton.setEnabled(False)
        self.executeSingleScanButton.repaint()

        # gather parameters
        self.params['transducerFrequency'] = float(self.transducerFrequency.text())
        self.params['pulserType'] = self.pulser.currentText()
        self.params['measureTime'] = float(self.measureTime.text())
        self.params['measureDelay'] = float(self.measureDelay.text())
        self.params['voltageRange'] = float(self.voltageRange.currentText())
        self.params['voltageAutoRange'] = self.voltageAutoRange.isChecked()
        self.params['waves'] = int(self.waves.text())
        self.params['samples'] = int(self.samples.text())
        self.params['halfCycles'] = int(self.halfCycles.text())

        self.params['experimentFolder'] = self.experimentFolderName.text()
        self.params['experimentName'] = self.experimentName.text()
        self.params['experimentBaseName'] = self.experimentName.text()
        self.params['saveFormat'] = self.saveFormat.currentText()
        self.params['pickleData'] = self.pickleData.isChecked()

        self.params['primaryAxis'] = self.primaryAxis.currentText()
        self.params['secondaryAxis'] = self.secondaryAxis.currentText()
        self.params['primaryAxisRange'] = float(self.primaryAxisRange.text())
        self.params['primaryAxisStep'] = float(self.primaryAxisStep.text())
        self.params['secondaryAxisRange'] = float(self.secondaryAxisRange.text())
        self.params['secondaryAxisStep'] = float(self.secondaryAxisStep.text())

        print(self.params)
        # scan.runScan(self.params)

        # change button back to normal
        self.executeSingleScanButton.setText("Execute Scan")
        self.executeSingleScanButton.setEnabled(True)

    def executeMultiScan(self):

        # change status of button while experiment is running
        self.executeMultiScanButton.setText("Scans Running...")
        self.executeMultiScanButton.setEnabled(False)
        self.executeMultiScanButton.repaint()

        # gather parameters
        self.params['transducerFrequency'] = float(self.transducerFrequency.text())
        self.params['pulserType'] = self.pulser.currentText()
        self.params['measureTime'] = float(self.measureTime.text())
        self.params['measureDelay'] = float(self.measureDelay.text())
        self.params['voltageRange'] = float(self.voltageRange.currentText())
        self.params['voltageAutoRange'] = self.voltageAutoRange.isChecked()
        self.params['waves'] = int(self.waves.text())
        self.params['samples'] = int(self.samples.text())
        self.params['halfCycles'] = int(self.halfCycles.text())

        self.params['experimentFolder'] = self.experimentFolderName.text()
        self.params['experimentName'] = self.experimentName.text()
        self.params['experimentBaseName'] = self.experimentName.text()
        self.params['saveFormat'] = self.saveFormat.currentText()
        self.params['pickleData'] = self.pickleData.isChecked()

        self.params['primaryAxis'] = self.primaryAxis.currentText()
        self.params['secondaryAxis'] = self.secondaryAxis.currentText()
        self.params['primaryAxisRange'] = float(self.primaryAxisRange.text())
        self.params['primaryAxisStep'] = float(self.primaryAxisStep.text())
        self.params['secondaryAxisRange'] = float(self.secondaryAxisRange.text())
        self.params['secondaryAxisStep'] = float(self.secondaryAxisStep.text())

        self.params['scanInterval'] = int(self.scanInterval.text())
        self.params['numberOfScans'] = int(self.numberOfScans.text())

        # change button back to normal
        self.executeMultiScanButton.setText("Execute Scans")
        self.executeMultiScanButton.setEnabled(True)

# function called from runUltrasonicExperiment to start setup through gui
#TODO: currently passing in params to get port names, default values. This might be better to update?
def startGUI(params : dict):

    app = QApplication([])

    window = MainWindow(params)
    window.show()

    app.exec_()
