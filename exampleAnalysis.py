#Example usage of analysis functions

# Analysis functions are contained in the files pickleJar.py and sqliteUtils.py
import pickleJar as pj
import sqliteUtils as squ
import numpy as np
import os.path
import matplotlib.pyplot as plt

#####################################################################
########## Table of Contents ########################################
#####################################################################
# 1. Loading and analyzing a single file
# 2. Plotting a scan
# 3. Plotting a repeat pulse
# 4. Loading, analyzing, and plotting a multi scan
# Appendix : Analysis functions and usage

##############################################################
###############         1             #########################
############# Analyzing a single file #######################
############################################################

# First we load the data from the file we want to analyze
# The experiment should always output sqlite3 files, so let's convert them to a more usable pickle form first
sqliteFile = 'C//file//you//want//to//analyze.sqlite3'

# Convert the sqlite3 to a .pickle
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
# Other than inputting a list of filenames rather than a single dict, this function follows the same input patter
fileToAnalyze0 = 'C//file//you//want//to//analyze0.sqlite3'
fileToAnalyze1 = 'C//file//you//want//to//analyze1.sqlite3'
pj.applyFunctionToPickles([fileToAnalyze0, fileToAnalyze1], np.max, 'max', ['voltage'])
# Note that applyFunctionToPickles saves the results in the corresponding files but does not return the updated dict. If
# you want to work with it further, you need to manually load it
otherData = pj.loadPickle(fileToAnalyze0)


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
# To show this, here's a more complicated example. We will first define an fft function, use it with applyFunctionToData,
# and then plot the fft at the specified coordinates

#TODO: test this. also move up to the analysis section
# First calculate the  fft using numpy's builtin function
data = pj.applyFunctionToData(data, np.fft.rfft, 'fft_y', ['voltage'])

# Then calculate the magnitude of the fft by applying abs() to the result
data = pj.applyFunctionToData(data, abs, 'abs_fft_y', ['fft_y'])

# Next we calculate the fft frequencies. First we calculate the time step in seconds
timeStep = (data[0]['time'][1] - data[0]['time'][0]) / 1000000000
# Then apply the rfftfreq function using timestep as an extra parameter
data = pj.applyFunctionToData(data, np.rfftfreq(len), 'fft_x', timeStep)

# finally, let's plot the results for the coordinates we were interested in before
pj.plotScanWaveforms(data, coordinatesToPlot, xDat = 'fft_x', yDat = 'abs_fft_y')

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
dirName = "C://directory//where//scan//data//is//"

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

