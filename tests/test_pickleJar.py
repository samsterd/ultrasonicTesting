import os
import sys
import pickle
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
    badDictToPickle = {'key' : 1}

    # attempt to save without specifying fileName
    assert pj.savePickle(badDictToPickle) == -1

    # specify fileName and save
    testDir = os.path.dirname(__file__)
    testFileName = testDir + '\\test_files\\testPickle0.pickle'
    goodDictToPickle = {'key' : 1, 'fileName' : testFileName}
    assert pj.savePickle(goodDictToPickle) == 0

    # load the pickle and verify data is there
    loadedPickle = pj.loadPickle(testFileName)
    assert loadedPickle['key'] == 1

    # delete the pickle
    os.remove(testFileName)

# test loadPickle
def test_loadPickle():

    # create a test dict and pickle it
    testDir = os.path.dirname(__file__)
    testFileName0 = testDir + '\\test_files\\testPickle0.pickle'
    testDict = {'key' : 1, 'fileName' : testFileName0}
    with open(testFileName0, 'wb') as f:
        pickle.dump(testDict, f)
    f.close()

    # load the pickle, verify the data is there, and delete it
    assert pj.loadPickle(testFileName0)['key'] == 1
    assert pj.loadPickle(testFileName0)['fileName'] == testFileName0
    os.remove(testFileName0)

    # pickle a non-dict to verify loading will raise proper errors
    testFileName1 = testDir + '\\test_files\\testPickle1.pickle'
    testList = [1, 2, 3]
    with open(testFileName1, 'wb') as f:
        pickle.dump(testList, f)
    f.close()
    loadedList = pj.loadPickle(testFileName1)
    # test the list loads properly
    assert testList == loadedList
    # test that loading printed an warning message
    printedWarning = capsys.redouterr()
    assert printedWarning.out == 'loadPickle Warning: loading ' + testFileName1 + ' does not result in a dict. Data manipulation functions and scripts will likely fail.'
    # clean up the files
    os.remove(testFileName1)

    # manually pickle a dict without 'fileName', load it and verify 'fileName' was added

    # manually pickle a dict with an incorrect fileName. load it and verify the fileName is fixed

    return 0
