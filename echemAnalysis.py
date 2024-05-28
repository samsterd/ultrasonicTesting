import csv
import os.path
import numpy as np
from matplotlib import pyplot as plt
from matplotlib import colormaps as cmp
import pickleJar as pj
import pandas as pd
import math
from impedance import preprocessing
from impedance.models.circuits.fitting import circuit_fit
from impedance.models.circuits import Randles, CustomCircuit
from tqdm import tqdm

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


#########################################################
######### Plotting ################################
#################################################

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

##################################################################
########### EIS Fitting ##########################################
#################################################################

# Set of functions for using the data dicts within the impedance module

# convert data from a single eis experiment into the f, Z used by the impedance module
# inputs the data dict e.g. data['eis0'], outputs two arrays - the frequencies, and the Z as complex numbers
def eisConvertData(data : dict):

    if 'dataType' not in data.keys() or data['dataType'] != 'eis':
        print("eisConvertData: input data dict does is not the proper type. Check that the input data was produced using a pre-made pickling function.")
        return -1

    f = data['freq']
    Z = data['re_z'] + 1j*data['im_z']

    return f, Z

# fit eis to a Randles model with a CPE and fixing the R0 value to the high frequency zero crossing
# saves data as key['randles_circuit'] for the impedance package circuit object, ['randles_fit'] for the fit parameters and ['randes_err'] for the fitting errors
def constrainedRandlesFit(dataDict : dict, firstParams : list):

    # gather eis keys by experiment time using orderPickles as the template
    times = []
    eisKeys = []
    for key in dataDict.keys():
        if key != 'fileName' and dataDict[key]['dataType'] == 'eis':
            times.append(dataDict[key]['time_collected'])
            eisKeys.append(key)

    zippedTimeKeys = zip(times, eisKeys)
    orderedKeys = [key for _, key in sorted(zippedTimeKeys)]

    # calculate the high frequency zero crossing if it hasn't been calculated
    if 'hfr' not in dataDict[orderedKeys[0]]:
        print("Calculating high frequency resistance...\n")
        dataDict = applyFunctionToData(dataDict, 'eis', nyquistZeroCrossing, ['re_z', 'im_z'], 'hfr')

    # define circuit string for fitting
    randlesString = 'R0-p(R1-Wo1,CPE1)'

    # iterate through keys
    print("Fitting circuits...\n")
    for i in tqdm(range(len(orderedKeys))):

        # get data into a usable form and trim out data in the wrong quadrant
        key = orderedKeys[i]
        freq, z = eisConvertData(dataDict[key])
        freq, z = preprocessing.ignoreBelowX(freq, z)

        # generate guesses. If first eis spectrum, use user input. Otherwise use the previous fit as the starting point for the next one
        if i == 0:
            guesses = firstParams
        else:
            guesses = dataDict[orderedKeys[i-1]]['randles_fit']

        # generate a dict for r0 to be held constant in fitting
        r0 = {'R0' : dataDict[key]['hfr']}

        # fit circuit
        fit, err = circuit_fit(freq, z, randlesString, guesses, r0)

        # gather data and save in datadict
        circuit = Randles(initial_guess = fit, CPE = True, constants = r0)
        dataDict[key]['randles_circuit'] = circuit
        dataDict[key]['randles_fit'] = fit
        dataDict[key]['randles_err'] = err
        dataDict[key]['randles_r1'] = fit[0]
        dataDict[key]['randles_w0'] = fit[1]
        dataDict[key]['randles_w1'] = fit[2]
        dataDict[key]['randles_cpe0'] = fit[3]
        dataDict[key]['randles_cpe1'] = fit[4]

    # re-pickle the dict
    pj.savePickle(dataDict)

    return dataDict

##############################################################
######## Basic Analysis Functions #######################
###########################################################

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

# find the zero crossing of a nyquist plot. Returns the highest frequency real impedance if there is no zero crossing
def nyquistZeroCrossing(re, im):

    crossing = pj.zeroCrossings(-1*im, re, True)

    # handle case where no zero crossing found, instead return the highest frequency value of re
    if crossing == -1:
        return re[0]
    else:
        return crossing[0]

##########################################################################
######## Deprecated Code ##############################
########################################################
#----DEPRECATED-----
# It turns out this function is unneeded an the freq, Z arrays can be directly loaded into the impedance module...
# helper function that reads in pickled output files (should work with squidstat or ivium) and converts it to a simple 3-column CSV
# of frequency, Z_real, and Z_imag. This makes it easier to use the impedance.py package
# Note: this process of reading machine output->pickling to a custom set -> remaking it as a series of csvs -> then doing analysis is really inefficient
# This process should be improved
# Inputs: the path to the pickled squidstat data and an optional name for the subdirectory where the new files will go
# Outputs: writes each EIS data set as a CSV in a subfolder called "impedance_csv//"
#   Each file will have the original filename so the metadata can be accessed again
def convertPickleToReadableCSV(pickleFile, destinationDir = '//impedance_csv//'):

    # load the eis pickle
    data = pj.loadPickle(pickleFile)

    # create the destination directory
    newDir = os.path.dirname(pickleFile) + destinationDir
    try:
        os.mkdir(newDir)
    except FileExistsError:
        print("convertPickleToReadableCSV: destination directory " + newDir + " already exists. Conversion aborted to avoid "
                                                                              "overwriting existing files. Either input a new destinationDir or delete old files and rerun.")
        return -1

    # iterate through the data sets, operating on 'dataType' == 'eis'
    for key in data.keys():

        if key != 'fileName' and data[key]['dataType'] == 'eis':

            # gather data fields. transpose them so that they are rows
            freq = data[key]['freq']
            reZ = data[key]['re_z']
            imZ = data[key]['im_z']
            dataRows = np.transpose(np.array([freq, reZ, imZ]))

            # generate filename
            fileName = newDir + data[key]['originalFileName']

            # open file, write in data
            with open(fileName, 'w+', newline = '') as f:
                csvWriter = csv.writer(f)
                csvWriter.writerows(dataRows)

            f.close()

    return 0