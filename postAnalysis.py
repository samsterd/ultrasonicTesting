import pickleJar as pj

# set of functions for executing post data collection analysis and plotting
# the goal is to create a simple master function which takes the experiment input params and links them to the
# appropriate functions in pickleJar.py
# this functionality will then need to be imported into the GUI

# first pass-
#   first: handle pickling. rename pickle option to post-collection analysis
# new options in experiment params:
#   need to generate input to applyFunctionsToData, generateScanPlots,
#   todo: add repeat pulse through time plotting. take a given data key, plot it vs time if repeat_pulse and as a scan if scan or multiscan
#   functionDictList style input to

def postAnalysis(params : dict):

    # check that saveFormat == SQL, otherwise abort
    if params['saveFormat'] != 'sqlite':
        print("postAnalysis error: saveFormat must be set to 'sqlite' in order to perform post-analysis.")
        return -1

    # check that the plotting keys are a strict subset of the function result keys

    # pickle the data
    dataDict = pj.sqliteToPickle(params['fileName'] + '.sqlite3')

    funcDictList = params['funcDictList']
    # applyFunctionToData
    # todo: add safety check on applyFunctionsToData to make sure the functions exist, error handling for bad inputs
    pj.applyFunctionsToData(dataDict, params['funcDictList'])

    # generate plots
    # separate handling based on scan vs non-scan, call appropriate function
    # with save and show flags according to params
    for funcDict in funcDictList:

        if 'plot' in funcDict.keys() and funcDict['plot']:
            if params['experiment'] == 'single scan' or params['experiment'] == 'multi scan':
                pj.plotScan(dataDict, funcDict['resKey'])

    return 0