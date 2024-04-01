import sqlite3
import numpy as np
from scipy.signal import hilbert
from typing import Callable
from tqdm import tqdm
import bottleneck as bn
import os
import time
import math
import json
from matplotlib import pyplot as plt
from matplotlib import colormaps as cmp

#Roadmap:

#change over to ? from string formatting

###############################################################
#### Basic DB manipulation ###################################
###############################################################

# TODO: create cursors within functions rather than pass around a global cursor?
# Open a connection to the database specified in filepath and initialize a cursor
# Returns the database connection object and the initialized cursor
def openDB(fileName):

    connection = sqlite3.connect(fileName)

    # Set rows to be represented by sqlite3 row class
    # connection.row_factory = sqlite3.Row

    cursor = connection.cursor()

    return connection, cursor

# Inputs a cursor and a name for a table
# Outputs a list of strings with the name of every column
# Use to extract a list of parameters for a given experiment, or to check what axes were scanned along
def columnNames(cursor, table : str):

    # Generate PRAGMA table_info query
    query = "PRAGMA table_info(" + table + ")"

    res = cursor.execute(query).fetchall()

    # The result will be a list of tuples. The name of the column is entry 1
    names = []
    for column in res:
        names.append(column[1])

    return names

# Inputs a cursor and table name
# Outputs the number of rows in the table
def numberOfRows(cursor, table: str):

    query = "SELECT COUNT(*) FROM " + table

    res = cursor.execute(query)

    return res.fetchone()[0]


# Retrieve experiment parameters
# Takes a cursor object and a name of the table containing the parameters (default 'parameters')
# Outputs a dict with the column names as keys and the first row as values
def retrieveParameters(cursor, table = 'parameters'):

    # Retrieve column names to use as keys
    paramNames = columnNames(cursor, table)

    # Combine the keys into a SELECT query
    query = 'SELECT ' + ", ".join(paramNames) + ' FROM ' + table

    # Fetch the first (and only) row
    res = cursor.execute(query)
    paramValues = res.fetchone()

    # Contruct a dict with the keys and the query result
    paramDict = dict(zip(paramNames, paramValues))

    return paramDict

# A function that executes an UPDATE query at a single (row,col) in the DB but does not commit it
#   Avoiding commits gives a large speed improvement when iterating over many rows
# Inputs the cursor objects, the name of the column to update, the name of the table
#     and the column and value to use as the row identifier (should be the PRIMARY KEY of the table)
# Outputs nothing
def updateCol(cur, column : str, table : str, value, keyCol, keyVal):

    # Generate the UPDATE query
    updateQuery = "UPDATE " + table + " SET " + column + " = ? WHERE " + keyCol + " = ?"

    # Execute and commit the result
    cur.execute(updateQuery, (value, keyVal))

# Faster function to update columns using a list of values and their corresponding PRIMARY KEY values
# Works by setting some memory parameters that increase speed (at the risk of corruption)
# Then it manually opens a transaction, executes the update query, and closes the transation
# Should be a MASSIVE performance improvement
def fastUpdateCol(cur, column : str, table : str, values, keyCol : str, keyValues):

    if len(values) != len(keyValues):
        print("Error (fastUpdateCol): values and keyValues lists must have equal length")
        return -1

    # First we convert the values and keyValues into paired sequences
    insertSeq = ((v, kv) for v, kv in zip(values, keyValues))

    # speed boost from using ram as temp memory and not waiting for write confirmation
    cur.execute("PRAGMA synchronous = OFF")
    cur.execute("PRAGMA temp_store = MEMORY")
    cur.execute("PRAGMA journal_mode = MEMORY")

    # Manually opening and closing the transaction gives a large speed increase
    cur.execute("BEGIN TRANSACTION")

    updateQuery = "UPDATE " + table + " SET " + column + " = ? WHERE " + keyCol + " = ?"
    cur.executemany(updateQuery, insertSeq)

    cur.execute("END TRANSACTION")

# Adds multiple values to multiple columns within a row. Runs many UPDATE queries in an optimized manner
# columns is a list of column names as string. values is a list of tuples. The final member of each tuple must be the key value, the others are the column values
#   the length of each tuple is then len(columns) + 1. keyCol is the name of the PRIMARY KEY used for updating. Code will work if it is not the primary key but it
#   will be signicantly slower
def updateCols(cur, columns : list, values : list, keyCol : str, table  = 'acoustics'):

    # convert the columns and values lists into properly formatted strings
    formattedColumns = "(" +  ", ".join(columns) + ")"

    # generate a string (?,?,...?) that is as long as len(columns)
    qMarks = "(" + ("?," * (len(columns)-1)) + "?)"

    # Generate UPDATE query
    # UPDATE table SET (column0,column1,...) = (?,?,...) WHERE keyCol = ?
    updateQuery = "UPDATE " + table + " SET " + formattedColumns + " = " + qMarks + " WHERE " + keyCol + " = ?"

    # speed boost from using ram as temp memory and not waiting for write confirmation
    # NOTE: this is mildly unsafe and could result in corrupted data if the program crashes mid-write
    cur.execute("PRAGMA synchronous = OFF")
    cur.execute("PRAGMA temp_store = MEMORY")
    cur.execute("PRAGMA journal_mode = MEMORY")

    # Manually opening and closing the transaction gives a large speed increase
    cur.execute("BEGIN TRANSACTION")

    cur.executemany(updateQuery, values)

    cur.execute("END TRANSACTION")


# Create a new column within a table
def createNewColumn(con, cur, table : str, columnName : str):

    # Create query from input
    query = "ALTER TABLE " + table + " ADD COLUMN " + columnName + " REAL"

    try:
        cur.execute(query)
        con.commit()
    except sqlite3.OperationalError:
        print("Error creating new column. Column likely already exists. Data will be overwritten")

# delete an existing column in a table. USE WITH CAUTION
def deleteColumn(con, cur, table: str, columnName: str):

    # Create query from input
    query = "ALTER TABLE " + table + " DROP COLUMN " + columnName

    cur.execute(query)
    con.commit()

# Retrieve data within a column
# TODO: update functionality to properly handle arrays
def fetchData(cursor, column : str, table = 'acoustics'):

    selectQuery = "SELECT " + column + " FROM " + table

    #execute query
    cursor.execute(selectQuery)
    rawData = cursor.fetchall()

    formattedData = np.array([stringConverter(x[0]) for x in rawData])

    return formattedData

# Retrieve data columns that are within certain coordinate ranges
# Returns requested data as a dict where the keys are dataColumns and values are arrays
# NOTE: ordering cannot be guaranteed in the data. To get the coordinate that corresponds to the data,
#   include the coordinates in the dataColumns
def fetchDataInBox(cursor, dataColumns : list, primaryCoorLimits : list, secondaryCoorLimits : list, primaryAxis = 'X', secondaryAxis = 'Z', table = 'acoustics'):

    # format the datacolumns for the query
    formattedDataColumns = ", ".join(dataColumns)

    # format the coor limits for the query
    primaryBounds = primaryAxis + ' > ' + str(primaryCoorLimits[0]) + ' AND ' + primaryAxis + ' < ' + str(primaryCoorLimits[1]) + ' AND '
    secondaryBounds = secondaryAxis + ' > ' + str(secondaryCoorLimits[0]) + ' AND ' + secondaryAxis + ' < ' + str(secondaryCoorLimits[1])
    whereCondition = ' WHERE ' + primaryBounds + secondaryBounds

    selectQuery = 'SELECT ' + formattedDataColumns + ' FROM ' + table + whereCondition

    cursor.execute(selectQuery)

    data = cursor.fetchall()

    dataDict = {}
    for i in range(len(dataColumns)):
        dataDict[dataColumns[i]] = np.array([stringConverter(x[i]) for x in data])

    return dataDict

# Function to lookup data from dataColumns list using collection_index as the selection parameter
#   Using collection_index is much faster than other search criteria
def fastLookup(cursor, index: int, dataColumns: list, table='acoustics'):

    # generate a where query using the pixel's index
    whereCondition = "collection_index = " + str(index)

    # format the datacolumns for the query
    formattedDataColumns = ", ".join(dataColumns)

    # Combine info into a SELECT query
    selectQuery = "SELECT " + formattedDataColumns + " FROM " + table + " WHERE " + whereCondition

    # Execute query and fetch data
    cursor.execute(selectQuery)
    # fetchone() is used because we are searching by primary key so only one result should return
    data = cursor.fetchone()

    return data

# Helper function that takes in a string returned from a table lookup and attempts to convert it to the appropriate data type
# Only handles floats and lists right now. If it isn't recognized, it returns the unchanged string
def stringConverter(string : str):

    # First attempt a float
    try:
        data = float(string)
        return data
    except ValueError or TypeError:
        # it isn't a float, so try to convert a list
        try:
            data = stringListToArray(string)
            return data
        # it isn't a list either. return the string unchanged
        except json.decoder.JSONDecodeError:
            return string

# Helper function to convert a 'stringified' list ('[1.1, 3.2, 4.3]') into a numpy array ([1.1, 3.2, 4.3])
# Inputs the string, outputs the list
# Used to convert sql-saved lists into numpy arrays
# TODO: in the future, saving and loading can be made smarter - save the data as binary and directly load it into an array
def stringListToArray(strList : str):

    # For some reason it is faster to use json.loads rather than np.fromstring
    return np.array(json.loads(strList))


##########################################################################
########## Data Analysis #################################################
#########################################################################

# Applies a function to a data set by iterating through it line by line and stores the result
# Inputs: database cursor, the function to apply to the dataset, the name of the column to store the result in
#   the column names to retrieve the data from (a list of strings), and the name of the table to retrieve from
# NOTE: func is assumed to operate on a list of two arrays i.e. [ ([x1,x2,...]), ([y1,y2,...])]
# Outputs: the result of applying the function to all rows as a list. It also writes the result into a new column in the database
def applyFunctionToData(connection, cursor, func : Callable, resName : str, dataColumns = ['time', 'voltage'], keyColumn = ['collection_index'], table = 'acoustics', *funcArgs):

    # Gather the number of rows in the db
    numRows = numberOfRows(cursor, table)

    # Create a new column in the table to hold the generated data
    createNewColumn(connection, cursor, table, resName)

    # Generate and execute a db query to get the data and the primary key
    columnsToSelect = dataColumns + keyColumn
    selectQuery = "SELECT " + ", ".join(columnsToSelect) + " FROM " + table

    res = cursor.execute(selectQuery)

    # Track the function results and their corresponding PRIMARY KEY values in index-matched lists
    funcResultList = []
    keyList = []

    # Iterate through the result, convert the data to numpy arrays, apply the function, record in a list with keys
    for i in tqdm(range(numRows)):

        row = res.fetchone()

        # Initialize a list to save the data arrays
        arrayList = []

        # row is a tuple of length >= 2, with the final entry being the primary key
        # convert each entry in row to an array except the final primary key
        for i in range(len(row) - 1):
            arrayList.append(stringConverter(row[i]))

        # Retrieve the primary key value of the row as the last member
        keyValue = row[-1]

        funcResult = func(arrayList, *funcArgs)

        funcResultList.append(funcResult)
        keyList.append(keyValue)

    # Write the results within a single transaction
    # First open a db transaction
    writeCursor = connection.cursor()
    # fastUpdateCol(writeCursor, resName, table, funcResultList, keyColumn[0], keyList)
    # connection.commit()

    fastUpdateCol(writeCursor, resName, table, funcResultList, keyColumn[0], keyList)

    # connection.commit()

    return funcResultList


# Version of applyFunctionToData that applies muliple functions to the same data set and saves it
#   This version should be significantly faster vs calling applyFunctionToData multiple times
#   because it minimizes the number of read/write steps
# funcs is now a list of callable functions
# Inputs: connection and cursor objects, a list of functions to apply, a list of column names for the results (index matched to funcs),
#   a list of 2 data columns to apply the functions to (i.e. times vs voltage), the key column (the PRIMARY KEY) used to identify the rows,
#   a table name, and an option funcArgs dict which maps the functions to a tuple of additional arguments (e.g. for staltaFirstBreak)
# Outputs nothing, but writes results to the database
def applyFunctionsToData(connection, cursor, funcs : list, resNames : list, dataColumns = ['time', 'voltage'], keyColumn = ['collection_index'], table = 'acoustics', funcArgs = {}):

    # Gather the number of rows in the db
    numRows = numberOfRows(cursor, table)

    # Create a new column in the table for each function to be calculated
    for col in resNames:
        createNewColumn(connection, cursor, table, col)

    # Generate and execute a db query to get the data and the primary key
    columnsToSelect = dataColumns + keyColumn
    selectQuery = "SELECT " + ", ".join(columnsToSelect) + " FROM " + table

    res = cursor.execute(selectQuery)

    # create a list to track the values and associate keyValue for each row
    # This list will be populated with tuples which will be fed to updateCols
    funcResultsList = []

    # Iterate through the result, convert the data to numpy arrays, apply the functions, and save the results
    for i in tqdm(range(numRows)):

        row = res.fetchone()

        # Initialize a list to save the data arrays
        arrayList = []

        # row is a tuple of length >= 2, with the final entry being the primary key
        # convert each entry in row to an array except the final primary key
        for i in range(len(row) - 1):
            arrayList.append(stringConverter(row[i]))

        # Retrieve the primary key value of the row as the last member
        keyValue = row[-1]

        funcResults = []

        extraArgs = ()

        for func in funcs:

            # Run func with extra arguments if func is in the funcArgs dict
            if func in funcArgs:
                funcResults.append(func(arrayList, *funcArgs[func]))

            else:
                funcResults.append(func(arrayList))

        #add the keyValue to the end of funcResults, convert it to a tuple, then append it to funcResultList
        #This puts the results in the format [(func0(row0), func1(row0), .., key(row0)), (func0(row1), func1....]
        # which is nice for sql queries
        funcResults.append(keyValue)
        funcResTuple = tuple(funcResults)

        funcResultsList.append(funcResTuple)

    writeCursor = connection.cursor()
    # write func results into current row
    updateCols(writeCursor, resNames, funcResultsList, keyColumn[0], table)

    connection.commit()

# Function that runs applyFunctionsToData on multiple databases
# Setting verbose = True will print the name of each file as it is analyzed
def analyzeDatabases(fileNames : list, funcs : list, resNames : list, dataColumns = ['time', 'voltage'], keyColumn = ['collection_index'], table = 'acoustics', funcArgs = {}, verbose = True):

    #Iterate through filenames
    for file in fileNames:

        if verbose == True:
            print("Analyzing " + file)

        #Create DB connection
        con, cur = openDB(file)

        #Run applyFunctionsToData
        if len(funcs) > 1:
            applyFunctionsToData(con, cur, funcs, resNames, dataColumns, keyColumn, table, funcArgs)
        else:
            applyFunctionToData(con, cur, funcs[0], resNames[0], dataColumns, keyColumn, table)

        #Close connection
        con.close()

def analyzeDirectory(dir, funcs : list, resNames : list, dataColumns = ['time', 'voltage'], keyColumn = ['collection_index'], table = 'acoustics', funcArgs = {}, verbose = True):

    # Grab list of files with .sqlite3 extension in the folder
    files = os.listdir(dir)
    fileNames = []
    for file in files:
        if file.endswith(".sqlite3"):
            fileNames.append(os.path.join(dir, file))

    # Analyze gathered files
    analyzeDatabases(fileNames, funcs, resNames , dataColumns, keyColumn, table, funcArgs, verbose)

# Perform a routine set of analysis of multiscan data within a folder
# Analysis functions: absolute_sum, arrayMax, and staltaFirstBreak(5,30,0.75)
# Results are stored as columns with the function names and parameters
def defaultMultiScanAnalysis(dir, plot = True):

    # list functions and dict their optional parameters
    funcList = [absoluteSum, arrayMax, staltaFirstBreak, envelopeThresholdTOF]
    funcParams = {staltaFirstBreak : (5, 30, 0.75)}

    # Convert function and parameter information into column names
    # Functions with parameters are stored as functionName_(parameters)
    colNames = []
    for func in funcList:
        if func in funcParams:
            # funcParams must be converted from tuple to underscored list to avoid confusing later SQL calls with parenthesis
            # also replaces decimal points with 'd'
            formattedParams = str(funcParams[func]).strip('()').replace(', ', '_').replace('.', 'd')
            colNames.append(str(func.__name__) + '_' + formattedParams)
        else:
            colNames.append(str(func.__name__))

    # run analysis
    analyzeDirectory(dir, funcList, colNames, funcArgs = funcParams)

    # generate plots
    if plot:
        generate2DScansDirectory(dir, 'X', 'Z', colNames)


# Retrieves the values in dataColumns at a given pixel coordinate
# Returns the values as an dict with dataColumns as the keys and the float-converted data as values
# Explanation for the speedup can be found in the function coordinatesToCollectionIndex
def dataAtPixel(cursor, dataColumns : list, primaryCoor, secondaryCoor, primaryAxis = 'X',  secondaryAxis = 'Z', table = 'acoustics', verbose = False):

    # Convert input coordinate to a collection_index
    pixelIndex = coordinatesToCollectionIndex(cursor, [primaryCoor], [secondaryCoor], primaryAxis, secondaryAxis, table, verbose)[0]

    data = fastLookup(cursor, pixelIndex, dataColumns, table)

    dataDict = {}
    # If data was not found, print a warning and return None
    # Otherwise, convert the data to floats and put it with the correct data key
    if data == None:
        print("dataAtPixel: no data returned. Check that the provided coordinates (" + str(primaryCoor) + ", " + str(
            secondaryCoor) + ") exist within the data set")
        return None
    else:
        for i in range(len(data)):
            dataDict[dataColumns[i]] = stringConverter(data[i])
        return dataDict

# Retrieves the values in dataColumns for given pixel coordinates
# Returns the values as a dict of dicts with dataColumns as the keys and the float-converted data as values
#                 (x0, z0) : {column 0 : val 00, column 1 : val 01, ...}
#   pixelsDat = { (x1, z1) : {column 0 : val 10, column 1 : val 11, ...}  }
#                 (x2, z2) : {column 0 : val 20, column 1 : val 21, ...}
# Explanation for the speedup can be found in the function coordinatesToCollectionIndex
def dataAtPixels(cursor, dataColumns: list, primaryCoors, secondaryCoors, primaryAxis='X', secondaryAxis='Z', table='acoustics', verbose=False):

    # check that primary and secondary coor lists are valid
    if len(primaryCoors) != len(secondaryCoors):
        print("dataAtPixels: length of primaryCoors and secondaryCoors must be equal. Returning None")
        return None

    # Convert input coordinate to a collection_index
    pixelIndices = coordinatesToCollectionIndex(cursor, primaryCoors, secondaryCoors, primaryAxis, secondaryAxis, table, verbose)

    coorDict = {}
    # iterate through pixels, grab data, convert to a dict, add to coorDict
    for i in range(len(pixelIndices)):
        index = pixelIndices[i]
        coor = (primaryCoors[i], secondaryCoors[i])
        dataDict = {}
        if index == None:
            print(
                "fastDataAtPixels: data index is None. Check that the provided coordinates (" + str(coor[0]) + ", " + str(
                    coor[1]) + ") exist within the data set")
            for i in range(len(dataColumns)):
                dataDict[dataColumns[i]] = None
        else:
            data = fastLookup(cursor, index, dataColumns, table)
            for i in range(len(dataColumns)):
                dataDict[dataColumns[i]] = stringConverter(data[i])
        coorDict[coor] = dataDict.copy()

    return coorDict

# Function to convert coordinates to a collection_index
    # Inputs a list of coordinates and axes, outputs the collection_index corresponding to each coordinate
# This does some algebra to massively speed up queries. More details are here:
#       Motivation: SQL searches are O(1) or O(ln n) with the int primary key (vs O(n) w/ other keys)
#       In order to search for pixels by primary key, we need a function which converts a given coordinate to a collection_index
#           This requires some algebra since we do not know a priori what the coordinate steps are. We must solve that using
#           the known ranges and a few sample coordinates. The math works as follows:
#           For an (x,z) scan, let xs, zs be the coordinate step that the map was collected at
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
def coordinatesToCollectionIndex(cursor, primaryCoors : list, secondaryCoors : list, primaryAxis = 'X',  secondaryAxis = 'Z', table = 'acoustics', verbose = True):

    # check that primary and secondary coor lists are valid
    if len(primaryCoors) != len(secondaryCoors):
        print("coordinatesToCollectionIndex: length of primaryCoors and secondaryCoors must be equal. Returning None")
        return None

    # Collect the needed constants
    # We will be using x as the primary coordinate and z as the secondary to match most common scanning data
    # (kf, xf, zf)
    kf = numberOfRows(cursor, table) - 1
    # Do some quick error checking - make sure kf > 0 or else the rest will fail
    if kf <= 1:
        print("coordinatesToCollectionIndex: input table only has one row. Check that the table and data are correct")
        return None
    # xf, zf == coordinates at kf
    formattedCoordinates = primaryAxis + ", " + secondaryAxis
    xfzfQuery = "SELECT " + formattedCoordinates + " FROM " + table + " WHERE collection_index = " + str(kf)
    xfzfTuple = cursor.execute(xfzfQuery).fetchone()
    xf = xfzfTuple[0]
    zf = xfzfTuple[1]

    # collect a second set of (k, x, z) at the second to last coordinate
    k0 = kf - 1
    x0z0Query = "SELECT " + formattedCoordinates + " FROM " + table + " WHERE collection_index = " + str(k0)
    x0z0Tuple = cursor.execute(x0z0Query).fetchone()
    x0 = x0z0Tuple[0]
    z0 = x0z0Tuple[1]

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
        print("coordinatesToCollectionIndex: unable to identify coordinate step. Unclear what went wrong, but its probably related to floating point rounding. Your data is probably cursed, contact Sam for an exorcism (or debugging).")
        return None

    # Now iterate through the input coordinates and convert to indices
    # using equation k = n(z/zs) + (x/xs)
    collectionIndices = []

    for i in range(len(primaryCoors)):
        x = primaryCoors[i]
        # Raise warnings if rounding
        if verbose == True and (x % xs != 0):
            print('coordinatesToCollectionIndex: primary coordinate ' + str(x) + 'is not a multiple of the primary step. Rounding coordinate.')

        z = secondaryCoors[i]
        if verbose == True and (z % zs != 0):
            print('coordinatesToCollectionIndex: secondary coordinate ' + str(z) + 'is not a multiple of the secondary step. Rounding coordinate.')

        index = (n * (z / zs)) + (x / xs)

        # handle out of bounds indices as None
        if index < 0:
            collectionIndices.append(None)
        else:
            collectionIndices.append(int(index))

    return collectionIndices

# Runs dataAtPixels across multiple scans,
# Returns a dict with the keys as (x,y) coordinates, and the values as a dict with keys as data columns and values as a numpy array
def multiScanDataAtPixels(fileNames : list, dataColumns : list, primaryCoors : list, secondaryCoors : list, primaryAxis = 'X',  secondaryAxis = 'Z', table = 'acoustics', verbose = True):

    # initialize storage list
    dataDictList = []

    # Iterate through files
    for file in fileNames:

        if verbose == True:
            print("Gathering data from " + file)

        # open connection
        con, cur = openDB(file)

        # collect data at pixels
        dataDictList.append(dataAtPixels(cur, dataColumns, primaryCoors, secondaryCoors, primaryAxis, secondaryAxis, table))

        con.close()

    # Merge data. storage list is a list of dicts of dicts. This got ugly...
    # First make a copy of dataDictList[0] but with the values as numpy arrays
    masterDict = {}

    for coordinate, coordinateData in dataDictList[0].items():
        masterDict[coordinate] = {dataColumn : np.array(value) for dataColumn, value in coordinateData.items()}

    # Now iterate through the rest of dataDictList, merging the values into the arrays of masterDict
    for scan in dataDictList[1:]:

        # for each scan in list, iterate through the keys (coordinates) and values (values == innerDict of data columns)
        for coor, coordinateData in scan.items():

            # set the value of masterDict[coordinate/key][data column / inn
            for dataColumn, value in coordinateData.items():
                if type(value) == float:
                    masterDict[coor][dataColumn] = np.append(masterDict[coor][dataColumn], value)
                elif type(value) == np.ndarray:
                    masterDict[coor][dataColumn] = np.vstack((masterDict[coor][dataColumn], value))

    return masterDict

# Runs multiScanDataAtPixels on all of the files within a given directory
# Returns a dict with the keys as (x,y) coordinates, and the values as a dict with keys as data columns and values as a numpy array
def directoryScanDataAtPixels(dir : str, dataColumns : list, primaryCoors : list, secondaryCoors : list, primaryAxis = 'X',  secondaryAxis = 'Z', table = 'acoustics', verbose = True):

    # Grab list of files with .sqlite3 extension in the folder
    files = os.listdir(dir)
    fileNames = []
    for file in files:
        if file.endswith(".sqlite3"):
            fileNames.append(os.path.join(dir, file))

    data = multiScanDataAtPixels(fileNames, dataColumns, primaryCoors, secondaryCoors, primaryAxis, secondaryAxis, table, verbose)

    return data


########################################################################
################## Plotting ############################################
########################################################################

# plot the first waveform in the db
def plotWaveform(cursor, xCol = 'time', yCol = 'voltage', table = 'acoustics'):

    # Format the requested columns for the db query
    columns = xCol + ', ' + yCol

    # Formate and execute SELECt query
    selectQuery = "SELECT " + columns + " FROM " + table

    rawData = cursor.execute(selectQuery).fetchone()

    xDat = stringConverter(rawData[0])
    yDat = stringConverter(rawData[1])

    plt.plot(xDat, yDat)
    plt.show()

def plotRepeatPulseData(cursor, xCol : str, yCol : str, table = 'acoustics'):

    # gather data
    xDat = fetchData(cursor, xCol, table)
    yDat = fetchData(cursor, yCol, table)

    # If x-axis is time_collected, bring the data to 0 and convert to hours
    if xCol == 'time_collected':

        minTime = min(xDat)
        xDat = (xDat - minTime) / 3600

    plt.scatter(xDat, yDat)
    plt.show()

# def plotRepeatPulseWaveOverTime(cursor, xCol: str, yCol: str, table='acoustics'):
#
#     # gather data
#     xDat = fetchData(cursor, xCol, table)
#     yDat = fetchData(cursor, yCol, table)
#
#     # If x-axis is time_collected, bring the data to 0 and convert to hours
#     if xCol == 'time_collected':
#         minTime = min(xDat)
#         xDat = (xDat - minTime) / 3600
#
#     plt.scatter(xDat, yDat)
#     plt.show()


# Plots the waveform at a specific single pixel
def plotPixelWaveform(cursor, primaryCoor, secondaryCoor, primaryAxis = 'X', secondaryAxis = 'Z', xCol = 'time', yCol = 'voltage', table = 'acoustics'):

    # get the pixel index
    pixelIndex = coordinatesToCollectionIndex(cursor, [primaryCoor], [secondaryCoor], primaryAxis, secondaryAxis, table, True)[0]

    # gather the data
    data = fastLookup(cursor, pixelIndex, [xCol, yCol], table)

    # convert the data to a numpy array
    xDat = stringConverter(data[0])
    yDat = stringConverter(data[1])

    # plot
    plt.plot(xDat, yDat, label = "(" + str(primaryCoor) + ", " + str(secondaryCoor) + ")")
    plt.xlabel("Time (ns)")
    plt.ylabel("Voltage (mV)")
    plt.show()

# Plots the waveform at a a list of pixels
def plotPixelsWaveform(cursor, primaryCoors : list, secondaryCoors : list, primaryAxis='X', secondaryAxis='Z', xCol='time',
                      yCol='voltage', table='acoustics'):

    # Check that inputs are properly formed
    if len(primaryCoors) != len(secondaryCoors):
        print("Error: plotPixelsWaveform: primaryCoors and secondaryCoors have different lengths.")
        return -1

    # get the pixel indices
    pixelIndices =  coordinatesToCollectionIndex(cursor, primaryCoors, secondaryCoors, primaryAxis, secondaryAxis, table, True)

    # gather and plot data at each pixel
    for i in range(len(primaryCoors)):

        coor = (primaryCoors[i], secondaryCoors[i])
        pixel = pixelIndices[i]

        # gather the data
        data = fastLookup(cursor, pixel, [xCol, yCol], table)

        # convert the data to a numpy array
        xDat = stringConverter(data[0])
        yDat = stringConverter(data[1])

        # plot
        plt.plot(xDat, yDat, label=str(coor))
        plt.xlabel("Time (ns)")
        plt.ylabel("Voltage (V)")

    plt.legend()
    plt.show()

# Plots the waveform at a specific single pixel
def plotPixelWaveformOverTime(dir, primaryCoor, secondaryCoor, primaryAxis = 'X', secondaryAxis = 'Z', xCol = 'time', yCol = 'voltage', table = 'acoustics'):

    dataDict = directoryScanDataAtPixels(dir, [xCol, yCol, 'time_collected'], [primaryCoor], [secondaryCoor], primaryAxis, secondaryAxis,
                                         table, verbose = True)

    # Convert time_collected to a common zero, then normalize it to [0,1] for use in colormaps'
    timesCollected = dataDict[(primaryCoor, secondaryCoor)]['time_collected']
    minTime = min(timesCollected)
    timesCollectZeroRef = timesCollected - minTime
    maxTime = max(timesCollectZeroRef)
    normTime = timesCollectZeroRef/maxTime

    for coor in dataDict.keys():
        for wave in range(len(dataDict[coor][xCol])):
            plt.plot(dataDict[coor][xCol][wave], dataDict[coor][yCol][wave],
                     c = cmp['viridis'](normTime[wave]),
                     label = round(timesCollectZeroRef[wave]/3600, 2))
    plt.legend()
    plt.show()


# Generates a plot of the given data column at certain coordinate values for all databases in a directory
# Plot x-axis is the first entry in dataColumns, y-axis is the second
# useful for multiscans
# If the normalized option is set to True, all values in dataColumns[1] will be divided by the value at the first coordinate
# If the
def plotScanDataAtPixels(dir : str, dataColumns : list, primaryCoors : list, secondaryCoors : list, primaryAxis = 'X',  secondaryAxis = 'Z', table = 'acoustics', verbose = True, normalized = False):

    dataDict = directoryScanDataAtPixels(dir, dataColumns, primaryCoors, secondaryCoors, primaryAxis, secondaryAxis, table, verbose)

    # Convert time axis to a common zero if the x-axis is experiment time'
    if dataColumns[0] == 'time_collected':
        minTimes = []
        for coor in dataDict:
            times = dataDict[coor]['time_collected']
            # Collect the first time (which should be the minimum)
            minTimes.append(times[0])

        # Find the experiment start time by taking the min of the mins
        t0 = min(minTimes)

    if normalized == True:
        # grab values from first coordinate
        normValue = dataDict[(primaryCoors[0], secondaryCoors[0])][dataColumns[1]]
        # iterate through all coors and divide by first coordinate
        for coor in dataDict.keys():
            # be wary of issues with copy and references here - may need to revise
            dataDict[coor][dataColumns[1]] = dataDict[coor][dataColumns[1]]/normValue

    for coor in dataDict.keys():
        if dataColumns[0] == 'time_collected':
            # Convert to common 0 by subtracting start time. Divide by 3600 to display in hours instead of seconds
            plt.scatter((dataDict[coor][dataColumns[0]] - t0)/3600, dataDict[coor][dataColumns[1]], label = str(coor))
        else:
            plt.scatter(dataDict[coor][dataColumns[0]], dataDict[coor][dataColumns[1]], label=str(coor))

    plt.legend()
    plt.show()

def baselineTest(dir : str, dataColumns : list, primaryCoors : list, secondaryCoors : list, primaryAxis = 'X',  secondaryAxis = 'Z', table = 'acoustics', verbose = True, normalized = False):

    dataDict = directoryScanDataAtPixels(dir, dataColumns, primaryCoors, secondaryCoors, primaryAxis, secondaryAxis, table, verbose)

    # Convert time axis to a common zero if the x-axis is experiment time'
    if dataColumns[0] == 'time_collected':
        minTimes = []
        for coor in dataDict:
            times = dataDict[coor]['time_collected']
            # Collect the first time (which should be the minimum)
            minTimes.append(times[0])

        # Find the experiment start time by taking the min of the mins
        t0 = min(minTimes)

    if normalized == True:
        # grab values from first coordinate
        normValue = dataDict[(primaryCoors[0], secondaryCoors[0])][dataColumns[1]]
        # iterate through all coors and divide by first coordinate
        for coor in dataDict.keys():
            # be wary of issues with copy and references here - may need to revise
            dataDict[coor][dataColumns[1]] = dataDict[coor][dataColumns[1]]/normValue

    for coor in dataDict.keys():
        if dataColumns[0] == 'time_collected':
            # Convert to common 0 by subtracting start time. Divide by 3600 to display in hours instead of seconds
            plt.scatter((dataDict[coor][dataColumns[0]] - t0)/3600, dataDict[coor][dataColumns[1]] -  dataDict[coor][dataColumns[2]], label = str(coor))
        else:
            plt.scatter(dataDict[coor][dataColumns[0]], dataDict[coor][dataColumns[1]], label=str(coor))

    plt.legend()
    plt.show()

# plot a map
# xCol, yCol, datCol - names of the table columns for the xy coordinates and the data to colormap to
# datRange = [min, max] clips the datCol values to max or min values. This helps to make the colormap more uniform across different maps
# todo: put limits on the z/color axis to allow easier comparison between scans
def plot2DScan(cursor, xCol : str, yCol : str, datCol : str, datRange = [None, None], save = False, show = True, fileName = '', table = 'acoustics'):

    # Format the requested columns for the db query
    columns = xCol + ', ' + yCol + ', ' + datCol

    # Formate and execute SELECt query
    selectQuery = "SELECT " + columns + " FROM " + table

    rawData = cursor.execute(selectQuery).fetchall()

    xDat = np.array([])
    yDat = np.array([])
    cDat = np.array([])

    for row in rawData:
        xDat = np.append(xDat, stringConverter(row[0]))
        yDat = np.append(yDat, stringConverter(row[1]))
        cDat = np.append(cDat, stringConverter(row[2]))

    if datRange[0] != None or datRange[1] != None:
        cDat = np.clip(cDat, datRange[0], datRange[1])


    plt.scatter(xDat, yDat, c = cDat)
    plt.colorbar()

    if save == True:
        plt.savefig(fileName)
        plt.close()

    if show == True:
        plt.show()

# Function to generate plots from several DB files.
# Saves plots from multiple files and can handle multiple data columns to plot as the z (color) axis
# Save the plots as datCol//fileName_datCol
def generate2DScans(fileNames : list, xCol : str, yCol : str, datCols : list, datRange = [None, None],  format = '.png', verbose = True):

    for file in fileNames:

        if verbose == True:
            print("Plotting " + file)

        # Open database connection
        con, cur = openDB(file)

        for dat in datCols:

            # Generate the save filename for each plot
            # Puts each different type of data plot in a separate folder for easier organization
            saveDir = os.path.dirname(file) + '//' + dat + '//'

            # make the saveDir if it doesn't exist
            if not os.path.exists(saveDir):
                os.makedirs(saveDir)

            # Generate savename by gathering the basename, removing the exension, adding the data column name and format extension
            saveName = os.path.basename(os.path.splitext(file)[0]) + dat + format
            saveFile = saveDir + saveName

            # run plot2dscan with save = True and show = False
            plot2DScan(cur, xCol, yCol, dat, datRange, save = True, show = False, fileName = saveFile)

        # Close db connection
        con.close()

def generate2DScansDirectory(dir, xCol : str, yCol : str, datCols : list, datRange = [None, None],  format = '.png', verbose = True):

    # Grab list of files with .sqlite3 extension in the folder
    files = os.listdir(dir)
    fileNames = []
    for file in files:
        if file.endswith(".sqlite3"):
            fileNames.append(os.path.join(dir, file))

    # run multiGenerateScanPlots with the list of fileNames
    generate2DScans(fileNames, xCol, yCol, datCols, datRange,  format, verbose)

##########################################################################33
############### Analysis Functions #########################################
##### For use with applyFunctionToData ###################################
###########################################################################

# Simple function to take the sum of the absolute values of the 'y' values
def absoluteSum(arrList):
    return bn.nansum(abs(arrList[1]))

# Return the  max of the y-values
def arrayMax(arrList):
    return bn.nanmax(arrList[1])

# Return the maximum minus the minimum. This value should indicated changes in attenuation without influence of baseline
#   drift
def maxMinusMin(arrList):
    return bn.nanmax(arrList[1]) - bn.nanmin(arrList[1])

# Calculate the mean of the last n y-values. Used to estimate the baseline for correcting oscilloscope wandering
def endMean(arrList, n = 5):

    # take last n values
    lastN = arrList[1][-n:]

    return np.mean(lastN)

# Calculate the time of the first break using STA/LTA algorithm
# Inputs the arrayList from applyFunctionToData, the length (in number of elements, NOT time) of the short and long averaging window,
#   and tresholdRatio, a number in (0,1) that determines what fraction of the maximum STA/LTA counts as the first break
def staltaFirstBreak(arrayList, shortWindow : int, longWindow : int, thresholdRatio = 0.75):

    # Assume that arrayList is (time, voltage) data
    timeData = arrayList[0]
    voltageData = arrayList[1]

    staltaArray = stalta(voltageData, shortWindow, longWindow)

    threshold = thresholdRatio * bn.nanmax(staltaArray)

    # Return time where first value in staltaArray is above threshold
    for i in range(len(staltaArray)):
        if staltaArray[i] > threshold:
            return timeData[i]

    # No value was found above threshold. Return -1
    return -1

def hilbertEnvelope(arrList):

    hilbertTransform = hilbert(arrList[1])

    return np.abs(hilbertTransform)

# method to calculate the time of flight by calculating the function envelope using a
# hilbert transform and finding the time where the envelope reaches a certain fraction of
# its max value
def envelopeThresholdTOF(arrList, threshold = 0.1):

    envelope = hilbertEnvelope(arrList)

    thresh = threshold * bn.nanmax(envelope)

    for i in range(len(envelope)):
        if envelope[i] > thresh:
            return arrList[0][i]

    print("envelopeThresholdTOF: no value was found above the threshold. Check that 0 < threshold < 1")
    return 0

# return absolute value of the real fast Fourier Transform
# def fft(arrList):
#     return abs(np.fft.rfft(arrList[1]))

###########################################################################
########## Analysis Helper Functions ####################################
#### Do not directly use with applyFunctionToData ###########################
########################################################################

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

# generate a grid of coordinates compatible with pixel isolating functions
# inputs one of the corners of the grid, the length in both dimensions, and the steps between points in both dimensions
# outputs a list of x and y coordinates
def generateCoordinateGrid(corner, lengths, steps):

    xStart = corner[0]
    xStop = xStart + lengths[0]
    # calculate the number of points in the linspace. Take abs since coordinates could be negative. Floor insures it is an int
    xPts = math.floor(abs(xStop - xStart)/steps[0]) + 1
    xLinspace = np.linspace(xStart, xStop, xPts)

    yStart = corner[1]
    yStop = yStart + lengths[1]
    yPts = math.floor(abs(yStop - yStart)/steps[1]) + 1
    yLinspace = np.linspace(yStart, yStop, yPts)

    x, y = np.meshgrid(xLinspace, yLinspace)

    return x.flatten(), y.flatten()

######################################################################
#### DEPRECATED CODE GRAVEYARD #################################

# code fragments from a prior write speed experiment
# wrote columns by creating a temporary table and merging it
    # # Create the temporary table
    # cur.execute("CREATE TABLE temp (" + column + " REAL, " + keyCol + " INTEGER PRIMARY KEY)")
    #
    # # Insert our values into the temp table
    # cur.executemany("INSERT INTO temp VALUES(?,?)", insertSeq)
    #
    # # Merge temp table into target table
    # # Example: table = acoustics, data column is absoluteSum and keyCol is collection_index
    # # "UPDATE acoustics SET(absoluteSum)=(temp.absoluteSum) FROM temp WHERE acoustics.collection_index = temp.collection_index
    # mergeQuery = "UPDATE " + table + " SET(" + column + ")=(temp." + column + ") FROM temp WHERE " + table + "." + keyCol + " = temp." + keyCol
    # cur.execute(mergeQuery)
    #
    # # delete the temp table
    # cur.execute("DROP TABLE temp")
    #
    # cur.execute("END TRANSACTION")