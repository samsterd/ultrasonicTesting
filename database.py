## Modified from previous code
# TODO: modify style to bring in line with rest of project

import sqlite3
import numpy as np
import io
import time

class Database:
    """Writes to a local database.

    Example:
        db = database.Database(db_filename='INL_GT_DE_2022_08_01_1')
        while *data is being updated*:
            *make some payload*
            query: str = database.parse_query(payload=payload)
            database.write(query)
    """

    def __init__(self, params : dict):

        #create db connection, create cursor
        self.connection = sqlite3.connect(params['fileName'] + '.sqlite3')
        self.cursor = self.connection.cursor()

        #create data_table_initializer and parameters_table_initializer based on experiment type
        paramTableInit = self.parameter_table_initializer(params)
        dataTableInit = self.data_table_initializer(params)

        #create parameters table
        self.cursor.execute(paramTableInit)

        #generate command to write parameters to the table
        paramQuery = self.write_parameter_table(params)

        #write query to parameter table
        self.write(paramQuery)

        #create data table
        self.cursor.execute(dataTableInit)

    # Generates an SQL query string to intialize the data table based on the experiment function
    def data_table_initializer(self, params : dict):

        # acoustics is name of TABLE. Not sure if we want this hardcoded
        # general table structure that is true in all experiments
        #TODO: synchronize these to input keys in runUltrasonicExperiment
        initTable = '''CREATE TABLE IF NOT EXISTS acoustics (
            voltage BLOB,
            time REAL,
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

    # initialize table to record oscilloscope parameters
    def parameter_table_initializer(self, params : dict):
        initTable = '''CREATE TABLE IF NOT EXISTS parameters (
            time_started REAL PRIMARY KEY,
            measure_time REAL,
            delay REAL,
            waves REAL,
            samples REAL,
            voltage_range REAL)
        '''
        return initTable

    # Generates a database query for writing the experimental parameters
    def write_parameter_table(self, params : dict):

        # copy over parameters into a separate dict. This isn't the best way to do this and really exposes some bad namespace choices :(
        # TODO: return to this and improve it
        parameters = {}
        parameters['time_started'] = time.time()
        parameters['measure_time'] = params['measureTime']
        parameters['delay'] = params['measureDelay']
        parameters['waves'] = params['waves']
        parameters['samples'] = params['samples']
        parameters['voltage_range'] = params['voltageRange']

        #create db query for the parameters to the parameters table
        query = self.parse_query(parameters, 'parameters')

        return query

    # Parse query takes a dict and turns it into an SQL-readable format for writing the data
    @staticmethod
    def parse_query(payload: dict, table: str = 'acoustics') -> str:
        #TODO: update this approach. Also using ? for data, not string formatting, is best practice
        """Taken from Wes' prior code. Prepares the query.

        It's very hacky, but leaving for now. We have to parse the amps to a
        SQL-readable format. It doesn't accept the pythonic list directly;
        we must parse it to string literal.

        Args:
            payload (dict): The payload, with one entry being the acoustics data
                as received from runPicoMeasurement().
            table (str, optional): Table name, Defaults to "acoustics".

        Returns:
            str: The query.
        """

        keys: str = ', '.join([key for key in payload.keys()])

        #todo: this should be updated. json.dumps might be a universal solution here
        values_parsed: list = [f'"{str(val)}"' if isinstance(val, list) else str(val) for val in payload.values()]
        values: str = ', '.join(values_parsed)

        return f'INSERT INTO {table} ({keys}) VALUES ({values});'

    def write(self, query: str) -> int:
        """Writes data out to Drops.

        Args:
            query (str): The query as constructed from parse_query().

        Returns:
            int: ID of last row. Useful for seeing whether data was actually inserted.
        """

        self.cursor.execute(query)
        self.connection.commit()

        return self.cursor.lastrowid