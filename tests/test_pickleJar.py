import os
import sys
# add directory above testing dir (which contains file under test) to sys.path
sys.path.append(os.path.split(os.path.dirname(__file__))[0])
import pickleJar as pj

# Test sqliteToPickle on existing test sqlite3 file
def test_sqliteToPickle():

    # get file location. name is hard coded here
    testDir = os.path.dirname(__file__)
    testFileName = testDir + '\\test_files\\test-scan-0'
    testFile = testFileName + '.sqlite3'

    # attempt to pickle the file
    dataDict = pj.sqliteToPickle(testFile)

    # check that sqliteToPickle created a dict
    assert type(dataDict) == dict

    # check that every key is either 'fileName', 'parameters', or an int
    for key in dataDict.keys():
        assert type(key) == int or key == 'fileName' or key == 'parameters'

    # check the filename is correct
    assert dataDict['fileName'] == testFileName + '.pickle'

    # check that the parameters key is a dict
    assert type(dataDict['parameters']) == dict

    # check that sqliteToPickle properly handles an already existing pickle
    assert pj.sqliteToPickle(testFile) == -1

    # delete the pickle file
    os.remove(testFileName + '.pickle')

# test savePickle
def test_savePickle():

    # create a dict to pickle

    # attempt to save without specifying fileName

    # specify fileName and save

    # load the pickle and verify data is there

    # delete the pickle

    return 0

# test loadPickle
def test_loadPickle():

    # create a test dict and pickle it

    # load the pickle and verify the data is there

    # pickle a non-dict and load it, verify warning occurs

    # manually pickle a dict without 'fileName', load it and verify 'fileName' was added

    # manually pickle a dict with an incorrect fileName. load it and verify the fileName is fixed

    return 0
