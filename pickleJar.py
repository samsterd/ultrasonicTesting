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
#  'fileName' : name of file to load and save the pickle?
# }

import pickle
import sqlite3
import sqliteUtils as squ
from typing import Callable
from tqdm import tqdm
import time
import numpy as np
import os

# Functions needed:
# implement as a class!
#   no b/c we want to apply to functions across multiple dicts
#   yes b/c we want to keep the filename as a property of the dict?
#   compromise: fileName is always a top level key of the pickle/dataDict
#       this isn't great - what if the pickle moves? should it be rewritten every time it is loaded?
#   __init__() creates an empty dict?
# sqlite_to_pickle
# save_pickle
# load_pickle
# before doing all of this - need to make sure this is actually faster
#   write sqlite_to_pickle for a simple case and test saving / loading

tstFile = "C://Users//shams//Drexel University//Chang Lab - General//Individual//Sam Amsterdam//acoustic scan data//sa-1-2b wetting scan//sa_1_2b_1MLiDFOB_wetting_1.sqlite3"
pickleFile = "C://Users//shams//Drexel University//Chang Lab - General//Individual//Sam Amsterdam//acoustic scan data//sa-1-2b wetting scan//sa_1_2b_1MLiDFOB_wetting_1.pickle"

#
# Convert sqlite database
# Inputs a filename with .sqlite3 extension
# Creates a data dict and saves it as the same filename .pickle
# Returns the dataDict
# TODO: this is not handling the parameter table yet
def sqliteToPickle(file : str):

    # Open db connection
    con, cur = squ.openDB(file)

    # get column names
    colNames = squ.columnNames(cur, 'acoustics')

    # find the position of collection_index, which is used to create keys for the dataDict
    indexPosition = colNames.index('collection_index')

    dataDict = {}

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
            if row[i] != None:
                dataDict[index][colNames[i]] = squ.stringConverter(row[i])
            else:
                pass

    # remove .sqlite3 extension and .pickle extension
    pickleFile = os.path.splitext(file)[0] + '.pickle'
    dataDict['fileName'] = pickleFile

    # save the dataDict as a pickle
    with open(pickleFile, 'wb') as f:
        pickle.dump(dataDict, f)

    con.close()

    return dataDict


# Convert multiple sqlite files to pickle
# Returns None
def multiSqliteToPickle(files : list):

    for file in files:
        sqliteToPickle(file)

# Convert all sqlite DBs in a directory to pickles
# Returns None
def directorySqliteToPickle(dir : str):

    files = os.listdir(dir)
    fileNames = []
    for file in files:
        if file.endswith(".sqlite3"):
            fileNames.append(os.path.join(dir, file))

    multiSqliteToPickle(fileNames)

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

    return dataDict

# apply function to key
# takes a dataDict, a function, the key to store the result in, a list of keys to use as the function arguments, and a list of additional arguments if needed
# def applyFunctionToData(dataDict : dict, func : Callable, resKey, dataKeys : list, *funcArgs):
#
#     # Iterate through the keys (coordinates) in the dataDict
#     for key in dataDict:
#
#         # Gather the data from dataKeys into a list to use as input to func
#         funcInputs = [dataDict[key][dataKey] for dataKey in dataKeys]
#
#         dataDict[key][resKey] = func(*funcInputs, *funcArgs)
#
#     # Repickle


# apply function to keys

# apply function to pickles

# apply function to pickles in directory

# normalize data across pickles in directory
#   need to specify name of t=0 pickle

#
# # pickle the dict
# start = time.time()
# with open(pickleFile, 'rb') as f:
#     # pickle.dump(dataDict, f)
#     dataDict = pickle.load(f)
#
# print("pickle time: " + str(time.time() - start))
#
# print(np.mean(dataDict[100]['voltage']))