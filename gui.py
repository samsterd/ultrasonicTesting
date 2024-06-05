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
from typing import Callable

#TODO:
# xmake an initial experiment select window
# xmake the move window
# xfigure out how to transition windows
# xdefine windows for other experiments
# xmove files to gui.py, integrate gui start into run script
# xdefine control flow of experiment!
#      xIt might be better to make buttons for moving from any window to any other relevant window?
# IMPLEMENT EVERYTHING AS QSTACKEDWIDGET()
# fix control flow to include timeWindow (forgot about that)
# create an experiment window that summarizes parameters and has option to abort or run
# create executeExperiment for every experiment
#   on move: change button to Moving..., make unclickable for duration
#   add progress bars?
# figure out mouseover notes
# gather parameters from widgets
# define initialization/setup experiment
#   save ports etc in a json file?
# clean up imports
# put main loop somewhere better?
# fill in option defaults based on values in params dict
# implement a back button


# windowType = init, move, pulse, save, scan, time, experiment
# windowIndex = {init : 0, move : 1, pul
# experimentType = init, "Move", "Single Pulse Measurement", "Repeat Pulse Measurement", "Single Scan", "Multiple Scans"])
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
        self.windowIndices = {'init' : 0, 'move' : 1, 'pulse' : 2, 'save' : 3, 'scan' : 4, 'time' : 5, 'experiment' : 6}

        # add widgets to stackedwidget in order defined by windowIndices
        self.mainWidget = QStackedWidget()
        self.mainWidget.addWidget(self.initWindow())

        # self.mainWidget.addWidget(self.experimentWindow())
        self.mainWidget.setCurrentIndex(0)

        self.setCentralWidget(self.mainWidget)


    # init window is where experiment type is specified
    #TODO: next button stops working after first return to init page
    def initWindow(self):

        self.experimentSelect = QComboBox()
        self.experimentSelect.addItems(
            ["Move", "Single Pulse Measurement", "Repeat Pulse Measurement", "Single Scan", "Multiple Scans"])
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

        #todo: add a move button to execute experiment separate from the next button
        #TODO: add safety check and a dialog box if the move is invalid

        return widget


    # pulse window specifies scope and pulser paramters
    #TODO: add a test pulse button
    def pulseWindow(self):

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
        layout.addWidget(self.nextButtonPulse, 10, 1)

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

        if self.experimentType == 'Repeat Pulse Measurement':
            print(self.pulser.currentText())
            # layout = QGridLayout()
            # # layout.addWidget(self.pulseLabel, 0, 0)
            # layout.addWidget(self.transducerFrequencyLabel, 1, 0)
            # layout.addWidget(self.transducerFrequency, 1, 1)
            # layout.addWidget(self.pulserType, 2, 0)
            # layout.addWidget(self.pulser, 2, 1)
            # layout.addWidget(self.measureTimeLabel, 3, 0)
            # layout.addWidget(self.measureTime, 3, 1)
            # layout.addWidget(self.measureDelayLabel, 4, 0)
            # layout.addWidget(self.measureDelay, 4, 1)
            # layout.addWidget(self.voltageRangeLabel, 5, 0)
            # layout.addWidget(self.voltageRange, 5, 1)
            # layout.addWidget(self.voltageAutoRangeLabel, 6, 0)
            # layout.addWidget(self.voltageAutoRange, 6, 1)
            # layout.addWidget(self.samplesLabel, 7, 0)
            # layout.addWidget(self.samples, 7, 1)
            # layout.addWidget(self.wavesLabel, 8, 0)
            # layout.addWidget(self.waves, 8, 1)
            # layout.addWidget(self.halfCyclesLabel, 9, 0)
            # layout.addWidget(self.halfCycles, 9, 1)
            # layout.addWidget(self.nextButton, 10, 1)
            #
            # widget = QWidget()
            # widget.setLayout(layout)
            # return widget

    # create warning message subclass
    class WarningDialog(QDialog):
        def __init__(self, warningMessage : str, parent = None):
            super().__init__()

            self.setWindowTitle("Warning!")

            QBtn = QDialogButtonBox.Abort | QDialogButtonBox.Ok

            self.warningButtonBox = QDialogButtonBox(QBtn)
            # Todo: make sure ok and abort are tied to correct actions. define actions to return to prev window vs go back to init
            # a hacky way to do this is to treat the abort button as hitting 'Next' after changing experimentType and windowType
            # self.warningButtonBox.accepted.connect(self.accept)
            # self.warningButtonBox.rejected.connect(self.accept)

            self.layout = QVBoxLayout()
            message = QLabel(warningMessage)
            self.layout.addWidget(message)
            self.layout.addWidget(self.warningButtonBox)
            self.setLayout(self.layout)

    def dirButtonClicked(self):

        dlg = QFileDialog(self)
        dlg.setFileMode(QFileDialog.Directory)
        dlg.exec()
        file = str(dlg.getExistingDirectory(self, "Select Directory"))
        self.experimentFolderName.setText(file)

    # this function handles control flow of the gui. uses the current window and experiment type to set the next window
    def nextButtonClicked(self):

        # Handle initialization case first
        if self.windowType == 'init' and self.experimentType == 'init':

            # grab the experiment type from the combobox
            self.experimentType = self.experimentSelect.currentText()

            # initialize the other windows after the experiment is chosen
            # this is done here instead of __init__ because some options are experiment-dependent
            self.mainWidget.addWidget(self.moveWindow())
            self.mainWidget.addWidget(self.pulseWindow())
            self.mainWidget.addWidget(self.saveWindow())
            self.mainWidget.addWidget(self.scanWindow())
            self.mainWidget.addWidget(self.timeWindow())

            if self.experimentType == 'Repeat Pulse Measurement':
                self.switchWindow('pulse')

            elif self.experimentType != 'Setup':
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

        # all unhandled cases (including experiment) go back to the init window
        else:

            self.switchWindow('init')

    # inputs the name of the target window. grabs the stacked widget index of the window and changes the index of the stacked widget
    # also updates the self.windowType field to destinationWindow
    def switchWindow(self, destinationWindow : str):
        self.windowType = destinationWindow
        destinationIndex = self.windowIndices[destinationWindow]
        self.mainWidget.setCurrentIndex(destinationIndex)

    # execute a physical move the gantry
    def executeMove(self):

        #todo: change the label while move is executing, set to unclickable?

        # gather the input parameters from widgets
        self.params['axis'] = self.moveAxis.currentText()
        self.params['distance'] = float(self.distance.text())

        print(self.params['axis'])
        print(self.params['distance'])

        # execute the move
        # moveRes = setup.moveScanner(self.params)
        #
        # # show a dialog box if move is invalid
        # if moveRes == -1:
        #     self.WarningDialog("Specified move is unsafe and will not execute. Check the move parameters and the position of the\n"
        #                        "transducer holder and try again. If you are sure the move should be safe, hit Abort and run the Setup experiment\n"
        #                        "to ensure the size parameters are correct and the gantry has been homed.")

# function called from runUltrasonicExperiment to start setup through gui
#TODO: currently passing in params to get port names, default values. This might be better to update?
def startGUI(params : dict):

    app = QApplication([])

    window = MainWindow(params)
    window.show()

    app.exec_()

startGUI({})