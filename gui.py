#todo: clean up imports!!!
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
# from PyQt5.QtWidgets import QFileDialog
import sys

#TODO:
# xmake an initial experiment select window
# xmake the move window
# xfigure out how to transition windows
# xdefine windows for other experiments
# move files to gui.py, integrate gui start into run script
# define control flow of experiment!
# figure out mouseover notes
# gather parameters from widgets
# define initialization experiment
#   save ports etc in a json file?
# clean up imports
# put main loop somewhere better


# windowType = init, move, pulse, save, scan, time
# experimentType = "Move", "Single Pulse Measurement", "Repeat Pulse Measurement", "Single Scan", "Multiple Scans"])
#
# algorithm:
# start on init window
# when next button is pressed, determine the next window to display based on current windowtype, experimenttype, and other info entered
# create functions for each type of window

class MainWindow(QMainWindow):

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        self.setWindowTitle("Ultrasound Experiment")

        self.windowType = 'init'
        self.experimentType = 'init'

        initWidget = self.initWindow()

        self.setCentralWidget(initWidget)

        nextWidget = self.nextButton.clicked.connect(self.nextButtonClicked)
        # container = QWidget()
        # container.setLayout(layout)
        #
        # printButton = QPushButton("Print")
        # printButton
        # startButton = QPushButton("Run Experiment")
        # startButton.setCheckable(True)
        # startButton.clicked.connect(self.startButtonClicked)
        # startButton.clicked.connect(self.startButtonToggled)
        # self.setCentralWidget(startButton)
        #
        # label = QLabel("Filler text")
        # label.setAlignment(Qt.AlignCenter)

        # self.setCentralWidget(container)

    # window layouts

    # init window is where experiment type is specified
    def initWindow(self):

        self.experimentSelect = QComboBox()
        self.experimentSelect.addItems(
            ["Move", "Single Pulse Measurement", "Repeat Pulse Measurement", "Single Scan", "Multiple Scans"])
        self.experimentSelectLabel = QLabel("Select Experiment Type: ")
        # self.input.textChanged.connect(self.label.setText)

        self.nextButton = QPushButton("Next")

        layout = QGridLayout()
        layout.addWidget(self.experimentSelectLabel, 0, 0)
        layout.addWidget(self.experimentSelect, 0, 1)
        layout.addWidget(self.nextButton, 1, 1)

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

        layout = QGridLayout()
        layout.addWidget(self.moveLabel, 0,0)
        layout.addWidget(self.moveAxisLabel, 1, 0)
        layout.addWidget(self.moveAxis, 1, 1)
        layout.addWidget(self.distanceLabel, 2, 0)
        layout.addWidget(self.distance, 2, 1)
        layout.addWidget(self.nextButton, 3, 1)

        widget = QWidget()
        widget.setLayout(layout)

        #todo: add a move button to execute experiment separate from the next button
        #TODO: add safety check and a dialog box if the move is invalid

        return widget

    # pulse window specifies scope and pulser paramters
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
        layout.addWidget(self.nextButton, 10, 1)

        widget = QWidget()
        widget.setLayout(layout)
        return widget

    # save specifies save location, file name, file type, and optional pickling

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

        layout.addWidget(self.nextButton, 4, 1)

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
        layout.addWidget(self.nextButton, 7, 1)
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
        layout.addWidget(self.nextButton, 6, 1)

        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def dirButtonClicked(self):

        dlg = QFileDialog(self)
        dlg.setFileMode(QFileDialog.Directory)
        dlg.exec()
        file = str(dlg.getExistingDirectory(self, "Select Directory"))
        self.experimentFolderName.setText(file)

    def nextButtonClicked(self):
        print("yes")

        # Handle initialization case first
        if self.windowType == 'init' and self.experimentType == 'init':

            # grab the experiment type from the combobox
            self.experimentType = self.experimentSelect.currentText()

            if self.experimentType == 'Move':
               widget = self.moveWindow()
               nextWidget = widget
               self.setCentralWidget(widget)

            elif self.experimentType == 'Single Pulse Measurement':
                widget = self.pulseWindow()
                nextWidget = widget
                self.setCentralWidget(widget)

            elif self.experimentType == 'Single Scan':
                widget = self.saveWindow()
                nextWidget = widget
                self.setCentralWidget(widget)

            elif self.experimentType == 'Repeat Pulse Measurement' or self.experimentType == 'Multiple Scans':
                widget = self.timeWindow()
                nextWidget = widget
                self.setCentralWidget(widget)


        #next button must not be overwritten!
        # self.nextButton = QPushButton("Next")
        # layout = QGridLayout()
        # layout.addWidget(self.nextButton, 1, 1)
        #
        # widget = QWidget()
        # widget.setLayout(layout)

        # nextWidget = widget
        # self.setCentralWidget(widget)

    def startButtonClicked(self):
        print("running Experiment")

    def startButtonToggled(self, checked):
        print(checked)

# function called from runUltrasonicExperiment to start setup through gui
def startGUI():
    app = QApplication([])

    window = MainWindow()
    window.show()

    app.exec_()
