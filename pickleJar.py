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
from scipy.optimize import curve_fit
import math
import csv


###########################################################################
############## Saving, Loading, Manipulating Data##########################
############################################################################

# Convert sqlite database
# Inputs a filename with .sqlite3 extension
# Creates a data dict and saves it as the same filename .pickle
# Returns the dataDict
#TODO: check if file exists before converting!
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
            # needs to first check if the value is an array b/c truth values don't apply to whole arrays
            if type(row[i]) == np.ndarray or row[i] != None:
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
# NOTE: the first warning message will be thrown for loading DataCubes. This should be fine
def loadPickle(fileName : str):

    with open(fileName, 'rb') as f:
        dataDict = pickle.load(f)

    pickleType = type(dataDict)

    if pickleType != dict and pickleType != DataCube:
        print('loadPickle Warning: loading ' + fileName + ' does not result in a dict. Data manipulation functions and scripts will likely fail.')

    # handle problems with dataDict fileName field
    elif pickleType == dict and 'fileName' not in dataDict.keys():
        print('loadPickle Warning: \'fileName\' not in list of dataDict keys. Updated dataDict[\'fileName\'] = ' + fileName)
        dataDict['fileName'] = fileName
        savePickle(dataDict)

    elif pickleType == dict and dataDict['fileName'] != fileName:
        print('loadPickle Warning: dataDict[\'fileName\'] does not match input fileName. Value of dataDict key has been updated to match new file location.')
        dataDict['fileName'] = fileName
        savePickle(dataDict)

    # handle problems with DataCube fileName field
    elif pickleType == DataCube and dataDict.fileName != fileName:
        print('loadPickle Warning: dataCube.fileName does not match input fileName. Value of DataCube.fileName has been updated to match new file location.'
              '\nNOTE: if the source multi scan data has also moved, run DataCube.updateCube(\'new//data//location//\')')
        dataDict.fileName = fileName
        dataDict.saveCube()

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

# stitches together data from multiple repeat pulse experiments in chronological order
# used to combine experimental data that got separated due to e.g. power surges
# inputs a list of data dict objects and a name to save the combined pickle as
# outputs a data dict of the combined pickles and also saves the file
def combineRepeatPulseData(dataList, saveName : str):

    # determine the order of the pickles
    startTimes = [data[0]['time_collected'] for data in dataList]
    orderedData = [data for _,data in sorted(zip(startTimes, dataList), key = lambda pair: pair[0])]

    # determine the last collection_index of each pickle
    # -3 is because the indices are 0-indexed and there are two non-index keys (fileName and parameters)
    endIndices = [len(data.keys()) - 3 for data in orderedData]

    # calculate the starting index of each dict once they are combined
    # i.e. if the data have endIndices=[200,300,400], the startingIndices=[0, 201, 502]
    startIndices = [sum(endIndices[:i]) + i for i in range(len(endIndices))]

    # determine the max index for the combined data. len(indices)-1 is added to account for all data being 0-indexed
    maxIndex = sum(endIndices) + len(endIndices) - 1

    # initialize the new data dict. Since we are not verifying the parameters are the same for all data, this will not be copied
    newData = {}

    # iterate through pickles
    for i in tqdm(range(len(orderedData))):

        print("Adding data from " + orderedData[i]['fileName'] + '...')
        # write new dict by updating the indices
        # the collection_index of newData is extended by the value of startIndices
        for j in tqdm(range(endIndices[i])):
            newData[startIndices[i] + j] = orderedData[i][j]

    # generate fileName for the new pickle
    fileName = os.path.dirname(orderedData[0]['fileName']) + '//' + saveName + '.pickle'
    newData['fileName'] = fileName
    savePickle(newData)
    return newData

# Simple post-experiment analysis automation
# Receives the experiment params dict, converts sqlite to pickle
# runs max-min, sta/lta, hilbert envelope, generates plots, and dumps coordinates/metrics as a csv
def simplePostAnalysis(params : dict):

    # check that saveFormat == 'sqlite' or abort
    if params['saveFormat'] != 'sqlite':
        print("saveFormat must be set to 'sqlite' to perform post-analysis. Analysis aborted.")
        return -1

    # get filename from params
    file = params['fileName'] + '.sqlite3'

    # convert sqlite to pickle
    dataDict = sqliteToPickle(file)

    # generate functionDictList for applyFunctionsToData
    funcDictList = [
        {'func' : maxMinusMin, 'dataKeys' : ['voltage'], 'resKey' : 'maxMinusMin'},
        {'func': staltaFirstBreak, 'dataKeys' : ['voltage', 'time'], 'resKey' : 'staltaTOF_5_50_0d5', 'funcArgs' : [5,50,0.5]},
        {'func': envelopeThresholdTOF, 'dataKeys' : ['voltage', 'time'], 'resKey' : 'envelopeTOF_0d8', 'funcArgs' : [0.8]}
    ]

    # run applyFunctionsToData
    dataDict = applyFunctionsToData(dataDict, funcDictList)

    # generate and save data plots (as png and svg)
    plotScan(dataDict, 'maxMinusMin', save = True, saveFormat = '.png', show = False)
    plotScan(dataDict, 'maxMinusMin', save=True, saveFormat='.svg', show=False)
    plotScan(dataDict, 'staltaTOF_5_50_0d5', save=True, saveFormat='.png', show=False)
    plotScan(dataDict, 'staltaTOF_5_50_0d5', save=True, saveFormat='.svg', show=False)
    plotScan(dataDict, 'envelopeTOF_0d8', save=True, saveFormat='.png', show=False)
    plotScan(dataDict, 'envelopeTOF_0d8', save=True, saveFormat='.svg', show=False)

    # dump data dict as csv
    dictToCSV(dataDict, ['X', 'Z', 'time_collected', 'maxMinusMin', 'staltaTOF_5_50_0d5', 'envelopeTOF_0d8'])


# function to dump all single point data from a datadict to a csv file for outside analysis
def dictToCSV(dataDict : dict, keysToDump = []):

    # if not input keys, identify keys that contain single point data basd on dataDict[0]
    if keysToDump == []:
        keyList = []
        for key in dataDict[0].keys():
            val = dataDict[0][key]
            if type(val) == int or type(val) == float:
                keyList.append(key)
    else:
        keyList = keysToDump

    numberOfCoors = len(dataDict.keys()) - 2

    destinationFile = os.path.splitext(dataDict['fileName'])[0] + '.csv'

    with open(destinationFile, 'w', newline = '') as csvfile:

        csvwriter = csv.writer(csvfile)

        csvwriter.writerow(keyList)

        # iterate through non-parameter keys, create list of values, dump to csv
        for i in range(numberOfCoors):

            row = [dataDict[i][key] for key in keyList]

            csvwriter.writerow(row)

    return 0



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

# helper function to order the pickles in a directory by their experiment start times
# inputs a directory with .pickle files in it
# outputs a list of the pickle filenames in order of their first time_collected
def orderPickles(dirName):

    # gather all pickles in the directory
    pickleFiles = listFilesInDirectory(dirName, '.pickle')

    # gather the first time_collected from each file
    timeStarted = []

    for i in tqdm(range(len(pickleFiles))):
        dat = loadPickle(pickleFiles[i])
        timeStarted.append(dat[0]['time_collected'])

    # order the pickleFiles by timeStarted by zipping and sorting
    zippedTimesFiles = zip(timeStarted, pickleFiles)
    return [x for _, x in sorted(zippedTimesFiles)]

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

    mappingParams = coordinateToIndexMap(dataDict)
    # extract mapping parameters
    m = mappingParams['m']
    n = mappingParams['n']
    xs = mappingParams['xs']
    zs = mappingParams['zs']
    kf = mappingParams['kf']

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

# helper function following similar logic to above
# converts a collection index into an array index coordinate i,j (where the index is from 0 to m or n)
def collectionIndexToArrayIndex(dataDict : dict, collection_index):

    # first find m and n, the number of rows and columns
    mappingParams = coordinateToIndexMap(dataDict)
    n = mappingParams['n']
    m = mappingParams['m']
    kf = mappingParams['kf']

    if collection_index > kf:
        print("collectionIndexToArrayIndex WARNING: input collection_index is greater than the final index of the data.")

    # next calculate i and j - the array coordinates (column, row) along the m and n dimensions
    i = collection_index % n
    j = math.floor(collection_index / n)

    return i, j

# the logic described in the comment above coordinatesToCollectionIndex is abstracted here as it is used in many functions
# coordinateToIndexMap takes in a dataDict and outputs the parameters needed to map between real spatial coordinates (x,y),
# array coordinates (i,j), and the collection_index
# the output is a dict with keys 'm', 'n', 'xs', 'zs', where 'm' and 'n' are the number of points in the x and z axis and
# xs and zs are the distance steps between each coordinate in the physical scans, and kf is the last index in the scan
def coordinateToIndexMap(dataDict):
    # this assumes that the dataDict contains a key for each point + 'fileName' + 'parameters'
    # Need to subtract an additional 1 because len is 1-indexed but collection_index is 0-indexed
    kf = len(dataDict.keys()) - 3
    # Do some quick error checking - make sure kf > 0 or else the rest will fail
    if kf <= 1:
        print("coordinateToIndexMap: input table only has one row. Check that the table and data are correct")
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
            "coordinateToIndexMap: unable to identify coordinate step. Unclear what went wrong, but its probably related to floating point rounding. Your data is probably cursed, contact Sam for an exorcism (or debugging).")
        return None

    #Note: math.floor is used to ensure m and n are integers
    return {'m' : math.floor(m), 'n' : math.floor(n), 'xs' : xs, 'zs' : zs, 'kf' : kf}

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

# Function that gathers the data keys within a box and then fits their change over time to a given function
# For example, fitting the change in max-min at each coordinate to a logistic function
# Returns the data as a dict of coordinats with keys for each fitting parameter as well as fitting 'goodness' metrics
# This data will be pickled in a subdirectory since this operation will take several minutes to run
def multiScanFitDataInBox(dir, dataKeys : list, fitFunction, topLeft, bottomRight, steps):
    return 0


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

    # legend becomes too crowded for 100+ curves
    # plt.legend()
    plt.show()


# Plots a 2D scan as a scatter plot. XY data is the scan coordinate, colorKey determines parameters used to color the map
# Optional inputs: the range for the coloring parameter (values outside the range will be set to the max/min of the range)
# scalePlot sets the plot scales equal (plt.axis('scaled')). Defaults to False, which outputs square plots
# save = True will save the file, with the optional fileName string used to name it.
#       file name will be automatically generated based as dataDict['fileName'] + '_colorKey' + saveFormat
# show = True will show the plot when the function is run. This is useful for single uses, but slows down mass plot saving
def plotScan(dataDict, colorKey, colorRange = [None, None], scalePlot = False, save = False, fileName = '', saveFormat = '.png', show = True):

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

    # need to reshape the cDat into an x by y array to use as input in pcolormesh
    # do this by gathering the array indices of the final scan point and use that to reshape cDat
    nRows, nCols = collectionIndexToArrayIndex(dataDict, len(cDat) - 1)
    cMesh = cDat.reshape((nCols + 1, nRows + 1))

    # need to convert x- and y- into column vectors for generating the mesh
    # also need to invert the order if the scan goes into negative coordinates since
    # np.unique will sort them in the opposite order of collection
    # note: there is likely a more efficient way to do this, but probably not worth optimizing this too much
    xCol = reverseNegativeCoordinates(np.unique(xDat))
    yCol = reverseNegativeCoordinates(np.unique(yDat))

    # plot
    plt.pcolormesh(xCol, yCol, cMesh, vmin=colorRange[0], vmax=colorRange[1])
    if scalePlot:
        plt.axis('scaled')
    plt.colorbar()

    # save. generate a filename if it isn't specified
    if save == True:

        # generate a save file name if not provided
        if fileName == '':
            dataFile = dataDict['fileName']
            saveFile = os.path.splitext(dataFile)[0] + '_' + str(colorKey) + saveFormat
        else:
            saveFile = fileName
        plt.savefig(saveFile)
        if show == False:
            plt.close()

    if show == True:
        plt.show()



# helper function for plotScan that reverses coordinate lists that start negative
# inputs an array. Outputs an array that is reversed if the input started negative
def reverseNegativeCoordinates(arr):

    if arr[0] < 0:
        return np.flip(arr)
    else:
        return arr

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

        plotScan(data, colorKey, colorRange = colorRange, save = True, fileName = saveFile, show = False)

    # return to previous backend
    plt.switch_backend(backend)

# generate scan images for all pickles in a directory. Used to mass produce scan images from multi scan experiments
def generateScanPlotsInDirectory(dirName : str, colorKey, colorRange = [None, None], saveFormat = '.png'):

   fileNames = listFilesInDirectory(dirName)

   generateScanPlots(fileNames, colorKey, colorRange = colorRange, saveFormat = saveFormat)

# Plot the evolution of the value of dataKey vs time at a given list of coordinates
# If normalized = True, the data will be divided by the corresponding value in the first coordinate
# TODO: add colormap to plot (esp for linecuts)
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

# generate repeat pulse plot
# inputs: dataDict from a pickle and the key for the data to plot
# generates a scatter plot of the dataKey data vs time (in hours)
def plotRepeatPulseDataVsTime(dataDict, dataKey):

    rawTime = np.array([])
    data = np.array([])
    # gather timeCollected and data
    for index in dataDict.keys():
        if type(index) == int:
            rawTime = np.append(rawTime, dataDict[index]['time_collected'])
            data = np.append(data, dataDict[index][dataKey])

    time = timeCollectedToExperimentHours(rawTime)
    plt.scatter(time, data)
    plt.show()

##############################################################################3
############ Analysis and Data Correction Functions ############################33
################################################################################

# function for use in applyFunctionToData that calculates the maximum minus minimum value
def maxMinusMin(voltages):

    return np.max(voltages) - np.min(voltages)

# returns the x-value where ydat array is at its maximum
def maxXVal(xdat, ydat):

    return xdat[ydat.argmax()]

# returns the sum of the absolute value of an input array. This value is directly proportional to the integral of the signal
def absoluteSum(voltages):

    return np.sum(abs(voltages))


def baselineCorrectVoltage(voltage, baseline):

    return voltage - baseline

# removes the effect of pulser gain from pulse-echo data by solving for linear gain from dB-gain
# linear gain = 10**(decibel gain / 10), then v(input) = v(output) / linear gain
def correctVoltageByGain(data, gain):

    # note: pulser gain is in units of 10ths of a dB (i.e. 100ths of a power of ten)
    # inverting the gain requires a negative power
    linearGain = 10**(gain / 100)

    return data / linearGain

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

# A simple ToF algorithm that gets most of the functionality of the hilbert threshold method without the edge artifacts of the
# hilber transform. Should also be much faster
# Takes in the y (voltage) data (hopefully baseline corrected) and the x (time) data. OPtional threshold argument determines
# the fraction of max to determine arrival
# Algorithm takes the absolute value of the yData, determines the threshold from the max(abs(y))
# and then returns the x-value that first exceeds this threshold
def simpleThresholdTOF(yDat, xDat, threshold = 0.1):

    if len(yDat) != len(xDat):
        print("simpleThresholdTOF Error: x- and y- data must be the same length. Check that the correct keys are being used.")
        return -1

    if threshold <=0 or threshold >=1:
        print("simpleThresholdTOF Error: input threshold is out of bounds. Threshold must be >0 and <1.")
        return -1

    absY = abs(yDat)

    thresholdValue = threshold * np.max(absY)

    firstBreakIndex = firstIndexAboveThreshold(absY, thresholdValue)

    return xDat[firstBreakIndex]

# Calculate the time of flight for a signal by calculating the Hilbert envelope and returning the time value where it reaches
# a certain fraction of its max value
# Inputs y-data of the signal ('voltage'), x-data ('time') and the fraction of maximum for the threshold (number in (0,1))
# Includes an option to linearly interpolate the ToF rather than return the closest measured value
# Returns the time of flight
def envelopeThresholdTOF(yDat, xDat, threshold = 0.5, linearInterpolation = True):

    if len(yDat) != len(xDat):
        print("envelopeThresholdTOF Error: x- and y- data must be the same length. Check that the correct keys are being used.")
        return -1

    if threshold <=0 or threshold >=1:
        print("envelopeThresholdTOF Error: input threshold is out of bounds. Threshold must be >0 and <1.")
        return -1

    envelope = hilbertEnvelope(yDat)

    # Calculate the actual value of the threshold
    thresholdValue = threshold * np.max(envelope)

    firstBreakIndex = firstIndexAboveThreshold(envelope, thresholdValue)

    if linearInterpolation:

        # handle edge case where first break is the first data point. In this case, do not interpolate
        if firstBreakIndex == 0:
            return xDat[0]
        else:
            # gather two points around the threshold crossing, perform linear interpolation
            point0 = (xDat[firstBreakIndex - 1], envelope[firstBreakIndex - 1])
            point1 = (xDat[firstBreakIndex], envelope[firstBreakIndex])
            slope = (point1[1] - point0[1]) / (point1[0] - point0[0])
            intercept = point0[1] - (slope * point0[0])
            xInterp = (thresholdValue - intercept) / slope
            return xInterp

    else:
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

# Calculate the noise level as the square of the standard deviation of the first values of the waveform
# inputs a voltage array (should baseline corrected so the mean value can be assumed to be 0)
# outputs the standard deviation squared
def noiseLevelByStartingValues(voltage, startWindow):

    stdV = np.std(voltage[0:startWindow])

    return stdV**2

# Calculate the time of flight of a wave based on when the wave's value rises above a certain signal to noise threshold (wave voltage **2 / noise standard deviation **2)
# inputs the (baseline-corrected) voltage and time data, as well as the window length in the beginning to calculate the noise floor,
#   and the target signal to noise ratio. Returns the time when the wave first exceeds the signalToNoiseRatio
# returns the time that first exceeds the target signal to noise. If no point exceeds the signal to noise, returns -1
def signalToNoiseTOF(voltage, time, startWindow = 50, signalToNoiseRatio = 50):

    # calculate noise std
    noise = noiseLevelByStartingValues(voltage, startWindow)

    # calculate signal to noise of each point in wave
    snr = np.square(voltage) / noise

    tofIndex = np.nonzero(snr >= signalToNoiseRatio)[0]

    if len(tofIndex) > 0:
        return time[tofIndex[0]]
    else:
        return -1

# A helper function to generate a list of coordinates on a line
# used to feed into plotScanDataAtCoors to look at linecuts of data
# Inputs: startCoor 2-tuple, length of the line, axis 2-tuple i.e. (1, 0) for X-line, (0, 1) for Y-line or (1,1) for diagonal,
# and step size on line
def generateLineCoors(startCoor, length, axis, step):

    # floor is used to round and convert to an int
    numberOfSteps = math.floor(length / step)

    return [(startCoor[0] + (axis[0] * step * i), startCoor[1] + (axis[1] * step *i)) for i in range(numberOfSteps)]

# define a logistic function for curve fitting
# x is the independent variable, A is the amplitude, x0 is the x-axis shift, k is the midpoint slope, and c is the y-axis shift
def logisticFunction(x, A, x0, k, c):
    return A / (1 + np.exp(-k * (x - x0))) + c

# helper function for logistic fitting that provides initial guesses for the fitting parameters
def logisticFunctionPreFit(xDat, yDat):

    # offset c is the initial value before the fast rise. Take first y-value for c
    c = yDat[0]

    # x0 is the location where the derivative is maximized and k is the value of the derivative at that maximum
    # we calculate that derivative using a Savitzy-Golay filter
    deriv = savgolFilter(yDat, xDat, derivOrder = 1)
    k = max(deriv)
    kIndex = np.argmax(deriv)
    x0 = xDat[kIndex]

    # A is the increase in size before and after. take the value 2 indices after x0 minus the c-guess as a starting value
    #   NOTE: previously this used max minus min, but because lots of data has a linear growth after the exponential section
    #         this will more accurately reflect the logistic portion of the data
    # NOTE: we need to also check for the edge case where kIndex + 2 is out of the list bounds
    aIndex = min(kIndex + 2, len(yDat) - 1)
    A = yDat[aIndex] - c

    return np.array([A, x0, k, c])

# A function for fitting data to a logistic function that generates smart guesses for the fitting parameters
# and sets the parameter bounds to be within an input fraction of those generated guesses
def smartLogisticFit(xDat, yDat, boundFactor = 0.1, maxfev = 10000):

    # generate guesses for fitting parameters
    guesses = logisticFunctionPreFit(xDat, yDat)

    # generate bounds for the fitting parameters
    boundFraction = boundFactor * guesses
    upperBound = guesses + boundFraction
    lowerBound = guesses - boundFraction

    # do an error check to prevent lowerBound[i] > upperBound[i], which can happen when the bounds are negative
    # this should not occur in normal data, but can happen when the data is non logistic and decreasing
    for i in range(len(upperBound)):
        #swap bounds if they are switched
        if lowerBound[i] > upperBound[i]:
            lower = lowerBound[i]
            upper = upperBound[i]
            upperBound[i] = lower
            lowerBound[i] = upper

    return curve_fit(logisticFunction, xDat, yDat, guesses, bounds = (lowerBound, upperBound), maxfev = maxfev)

# same as above, but including a linearly increasing tail instead of a constant offset
def logisticFunctionLinearTail(x, A, x0, k, c):
    return A / (1 + np.exp(-k * (x - x0))) + (c * x)

# a smarter version of the above: a piecewise function that is logistic below x0+1 and linear at the point
# (x0+1, A + c) with slope m. The equation for this line is then y = m (x - x0 - 1) + A + c
def logisticLinearPiecewise(x, A, x0, k, c, m):

    return np.piecewise(x, [x < x0 + 1, x >= x0 + 1],
                 [lambda x: logisticFunction(x, A, x0, k, c),
                  lambda x: (m * (x - x0 - 1)) + A + c])

# helper function for logistic-linear fitting that provides initial guesses for the fitting parameters
def logisticLinearFunctionPreFit(xDat, yDat):

    # offset c is the initial value before the fast rise. Take first y-value for c
    c = yDat[0]

    # x0 is the location where the derivative is maximized and k is the value of the derivative at that maximum
    # we calculate that derivative using a Savitzy-Golay filter
    deriv = savgolFilter(yDat, xDat, derivOrder=1)
    k = max(deriv)
    kIndex = np.argmax(deriv)
    x0 = xDat[kIndex]

    # A is the increase in size before and after. take the value 2 indices after x0 minus the c-guess as a starting value
    # NOTE: we need to also check for the edge case where kIndex + 2 is out of the list bounds
    aIndex = min(kIndex + 2, len(yDat) - 1)
    A = yDat[aIndex] - c

    # m is guessed by taking the average of the derivative from the aIndex to the end of the data (i.e. the section after logitstic growth)
    m = np.mean(deriv[aIndex:])

    return np.array([A, x0, k, c, m])

# A function for fitting data to a logistic-linear piecewise function that generates smart guesses for the fitting parameters
# and sets the parameter bounds to be within an input fraction of those generated guesses
def smartLogisticLinearPiecewiseFit(xDat, yDat, boundFactor = 0.1, maxfev = 2000):

    # generate guesses for fitting parameters
    guesses = logisticLinearFunctionPreFit(xDat, yDat)

    # generate bounds for the fitting parameters
    boundFraction = boundFactor * guesses
    upperBound = guesses + boundFraction
    lowerBound = guesses - boundFraction

    # do an error check to prevent lowerBound[i] > upperBound[i], which can happen when the bounds are negative
    # this should not occur in normal data, but can happen when the data is non logistic and decreasing
    for i in range(len(upperBound)):
        #swap bounds if they are switched
        if lowerBound[i] > upperBound[i]:
            lower = lowerBound[i]
            upper = upperBound[i]
            upperBound[i] = lower
            lowerBound[i] = upper
        elif upperBound[i] == 0:
            upperBound[i] = 1

    # need to catch RuntimeErrors when curve_fit doesn't converge. For some reason this doesn't work in the wrapper
    # fitCubeTimeData() so it must be done here
    try:
        fit, cov = curve_fit(logisticLinearPiecewise, xDat, yDat, guesses, bounds = (lowerBound, upperBound), maxfev = maxfev)
    except RuntimeError:
        fit, cov = np.array([np.nan,np.nan,np.nan,np.nan,np.nan]), np.array([np.nan])

    return fit, cov


###############################################################################################################
########################## THE DATA CUBE ######################################################################
################################################3##############################################################

# Functions for creating, saving, editing, and manipulating 4D data pulled from multi-scans
# This will enable faster analysis and plotting of data sets through time vs previous methods
# An explanation:
#   Multiscan data is a 4D tensor:
#       2 spatial dimensions (X,Z)
#       1 time dimension
#       1 data dimension (data sets at each (X, Z, t) point))
#   Condensing all of this info into one large pickled array will enable faster analysis
#   The caveat: we need to drop all large data sets from the array - it can only carry the calculated single-number data (e.g. max-min)
#       but not the raw data (e.g. time, voltage). The time, voltage data uses 99% of the memory of a data set, so including that
#       means we wouldn't be able to load the whole array into memory
#   A full workflow would then be:
#       sqlite3 raw data -> pickled dictionary -> perform analysis -> save analysis results in -THE CUBE- -> perform further analysis on THE CUBE
# THE CUBE is implemented as a class with variables 'fileName', 'dataKeys', 'sampleName', and 'data'
#   'fileName' and 'sampleName' values are strings which disignate the filename the cube is pickled in, and a name of the sample being analyzed
#   'dataKeys' is a dict with number of keys == length of 4th array dimension. Each key is a string which is the name of a data point in the CUBE.
#       The value is the integer index of that key within data[i,j,k]; that is, if dataCube['dataKeys']['maxMinusMin'] = 2, then
#       data[i,j,k,2] is the value of 'maxMinusMin' for all coordinates and times
#       This structure is sufficient for small (<100) numbers of keys. If the number of data points becomes large, this may become slow
#       and the inverse dict may also be constructed for fast identification of data indices
#   'fileTimes' is a dict that matches the time index to a fileName for the corresponding scan. This makes updating the DATACUBE significantly faster
#   'data' contains the 4D numpy array:
#       data[i,j,k] = np.array([data0, data1, data2,...])
#       where i is an integer corresponding to the x-coordinates of the scan
#       j is an integer corresponding to the z- or y- coordinates of the scan
#       k is an integer corresponding to the start time of the scan
#       The minimum cube must contain data[i,j,k] = [x-coordinate, z-coordinate, time_collected, collection_index]

# functions needed: convert pickles to cube, load cube, save cube, add to cube, update cube
# extract from cube: point, line in space, line in time, box in space, box in space-time, smaller cube
#   need a helper function: quickly convert from actual coordinates (x, z, experiment time) to data indices
#       Should be doable in O(1) by taking first and last point along axis and assuming it divides evenly. This is
#       Always true for spatial coordinates and should be approximately true (good enough) for time coordinates
# This should be implemented as a class

class DataCube():

    # DataCube must be given data to initialize
    # inputs: the directory of the pickles to assimilate into the cube, plus a fileName to save the cube as
    # the cube is saved in a directory below dirName with the name 'DATACUBE//'
    def __init__(self, dirName, sampleName):

        #TODO: check if the cube already exists before making a new one. If the cube already exists, run updateCube instead
        self.sampleName = sampleName
        self.picklesToCube(dirName)

    def picklesToCube(self, dirName):

        print("\nOrdering files by time...\n")
        orderedFiles = orderPickles(dirName)

        # gather the data keys
        print("\nGathering data keys...\n")
        firstData = loadPickle(orderedFiles[0])

        # we will use the keys from the first collection_index and assume that applies for all data
        keyDict = {}
        keyIndex = 0
        for key in firstData[0].keys():

            # need to gather all keys whose values are not a list or numpy array since those are too large to efficiently CUBE
            if type(firstData[0][key]) != list and type(firstData[0][key]) != np.ndarray:
                keyDict[key] = keyIndex
                keyIndex += 1

        self.dataKeys = keyDict

        # initialize the DATACUBE array
        # first determine the spatial axes and their length
        spatialAxes = coordinateToIndexMap(firstData)
        axis0len = spatialAxes['n']
        axis1len = spatialAxes['m']
        # the length of the time axis is number of scans (=number of files)
        timelen = len(orderedFiles)
        # the length of the data axis is the number of dataKeys
        datalen = len(keyDict.keys())

        dataCube = np.zeros((axis0len, axis1len, timelen, datalen))

        #initialize fileTimes dict
        fileTimes = {}

        # iterate through scans, ASSIMILATE DATA INTO THE CUBE
        # every data point has coordinate i,j,t,d, where i,j are the spatial coordinates, t is time, and d is data index
        print("\n---ASSIMILATING DATA INTO THE CUBE---\n")
        for t in tqdm(range(len(orderedFiles))):

            # load the scan
            scanData = loadPickle(orderedFiles[t])

            # populate the fileTimes dict
            fileTimes[t] = orderedFiles[t]

            # iterate through collection_indices of the data
            for collection_index in scanData.keys():

                # verify that the dataPoint is indeed a collection_index, not 'parameters' or 'fileName'
                if type(collection_index) == int:

                    # convert collection_index to array indices
                    i, j = collectionIndexToArrayIndex(scanData, collection_index)

                    # iterate through dataKeys, fill in corresponding data
                    for dataKey in keyDict.keys():

                        # get the index to save the data in
                        d = keyDict[dataKey]

                        # write the data in the coordinate. Use try/except to put in NaN when a KeyError occurs (i.e. applyFunctionToData halted before finishing on a data set)
                        try:
                            dataCube[i,j,t,d] = scanData[collection_index][dataKey]
                        except KeyError:
                            dataCube[i,j,t,d] = np.nan

        self.data = dataCube
        self.fileTimes = fileTimes

        print("\nSaving the DATACUBE...\n")
        # create fileName to save under
        self.fileName = dirName + 'DATACUBE//' + self.sampleName + '.pickle'

        # create the directory if it doesn't exist
        os.makedirs(dirName + 'DATACUBE//', exist_ok = True)

        # save the cube
        self.saveCube()

    def saveCube(self):

        fileName = self.fileName
        # extract directory from fileName

        with open(self.fileName, 'wb') as f:
            pickle.dump(self, f)

        f.close()

    #NOTE: cannot define loadCube() as a class method - loadPickle should work instead

    # update cube adds newly calculated data from the multi-scan pickles to the cube
    # if no dirName is provided, updateCube will use self.fileTimes to find the files
    #   the dirName argument shoud ONLY be used if the files have been moved. If that is the case, the files will need to be re-ordered
    # updateCube will also only check the first scan for changes. dataKeys must be added to all pickles in the multi-scan -
    #       missing dataKeys in later scans will cause failures
    def updateCube(self, dir = 'default'):

        # if the directory is not default, need to remake the self.fileTimes dict
        if dir != 'default':

            print("updateCube: non-default directory input. Updating fileTimes dict...")
            orderedFiles = orderPickles(dir)

            # check that the number of files in the input directory match the number of files in fileTimes
            # if they do not match, print an error message and fail
            if len(orderedFiles) != len(self.fileTimes.keys()):
                print("updateCube ERROR: number of files in input directory does not match the number of files in current DATACUBE.\n"
                      "Consider initializing a new cube in the target directory rather than updating the existing cube.")
                return -1

            # update the fileTimes dict by iterating through the orderedFiles
            for i in range(len(orderedFiles)):
                self.fileTimes[i] = orderedFiles[i]

        # load first scan and determine if any keys are updated
        firstScan = loadPickle(self.fileTimes[0])

        # count the number of single data-point dataKeys in firstScan[0]
        dataKeys = []
        for key in firstScan[0].keys():

            # need to gather all keys whose values are not a list or numpy array since those are too large to efficiently CUBE
            if type(firstScan[0][key]) != list and type(firstScan[0][key]) != np.ndarray:
                dataKeys.append(key)

        # test whether any new dataKeys were added by doing a set difference
        newKeySet = set(dataKeys)
        oldKeySet = set(self.dataKeys.keys())
        addedKeys = newKeySet - oldKeySet

        # if there are no added keys, print a message and return
        if len(addedKeys) == 0:
            print("updateCube: no new data keys to add. Update finished")
            return 0

        # add the new keys to self.dataKeys, making sure to add on to the end of the existing indices
        # first make sure all of dataKeys.values() are integers before taking their maximum
        for val in self.dataKeys.values():
            if type(val) != int:
                print("updateCube ERROR: cube.dataKeys.values() must be integers but it contains " + str(val) +
                      "\n. updateCube aborted, consider remaking the dataCube using DataCube(dir, sample)")
                return -1

        newIndex = max(self.dataKeys.values()) + 1

        for newKey in addedKeys:
            self.dataKeys[newKey] = newIndex
            newIndex += 1

        # the new cube must be made by padding the 4th axis. Using np.resize causes values to shift in ways that do not preserve ordering
        padLength = len(addedKeys)
        newCube = np.pad(self.data, ((0,0),(0,0),(0,0),(0,padLength)))

        # iterate through files, add in new data
        print("\n---ASSIMILATING NEW DATA INTO THE CUBE---\n")
        for t in tqdm(self.fileTimes.keys()):

            scanData = loadPickle(self.fileTimes[t])

            # iterate through collection_indices of the data
            for collection_index in scanData.keys():

                # verify that the dataPoint is indeed a collection_index, not 'parameters' or 'fileName'
                if type(collection_index) == int:

                    # convert collection_index to array indices
                    i, j = collectionIndexToArrayIndex(scanData, collection_index)

                    # iterate through dataKeys, fill in corresponding data
                    for dataKey in addedKeys:

                        # get the index to save the data in
                        d = self.dataKeys[dataKey]

                        # write the data in the coordinate. Use try/except to put in NaN when a KeyError occurs (i.e. applyFunctionToData halted before finishing on a data set)
                        try:
                            newCube[i, j, t, d] = scanData[collection_index][dataKey]
                        except KeyError:
                            newCube[i, j, t, d] = np.nan

        self.data = newCube
        self.saveCube()

    # function for converting linux time to experiment time (hours since first point)
    # adds 'experiment_time' as a new point along the data dimension
    def calculateExperimentTime(self):

        # find the index for 'time_collected'. raise an error if it isn't present
        if 'time_collected' in self.dataKeys.keys():
            timeIndex = self.dataKeys['time_collected']
        else:
            print("adjustCubeTime ERROR: 'time_collected' is not a data point in the cube. Check the raw data and then re-make the DATACUBE")

        # grab minimum time. since cube slices are in order, this is cube[0,0,0,time_collected]
        minTime = self.data[0,0,0,timeIndex]

        # add experiment_time to datakeys
         # first make sure all of dataKeys.values() are integers before taking their maximum
        for val in self.dataKeys.values():
            if type(val) != int:
                print("updateCube ERROR: cube.dataKeys.values() must be integers but it contains " + str(val) +
                      "\n. updateCube aborted, consider remaking the dataCube using DataCube(dir, sample)")
                return -1

        newIndex = max(self.dataKeys.values()) + 1
        self.dataKeys['experiment_time'] = newIndex

        # add padding to the cube
        newCube = np.pad(self.data, ((0, 0), (0, 0), (0, 0), (0, 1)))

        # iterate through all points and calculate experiment time
        cubeSize = np.shape(newCube)
        for i in tqdm(range(cubeSize[0])):
            for j in range(cubeSize[1]):
                for t in range(cubeSize[2]):
                    newCube[i,j,t,newIndex] = (newCube[i,j,t,timeIndex] - minTime) / 3600

        # save the cube
        self.data = newCube
        self.saveCube()

    # curve fitting over time
    # inputs a fitFunc (a wrapped version of e.g. scipy.optimize.curve_fit() like in smartLogisticFit
    # also inputs a list of ordered datakeys to input to the fitting function, a 2-tuple range of time indices to fit over
    #   (with range (0, None) indicating to use the whole time range), and finally any additional arguments to be passed to
    #   the fitFunc. Also contains optional save and saveName parameters, which will pickle the output array in the directory of the DATACUBE
    #   if the saveName input is left as an empty string '' then the pickle will be named by combining self.sampleName and fitFunc
    # the output is an array of fit parameters for each i,j spatial coordinate, along with the absolute coordinates
    def fitCubeTimeData(self, fitFunc, fitKeys : list, timeRange = (0, None), save = False, saveName = '', *fitargs):

        # gather data indices. First check that all input fitKeys are in self.dataKeys
        for key in fitKeys:
            if key not in self.dataKeys.keys():
                print("fitCubeTimeData ERROR: input data key " + str(key) + " is not in self.dataKeys. Check the spelling of the keys and that the desired datapoint has been added to the CUBE.\n"
                                                                            "Here is a list of keys in self.dataKeys for reference: " + str(self.dataKeys.keys()))
                return -1

        dataIndices = [self.dataKeys[key] for key in fitKeys]

        # also need to determine the coordinate keys and indices.
        # first determine which axes were used for the scan
        # NOTE: the assumption of order in the for loop means that scans with unexpected primary/secondary axes (i.e. Z/X instead of X/Z) will be rotated in the output array
        coorKeys = []
        for axis in ['X', 'Y', 'Z']:
            if axis in self.dataKeys.keys():
                coorKeys.append(axis)

        # next gather the axis indices
        axisIndices = [self.dataKeys[key] for key in coorKeys]

        # determine the length of the output fit parameters by performing a test fit on the first point
        # for normal datacube data sets of ~4000 points, this will add ~<1% extra time depending on the fitness of the first data point
        tstData = []
        for d in dataIndices:
            tstData.append(self.data[0, 0, timeRange[0]:timeRange[1], d])
        tstFit, tstCov = fitFunc(*tstData, *fitargs)
        fitLen = len(tstFit)

        # initialize the result array. It should be 3 dimensional, with 2 axes corresponding to the spatial axis of the DATACUBE
        # and one axis of length = fit parameters + number of spatial axes (2)
        dataShape = np.shape(self.data)
        fittingArray = np.zeros((dataShape[0], dataShape[1], fitLen + 2))

        # iterate through spatial coordinates, gather data and perform fit at every coordinate and save the result in the corresponding array position
        print("Fitting DATACUBE...\n")
        for i in tqdm(range(dataShape[0])):
            for j in range(dataShape[1]):

                # gather data at coordinate
                fittingData = []
                for d in dataIndices:
                    fittingData.append(self.data[i, j, timeRange[0]:timeRange[1], d])

                # fit the data. Use try/except to catch RuntimeErrors where fit does not converge. Use nan for results there
                try:
                    fit, cov = fitFunc(*fittingData, *fitargs)
                except RuntimeError:
                    print("fitCubeTimeData Warning: fitting at coordinate index (" + str(i) + ", " + str(j) + ") did not converge")
                    fit = [np.nan for x in range(fitLen)]

                # add the data to the fittingArray
                # first add the fitting parameters
                for k in range(0, fitLen):
                    fittingArray[i, j, k] = fit[k]

                # next add the spatial coordinates. Because the fittingArray was allocated to have len(fitLen) + 2, these operations are safe
                fittingArray[i, j, fitLen] = self.data[i, j, 0, axisIndices[0]]
                fittingArray[i, j, fitLen + 1] = self.data[i, j, 0, axisIndices[1]]

        # if saving, determine the directory of the DATACUBE and then pickle the result array there
        if save:

            # find the directory of the DATACUBE
            cubeDir = os.path.dirname(self.fileName) + '//'

            # if saveName is informed, add it to the directory and append '.pickle'
            if type(saveName) == str and saveName != '':
                saveFile = cubeDir + saveName + '.pickle'

            # if saveName is not informed or isn't a string, generate a saveName from self.sampleName and fitFunc
            else:
                saveFile = cubeDir + self.sampleName + '_' + fitFunc.__name__ + '.pickle'

            # pickle the file
            print("fitCubeTimeData: saving fitting parameter array as " + saveFile)
            with open(saveFile, 'wb') as f:
                pickle.dump(fittingArray, f)

            f.close()

        return fittingArray

    # function for checking fits
    # inputs coordinate to check, the x- and y-data keys that were fit, the function that was fit to, a pickle containing an array for all coordinates with the best fit parameters at each coordinate,
    # and the time range as a 2-tuple or list
    # returns a plot of the data points with the fitting overlaid
    def checkFit(self, i, j, dataKeys, fitFunc, fitData, fitTimeRange):

        for key in dataKeys:
            if key not in self.dataKeys.keys():
                print("checkFit ERROR: input data key " + str(
                    key) + " is not in self.dataKeys. Check the spelling of the keys and that the desired datapoint has been added to the CUBE.\n"
                           "Here is a list of keys in self.dataKeys for reference: " + str(self.dataKeys.keys()))
                return -1

        # retrieve the data that was fit from the data cube
        dataIndices = [self.dataKeys[key] for key in dataKeys]

        xData = self.data[i,j,fitTimeRange[0]:fitTimeRange[1], dataIndices[0]]
        yData = self.data[i,j,fitTimeRange[0]:fitTimeRange[1], dataIndices[1]]

        # gather the fit parameters at the given i,j
        fitParams = fitData[i,j, 0:-2]

        # generate data for plotting fit line
        fitX = np.linspace(xData[0], xData[-1], 100)
        fitY = fitFunc(fitX, *fitParams)

        # make plots
        plt.scatter(xData, yData, c = 'orange')
        plt.plot(fitX, fitY)
        plt.show()


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
