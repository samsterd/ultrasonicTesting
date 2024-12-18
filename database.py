import sqlite3
import numpy as np
import io
import time
import os

# Class for creating/saving into SQlite Database during ultrasound experiments
# Contains functions for initializing databases, saving experimental parameters, and reformatting/saving data from dictionaries
class Database:

    def __init__(self, params : dict):

        #create db connection, create cursor
        # first check if the requested filename already exists. If so print a warning and generate a new filename with the timestamp
        # todo: implement checks earlier in the experiment creation to prevent the user from inputting an existing file
        if os.path.exists(params['fileName'] + '.sqlite3'):
            # this is kind of cursed, sorry
            fileName = params['fileName'] + str(int(time.time())) + '.sqlite3'
            print("Database Warning: requested save file already exists. \nCurrent will be saved as " + fileName + " instead.")
        else:
            fileName = params['fileName'] + '.sqlite3'

        self.connection = sqlite3.connect(fileName)
        self.cursor = self.connection.cursor()

        # register adapters for converting between numpy arrays and text
        # modified from https://stackoverflow.com/questions/18621513/python-insert-numpy-array-into-sqlite3-database
        # Converts np.array to TEXT when inserting
        sqlite3.register_adapter(np.ndarray, self.adaptArray)
        # Converts TEXT to np.array when selecting
        sqlite3.register_converter("array", self.convertArray)

        #create dataTableInitializer and parameters_table_initializer based on experiment type
        paramTableInit = self.parameterTableInitializer(params)
        dataTableInit = self.dataTableInitializer(params)

        #create parameters table
        self.cursor.execute(paramTableInit)

        #generate command to write parameters to the table
        paramQuery, paramVals = self.writeParameterTable(params)

        #write query to parameter table
        self.write(paramQuery, paramVals)

        #create data table
        self.cursor.execute(dataTableInit)

    # define adapters for converting numpy arrays to sqlite-usable format
    # copied from stackoverflow: https://stackoverflow.com/questions/18621513/python-insert-numpy-array-into-sqlite3-database
    @staticmethod
    def adaptArray(arr):
        """
        http://stackoverflow.com/a/31312102/190597 (SoulNibbler)
        """
        out = io.BytesIO()
        np.save(out, arr)
        out.seek(0)
        return sqlite3.Binary(out.read())

    # define adapters for converting numpy arrays to sqlite-usable format
    # copied from stackoverflow: https://stackoverflow.com/questions/18621513/python-insert-numpy-array-into-sqlite3-database
    @staticmethod
    def convertArray(text):
        out = io.BytesIO(text)
        out.seek(0)
        return np.load(out)

    # Generates an SQL query string to intialize the data table based on the experiment function
    def dataTableInitializer(self, params : dict):

        # acoustics is name of TABLE. Not sure if we want this hardcoded
        # general table structure that is true in all experiments
        initTable = "CREATE TABLE IF NOT EXISTS acoustics (\n"

        voltageString = self.generateVoltageString(params)
        gainOffsetString = self.generateGainOffsetString(params)
        initTable += voltageString + gainOffsetString

        initTable = initTable + '''time array,
            time_collected REAL,
            collection_index INTEGER PRIMARY KEY'''

        # If the experiment involves scanning, also include the location and axis data
        if params['experiment'] == 'single scan' or params['experiment'] == 'multi scan':

            #need to add a comma to the end of initTable
            initTable = initTable + (',\n')

            #add a column for each axis
            primaryAxisColumn = params['primaryAxis'] + ' REAL,\n'
            secondaryAxisColumn = params['secondaryAxis'] + ' REAL'
            initTable += primaryAxisColumn + secondaryAxisColumn

        return initTable + ')'

    # helper function to generate initialization strings for the different voltages dependent on the experiment parameters
    def generateVoltageString(self, params):

        baseString = 'voltage_'
        mode = params['collectionMode']
        direction = params['collectionDirection']
        modeStrings = []

        # short circuit in the simplest case and default to 'voltage' to maintain backward compatibility
        if mode == 'transmission' and direction == 'forward':
            return 'voltage array,\n'

        # in other cases, build the more complex labels
        if mode == 'transmission' or mode == 'both':
            modeStrings.append(baseString + 'transmission_')
        if mode == 'echo' or mode == 'both':
            modeStrings.append(baseString + 'echo_')

        if direction == 'forward':
            dirStrings = [modeString + 'forward' for modeString in modeStrings]
        elif direction == 'reverse':
            dirStrings = [modeString + 'reverse' for modeString in modeStrings]
        elif direction == 'both':
            dirStringsf = [modeString + 'forward' for modeString in modeStrings]
            dirStringsr = [modeString + 'reverse' for modeString in modeStrings]
            dirStrings = dirStringsf + dirStringsr

        # format the dirStrings into 'voltage_type array,\n'
        return ' array,\n'.join(dirStrings) + ' array,\n'  # need to add final separator at the end

    # a helper function to generate initialization strings for the gain and offsets in pulse-echo mode, if applicable
    # this only saves the data if there is echo data in the experiment and echo auto range is on
    # only saves the offset/gain for the directions that are collected in the experiment
    def generateGainOffsetString(self, params):

        gainOffsetString = ''
        # check if the mode includes pulse-echo and auto ranging is on
        if (params['collectionMode'] == 'echo' or params['collectionMode'] == 'both') and params['autoRangeEcho'] == True:
            if params['collectionDirection'] == 'forward' or params['collectionDirection'] == 'both':
                gainOffsetString += 'voltageOffsetForward REAL,\ngainForward INT,\n'
            if params['collectionDirection'] == 'reverse' or params['collectionDirection'] == 'both':
                gainOffsetString += 'voltageOffsetReverse REAL,\ngainReverse INT,\n'
            return gainOffsetString
        else:
            return ''

    # initialize table to record all input parameters for the experiment
    def parameterTableInitializer(self, params : dict):

        paramString = '''CREATE TABLE IF NOT EXISTS parameters ('''
        for key in params.keys():

            keyString = key
            # need to determine sqlite data type based on param value
            valType = type(params[key])
            if valType == float:
                keyType = ' REAL,\n'
            elif valType == int:
                keyType = ' INT,\n'
            else:
                keyType = ' TEXT,\n'

            paramString += keyString + keyType

        # need to replace ending ",\n" with a ")"
        tableString = paramString.removesuffix(",\n") + ")"

        return tableString

    # Generates a database query for writing the experimental parameters
    def writeParameterTable(self, params : dict):

        #create db query for the parameters to the parameters table
        query, vals = self.parseQuery(params, 'parameters')

        # vals need extra formatting to ensure they are all either an int, float, or array. Anything that isn't one of these
        # i.e. tuples or None are converted to strings
        safeValTypes = [
            val if (type(val) == int or type(val) == float or type(val) == np.ndarray) else str(val) for val in vals
        ]

        return query, safeValTypes

    # Parse query takes a dict and turns it into an SQL-readable format for writing the data
    # returns a query string and the values as a list to be executed on the db connection
    @staticmethod
    def parseQuery(inputDict: dict, table: str = 'acoustics'):

        dictKeys = inputDict.keys()
        keyString = ', '.join([key for key in dictKeys])

        qMarks = "(" + ("?," * (len(dictKeys)-1)) + "?)"

        vals = [inputDict[key] for key in dictKeys]

        query = 'INSERT INTO ' + table + ' (' + keyString + ') VALUES ' + qMarks + ';'

        return query, vals

    # takes the output of parseQuery and writes it to the database
    # inputs the query string and value list from parseQuery
    # outputs the cursor at the end of the table
    def write(self, query: str, vals: list):

        self.cursor.execute(query, vals)
        self.connection.commit()

        return self.cursor.lastrowid

    # wrapper function to combine generating queries and writing to database.
    # only inputs the data dict. Assumes you are writing to the 'acoustics' table
    def writeData(self, dataDict, table : str = 'acoustics'):

        query, vals = self.parseQuery(dataDict, table)
        self.write(query, vals)