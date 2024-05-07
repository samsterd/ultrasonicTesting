import csv
import os.path
import numpy as np
from matplotlib import pyplot as plt
from matplotlib import colormaps as cmp
import pickleJar as pj
import pandas as pd
import math
import sqliteUtils as squ
import copy

# Helper functions for loading, analyzing, and plotting electrochemistry data from Ivium and Squidstat potentiostats

# Plan: load files, store data in dict
# get creation time (ctime), record original filename, decide whether it is OCP or EIS, rename file accordingly
# then save as a pickle
# next consolidate all data into one pickle
#                    col0 : np.array([...])
#                    col1 : ...
# singleScanDict = { time_collected : time          }
#                    originalFileName : file string
#                    dataType : eis or ocp
#              'eis0' : {firstEISDict},
# dataDict = { 'ocp0' : {firstOCPDict}, }
#                 ...
#               'fileName' : file name string

# Inputs the directory where the ivium scans are stored and a name for the output pickle file
# Outputs the data in the directory, sorted by type (OCP or EIS), with timestamps and
def pickleIviumData(dir, saveName : str):

    # list csv files in dir
    files = pj.listFilesInDirectory(dir, '.csv')

    dataDict = {'fileName' : dir + saveName + '.pickle'}
    eisCounter = 0
    ocpCounter = 0
    otherCounter = 0

    # iterate through files
    for file in files:

        # load csv file into a dict
        fileDat = loadIviumCSV(file)

        # generate a keyname for the data, add it to the master dict
        if fileDat['dataType'] == 'eis':
            keyString = 'eis' + str(eisCounter)
            eisCounter += 1
            dataDict[keyString] = fileDat
        elif fileDat['dataType'] == 'ocp':
            keyString = 'ocp' + str(ocpCounter)
            ocpCounter += 1
            dataDict[keyString] = fileDat

    # pickle the master dict, return dict
    pj.savePickle(dataDict)
    return dataDict

# Inputs a filename
# Outputs a singleScan data dict with the scan type identified, the data created included, and data columns properly labeled
def loadIviumCSV(file):

    dataDict = {}
    # NOTE: this only works on windows files
    # NOTE: we are using m (modified) time, not c (created) time because the ctime is changed when the data is moved from its original computer
    #       while the mtime does not change from its original creation date (assuming the data hasn't been modified, which it should be!
    timeCreated = os.path.getmtime(file)
    dataDict['time_collected'] = timeCreated
    dataDict['originalFileName'] = os.path.basename(file)

    with open(file, 'rb') as f:

        # load data as columns instead of rows by transposing
        data = np.transpose(np.loadtxt(f, delimiter = ','))

    # identify data type
    dataDict['dataType'] = iviumDataType(data)

    if dataDict['dataType'] == 'eis':
        dataDict['re_z'] = data[0]
        dataDict['im_z'] = data[1]
        dataDict['freq'] = data[2]
    elif dataDict['dataType'] == 'ocp':
        dataDict['time'] = data[0]
        dataDict['voltage'] = data[1]
        dataDict['ocp_other_data'] = data[2]
    elif dataDict['dataType'] == 'other':
        dataDict['data'] = data

    return dataDict

# Identifies whether the data stored in the dict belongs to an OCP or EIS experiment
# right now this is extremely crude: if the first column is evenly spaced, it is OCP. IF the first value of the third column is 100,000, it is EIS
# this is not generally applicable and only useful for this first data set
def iviumDataType(data):

    if data[2][0] > 1:
        return 'eis'
    elif data[0][0] > 0 and data[0][0] < 2:
        return 'ocp'
    else:
        return 'other'


# Strategy for Squidstat data is similar to Ivium but uses Pandas dataframes for easier importing
# Data is read as a pandas data frame and saved into a dict containing the data type ('eis' or 'ocp') as well as the original filename and time created
# The overall data is a dict of dicts containing the saved data for each experiment, all consolidated into one larger file
# Note that extra keys are added to the scan dicts to match the formatting of the Ivium data. This information is redundant
# (it is already in the 'data' dataframe) but it makes all other Ivium - related functions compatible with the Squidstat data
#               { 'fileName' : original file name
# single scan =   'time_collected' : time file created
#                 'dataType' : 'eis' or 'ocp'
#                 're_z' ... or 'voltage' ... : data from pandas dataframe as top-level key for Ivium compatibility
#                 'data' : pandas dataframe}
#                   { 'fileName' : file name of dict pickle
# experiment dict =   'eis0' : eis scan dict
#                     'ocp0' : ocp scan dict
#                     'eis1' : ... }
# Also includes an optional parameter stepToIgnore. This checks the 'Step number' in the imported data and does not import
#   if the step = 0 % stepToIgnore. This functionality is useful for ignoring 'filler' experiments like a 30 minute OCP measurement
def loadSquidstatCSV(file, stepToIgnore = None):

    dataDict = {}

    # gather the original filename from the input file
    dataDict['originalFileName'] = os.path.basename(file)

    # gather the time. mtime should be safe to use on windows and linux
    # NOTE: we are using m (modified) time, not c (created) time because the ctime is changed when the data is moved from its original computer
    #       while the mtime does not change from its original creation date (assuming the data hasn't been modified, which it should be!
    timeCreated = os.path.getmtime(file)
    dataDict['time_collected'] = timeCreated

    # load data into pandas dataframe
    csvdf = pd.read_csv(file)
    dataDict['data'] = csvdf

    # check if the data should be ignored
    if stepToIgnore != None and type(stepToIgnore) == int and csvdf['Step number'][0] % stepToIgnore == 0:
        return -1

    # extract the data type from the 'Step name' of the data
    # also adds top level keys to match the structure of the Ivium data
    stepName = csvdf['Step name'][0]
    if stepName == 'Potentiostatic EIS':
        dataDict['dataType'] = 'eis'
        dataDict['re_z'] = np.array(csvdf['Z\' (Ohms)'])
        dataDict['im_z'] = -1 * np.array(csvdf['-Z" (Ohms)'])
        dataDict['freq'] = np.array(csvdf['Frequency (Hz)'])
    elif stepName == 'Open Circuit Potential':
        dataDict['dataType'] = 'ocp'
        dataDict['time'] = np.array(csvdf['Elapsed Time (s)'])
        dataDict['voltage'] = np.array(csvdf['Working Electrode (V)'])

    return dataDict

# Inputs the directory where the squidstat scans are stored and a name for the output pickle file
# Outputs the data in the directory, sorted by type (OCP or EIS), with timestamps
# stepsToIgnore is passed to the loadSquidstatCSV function
def pickleSquidstatData(dir, saveName : str, stepsToIgnore = None):

    # list csv files in dir
    files = pj.listFilesInDirectory(dir, '.csv')

    dataDict = {'fileName' : dir + saveName + '.pickle'}
    eisCounter = 0
    ocpCounter = 0

    # iterate through files
    for file in files:

        # load csv file into a dict
        fileDat = loadSquidstatCSV(file, stepsToIgnore)

        # if import was ignored (i.e. it was an ignored step), pass this iteration
        if fileDat == -1:
            pass

        # generate a keyname for the data, add it to the master dict
        elif fileDat['dataType'] == 'eis':
            keyString = 'eis' + str(eisCounter)
            eisCounter += 1
            dataDict[keyString] = fileDat
        elif fileDat['dataType'] == 'ocp':
            keyString = 'ocp' + str(ocpCounter)
            ocpCounter += 1
            dataDict[keyString] = fileDat

    # pickle the master dict, return dict
    pj.savePickle(dataDict)
    return dataDict

# Apply an input function to all of a certain dataType, using the data in argKeys as the function arguments and saving the result as resKey
# Repickles the data when finished
def applyFunctionToData(dataDict, dataType, func, argKeys, resKey, *funcArgs):

    # iterate through keys
    for key in dataDict.keys():

        # check that the data is correct type
        if key != 'fileName' and dataDict[key]['dataType'] == dataType:

            # gather the arguments
            funcInputs = [dataDict[key][arg] for arg in argKeys]

            # calculate function on funcArgs
            result = func(*funcInputs, *funcArgs)

            # save data as resKey within scan
            dataDict[key][resKey] = result

    # repickle the data
    pj.savePickle(dataDict)

    # return the data
    return dataDict

def plotKeyVsTime(dataDict, dataType, yKey):

    # initialize result list
    timeList = []
    yList = []

    # iterate through keys
    for key in dataDict:

        # check that data is correct type
        if key != 'fileName' and dataDict[key]['dataType'] == dataType:

            # gather time_collected and yKey
            timeList.append(dataDict[key]['time_collected'])
            yList.append(dataDict[key][yKey])

    # format the time list so it is 0-referenced and in hours, not seconds
    timeArr = np.array(timeList)
    minTime = np.min(timeArr)
    formattedTime = (timeArr - minTime) / 3600

    # plot results
    plt.scatter(formattedTime, np.array(yList))
    plt.show()

# Gather a piece of data over time. Same as the data that gets plotted in plotKeyVsTime, but returns the arrays
# instead of plotting. Useful for setting up other plots (i.e. plotting e-chem vs ultrasound data)
def gatherDataVsTime(dataDict, dataType, dataKey):
    # initialize result list
    timeList = []
    dataList = []

    # iterate through keys
    for key in dataDict:

        # check that data is correct type
        if key != 'fileName' and dataDict[key]['dataType'] == dataType:
            # gather time_collected and yKey
            timeList.append(dataDict[key]['time_collected'])
            dataList.append(dataDict[key][dataKey])

    # format the time list so it is 0-referenced and in hours, not seconds
    timeArr = pj.timeCollectedToExperimentHours(timeList)

    return timeArr, np.array(dataList)

# Plot scans with the data points colormapped to time_collected
def plotDataVsTime(dataDict, dataType, xKey, yKey, plotType = 'scatter'):

    # initialize result list
    xList = []
    yList = []
    timeList = []

    # iterate through keys
    for key in dataDict:

        # check that data is correct type
        if key != 'fileName' and dataDict[key]['dataType'] == dataType:

            # gather time_collected and yKey
            timeList.append(dataDict[key]['time_collected'])
            xList.append(dataDict[key][xKey])
            yList.append(dataDict[key][yKey])

    # format the time list so it is 0-referenced and in hours, not seconds
    timeArr = np.array(timeList)
    minTime = np.min(timeArr)
    time0ref = timeArr - minTime
    maxTime = np.max(time0ref)
    normTime = time0ref / maxTime
    formattedTime = (timeArr - minTime) / 3600

    # plot results
    for i in range(len(timeList)):
        if plotType == 'scatter':
            plt.scatter(xList[i], yList[i], c = cmp['viridis'](normTime[i]), label = str(formattedTime[i]))
        elif plotType == 'line':
            plt.plot(xList[i], yList[i], c = cmp['viridis'](normTime[i]), label = str(formattedTime[i]))

    plt.show()

##############################################################
######## Basic Analysis Functions #######################
def negFunc(array):
    return -1 * array

# convert two arrays, which are the real and imaginary parts of a vector, into an array containing the log of their magnitude
def logabs(re, im):
    re2 = re**2
    im2 = im**2
    mag = np.sqrt(re2 + im2)
    return np.log10(mag)

# Returns the real impedance at a given target frequency
def resAtFreq(re_z, freq, targetFreq):

    # math.isclose is used for the comparison since the freq may be a float
    # returns indices where freq is within 1% of targetFreq
    nearlyEqualBools = np.array([math.isclose(f, targetFreq, rel_tol = 0.01) for f in freq])
    index = np.nonzero(nearlyEqualBools)

    try:
        return re_z[index[0][0]]
    except IndexError:
        print("resAtFreq: Frequency not found in array. Check your value of targetFreq")
        return None