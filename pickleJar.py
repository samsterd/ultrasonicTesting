# Files and scripts to support saving through pickling large data dicts
# This should avoid the time penalty of translating sqlite data from strings to arrays
#   This is intended as a supplement to sqlite saving. It is worthwhile to have the data in human readable and portable form
# Ideal work flow:
#   Collect data, save as sqlite AND pickle
#   Write scripts to convert existing sqlite to pickles
#   Perform analysis on pickles
#   Write data as needed back to sqlite
# Structure of data dict:
#   Primary key is collection index (makes it universal for scans and repeat pulse experiments)
#       Each value is a dict with the associated data
# Example: battery_scan_01.pickle -> unpickle to dict
#         voltage : np.array([...]),
#         time : np.array([...]),
# { 0 : { coordinate : (x, y),   },
#         primaryAxis : 'X',
#         absoluteSum : 5,
#
#  1 : { same keys : new data }
# ...
#  'fileName' : name of file to load and save the pickle
#   All experimental parameters are saved as a sub-dict with key 'parameters'
#  'parameters' :{time_started : x, delay : y,...}
# }

import pickle
import sqlite3
import sqliteUtils as squ
from typing import Callable
from tqdm import tqdm
from matplotlib import get_backend
from matplotlib import pyplot as plt
from matplotlib import colormaps as cmp
import time
import numpy as np
import os
import bottleneck as bn

# Functions needed:
# implement as a class!
#   no b/c we want to apply to functions across multiple dicts
#   yes b/c we want to keep the filename as a property of the dict?
#   compromise: fileName is always a top level key of the pickle/dataDict
#       this isn't great - what if the pickle moves? should it be rewritten every time it is loaded?
#   __init__() creates an empty dict?
# pickleToSqlite - save analysis in human readable format
# plotting functions

tstFile = "C://Users//shams//Drexel University//Chang Lab - General//Individual//Sam Amsterdam//acoustic scan data//sa-1-2b wetting scan//sa_1_2b_1MLiDFOB_wetting_1.sqlite3"
pickleFile = "C://Users//shams//Drexel University//Chang Lab - General//Individual//Sam Amsterdam//acoustic scan data//sa-1-2b wetting scan//sa_1_2b_1MLiDFOB_wetting_1.pickle"

#
# Convert sqlite database
# Inputs a filename with .sqlite3 extension
# Creates a data dict and saves it as the same filename .pickle
# Returns the dataDict
def sqliteToPickle(file : str):

    # Open db connection
    con, cur = squ.openDB(file)

    # get column names
    colNames = squ.columnNames(cur, 'acoustics')

    # find the position of collection_index, which is used to create keys for the dataDict
    indexPosition = colNames.index('collection_index')

    dataDict = {}

    # Generate the filename by removing .sqlite3 extension and .pickle extension
    pickleFile = os.path.splitext(file)[0] + '.pickle'
    dataDict['fileName'] = pickleFile

    # check if the pickle file already exists. If it does, print an error message and exit early
    if os.path.isfile(pickleFile):
        print("sqliteToPickle Warning: pickle file " + pickleFile + " already exists. Conversion aborted.")
        return -1

    # Gather the number of rows in the db
    numRows = squ.numberOfRows(cur, 'acoustics')

    # Create and execute a SELECT query to pull all of the data from the table
    selectQuery = "SELECT " + ", ".join(colNames) + " FROM acoustics"
    res = cur.execute(selectQuery)

    # Iterate through the result, convert the data to numpy arrays, apply the function, record in a list with keys
    for i in tqdm(range(numRows)):

        row = res.fetchone()

        #create a new dict for the given collection_index
        index = int(row[indexPosition])
        dataDict[index] = {}

        for i in range(len(colNames)):
            # some tables have blank columns due to code bugs. This skips over them
            if row[i] != None:
                dataDict[index][colNames[i]] = squ.stringConverter(row[i])
            else:
                pass

    # extract the experimental parameters from the sql table
    paramNames = squ.columnNames(cur, 'parameters')
    paramQuery = "SELECT " + ", ".join(paramNames) + " FROM parameters"
    paramRes = cur.execute(paramQuery)
    # only need to fetchone since the parameter table should be a single row
    params = paramRes.fetchone()

    # write the experimental parameters into a subdict of the dataDict
    dataDict['parameters'] = {}
    for i in range(len(paramNames)):
        if params[i] != None:
            dataDict['parameters'][paramNames[i]] = squ.stringConverter(params[i])
        else:
            pass

    # save the dataDict as a pickle. We checked if the file exists earlier, so this operation is safe
    with open(pickleFile, 'wb') as f:
        pickle.dump(dataDict, f)

    con.close()
    f.close()

    return dataDict


# Convert multiple sqlite files to pickle
# Returns None
def multiSqliteToPickle(files : list):

    for file in files:
        sqliteToPickle(file)

# Convert all sqlite DBs in a directory to pickles
# Returns None
def directorySqliteToPickle(dirName : str):

    fileNames = listFilesInDirectory(dirName, '.sqlite3')

    multiSqliteToPickle(fileNames)

# TODO: this should be written
def pickleToSqlite(dataDict):
    return 0

# Saves a dataDict as a pickle. If the 'fileName' key is not informed, a warning message is printed
def savePickle(dataDict : dict):

    if 'fileName' not in dataDict.keys():
        print('savePickle Error: \'fileName\' is not a key in input dict, pickle cannot be saved. Manually add dataDict[\'fileName\'] = fileName and retry saving.'
              'In the future, using loadPickle() or sqliteToPickle() ensures the dataDict is properly formatted')
        return -1

    else:
        fileName = dataDict['fileName']
        with open(fileName, 'wb') as f:
            pickle.dump(dataDict, f)
        f.close()
        return 0

# Load a pickle specified in a filename
# This will also do some basic error checking:
#   Makes sure the pickle is a dict
#   Checks if the 'fileName' key exists
#   Checks if the 'fileName' value matches the input fileName.
#       If either of the last two are not true, the 'fileName' key is updated
def loadPickle(fileName : str):

    with open(fileName, 'rb') as f:
        dataDict = pickle.load(f)

    if type(dataDict) != dict:
        print('loadPickle Warning: loading ' + fileName + ' does not result in a dict. Data manipulation functions and scripts will likely fail.')

    if 'fileName' not in dataDict.keys():
        print('loadPickle Warning: \'fileName\' not in list of dataDict keys. Updated dataDict[\'fileName\'] = ' + fileName)
        dataDict['fileName'] = fileName

    if dataDict['fileName'] != fileName:
        print('loadPickle Warning: dataDict[\'fileName\'] does not match input fileName. Value of dataDict key has been updated to match new file location.')
        dataDict['fileName'] = fileName

    f.close()
    return dataDict

# function to write values into the dataDict. Saves the dataDict as a pickle then returns the dict
# The indexMatched option determines how the data is added
# For default behavior (==False):
#   dataDict[collection_index][key] = dat
# For indexMatched data, dat must be an iterable of length == len(dataDict.keys())-2
#   If not, an error is thrown
#   otherwise, dataDict[collection_index][key] = dat[collection_index]
def writeDataToDict(dataDict : dict, dat, key, indexMatched = False):

    if indexMatched:

        # check that dat matches the index matching requirement
        if type(dat) == list and len(dat) == len(dataDict.keys()) - 2:

            # iterate through collection_indices and assign appropriate values
            for index in dataDict.keys():
                if type(index) == int:
                    dataDict[index][key] = dat[index]

            savePickle(dataDict)
            return dataDict

        # index matching condition failed. throw an error and return -1
        else:
            print("writeDataToDict: Error, indexMatched is set to True but dat is not of the correct length. Check inputs and length of dataDict.keys().")
            return dataDict

    # data is not index matched, set key to a constant value
    else:
        for index in dataDict.keys():
            if type(index) == int:
                dataDict[index][key] = dat
        savePickle(dataDict)
        return dataDict

# apply function to key
# takes a dataDict, a function, the key to store the result in, a list of keys to use as the function arguments, and a list of additional arguments if needed
# NOTE: if dataDict[collection_index][resKey] already exists, it will be overwritten
def applyFunctionToData(dataDict : dict, func : Callable, resKey, dataKeys, *funcArgs):

    # check if dataKeys is a list. If it isn't convert it to one
    dataKeys = [dataKeys] if not isinstance(dataKeys, list) else dataKeys

    # Iterate through the keys (coordinates) in the dataDict
    for key in dataDict:

        # check that the key is a collection_index (an int), not 'fileName' or 'parameters"
        if type(key) == int:

            # Gather the data from dataKeys into a list to use as input to func
            funcInputs = [dataDict[key][dataKey] for dataKey in dataKeys]

            dataDict[key][resKey] = func(*funcInputs, *funcArgs)

        else:
            pass

    # Repickle the data
    savePickle(dataDict)

    return dataDict

# Apply a function to a list of files
def applyFunctionToPickles(fileNames : list,  func : Callable, resKey, dataKeys, *funcArgs):

    for i in tqdm(range(len(fileNames))):

        file = fileNames[i]
        dataDict = loadPickle(file)
        applyFunctionToData(dataDict, func, resKey, dataKeys, *funcArgs)

# Apply a function to all of the .pickles in a directory
def applyFunctionToDir(dirName : str, func : Callable, resKey, dataKeys, *funcArgs):

    fileNames = listFilesInDirectory(dirName)

    applyFunctionToPickles(fileNames, func, resKey, dataKeys, *funcArgs)

# Assemble a '4D' dataDict of a multi scan experiment with the data at each coordinate / collection_index collected into an array
#   NOTE: data is not going to be in load order, not time order. Time ordering can only be achieved by index matching to 'time_collected'
#   NOTE: for long multi scans this could result in a very large file size
#   This function is not implemented yet because it would probably use up all of my RA<
# def assembleScanAcrossTime():
#     return 0

# apply function to keys

# apply function to pickles

# apply function to pickles in directory

# normalize data across pickles in directory to the value at the first scan
# inputs a directory with pickles in it (the first scan will be identified automatically)
# and a list of keys that should be normalized
# the results of normalized values will be stored in a dataDict[index]['keyName_normalized'] = value_normalized
def normalizeDataToFirstScan(dirName, keysToNormalize : list):

    # find the first scan
    print("Finding first scan...")
    firstScan = findFirstScan(dirName)

    # Check that the keysToNormalize are in firstScan
    for key in keysToNormalize:
        if key not in firstScan[0].keys():
            print("Error: key " + str(key) + " not found in " + firstScan['fileName'] + ". Normalization aborted. Check the spelling of the keys and whether their value has been calculated yet.")
            return -1

    # gather file names in directory
    fileNames = listFilesInDirectory(dirName)

    # iterate through dir
    print("\nNormalizing scans...")
    for i in tqdm(range(len(fileNames))):

        # load the pickle
        currentScan = loadPickle(fileNames[i])

        # iterate through collection_index / coordinates
        for index in currentScan.keys():

            # verify the key is a collection_index, not 'parameters' or 'fileName'
            if type(index) != int:
                pass

            else:

                #  iterate through keysToNormalize, divide by the corresponding value at firstScan
                # values are saved as 'keyName_normalized'
                for key in keysToNormalize:
                    normKey = key + '_normalized'
                    currentScan[index][normKey] = currentScan[index][key] / firstScan[index][key]

        # save pickle
        savePickle(currentScan)
        # clear memory of currentScan
        del currentScan

    return 0

# Calculate the time of the first break using STA/LTA algorithm
# Inputs the voltage and time arrays, the length (in number of elements, NOT time) of the short and long averaging window,
#   and tresholdRatio, a number in (0,1) that determines what fraction of the maximum STA/LTA counts as the first break
def staltaFirstBreak(voltageData, timeData, shortWindow : int, longWindow : int, thresholdRatio = 0.75):

    staltaArray = stalta(voltageData, shortWindow, longWindow)

    threshold = thresholdRatio * bn.nanmax(staltaArray)

    # Return time where first value in staltaArray is above threshold
    for i in range(len(staltaArray)):
        if staltaArray[i] > threshold:
            return timeData[i]

    # No value was found above threshold. Return -1
    return -1

# Calculate STA/LTA for a given short and long window
# Windows are specified in number of elements (not time)
# Returns an array of the same length as input. Values within longWindow-1 of the start of the array will be converted to NaNs
# NOTE: windows are left-handed in this implementation
def stalta(array, shortWindow, longWindow):
    # Calculate square of array values
    arrSquared = array ** 2

    # Calculate moving averages with optimized code from bottleneck package
    sta = bn.move_mean(arrSquared, shortWindow)
    lta = bn.move_mean(arrSquared, longWindow)

    return sta / lta

# takes in a directory with multiscan data
# creates a new voltage_baseline_corrected key and saves the data
# This assumes that for each point in the scan at time tn, in reference to the point at t=0, there is a
# multiplicative change to the intensity An that operates on the span of the wave (its maximum amplitude minus minimum amplitude)
# as well as an additive baseline change due to electronics drift (Bn)
# Our governing equations are then
# (0) An(Max(0) - Min(0)) = Max(n) - Min(n) (definition of multiplicative An)
# (0a) An = (Max(n) - Min(n)) / (Max(0) - Min(0))
# (1) Max(n) = An * Max(0) + Bn
# (2) Min(n) = An * Min(0) + Bn
# Rearranging and solving for Bn gives:
# Bn = Max(n) - Max(0) * An
# This function finds the t=0 reference scan, then for every subsequent scan calculates and saves An, Bn, and voltage_baseline
# This assumes that B0 = 0
def baselineCorrectScans(dirName):

    # find the first scan
    print("Finding first scan...")
    firstScan = findFirstScan(dirName)

    print("\nChecking that max and max minus min are calculated for first scan...")
    # check that max and max - min is calculated for the first scan. if not, calculate it
    if 'max' not in firstScan[0].keys():
        firstScan = applyFunctionToData(firstScan, bn.nanmax, 'max', ['voltage'])

    if 'maxMinusMin' not in firstScan[0].keys():
        firstScan = applyFunctionToData(firstScan, maxMinusMin, 'maxMinusMin', ['voltage'])

    # gather file names
    files = listFilesInDirectory(dirName)

    print("\nCalculating attenuation coefficient (An) and baseline correction (Bn)...")
    # iterate through scans
    for i in tqdm(range(len(files))):

        fileData = loadPickle(files[i])

        # check that the max has been calculated. If not, calculate it
        if 'max' not in fileData[0].keys():
            fileData = applyFunctionToData(fileData, bn.nanmax, 'max', ['voltage'])

        # check that max - min has been calculated. If not, calculate it
        if 'maxMinusMin' not in fileData[0].keys():
            fileData = applyFunctionToData(fileData, maxMinusMin, 'maxMinusMin', ['voltage'])

        # iterate through coordinates and calculate An and Bn at every point
        for index in fileData.keys():

            if type(index) == int:
                fileData[index]['An'] = fileData[index]['maxMinusMin'] / firstScan[index]['maxMinusMin']
                fileData[index]['Bn'] = fileData[index]['max'] - (firstScan[index]['max'] * fileData[index]['An'])

        # finally create the baseline-corrected voltage wave by subtracting voltages and Bn
        applyFunctionToData(fileData, baselineCorrectVoltage, 'voltage_baseline', ['voltage', 'Bn'])

# function for use in applyFunctionToData that calculates the maximum minus minimum value
def maxMinusMin(voltages):

    return bn.nanmax(voltages) - bn.nanmin(voltages)

# returns the sum of the absolute value of an input array. This value is directly proportional to the integral of the signal
def absoluteSum(voltages):

    return np.sum(abs(voltages))


def baselineCorrectVoltage(voltage, baseline):

    return voltage - baseline

# helper function to apply baseline correction to data

# Helper function to find the first scan in a directory
#   This is done based on the 'time_started' key in the 'parameters' dict
#
def findFirstScan(dirName):

    fileNames = listFilesInDirectory(dirName)

    # initialize a list of times started
    timesStarted = []

    # iterate through the list
    for i in tqdm(range(len(fileNames))):

        # load the file and gather the time_started
        data = loadPickle(fileNames[i])
        timeStarted = data['parameters']['time_started']
        timesStarted.append(timeStarted)

    # find the index of the minimum of time started
    minIndex = timesStarted.index(min(timesStarted))

    # find the file name that corresponds to that minimum start time
    minFile = fileNames[minIndex]

    # load the pickle and return the result
    return loadPickle(minFile)

# Helper function to list the files ending in .pickle within a given directory
# Inputs a directory name
# Outputs a list of file names
def listFilesInDirectory(dirName, ext = '.pickle'):

    files = os.listdir(dirName)
    fileNames = []
    for file in files:
        if file.endswith(ext):
            fileNames.append(os.path.join(dirName, file))

    return fileNames

# implement baseline correct as a function

# Determines the collection_index of each input coordinate for a given scan dataDict
#   this is needed to efficiently retrieve the data for a given coordinate without searching through all of a dict's keys.
#   (this converts searching for a coordinate from O(n) to O(1)
# Functionality is copied from the corresponding function in sqliteUtils.py
# Essentially, we are doing a bunch of algebra to calculate the collection_index the corresponds to a
# given coordinate. This is possible if we know the collection_index and coordinates of the last and second-to-last points
# For an (x,z) scan, let xs, zs be the coordinate step that the map was collected at
#           Let (xf, zf) be the final coordinates at the last collection_index kf
#           Let (x0, z0) be the coordinates of the second to last collection_index k0 = kf - 1
#                Looking up both of these coordinates takes O(1) time since we start from collection_index
#           Let (m, n) be the number of rows and columns of a given map
#           Our system of equations is then:
#               1)  kf = nm - 1
#               2)  xf = (n - 1) xs
#               3)  zf = (m - 1) zs
#               4)  kf = n (zf / zs) + xf/xs
#               5)  k0 = n (z0 / zs) + x0/xs
#               6) either xs = xf - x0 OR zs = zf - z0
#           We can directly solve (6) by checking which coordinate changes between kf and k0
#           The other unknowns (n, m, the remaining of xs or zs) can then be solved straighforwardly
# NOTE: the speed of this function relies on the number of coordinates in a scan being equal to len(dataDict.keys()) - 2 -
#       a dataDict contains keys for each point + 'fileName' + 'parameters'. This assumption is key to this algorithm working fast
#       if we need to sort keys to find the final coordinates the algorithm becomes O(nlogn) and we lose the speedup

def coordinatesToCollectionIndex(dataDict, coordinates):

    # this assumes that the dataDict contains a key for each point + 'fileName' + 'parameters'
    # Need to subtract an additional 1 because len is 1-indexed but collection_index is 0-indexed
    kf = len(dataDict.keys()) - 3
    # Do some quick error checking - make sure kf > 0 or else the rest will fail
    if kf <= 1:
        print("coordinatesToCollectionIndex: input table only has one row. Check that the table and data are correct")
        return None

    # determine which axes are used in dataDict (2 out of 'X', 'Y', and 'Z')
    axes = ['X', 'Y', 'Z']
    axisKeys = [axis for axis in axes if axis in dataDict[0].keys()]

    # Collect coordinates of final point
    xf = dataDict[kf][axisKeys[0]]
    zf = dataDict[kf][axisKeys[1]]

    # Collect coordinates of second-to-last point
    k0 = kf - 1
    x0 = dataDict[k0][axisKeys[0]]
    z0 = dataDict[k0][axisKeys[1]]

    # Check which coordinate changed and use that to solve the equations
    # First handle case where x coordinate changed
    if zf == z0:
        xs = xf - x0
        n = (xf / xs) + 1
        m = (kf + 1) / n
        zs = zf / (m - 1)
    elif xf == x0:
        zs = zf - z0
        m = (zf / zs) + 1
        n = (kf + 1) / m
        xs = xf / (n - 1)
    # We should not enter the final branch, but just in case lets put a panicked error message
    else:
        print(
            "coordinatesToCollectionIndex: unable to identify coordinate step. Unclear what went wrong, but its probably related to floating point rounding. Your data is probably cursed, contact Sam for an exorcism (or debugging).")
        return None

    # Now iterate through the input coordinates and convert to indices
    # using equation k = n(z/zs) + (x/xs)
    collectionIndices = []

    for i in range(len(coordinates)):
        x = coordinates[i][0]
        # Raise warnings if rounding
        if (x % xs != 0):
            print('coordinatesToCollectionIndex: primary coordinate ' + str(
                x) + 'is not a multiple of the primary step. Rounding coordinate.')

        z = coordinates[i][1]
        if (z % zs != 0):
            print('coordinatesToCollectionIndex: secondary coordinate ' + str(
                z) + 'is not a multiple of the secondary step. Rounding coordinate.')

        index = (n * (z / zs)) + (x / xs)

        # handle out of bounds indices as None
        if index < 0 or index > kf:
            print('coordinatesToCollectionIndex: input coordinate ' + str(coordinates[i]) + ' is out of bounds of the scan.' +
                    'Check the coordinate list and scan parameters and try again.')
            collectionIndices.append(None)
        else:
            collectionIndices.append(int(index))

    return collectionIndices

# Collect specified data from specified coordinates in a scan dataDict
# Inputs the dataDict, dataKeys as a list of strings, and coordinates a list of 2-tuples
# Outputs a dict with keys being coordinates and values being dicts with keys being the dataKeys and values being the corresponding value at that point
#               (x0, y0) : {dataKeys0 : val, dataKeys1 : val,...}
# resultDict = {(x1, y1) : {dataKeys0 : val, dataKeys1 : val,...}}
#                   ...
def scanDataAtPixels(dataDict: dict, dataKeys: list, coordinates: list):

    # convert coordinates into collection_indices
    coordinateIndices = coordinatesToCollectionIndex(dataDict, coordinates)

    resultDict = {}
    # iterate through collection_indices
    for i in range(len(coordinateIndices)):

        if coordinateIndices[i] != None:
            coorData = dataDict[coordinateIndices[i]]

            # iterate through dataKeys, adding values
            resultDict[coordinates[i]] = {key : coorData[key] for key in dataKeys}

        else:
            print("scanDataAtPixels: Cannot extract data. Coordinate " + str(coordinates[i]) + " is out of the scan bounds." +
                  "Check the coordinate list, scan parameters, and the signs of coordinates and try again.")
            return -1

    return resultDict

# Collect specific data from multiple scans at a given list of coordinates
# scans are specified as a list of fileNames, dataKeys as a list of strings, and coordinates as a list of (x,y) or [x,y]
# returns a dict of dicts. The top level dict has keys = coordinates. Each coordinate key has a value of a dict, with the keys
#   being the dataKeys and the values being an array of the values of that data at each scan. All values are index matched to each
#   other, so the values at the same index will be from the same scan across all coordinates
#   NOTE: the data will be in the order of fileNames, not necessarily in time order. They will be index-matched, so they can still
#       be time ordered by including time_collected in the dataKeys list
# format of output dict:
#               (x0, y0) : {dataKeys0 : [val0, val1,...], dataKeys1 : [val0, val1, ...],...}
# resultDict = {(x1, y1) : {dataKeys0 : [val0, val1,...], dataKeys1 : [val0, val1, ...],...}}
#                   ...
def multiScanDataAtPixels(fileNames : list, dataKeys : list, coordinates : list):

    dataDictList = []

    # iterate through files, loading the pickle and running scanDataAtPixels on each scan, saving the result in the list
    print("Gathering scan data...\n")
    for i in tqdm(range(len(fileNames))):

        fileData = loadPickle(fileNames[i])
        dataDictList.append(scanDataAtPixels(fileData, dataKeys, coordinates))

    print("\nMerging data...")
    # Merge data. storage list is a list of dicts of dicts. This got ugly...
    # First make a copy of dataDictList[0] but with the values as numpy arrays
    masterDict = {}

    for coordinate, coordinateData in dataDictList[0].items():
        masterDict[coordinate] = {dataColumn: np.array(value) for dataColumn, value in coordinateData.items()}

    # Now iterate through the rest of dataDictList, merging the values into the arrays of masterDict
    for scan in dataDictList[1:]:

        # for each scan in list, iterate through the keys (coordinates) and values (values == innerDict of data columns)
        for coor, coordinateData in scan.items():

            # append the data values for the scan to the masterdict
            for dataColumn, value in coordinateData.items():
                # Arrays must be handles differently from individual values - they should be 'stacked' rather than appended
                if type(value) == np.ndarray:
                    masterDict[coor][dataColumn] = np.vstack((masterDict[coor][dataColumn], value))
                else:
                    masterDict[coor][dataColumn] = np.append(masterDict[coor][dataColumn], value)

    return masterDict

# Runs multiScanDataAtPixels on all pickle files in a directory
# NOTE: data will be returned in load order, not time order. It will be index matched to time, if that is imported
def directoryScanDataAtPixels(dirName : str, dataKeys : list, coordinates : list):

    files = listFilesInDirectory(dirName)
    return multiScanDataAtPixels(files, dataKeys, coordinates)


############################################################
###### Plotting Functions###################################
###########################################################

# TODO: ADD plot vs time for repeat pulse

# plot the waveform at specified coordinates
def plotScanWaveforms(dataDict : dict, coors : list, xDat = 'time', yDat = 'voltage'):

    # gather waveform data
    waveDat = scanDataAtPixels(dataDict, [xDat, yDat], coors)

    # plot
    for coor in coors:
        plt.plot(waveDat[coor][xDat], waveDat[coor][yDat])

    plt.show()

# plots waveform change over time from multiscan data
def plotWaveformOverTimeAtCoor(dirName : str, coor : tuple, xDat = 'time', yDat = 'voltage'):

    # gather a dict of the data. Since we are only gathering at one coordinate, we use that to collect the data dict from that key
    dataDict = directoryScanDataAtPixels(dirName, [xDat, yDat, 'time_collected'], [coor])[coor]

    # convert time_collected to a common zero, then normalize it to [0,1] for the colormap
    timesCollected = dataDict['time_collected']
    minTime = min(timesCollected)
    timesCollectZeroRef = timesCollected - minTime
    maxTime = max(timesCollectZeroRef)
    normTime = timesCollectZeroRef / maxTime

    for wave in range(len(dataDict['time_collected'])):
        plt.plot(dataDict[xDat][wave], dataDict[yDat][wave], c = cmp['viridis'](normTime[wave]), label = round(timesCollectZeroRef[wave]/3600, 2))

    plt.legend()
    plt.show()


# Plots a 2D scan as a scatter plot. XY data is the scan coordinate, colorKey determines parameters used to color the map
# Optional inputs: the range for the coloring parameter (values outside the range will be set to the max/min of the range)
# save = True will save the file, with the optional fileName string used to name it.
#       file name will be automatically generated based as dataDict['fileName'] + '_colorKey' + saveFormat
# show = True will show the plot when the function is run. This is useful for single uses, but slows down mass plot saving
def plotScan(dataDict, colorKey, colorRange = [None, None], save = False, fileName = '', saveFormat = '.png', show = True):

    # determine which axes are used in dataDict (2 out of 'X', 'Y', and 'Z')
    axes = ['X', 'Y', 'Z']
    axisKeys = [axis for axis in axes if axis in dataDict[0].keys()]

    # check that exactly 2 axis keys were found, otherwise throw an error
    if len(axisKeys) != 2:
        print("plotScan Error: identified " + str(len(axisKeys)) + " scan axes in data. This number should be 2. Check that the input data is for a scan experiment.")
        return -1

    # gather coordinate and color data by iterating through the dataDict keys
    xDat = np.array([])
    yDat = np.array([])
    cDat = np.array([])
    for index in dataDict.keys():
        if type(index) == int:
            xDat = np.append(xDat, dataDict[index][axisKeys[0]])
            yDat = np.append(yDat, dataDict[index][axisKeys[1]])
            cDat = np.append(cDat, dataDict[index][colorKey])

    # plot
    plt.scatter(xDat, yDat, c = cDat, vmin = colorRange[0], vmax = colorRange[1])
    plt.colorbar()

    if show == True:
        plt.show()

    # save. generate a filename if it isn't specified
    if save == True:

        # generate a save file name if not provided
        if fileName == '':
            dataFile = dataDict['fileName']
            saveFile = os.path.splitext(dataFile)[0] + '_' + str(colorKey) + saveFormat
        else:
            saveFile = fileName
        plt.savefig(saveFile)
        plt.close()

# runs plotScan on a list of filenames with show = False and save = True, for use in mass figure generation.
#  Saves the figures in a subfolder named colorKey with the name dataDict['fileName'] + _colorKey + format
def generateScanPlots(fileNames : list, colorKey, colorRange = [None, None], saveFormat = '.png'):

    # switch tk backend to avoid Runtime main thread errors when generating large numbers of figures
    # NOTE: this will prevent displaying the figures, which isn't a problem for the generate function
    # The previous backend is saved and restored at the end of the function
    backend = get_backend()
    plt.switch_backend('agg')

    # iterate through fileNames
    for i in tqdm(range(len(fileNames))):

        file = fileNames[i]

        # generate save file name
        saveDir = os.path.dirname(file) + '//' + str(colorKey) + '//'

        # make saveDir if it doesn't exist
        if not os.path.exists(saveDir):
            os.makedirs(saveDir)

        # load dataDict
        data = loadPickle(file)

        # generate save file name
        saveName = os.path.basename(os.path.splitext(file)[0]) + '_' + str(colorKey) + saveFormat
        saveFile = saveDir + saveName

        plotScan(data, colorKey, colorRange, save = True, fileName = saveFile, show = False)

    # return to previous backend
    plt.switch_backend(backend)

# generate scan images for all pickles in a directory. Used to mass produce scan images from multi scan experiments
def generateScanPlotsInDirectory(dirName : str, colorKey, colorRange = [None, None], saveFormat = '.png'):

   fileNames = listFilesInDirectory(dirName)

   generateScanPlots(fileNames, colorKey, colorRange, saveFormat)

# Plot the evolution of the value of dataKey vs time at a given list of coordinates
# If normalized = True, the data will be divided by the corresponding value in the first coordinate
def plotScanDataAtCoorsVsTime(dirName : str, dataKey : str, coors : list, normalized = False):

    # gather the data
    dataDict = directoryScanDataAtPixels(dirName, ['time_collected', dataKey], coors)

    # Convert time axis to a common zero
    minTimes = []
    for coor in dataDict:
        times = dataDict[coor]['time_collected']
        # Collect the minimum time
        minTimes.append(min(times))

    # Find the experiment start time by taking the min of the mins
    t0 = min(minTimes)

    if normalized == True:
        # grab values from first coordinate
        normValue = dataDict[coors[0]][dataKey]
        # iterate through all coors and divide by first coordinate
        for coor in dataDict.keys():
            # be wary of issues with copy and references here - may need to revise
            dataDict[coor][dataKey] = dataDict[coor][dataKey]/normValue

    for coor in dataDict.keys():
        # Convert to common 0 by subtracting start time. Divide by 3600 to display in hours instead of seconds
        timeDat = (dataDict[coor]['time_collected'] - t0) / 3600
        plt.scatter(timeDat, dataDict[coor][dataKey], label = str(coor))

    plt.legend()
    plt.show()