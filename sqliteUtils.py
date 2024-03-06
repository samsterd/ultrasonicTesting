import sqlite3
import database as Database
import numpy as np
from typing import Callable
from tqdm import tqdm
import time

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

# Applies a function to a data set by iterating through it line by line and stores the result
# Inputs: database cursor, the function to apply to the dataset, the name of the column to store the result in
#   the column names to retrieve the data from (a list of strings), and the name of the table to retrieve from
# NOTE: func is assumed to operate on a list of two arrays i.e. [ ([x1,x2,...]), ([y1,y2,...])]
# Outputs: the result of applying the function to all rows as a list. It also writes the result into a new column in the database
# TODO: this will probably be faster if the write call is saved for the end
def applyFunctionToData(connection, cursor, func : Callable, resName : str, dataColumns = ['voltage', 'time'], keyColumn = ['collection_index'], table = 'acoustics'):

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

        funcResult = func(arrayList)

        writeToDB(connection, writeCursor, resName, table, funcResult, keyColumn[0], keyValue)

        funcResultList.append(funcResult)

    return funcResultList


# A function to write a data value to a specific row
# Inputs the connection and cursor objects, the name of the column to insert into, the name of the table
#     and the column and value to use as the row identifier (should be the PRIMARY KEY of the table)
# Saves the data to the database and returns nothing
def writeToDB(con, cur, column : str, table : str, value, keyCol, keyVal):

    # Generate the INSERT query based
    updateQuery = "UPDATE " + table + " SET " + column + " = " + str(value) + " WHERE " + keyCol + " = " + str(keyVal)

    # Execute and commit the result
    cur.execute(updateQuery)
    con.commit()

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

# Simple function to take the sum of the absolute values of the 'y' values
def absoluteSum(arrList):
    return sum(abs(arrList[1]))

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

# Create a new column in a database

# Write values to new column

# Load map coordinates and a data column

# plot a map