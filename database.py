import sqlite3
import numpy as np
import io
import time
import os

# Class for creating/saving into SQlite Database during ultrasound experiments
# Contains functions for initializing databases, saving experimental parameters, and reformatting/saving data from dictionaries
class Database:

    def __init__(self, params : dict):
        """
        A class for creating/saving/loading an SQlite database during ultrasound experiments. A new Database object is
        created for every ultrasound experiment

        Class methods:
            init(params : dict) : initialize the Database object, extract necessary information from the experimental parameters dict,
                and create the database file to hold the experimental data
            adaptArray(arr: numpy array): defines an adapter for converting numpy arrays to an sqlite-usable format
            convertArray(text): defines a converter for reading numpy arrays that have been saved using adaptArray
            dataTableInitializer(params : dict): creates the data table based on the experimental parameters
            generateVoltageString(params : dict): creates column titles for the voltage readings based on experimental parameters
            generateOffsetString(params : dict): creates column titles for the voltage offset if it is used in the experiment
            parameterTableInitializer(params : dict): creates a data table for saving the experimental parameters
            writeParameterTable(params : dict): creates a database query that writes the experimental parameters to the table
            parseQuery(inputDict: dict, table : str): generates an SQlite query string and a list of data in order to write the input dict into a table
            write(query : str, vals : list): takes the output string from parseQuery and writes it into the database
            writeData(dataDict : dict, table : str): a wrapper function which combines parseQuery and write into a single function
        Class variables:
            connection: sqlite3 database connection
            cursor: sqlite3 cursor for interacting with the database
        """

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
        Define adapters for converting numpy arrays to sqlite-usable format
        Taken from http://stackoverflow.com/a/31312102/190597 (SoulNibbler)
        This operation of storing numpy arrays as raw binary in an sqlite3 table is mildly cursed, but it makes a MASSIVE
        speed improvement versus converting the data arrays to strings

        Args:
            arr (numpy array) : the array to be converted
        Returns:
            Raw binary of the numpy array
        """
        out = io.BytesIO()
        np.save(out, arr)
        out.seek(0)
        return sqlite3.Binary(out.read())

    # define adapters for converting numpy arrays to sqlite-usable format
    # copied from stackoverflow: https://stackoverflow.com/questions/18621513/python-insert-numpy-array-into-sqlite3-database
    @staticmethod
    def convertArray(text):
        """
        Defines a converter for reading binary "array" types in the saved sqlite file and interpreting them as numpy arrays
        copied from stackoverflow: https://stackoverflow.com/questions/18621513/python-insert-numpy-array-into-sqlite3-database
        This operation of storing numpy arrays as raw binary in an sqlite3 table is mildly cursed, but it makes a MASSIVE
        speed improvement versus converting the data arrays to strings

        Args:
            text ("array" binary read from sqlite3 table)
        Returns:
            numpy array
        """
        out = io.BytesIO(text)
        out.seek(0)
        return np.load(out)

    def dataTableInitializer(self, params : dict):
        """
        Generates an SQL query string to intialize the data table based on the experiment function

        Args:
            params (dict): the experimental parameters dict
        Returns:
            query (str): an sqlite3 query string for creating the table with all appropriate columns
        """

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

    def generateVoltageString(self, params: dict):
        """
        Helper function to generate initialization strings for the different voltages dependent on the experiment parameters

        Args:
            params (dict): the experimental parameters dict
        Returns:
            voltage strings (str): a string specifying all of the measured voltage columns that will be needed for the experiment
        """

        baseString = 'voltage_'
        mode = params['collectionMode']
        direction = params['collectionDirection']
        mux = params['multiplexer']
        modeStrings = []

        # short circuit in the simplest case and default to 'voltage' to maintain backward compatibility
        if (mode == 'transmission' and direction == 'forward') or mux == False:
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


    def generateGainOffsetString(self, params : dict):
        """
        A helper function to generate initialization strings for the gain and offsets in pulse-echo mode, if applicable
        this only saves the data if there is echo data in the experiment and echo auto range is on
        only saves the offset/gain for the directions that are collected in the experiment

        Args:
            params (dict): the experimental parameters dict
        Returns:
            gain offset string (str): a string specifying the columns for offsets that should be saved based on the experiment
        """

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

    def parameterTableInitializer(self, params : dict):
        """
        Initialize table to record all input parameters for the experiment

        Args:
            params (dict): the experimental parameters dict
        Returns:
            table string (str): An sqlite3 query string for creating the table, to be passed to write()
        """

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

    def writeParameterTable(self, params : dict):
        """
        Generates a database query for writing the experimental parameters into the table created by parameterTableInitializer

        Args:
            params (dict): the experimental parameters dict
        Returns:
            query string (str), vals (list) : a string and list of values suitable for passing to write()
        """

        #create db query for the parameters to the parameters table
        query, vals = self.parseQuery(params, 'parameters')

        # vals need extra formatting to ensure they are all either an int, float, or array. Anything that isn't one of these
        # i.e. tuples or None are converted to strings
        safeValTypes = [
            val if (type(val) == int or type(val) == float or type(val) == np.ndarray) else str(val) for val in vals
        ]

        return query, safeValTypes

    @staticmethod
    def parseQuery(inputDict: dict, table: str = 'acoustics'):
        """
        Takes a dict and turns it into an SQL-readable format for writing the data

        Args:
            inputDict (dict): dict where the keys are columns and values are the data to write in those columns
            table (str) : the name of the table to write in
        Returns:
            query (str), vals (list) : a query string and the values as a list to be executed on the db connection
        """

        dictKeys = inputDict.keys()
        keyString = ', '.join([key for key in dictKeys])

        qMarks = "(" + ("?," * (len(dictKeys)-1)) + "?)"

        vals = [inputDict[key] for key in dictKeys]

        query = 'INSERT INTO ' + table + ' (' + keyString + ') VALUES ' + qMarks + ';'

        return query, vals

    def write(self, query: str, vals: list):
        """
        Use the output of parseQuery to write into the database file

        Args:
            query (str): an sqlite3-readable query string
            vals (list): a list of values to write into the table
        Returns:
            lastrowid of the sqlite3 cursor after the data has been written
        """

        self.cursor.execute(query, vals)
        self.connection.commit()

        return self.cursor.lastrowid

    # wrapper function to combine generating queries and writing to database.
    # only inputs the data dict. Assumes you are writing to the 'acoustics' table
    def writeData(self, dataDict : dict, table : str = 'acoustics'):
        """
        Wrapper function to combine generating query strings and writing into the database

        Args:
            dataDict (dict): a dict whose keys are columns and values are data to write into the table
            table (str) : the name of the table to write into

        Returns:
            None
        """

        query, vals = self.parseQuery(dataDict, table)
        self.write(query, vals)