import sqlite3
import numpy as np
from typing import Callable
from tqdm import tqdm
import bottleneck as bn
import time
from matplotlib import pyplot as plt


###############################################################
#### Basic DB manipulation ###################################
###############################################################

# TODO: create cursors within functions rather than pass around a global cursor
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
# Inputs the connection and cursor objects, the name of the column to update, the name of the table
#     and the column and value to use as the row identifier (should be the PRIMARY KEY of the table)
# Outputs nothing
def updateRowCol(con, cur, column : str, table : str, value, keyCol, keyVal):

    # Generate the INSERT query based
    updateQuery = "UPDATE " + table + " SET " + column + " = " + str(value) + " WHERE " + keyCol + " = " + str(keyVal)

    # Execute and commit the result
    start = time.time()
    cur.execute(updateQuery)
    exTime = time.time()
    # print(exTime - start)
    # con.commit()
    # comTime = time.time()
    # print(comTime - exTime)

# Create a new column within a table
def createNewColumn(con, cur, table : str, columnName : str):

    # Create query from input
    query = "ALTER TABLE " + table + " ADD COLUMN " + columnName + " REAL"

    cur.execute(query)
    con.commit()

# delete an existing column in a table. USE WITH CAUTION
def deleteColumn(con, cur, table: str, columnName: str):

    # Create query from input
    query = "ALTER TABLE " + table + " DROP COLUMN " + columnName

    cur.execute(query)
    con.commit()

# TODO: make a search pixels function to SELECT WHERE (pixelrange)

##########################################################################
########## Data Analysis #################################################
#########################################################################

# Applies a function to a data set by iterating through it line by line and stores the result
# Inputs: database cursor, the function to apply to the dataset, the name of the column to store the result in
#   the column names to retrieve the data from (a list of strings), and the name of the table to retrieve from
# NOTE: func is assumed to operate on a list of two arrays i.e. [ ([x1,x2,...]), ([y1,y2,...])]
# Outputs: the result of applying the function to all rows as a list. It also writes the result into a new column in the database
# TODO: this will probably be faster if the write call is saved for the end
# TODO: this function has become bloated and might need to be broken up
def applyFunctionToData(connection, cursor, func : Callable, resName : str, dataColumns = ['time', 'voltage'], keyColumn = ['collection_index'], table = 'acoustics', *funcArgs):

    # Gather the number of rows in the db
    numRows = numberOfRows(cursor, table)

    # Create a new column in the table to hold the generated data
    createNewColumn(connection, cursor, table, resName)

    # Generate and execute a db query to get the data and the primary key
    columnsToSelect = dataColumns + keyColumn
    selectQuery = "SELECT " + ", ".join(columnsToSelect) + " FROM " + table

    res = cursor.execute(selectQuery)

    writeCursor = connection.cursor()

    funcResultList = []

    # Iterate through the result, convert the data to numpy arrays, apply the function, and save the result
    for i in tqdm(range(numRows)):

        row = res.fetchone()

        # Initialize a list to save the data arrays
        arrayList = []

        # row is a tuple of length >= 2, with the final entry being the primary key
        # convert each entry in row to an array except the final primary key
        for i in range(len(row) - 1):
            arrayList.append(stringListToArray(row[i]))

        # Retrieve the primary key value of the row as the last member
        keyValue = row[-1]

        funcResult = func(arrayList, *funcArgs)

        updateRowCol(connection, writeCursor, resName, table, funcResult, keyColumn[0], keyValue)

        funcResultList.append(funcResult)

    connection.commit()

    return funcResultList

#TODO: make applyFunctionsToData that also iterates through a list of functions

# Helper function to convert a 'stringified' list ('[1.1, 3.2, 4.3]') into a numpy array ([1.1, 3.2, 4.3])
# Inputs the string, outputs the list
# Used to convert sql-saved lists into numpy arrays
# TODO: in the future, saving and loading can be made smarter - save the data as binary and directly load it into an array
def stringListToArray(strList : str):

    # Reformat the string by removing brackets and splitting along the ','
    strFormatted = strList.strip('[]').split(', ')

    floatList = []
    # Convert the string numbers to floats
    for num in strFormatted:
        floatList.append(float(num))

    return np.array(floatList)

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

    xDat = stringListToArray(rawData[0])
    yDat = stringListToArray(rawData[1])

    plt.plot(xDat, yDat)
    plt.show()

# TODO: finish writing this once you write a findPixel function
# def plotPixel(cursor, primaryCoor, secondaryCoor, primaryAxis = 'X', secondaryAxis = 'Z', xCol = 'time', yCol = 'voltage', table = 'acoustics'):
#
#     dataColumns = xCol + ', ' + yCol
#
#     # Format pixel coordinates as a WHERE statement
#     wherePixel = 'WHERE ' +

# plot a map
def plot2DScan(cursor, xCol : str, yCol : str, datCol : str, save = False, fileName = '', table = 'acoustics'):

    # Format the requested columns for the db query
    columns = xCol + ', ' + yCol + ', ' + datCol

    # Formate and execute SELECt query
    selectQuery = "SELECT " + columns + " FROM " + table

    rawData = cursor.execute(selectQuery).fetchall()

    xDat = np.array([])
    yDat = np.array([])
    cDat = np.array([])

    for row in rawData:
        xDat = np.append(xDat, float(row[0]))
        yDat = np.append(yDat, float(row[1]))
        cDat = np.append(cDat, float(row[2]))

    plt.scatter(xDat, yDat, c = cDat)
    plt.colorbar()

    if save == True:
        plt.savefig(fileName)

    plt.show()

    # Make SELECT query

    # Convert data to np arrays

    # plot

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