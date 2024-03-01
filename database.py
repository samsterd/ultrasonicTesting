##Author:
##Notes: Interface with writing to database.
##pithytimeout=0

import sqlite3
import numpy as np
import io

#todo: gather all experiment metadata here. this is experiment dependent, so create an initializer helper function that
#takes the experiment type
# TABLE_INITIALIZER = f'''CREATE TABLE IF NOT EXISTS {TABLE} (
#     voltage BLOB,
#     time REAL PRIMARY KEY,
#     waves REAL,
#     delay REAL,
#     voltage_range REAL,
#     duration REAL
# )
# '''


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

        #create table_initializer based on experiment type
        tableInit = self.table_initializer(params)

        #create db table
        self.cursor.execute(tableInit)

    def table_initializer(self, params : dict):
        #acoustics is name of TABLE. Not sure if we want this hardcoded
        # general table structure that is true in all experiments
        #TODO: synchronize these to input keys in runUltrasonicExperiment
        #TODO: find a better way to record these, since they are redundant for scans
        initTable = '''CREATE TABLE IF NOT EXISTS acoustics (
            voltage BLOB,
            time REAL,
            time_collected REAL PRIMARY KEY,
            waves REAL,
            delay REAL,
            voltage_range REAL
        '''
        # If the experiment involves scanning, also include the location and axis data
        if params['experiment'] == 'single scan' or params['experiment'] == 'multi scan':

            #need to add a comma to the end of initTable
            initTable = initTable + (',\n')

            #add a column for each axis
            primaryAxisColumn = params['primaryAxis'] + ' REAL,\n'
            secondaryAxisColumn = params['secondaryAxis'] + ' REAL'
            initTable = initTable + primaryAxisColumn + secondaryAxisColumn

        return initTable + ')'

    @staticmethod
    def parse_query(payload: dict, table: str = 'acoustics') -> str:
        """Prepares the query.

        It's very hacky, but leaving for now. We have to parse the amps to a
        SQL-readable format. It doesn't accept the pythonic list directly;
        we must parse it to string literal.

        Args:
            payload (dict): The payload, with one entry being the acoustics data
                as received from picoscope.callback().
            table (str, optional): Table name, Defaults to "acoustics".

        Returns:
            str: The query.
        """

        keys: str = ', '.join([key for key in payload.keys()])

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