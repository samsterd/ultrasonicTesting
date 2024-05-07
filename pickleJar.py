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
import scipy.signal
import math


###########################################################################
############## Saving, Loading, Manipulating Data##########################
############################################################################

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
        print("\nConverting " + file + "\n")
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

    elif 'fileName' not in dataDict.keys():
        print('loadPickle Warning: \'fileName\' not in list of dataDict keys. Updated dataDict[\'fileName\'] = ' + fileName)
        dataDict['fileName'] = fileName

    elif dataDict['fileName'] != fileName:
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

# Applies multiple functions to a data set. This can be faster than calling applyFunctionToData multiple times because data only needs to be loaded once
# takes a dataDict as well as an input called the funcDict, which is a list of dicts with information on the funcs to be applied
#   funcDictList = [{'func': funcName, 'dataKeys' : ['list of data keys to input'], 'resKey' : 'name of key to store func result', 'funcArgs' : [optional key with additional arguments in order]},...]
#   As an example here's a funcDictList to apply absoluteSum and staltaFirstBreak:
#   [{'func' : pj.absoluteSum, 'dataKeys' : ['voltage'], 'resKey' : 'absSum'}, {'func': pj.staltaFirstBreak, 'dataKeys' : ['voltage', 'time'], 'resKey' : 'stalta_5_30_0d75', 'funcArgs' : [5,30,0.75]}]
# Applies the functions to the data and then returns the new dataDict
def applyFunctionsToData(dataDict : dict, funcDictList : list):

    # iterate through keys in datadict
    for key in dataDict:

        # check that the key is a data set, not parameters or fileName
        if type(key) == int:

            # iterate through functions in funcDictList
            for funcDict in funcDictList:

                # format the dataKeys to an iterable input
                funcInputs = [dataDict[key][dataKey] for dataKey in funcDict['dataKeys']]

                # calculate the value of func. Split depending on whether additional inputs are needed
                if 'funcArgs' in funcDict.keys():
                    dataDict[key][funcDict['resKey']] = funcDict['func'](*funcInputs, *funcDict['funcArgs'])

                else:
                    dataDict[key][funcDict['resKey']] = funcDict['func'](*funcInputs)

    #repickle data
    savePickle(dataDict)

    return dataDict

# Apply a function to a list of files
def applyFunctionToPickles(fileNames : list,  func : Callable, resKey, dataKeys, *funcArgs):

    for i in tqdm(range(len(fileNames))):

        file = fileNames[i]
        dataDict = loadPickle(file)
        applyFunctionToData(dataDict, func, resKey, dataKeys, *funcArgs)

# same as above, but uses applyFunctionsToData and takes a funcDictList as input
def applyFunctionsToPickles(fileNames : list, funcDictList : list):

    for i in tqdm(range(len(fileNames))):

        file = fileNames[i]
        dataDict = loadPickle(file)
        applyFunctionsToData(dataDict, funcDictList)

# Apply a function to all of the .pickles in a directory
def applyFunctionToDir(dirName : str, func : Callable, resKey, dataKeys, *funcArgs):

    fileNames = listFilesInDirectory(dirName)

    applyFunctionToPickles(fileNames, func, resKey, dataKeys, *funcArgs)

# same as above, but for multiple functions using the funcDictList format
def applyFunctionsToDir(dirName : str, funcDictList : list):

    fileNames = listFilesInDirectory(dirName)

    applyFunctionsToPickles(fileNames, funcDictList)

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
                x) + ' is not a multiple of the primary step. Rounding coordinate.')

        z = coordinates[i][1]
        if (z % zs != 0):
            print('coordinatesToCollectionIndex: secondary coordinate ' + str(
                z) + ' is not a multiple of the secondary step. Rounding coordinate.')

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

# function to fetch all of the data within a defined rectangle and calculate the mean, sum, and standard deviation of its values.
# returns a dict of the values and the sum, mean, and standard deviation of the values of datakeys
# returns as a dict of dicts: {dataKey0 : {data : all values, mean : val, sum : val, std : val}, dataKey1 : {array :..., mean :...},...}
# Useful to get the overall behavior of ultrasound parameters in the area of a battery
# takes the datadict from loading the pickle, a list of data keys to analyze, the coordinates of the two corners defining the
# box as 2-tuples, and the steps / intervals in both coordinates
# returns the dict of dataKeys analyzed within the box
def scanAverageDataInBox(dataDict: str, dataKeys : list, topLeft, bottomRight, steps):

    # generate a list of coordinates
    # First calculate the number of coordinates in the box on each axis, i.e. the number of steps
    # Add 1 to make the edges inclusive. Use math.floor to ensure the result is an int, not a float
    xSteps = math.floor(((bottomRight[0] - topLeft[0]) / steps[0]) + 1)
    ySteps = math.floor(((bottomRight[1] - topLeft[1]) / steps[1]) + 1)

    if xSteps <= 0:
        print('scanAverageDataInBox: xSteps <= 0. Ensure that your coordinates and steps have the correct sign and alignment.')
    if ySteps <= 0:
        print('scanAverageDataInBox: ySteps <= 0. Ensure that your coordinates and steps have the correct sign and alignment.')

    # generate a flat list of the X- and Y- vals that will be used
    xVals = [topLeft[0] + (i * steps[0]) for i in range(xSteps)]
    yVals = [topLeft[1] + (i * steps[1]) for i in range(ySteps)]

    # Now generate a list of all possible coordinates from this list as 2-tuples
    boxCoors = [(x, y) for x in xVals for y in yVals]

    # pass the list of coordinates into scanDataAtPixels
    pixelData = scanDataAtPixels(dataDict, dataKeys, boxCoors)

    # initialize result dict
    resultDict = {}

    # iterate through dataKeys and results of scanDataAtPixels, calculate values and save
    for dataKey in dataKeys:

        resultDict[dataKey] = {}
        data = []
        # pixelData dict keys are the coordinates. Need to iterate through all coordinates and gather the values of dataKey
        for key in pixelData:
            data.append(pixelData[key][dataKey])
        resultDict[dataKey]['data'] = np.array(data)
        resultDict[dataKey]['mean'] = np.mean(data)
        resultDict[dataKey]['sum'] = np.sum(data)
        resultDict[dataKey]['std'] = np.std(data)

    return resultDict

# Same as above, but operating on multiple scans in a directory
# Returns a dict of dicts with dataKeys as keys, with values as dicts with keys 'mean', 'sum', and 'std', and those values being
#   index-matched arrays. The data will not always be in time order, but all data is index matched, so the same position in different dataKeys correspond
#   to the same scan
# result = { dataKey0 : {mean : [mean_dataKey0_scan0, mean_dataKey0_scan1,...], sum : [...], std : [...]}, dataKey1 : {mean : [...],...},... }
# It is highly recommended to include 'time_collected' as one of the input data keys
def multiScanAverageDataInBox(dir, dataKeys : list, topLeft, bottomRight, steps):

    files = listFilesInDirectory(dir)

    # initialize resultDict
    resultDict = {}
    for dataKey in dataKeys:
        resultDict[dataKey] = {'mean' : [], 'sum' : [], 'std' : []}

    # iterate through files
    for i in tqdm(range(len(files))):

        # load file
        dataDict = loadPickle(files[i])

        # gather data in box
        dataInBox = scanAverageDataInBox(dataDict, dataKeys, topLeft, bottomRight, steps)

        # append data into resultDict
        for dataKey in dataKeys:
            resultDict[dataKey]['mean'].append(dataInBox[dataKey]['mean'])
            resultDict[dataKey]['sum'].append(dataInBox[dataKey]['sum'])
            resultDict[dataKey]['std'].append(dataInBox[dataKey]['std'])

    return resultDict


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

# Plot a data key that contains a list of coordinates and plot it vs another data key
#   Plots will be color-mapped scatters, with the x-coordinate being the single data key, y-coorindates being the x-coors of the list
#   and colormapping is the y-coors in the list
# Used to plot the evolution of waveform extrema over time. Not sure this is actually valuable, but it will at least look cool
# Inputs: str directory of the multiscan data, a 2-tuple coordinate to take the data from, the key of the coordinate data, and the key of the single value
#   Also takes an optional input for the colormap normalization scal. Defaults to linear but log or symlog may also be useful
# Most common usage would be coorKey = 'extrema_coors' (from listExtrema)and dataKey = 'time_collected'
def plotXYListVsTimeAtCoor(dir, coor, coorKey, dataKey, mapNorm = 'linear'):

    # implementing this manually rather than using dataFromCoor functions because coorList could be a ragged array that doesn't stack
    files = listFilesInDirectory(dir)

    # goal is to gather the three pieces of data (coorListx, coorListy, data) into 3 index matched arrays to be plot all at once
    xdat = np.array([])
    ydat = np.array([])
    cdat = np.array([])

    # iterate through files
    for i in tqdm(range(len(files))):

        # load pickle
        dataDict = loadPickle(files[i])

        # find index of coordinate
        coorIndex = coordinatesToCollectionIndex(dataDict, [coor])[0]

        # grab coorList and dataKey
        coorList = dataDict[coorIndex][coorKey]
        dataPoint = dataDict[coorIndex][dataKey]

        # append data to the appropriate places. dataKey must be expanded using np.fill to index match to the coordinate data
        xdat = np.concatenate((xdat, np.full(len(coorList), dataPoint)), axis = None)
        ydat = np.concatenate((ydat, np.transpose(coorList)[0]), axis = None)
        cdat = np.concatenate((cdat, np.transpose(coorList)[1]), axis = None)

    # if the dataKey is 'time_collected', turn the time to a common baseline and convert to hours
    if dataKey == 'time_collected':
        minTime = np.min(xdat)
        xdat = (xdat - minTime) / 3600

    # now we have three long index matched arrays that can be directly plotted
    plt.scatter(xdat, ydat, c = cdat, norm = mapNorm, cmap = 'viridis')
    plt.colorbar()
    plt.show()

# plots data returned by multiScanAverageDataInBox. Scatter plots the mean of the first dataKey as X and mean of second dataKey as Y
# Booleans xErr and yErr will include the standard deviation in those parameters as error bars
def plotDataInBox(dir, dataKeys, topLeft, bottomRight, steps, xErr = False, yErr = False):

    dataInBox = multiScanAverageDataInBox(dir, dataKeys, topLeft, bottomRight, steps)

    if xErr or yErr:
        xErrList = dataInBox[dataKeys[0]]['std'] if xErr else None
        yErrList = dataInBox[dataKeys[1]]['std'] if yErr else None
        plt.errorbar(dataInBox[dataKeys[0]]['mean'], dataInBox[dataKeys[1]]['mean'], yerr = yErrList, xerr = xErrList, fmt = "o")

    else:
        plt.scatter(dataInBox[dataKeys[0]]['mean'], dataInBox[dataKeys[1]]['mean'])

    plt.show()

# same as plotDataInBox, but the x-axis is 'time_collected'. The x-axis is then formatted to be 0-referenced and converted to hours
def plotDataInBoxVsTime(dir, dataKey, topLeft, bottomRight, steps, yErr = False):

    dataInBox = multiScanAverageDataInBox(dir, ['time_collected', dataKey], topLeft, bottomRight, steps)

    timeDat = np.array(dataInBox['time_collected']['mean'])
    minTime = np.min(timeDat)
    formattedTime = (timeDat - minTime) / 3600

    if yErr:
        yErrList = dataInBox[dataKey]['std']
        plt.errorbar(formattedTime, dataInBox[dataKey]['mean'], yerr = yErrList, fmt = "o")

    else:
        plt.scatter(formattedTime, dataInBox[dataKey]['mean'])

    plt.show()

# helper function that takes an array of unix times and zero-references them (shift so that minimum time is 0) and converts to hours
# used when plotting a data point vs 'time_collected'
def timeCollectedToExperimentHours(timeCollected):

    # make sure timeCollected is an array
    timeArr = np.array(timeCollected)

    minTime = np.min(timeArr)
    zeroRefArr = timeArr - minTime

    return zeroRefArr/3600

##############################################################################3
############ Analysis and Data Correction Functions ############################33
################################################################################

# function for use in applyFunctionToData that calculates the maximum minus minimum value
def maxMinusMin(voltages):

    return bn.nanmax(voltages) - bn.nanmin(voltages)

# returns the sum of the absolute value of an input array. This value is directly proportional to the integral of the signal
def absoluteSum(voltages):

    return np.sum(abs(voltages))


def baselineCorrectVoltage(voltage, baseline):

    return voltage - baseline

# Applies a Savitzky-Golay filter to the data and optionally takes its first or second derivative
# Inputs the y-data ('voltage'), x-data ('time') along with 3 auxiliary parameters: the window length of filtering (defaults to 9),
#       the order of polynomials used to fit (defaults to 3), and the derivative order (default to 0, must be less than polynomial order)
# outputs the filtered data or its requested derivative. The output has the same shape as the input
def savgolFilter(yDat, xDat, windowLength = 9, polyOrder = 3, derivOrder = 0):

    # calculate the spacing of the xData
    xDelta = xDat[1] - xDat[0]

    return scipy.signal.savgol_filter(yDat, windowLength, polyOrder, derivOrder)

# Finds the x-coordinates where a function changes sign (crosses zero)
# This is useful for e.g. finding maxima by zero-crossings of the first derivative
# Inputs the y- and x- data, as well as an optional input linearInterp, which determines the nature of the returned values
#       if linearInterp = False, the function returns the values of the xData at the coordinate before the zero crossing occurs
#       if linearInterp = True, the function performs a linear interpolation of the two coordinates surrounding the zero-crossing
#           i.e. (x0, y0 > 0), (x1, y1 < 0), and returns the x-value where the interpolation equals 0
# Returns an array of the x-coordinates where the y values crossed zero
def zeroCrossings(yDat, xDat, linearInterp = False):

    # find the indices where zero crossing occurs
    # implementation taken from https://stackoverflow.com/questions/3843017/efficiently-detect-sign-changes-in-python
    zeroCrossingIndices = np.where(np.diff(np.signbit(yDat)))[0]

    # handle case where there are no zero crossings
    # Currently returns -1 which isn't ideal, but returning None makes further analysis and plotting difficult
    if len(zeroCrossingIndices) == 0:
        return np.array([-1])

    elif linearInterp:

        xIntercepts = []

        # iterate through indices, calculate x-intercept, and append to result list
        for i in zeroCrossingIndices:

            # gather data points surrounding the zero crossing and calculate x-intercept
            # note that the index-finding algorithm does not count sign changes in the last data point, so we do not need to check
            # for edge cases (that is, i < len(yDat) so we do not need to check that i + 1 is an acceptable list index)
            x0 = xDat[i]
            x1 = xDat[i+1]
            y0 = yDat[i]
            y1 = yDat[i+1]
            xIntercept = (-1 * (y0 * (x0 - x1))/(y0-y1)) + x0
            xIntercepts.append(xIntercept)

        return np.array(xIntercepts)

    else:
        return np.array([xDat[i] for i in zeroCrossingIndices])

# Similar to zeroCrossings, listExtrema takes y-values of a function, y-values of its derivative, and the x-values and returns
# an 2 x number of extrema array that correspond to the extrema of the function (i.e. the (x, y) values where the derivative crosses zero)
# inputs the yData array (i.e. 'voltage'), derivative of yData (i.e. 'savgol_1'), and the x-data ('time')
# returns an array of coordinates
def listExtrema(yDat, deriv, xDat):

    # find the indices where zero crossing occurs
    # implementation taken from https://stackoverflow.com/questions/3843017/efficiently-detect-sign-changes-in-python
    zeroCrossingIndices = np.where(np.diff(np.signbit(deriv)))[0]

    extremaList = []
    for i in zeroCrossingIndices:
        extremaList.append([xDat[i], yDat[i]])

    return np.array(extremaList)

# Calculate the time of flight for a signal by calculating the Hilbert envelope and returning the time value where it reaches
# a certain fraction of its max value
# Inputs y-data of the signal ('voltage'), x-data ('time') and the fraction of maximum for the threshold (number in (0,1))
# Returns the time of flight
def envelopeThresholdTOF(yDat, xDat, threshold = 0.5):

    if len(yDat) != len(xDat):
        print("envelopeThresholdTOF Error: x- and y- data must be the same length. Check that the correct keys are being used.")
        return -1

    if threshold <=0 or threshold >=1:
        print("envelopeThresholdTOF Error: input threshold is out of bounds. Threshold must be >0 and <1.")
        return -1

    envelope = hilbertEnvelope(yDat)

    # Calculate the actual value of the threshold
    thresholdValue = threshold * bn.nanmax(envelope)

    firstBreakIndex = firstIndexAboveThreshold(envelope, thresholdValue)

    return xDat[firstBreakIndex]

# Calculates the hilbert envelope of an input signal by taking the absolute value of the hilbert transform
def hilbertEnvelope(array):

    return np.abs(scipy.signal.hilbert(array))

# helper function that returns the index of the first value in the input array that exceeds a given threshold
# Used to pick first break data
def firstIndexAboveThreshold(array, threshold):

    # array > threshold converts array to booleans, argmax then returns index of first True
    return np.argmax(array > threshold)

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

# Simple baseline correction algorithm that assumes the start of the waveform should be zero
#   NOTE: this is only correct if a conservative delay was chosen when running the experiment. If the signal wave starts
#         quickly on waveforms, this algorithm will be very inaccurate
# Inputs the voltage array to be baseline corrected as well as the number of data points in beginning to use for baseline correcting
#  The algorithm takes the mean of the first startWindow number of voltages and then subtracts that number from all voltages
#  making the voltage centered around 0V
# Returns the baseline corrected voltages
def baselineCorrectByStartingValues(voltage, startWindow):

    meanV = np.mean(voltage[0:startWindow])

    return voltage - meanV

# A helper function to generate a list of coordinates on a line
# used to feed into plotScanDataAtCoors to look at linecuts of data
# Inputs: startCoor 2-tuple, length of the line, axis 2-tuple i.e. (1, 0) for X-line, (0, 1) for Y-line or (1,1) for diagonal,
# and step size on line
def generateLineCoors(startCoor, length, axis, step):

    # floor is used to round and convert to an int
    numberOfSteps = math.floor(length / step)

    return [(startCoor[0] + (axis[0] * step * i), startCoor[1] + (axis[1] * step *i)) for i in range(numberOfSteps)]

########################################################################3
############# Deprecated Code #########################################
######################################################################

# Old baseline correction algorithm that doesn't work well

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
# def baselineCorrectScans(dirName):
#
#     # find the first scan
#     print("Finding first scan...")
#     firstScan = findFirstScan(dirName)
#
#     print("\nChecking that max and max minus min are calculated for first scan...")
#     # check that max and max - min is calculated for the first scan. if not, calculate it
#     if 'max' not in firstScan[0].keys():
#         firstScan = applyFunctionToData(firstScan, bn.nanmax, 'max', ['voltage'])
#
#     if 'maxMinusMin' not in firstScan[0].keys():
#         firstScan = applyFunctionToData(firstScan, maxMinusMin, 'maxMinusMin', ['voltage'])
#
#     # gather file names
#     files = listFilesInDirectory(dirName)
#
#     print("\nCalculating attenuation coefficient (An) and baseline correction (Bn)...")
#     # iterate through scans
#     for i in tqdm(range(len(files))):
#
#         fileData = loadPickle(files[i])
#
#         # check that the max has been calculated. If not, calculate it
#         if 'max' not in fileData[0].keys():
#             fileData = applyFunctionToData(fileData, bn.nanmax, 'max', ['voltage'])
#
#         # check that max - min has been calculated. If not, calculate it
#         if 'maxMinusMin' not in fileData[0].keys():
#             fileData = applyFunctionToData(fileData, maxMinusMin, 'maxMinusMin', ['voltage'])
#
#         # iterate through coordinates and calculate An and Bn at every point
#         for index in fileData.keys():
#
#             if type(index) == int:
#                 fileData[index]['An'] = fileData[index]['maxMinusMin'] / firstScan[index]['maxMinusMin']
#                 fileData[index]['Bn'] = fileData[index]['max'] - (firstScan[index]['max'] * fileData[index]['An'])
#
#         # finally create the baseline-corrected voltage wave by subtracting voltages and Bn
#         applyFunctionToData(fileData, baselineCorrectVoltage, 'voltage_baseline', ['voltage', 'Bn'])
