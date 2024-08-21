import sqlite3
import numpy as np
import io
import time

#todo: update documentation for overall class
class Database:
    """Writes to a local database.

    Example:
        db = database.Database(db_filename='INL_GT_DE_2022_08_01_1')
        while *data is being updated*:
            *make some payload*
            query: str = database.parseQuery(payload=payload)
            database.write(query)
    """

    def __init__(self, params : dict):

        #create db connection, create cursor
        self.connection = sqlite3.connect(params['fileName'] + '.sqlite3')
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
        voltageTable = ' array,\n'.join(voltageString) + ' array,\n' # need to add final separator at the end
        initTable = initTable + voltageTable

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
            initTable = initTable + primaryAxisColumn + secondaryAxisColumn

        return initTable + ')'

    # helper function to generate initialization strings for the different voltages dependent on the experiment parameters
    def generateVoltageString(self, params):

        baseString = 'voltage_'
        mode = params['collectionMode']
        direction = params['collectionDirection']
        modeStrings = []

        # short circuit in the simplest case and default to 'voltage' to maintain backward compatibility
        if mode == 'transmission' and direction == 'forward':
            return 'voltage'

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

        return dirStrings

    # initialize table to record oscilloscope parameters
    #todo: generate table based on parameter dict. save full dict rather than hardcode every new parameter
    def parameterTableInitializer(self, params : dict):
        initTable = '''CREATE TABLE IF NOT EXISTS parameters (
            time_started REAL PRIMARY KEY,
            measure_time REAL,
            delay REAL,
            waves REAL,
            samples REAL,
            transducer_frequency REAL,
            voltage_range REAL,
            voltage_autorange INTEGER
            )
        '''
        if params['pulserType'] == 'tone burst':
            initTable = initTable + ',\nhalf_cycles INTEGER'
        return initTable

    # Generates a database query for writing the experimental parameters
    def writeParameterTable(self, params : dict):

        # copy over parameters into a separate dict. This isn't the best way to do this and really exposes some bad namespace choices :(
        parameters = {}
        parameters['time_started'] = time.time()
        parameters['measure_time'] = params['measureTime']
        parameters['delay'] = params['measureDelay']
        parameters['waves'] = params['waves']
        parameters['samples'] = params['samples']
        parameters['transducer_frequency'] = params['transducerFrequency']
        parameters['voltage_range'] = params['voltageRange']
        parameters['voltage_autorange'] = int(params['autoRange'])

        #create db query for the parameters to the parameters table
        query, vals = self.parseQuery(parameters, 'parameters')

        return query, vals

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
    def writeData(self, dataDict):

        query, vals = self.parseQuery(dataDict)
        self.write(query, vals)