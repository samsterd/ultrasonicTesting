#Example usage of analysis functions

# Analysis functions are contained in the files pickleJar.py and sqliteUtils.py
import pickleJar as pj
import sqliteUtils as squ
import numpy as np
from numpy import fft
import os.path
import matplotlib.pyplot as plt

#####################################################################
########## Table of Contents ########################################
#####################################################################
# 1. Loading and analyzing a single file
# 2. Plotting a scan
# 3. Plotting a repeat pulse
# 4. Loading, analyzing, and plotting a multi scan
# 5. Example workflow
# Appendix : Analysis functions and usage

##############################################################
###############         1             #########################
############# Analyzing a single file #######################
############################################################

# First we load the data from the file we want to analyze
# The experiment should always output sqlite3 files, so let's convert them to a more usable pickle form first
sqliteFile = "C://Users//shams//Drexel University//Chang Lab - General//Individual//Sam Amsterdam//ultrasonic example data//sa_1_2b_1MLiDFOB_wetting_1.sqlite3"

# Convert the sqlite3 to a .pickle
# This takes a few seconds. A progress bar will display in your terminal
pj.sqliteToPickle(sqliteFile)

# Load the pickle
pickleFile = os.path.splitext(sqliteFile)[0] + '.pickle'
data = pj.loadPickle(pickleFile)

# Your data is now loaded as a dict of dicts. Some notes on the structure of the data:
# Top level keys are the collection_index of each waveform. Values are dicts whose keys
#   are the data stored for each collection_index
#   In addition, there are two top level keys 'fileName' = pickleFile and 'parameters' which contain a dict of the pulse parameters
#          0 : {'voltage' : np.array(...), 'time' : np.array(...), 'time_collected' :, ... },
# data = { 1 : {'voltage' : np.array(...), 'time' : np.array(...), 'time_collected' :,... },
#           ...
#         'parameters' : { 'measure_time' : .., 'delay' : .. ,...},
#         'fileName' : pickleFile }

# Now let's do some basic analysis.
# applyFunctionToData takes a user-input analysis function and applies it to all your data
# It takes at least 4 arguments:
#   dataDict - the data object created by using pj.loadPickle()
#   func - the function to be applied to the data
#   resKey - the key the result will be stored in within dataDict
#   dataKeys - the data that will be input into func, as an ordered list. For example ['voltage', 'time']
# Here's a simple example which calculates the maximum voltage of each wave within data and saves it as 'max'
data = pj.applyFunctionToData(data, np.max, 'max', ['voltage'])

# applyFunctionToData can also take additional arguments if func requires them
# For example, the function pj.staltaFirstBreak calculates the first break time of a wave by the STA/LTA algorithm
#   This function requires several user defined paramaters in addition to the voltage and time: the short window (the
#   window to perform short time averaging), the long window (for long time averaging) and the threshold (a number in (0,1) )
#   to determine what counts as the wave breaking)
# In the example below, we apply the STA/LTA algorithm using a short window of 5, a long window of 30, and a threshold of 0.75
#   NOTE: the order that dataKeys and extra *funcargs are input matters! They must follow the input specified where the function is defined
data = pj.applyFunctionToData(data, pj.staltaFirstBreak, 'STA/LTA_fb', ['voltage', 'time'], 5, 30, 0.75)

# If you have several scans you want to analyze at once, use the function pj.applyFunctionToPickles using a list of filenames
# Other than inputting a list of filenames rather than a single dict, this function follows the same input pattern
fileToAnalyze0 = "C://Users//shams//Drexel University//Chang Lab - General//Individual//Sam Amsterdam//ultrasonic example data//sa_1_2b_1MLiDFOB_wetting_1.sqlite3"
fileToAnalyze1 = "C://Users//shams//Drexel University//Chang Lab - General//Individual//Sam Amsterdam//ultrasonic example data//sa_1_2b_1MLiDFOB_wetting_2.sqlite3"
# convert sqlite3 to pickle. Note that if the pickle already exists, the conversion will not occur
pj.multiSqliteToPickle([fileToAnalyze0, fileToAnalyze1])
# Note that applyFunctionToPickles will overwrite the result key if it already exists
# In this example, os.path.splitext()[0] + '.pickle' is used to remove the .sqlite3 from the filename and add the .pickle extension
pj.applyFunctionToPickles([os.path.splitext(fileToAnalyze0)[0] + '.pickle', os.path.splitext(fileToAnalyze1)[0] + '.pickle'], np.max, 'max', ['voltage'])
# Note that applyFunctionToPickles saves the results in the corresponding files but does not return the updated dict. If
# you want to work with it further, you need to manually load it using pj.loadPickle(pickleFile)

# Here's a more complicated example. Let's calculate the real parts of the fft of the waveform
# we can do this using the numpy function np.fft.rfft()
data = pj.applyFunctionToData(data, np.fft.rfft, 'fft', ['voltage'])

# To make a nice plot, we want the magnitude of the rfft by applying abs() to the result
data = pj.applyFunctionToData(data, abs, 'abs_fft', ['fft'])

# Next we calculate the fft frequencies using np.fft.rfftfreq(). This is handled a little differently since it is a constant array for all scans
# rfftfreq requires two inputs: the number of samples (= len('time') ), and the time step
# Since every scan should have the same 'time' values, we only need to calculate this once and set it for all data
timeStep = (data[0]['time'][1] - data[0]['time'][0]) / 1000000000
numSamples = len(data[0]['time'])
fft_freq = np.fft.rfftfreq(numSamples, timeStep)
# the function pj.writeDataToDict can be used to write a constant value for every collection_index
data = pj.writeDataToDict(data, fft_freq, 'fft_freq')
# Now we have the fft and its corresponding frequencies saved in the data under the keys 'abs_fft' and 'fft_freq'
# This data is also saved - any time we load the pickle in the future, it will be accessible

# There are several helper functions written in pickleJar.py for analysis in this format. A list is provided at the end
# with an explanation of the calculation and what is needed for their input

############################################################################
#########################       2         #################################
##################### Plotting Single Scan Experiments ######################
#############################################################################

#  First the basics - plot the first waveform in a data set
plt.plot(data[0]['time'], data[0]['voltage'])
plt.show()

# If your data is a scan, we can plot a 2D image of the scan with a colorscale corresponding to a calculated value at each point
# For this example, we plot the scan with the 'max' value calculated earlier
pj.plotScan(data, 'max')

# plotScan also takes a range for the colorscale as an argument
pj.plotScan(data, 'max', colorRange = [None, 100])

# plotScan also has optional arguments to skip showing the plot and save the figure
# these arguments are: save (True or False), fileName (if this is not provided, a reasonable default is assigned)
# saveFormat (format to save the file, if fileName is not specified. defaults to .png), and show (True or False)
# The example below creates the same figure as above, but instead of showing it saves it as the default filename:
# data['fileName']_max.png . The figure will not be shown but the file will be saved in the directory of the data
pj.plotScan(data, 'max', colorRange = [None, 100], save = True, show = False)

# There is also functionality to plot the waveforms at specified coordinates. Coordinates are input as a list of 2-tuples
# NOTE: errors will be thrown if the coordinates you supply are not in the scan. The offending coordinates will be printed in the terminal when this occurs
# When using this function, be sure to check the sign of your coordinates - scans with a negative step will have negative coordinates
coordinatesToPlot = [(0,0), (5, -10), (3, -1.5)]
pj.plotScanWaveforms(data, coordinatesToPlot)

# Also note that plotScanWaveforms has an optional arguments xDat and yDat which specify the key used to gather the x- and y- data
# This flexibility allows you to plot any transforms you may have made as well
# for example, we can plot the fft we calculated in the last section
pj.plotScanWaveforms(data, coordinatesToPlot, xDat = 'fft_freq', yDat = 'abs_fft')

##############################################################################
#####################        3          ######################################
############## Plotting Repeat Pulse Experiments ##############################
##############################################################################



###################################################################################
#######################        4         #########################################
##########  Analyzing and Plotting Multi Scan Experiments #########################
#################################################################################

# Analysis and plotting of multi scan experiments is complicated by the fact that the data exists across multiple files
# The general approach to these functions is to group all of the relevant data from a multi scan in a single folder
# Most of the plotting and analysis functions operate on all of the .sqlite3 or .pickle files in that folder, extracting
# formatting and sorting the data as needed
# Because of the larger data sets used, these functions often take much longer to run. Expect run times of minutes for
# data sets of hundreds of scans

# Now let's get started. First specify the directory the multi scan data is stored in
dirName = "C://Users//shams//Drexel University//Chang Lab - General//Individual//Sam Amsterdam//ultrasonic example data//"

# For faster processing, let's convert the scan data from .sqlite3 to .pickle if that hasn't already been done
# NOTE: this can take several seconds per scan
pj.directorySqliteToPickle(dirName)

# Applying functions to the multi scan works similar to applyFunctionToPickles, but only the directory name is needed
pj.applyFunctionToDir(dirName, np.max, 'max', ['voltage'])

# It is often useful to normalize the data in a scan to its value at the first scan. This is done on a point-by-point basis
# using the function normalizeDataToFirstScan
# In this example, we take the 'max' we just calculated and divide them by their value in the first scan
# The normalized data will be saved as the inputKey_normalized (in this case, 'max_normalized')
pj.normalizeDataToFirstScan(dirName, ['max'])

# Plotting can also be slow with large data sets. It is often more efficient to generate and save a figure for each scan
# rather than individually viewing them before saving. The function generateScanPlotsInDirectory is useful for this process:
# it calls plotScan on each data file with the options save = True and show = False. The resulting plots are saved in a
# new folder named after the data key used to color the scan dirName//colorKey//scans.png
# this function also takes the colorRange and saveFormat arguments as well
pj.generateScanPlotsInDirectory(dirName, 'max')

# It is also useful to observe how the waveform at a given point in the scan changes over time
# plotWaveformOverTimeAtCoor does this - it overlays the waveform at a given point across all plots, coloring the waves
# according to the time they were measured
# Like plotScanWaveforms, the x- and y- axis data default to 'time' and 'voltage' but can be specified to display calculated data like ffts or normalized voltages
# Unlike plotScanWaveforms, this function only accepts a single coordinate
# In the example, we see the change in the waveform at the coordinate (0,0)
pj.plotWaveformOverTimeAtCoor(dirName, (0,0))

# Another useful metric to plot is how a given calculated parameter changes over time
# plotScanDataAtCoorsVsTime does this for any parameter that has been calculated and saved in the data pickle
# it generates the plot for an input list of coordinates
# In the example, we see how the waveform maximum changes over time at the listed coordinates
coordinatesToPlot = [(0,0), (5, -10), (3, -1.5)]
pj.plotScanDataAtCoorsVsTime(dirName, 'max', coordinatesToPlot)

# plotScanDataAtCoorsVsTime has an additional option normalized = True or False (default is False)
# this option will divide the data by its value at the corresponding time for the first coordinate
# this is useful for long scans that contain temperature fluctuations. If the first coordinate is through water (not the
# battery) then this can compensate for temperature effects to some degree
pj.plotScanDataAtCoorsVsTime(dirName, 'max', coordinatesToPlot, normalized = True)


#####################################################################################
#######################   Appendix  ###########################################
# ###############Analysis Functions and Usage #########################################
#####################################################################################

