from matplotlib import pyplot as plt
from scipy.signal import butter, sosfiltfilt
from scipy.optimize import nnls
from scipy.ndimage import uniform_filter1d
# import pywt
# import gdecomp
import numpy as np
import time
import math
import pickleJar as pj



################################################
####### Material Stack Class #####################
##############################################

# Define a class to store information about a material stack
# This will be used to represent the layers of material in a battery that we are decomposing by tomography
# Important data:
#   Each material stack starts with a data set (i.e. pulse-echo or transmission)
#       That data set gets filtered and its envelope calculated
#       Gaussian decomposition is run on the envelope and creates a list of (mu, amp) that are converted to a material model
#   Each layer has an index integer
#       For each layer, five physical properties are recorded: speed of sound (c), density (p), elastic modulus (E),
#       length (l), and acoustic impedance (Z)
#       These properties are related by Z = pc = sqrt(Ep)
#       All physical properties are calculated from the two properties calculated by the fitting: transit time (tt) and
#           relative impedance (rz)
#   An initial
class MaterialStack():

    def __init__(self):

        # add spectrum, perform filtering and calculate hilbert envelope
        pass

    # input raw pulse-echo data. Performs a high pass filter and calculates the hilbert envelope
    def processEchoData(self, echoDat, timeDat):

        self.time = timeDat
        self.rawEcho = echoDat
        sos = createButterFilter()
        self.filteredEcho = sosfiltfilt(sos, self.rawEcho)
        self.filteredEchoEnvelope = pj.hilbertEnvelope(self.filteredEcho)


    # takes the input data and runs an initial gaussian decomposition
    def gaussianDecomposition(self, timeRange, timeStep, iterations, sigma, sigmaTolerance):

        self.sigma = sigma
        self.sigmaTol = sigmaTolerance
        decomp = gausFitBinaryAmplitudeMerge(self.filteredEchoEnvelope, self.time, timeRange, timeStep, iterations, sigma, sigmaTolerance)

        # filter out results where amp is 0
        ampNonZero = np.nonzero(decomp[1])
        self.decomp = (decomp[0][ampNonZero], decomp[1][ampNonZero])

    # converts a gaussian decomposition to a model of the material stack
    def decompToModel(self):

        # gather the decomposition parameters
        muArr = self.decomp[0]
        ampArr = self.decomp[1]

        # make a naive model as a first pass
        # this model assumes no double reflections, all reflecting interfaces are symmetric,
        # and that attenuation for all layers within the battery is the same. The governing equations are then:
        # A0 = P0L0R0, A1 = P0L0L1R1,...
        # where L0 = exp(-2(water attenuation)(transit time 0)) and all Li after 0 are:
        # Li = (1-R(i-1))^2 * exp(-2 (attenuation coeff alpha) (transit time i))
        # Taking the log of this equation and treating the first loss P0L0 separately gives:
        # log Ai = log Ri + log P0L0 - 2 alpha sum(1->i, transit time i) + 2 sum (0->i-1 log (1-Ri))
        # taking the difference of adjacent Ai gives
        # log Ai - log A(i-1) = log ((Ri * (1-R(i-1))^2)/R(i-1)) - 2 alpha transit time i
        # if we estimate the first interface is water - aluminum we can approximate R0 as 0.85
        # we can then solve this as a system of linear equations:
        # unknowns are alpha and Bi, coeffiecients are [TT1 1 0 0 ...][TT2 0 1 0 ...][TT3 0 0 1 ...]...
        # and dependent variables are log A0 - log A1, logA1 - logA2,...
        # Each Bi = log ((Ri * (1-R(i-1))^2)/R(i-1))
        # solving the system gives the value of A directly and values of Bi, which can be used to calculate each Ri given
        # the value of R0
        muDiffs = np.diff(muArr) # approximation of travel times assuming no double reflections
        logAmp = np.log(ampArr)
        logAmpDiffs = np.diff(logAmp)
        # create matrix for linear optimization. Taking all travel times after first and joining it to the front of an identity matrix
        alphaCoeffs = (-1 * muDiffs).reshape((len(logAmpDiffs), 1))
        idMatrix = np.identity(len(logAmpDiffs))
        coeffMatrix = np.concatenate((alphaCoeffs, idMatrix), axis = 1)
        # using lstsq instead of nnls because logs mean the solutions could be negative
        rawFit = np.linalg.lstsq(coeffMatrix, logAmpDiffs, rcond = -1)
        fit = rawFit[0]
        res = rawFit[1]
        alpha = fit[0]
        bi = fit[1:]
        r0 = 0.5 # calculated from water and known pouch material
        ri = self.reflectionsFromR0Bi(r0, bi)
        self.naiveAlpha = alpha
        self.naiveRi = ri

        return 0

    # helper function to recover the reflection coefficients from the fitting in the naive modeling method
    @staticmethod
    def reflectionsFromR0Bi(r0, bi):

        ri = np.zeros(len(bi) + 1)
        ri[0] = r0

        # indices get a little dicey here because len(ri) = len(bi) + 1
        for i in range(len(bi)):
            rPrev = ri[i]
            rNext = (rPrev * np.exp(bi[i]))/((1-rPrev)**2)
            ri[i+1] = rNext

        return ri

    # todo: start working on inverse construction for now: given list of (TT, R, L), generate expected echo signal
    # function to output list of (time, amplitude) values from an input stack model
    # includes higher order reflections up to the input value (i.e. first order is just one reflection, second order includes
    # all possible 3-reflection signals, etc)
    # input stack model is in the form [(TT0, R0, L0), (TT1, R1, L1),...]
    # also takes an input initial power term p0. When this is set to one, all amplitudes are normalized to that initial power
    #   This can be used downstream to set the calculated signal max to the actual signal max since choice of P0 is somewhat arbitrary
    #   Once future measurements of the actual p0 are done, this can be done in a more reasonable manner
    # the output (time, amplitude) also cuts off any coordinates where the time is outside of the bounds of self.time
    # todo: higher order not implemented yet, need to come up with a better abstraction for handling reflections
    #
    def timeAmplitudeFromStack(self, stackModel, reflectionOrder=2, p0=1):

        # pull out the model parameters - transit time tti, reflections ri, transmissions (1-ri), and loss coefficients li
        tti = np.transpose(stackModel)[0]
        ri = np.transpose(stackModel)[1]
        ti = 1 - ri
        li = np.transpose(stackModel)[2]

        # calculate first order reflections
        # mu is 2 * sum of travel times for each layer up to the layer of reflection
        # :i+1 is needed to make the sum inclusive to the end bound
        muFirstOrder = [2 * np.sum(tti[:i + 1]) for i in range(len(tti))]
        # amplitudes for reflections at layer i are p0 * ri * (transmission chance thru all prev layers)**2  * (loss thru all prev layers)**2
        #  transmission and loss coefficients are squared because the wave travels through each layer up to i twice
        ampFirstOrder = [p0 * ri[i] * np.prod(np.square(ti[:i])) * np.prod(np.square(li[:i + 1])) for i in
                         range(len(ri))]

        # second order terms
        # now need to sum over three terms i,j,k
        # i is index of first reflection, j is second reflection, and k is third
        # i <= number of layers, j < i, j < k, k <= number of layers
        # abandoning list comprehensions: sacrifice speed for readability here
        muSecondOrder = []
        ampSecondOrder = []
        for i in range(len(tti)):
            for j in range(i):
                for k in range(j + 1, len(tti)):
                    muSecondOrder.append(
                        np.sum(tti[:i + 1]) + np.sum(tti[j + 1:i + 1]) + np.sum(tti[j + 1:k + 1]) + np.sum(tti[:k + 1]))
                    ampSecondOrder.append(
                        p0 * ri[i] * ri[j] * ri[k] * np.prod(ti[:i]) * np.prod(li[:i + 1]) * np.prod(ti[j:i]) * np.prod(
                            li[j:i + 1]) * np.prod(ti[j:k]) * np.prod(li[j:k + 1]) * np.prod(ti[:k]) * np.prod(
                            li[:k + 1]))

        mu = np.array(muFirstOrder + muSecondOrder)
        amp = np.array(ampFirstOrder + ampSecondOrder)

        return mu, amp

    # algorithm to generate a reasonable material stack model based on the gaussian decomposition of the data
    # inputs: values for the input power p0 and loss coefficient of the first layer (water in most setups)
    # ampTol is the minimum amplitude value in a calculated (mu, amp) pair before it is set to 0. Defaults to 1
    # timeRange is the maximum and minimum time (mu values) to include from the gaussian decomposition. This is to exclude overfitting of
    #   noise, particularly early in the signal
    # outputs a list of [(tti, ri, li),...] that most closely generate the fitted data
    # note: this currently only calculates first and second order reflections
    # the algorithm works by calculating the first two layers from the initial p0 and l0 and assuming that the first two
    #   signals are primary reflections
    # next it iterates:
    #   first it calculates the second order reflection (mu, amp) from the layers calculated so far
    #   For each calculated second order mu value, the closest mu value from the fitting is identified and their corresponding
    #   amplitudes are subtracted. If the resulting amplitude is below ampTol, that fitted (mu, amp) value is removed
    #   Once the second order reflections are dealt with, the next lowest fitted mu value is assumed to be a primary reflection
    #   This is used to calculate the (tt, r, l) values for the next layer, which is added to the model and the corresponding
    #   fitting (mu, amp) is removed from consideration
    #   The cycle of calculating second order reflections then assuming a primary reflection and adding a layer is repeated
    #   until the list of  fitted (mu, amp) is empty. The  corresponding model is returned
    # Theoretical basis:
    #   this algorithm is based on the observation that second order terms should in general have later arrival times than first order terms
    #   More specifically, if we defined first order reflections by i, the layer index where the reflection occurs and
    #   second order reflections by i,j,k, the layer indices where the first, second, and third reflections occur,
    #   and if we assert that all TT values are similar such that 0.5 * TT(i+1) < TT(i), then we can assert that
    #   the time of flight mu for all first order reflections i is less than the time of flight for all second order reflections ijk
    #   This is just a formal way to say that up to a given layer, we expect primary reflections before the secondary reflections
    # todo: in the future, ampTol default should be based on the signal noise floor
    # todo: update documentation: the current implementation assumes only reflections, that is Li = 1 for i>0
    def generateModelFromFit(self, p0, l0, ampTol = 1, timeRange = [-1, np.inf]):

        # grab the (mu, amp) values within timeRange
        # gather the decomposition parameters
        muArr = self.decomp[0]
        ampArr = self.decomp[1]
        timeRangeIndices = np.argwhere((muArr >= timeRange[0]) & (muArr <= timeRange[1])).flatten()
        muFit = muArr[timeRangeIndices]
        ampFit = ampArr[timeRangeIndices]
        if len(muFit) <= 2:
            print("generateModelFromFit error: not enough fit parameters within the given time range. Returning -1")
            return -1

        # calculate first two layers by assuming the (mu0, amp0) and (mu1, amp1) are first order reflections
        tt0 = muFit[0]/2
        r0 = ampFit[0]/p0
        tt1 = (muFit[1] - muFit[0])/2
        r1 = ampFit[1] / (p0 * ((1 - r0)**2))
        tti = [tt0, tt1]
        ri = [r0, r1]
        ti = [1-r0, 1-r1]
        muFit = muFit[2:]
        ampFit = ampFit[2:]

        # start fitting loop: while length of fit parameters > 0
        while len(muFit) > 0:

            # calculate all second order reflections from current layer model
            numberOfLayers = len(tti)
            secondOrderAmps = []
            secondOrderTimes = []
            for i in range(numberOfLayers):
                for j in range(i):
                    for k in range(j+1, numberOfLayers):
                        # these get a little ugly
                        secondOrderTimes.append(
                            np.sum(tti[:i + 1]) + np.sum(tti[j + 1:i + 1]) + np.sum(tti[j + 1:k + 1]) + np.sum(
                                tti[:k + 1]))
                        secondOrderAmps.append(
                            p0 * ri[i] * ri[j] * ri[k] * np.prod(ti[:i]) * np.prod(ti[j+1:i]) * np.prod(ti[j+1:k]) * np.prod(ti[:k]))

            # for each second order reflection, find a corresponding (mu fit, amp fit) value and subtract the amps,
            # then update the muFit and ampFit arrays
            for i in range(len(secondOrderTimes)):

                # if the second order time is outside of the time range, ignore it
                if secondOrderTimes[i] > timeRange[1]:
                    continue

                # if there are no more fit paramters to use, break out of the loop
                if len(muFit) < 1:
                    break

                nearestIndex = (np.abs(muFit - secondOrderTimes[i])).argmin()
                newAmp = ampFit[nearestIndex] - secondOrderAmps[i]
                # check if the fit amp, mu pair should be removed
                if newAmp < ampTol:
                    muFit = np.delete(muFit, nearestIndex)
                    ampFit = np.delete(ampFit, nearestIndex)
                else:
                    ampFit[nearestIndex] = newAmp

            # if there are more fitted terms, identify the next  first order term. Calculate corresponding (tt, r, l)
            if len(muFit) > 1:
                firstOrderMu = muFit[0]
                firstOrderAmp = ampFit[0]
                muFit = np.delete(muFit, 0)
                ampFit = np.delete(ampFit, 0)
                # reminder that tti,ri,ti at this point do not have the current layer being added
                # the sum is from 0 to i-1, but since layer i isn't added yet we don't need to slice from 0:-1
                tt = (firstOrderMu - 2 * np.sum(tti)) / 2
                r = firstOrderAmp / (p0 * np.prod(np.square(ti)))
                t = 1-r

                # update layer model
                tti.append(tt)
                ri.append(r)
                ti.append(t)

        self.layerModel = np.transpose([tti, ri, ti])
        return self.layerModel

    # calculates the acoustic impedance of each layer from the model given the first layer's (usually water) impedance
    # then calculates the rest of the parameters by assuming all layers but the first have the same average density
    # the total thickness of the cell is used as an input to calculate the single density value rho = sum(zi * tti) / thickness
    # speed of sound and layer thickness are then calculated by ci = zi/rho and di = zi * tti / rho
    # default values for z0 and c0 are for water at 20C in m/s and kg/(m2s) (1500 and 1500000 respectively)
    # default value for thickness is 2 mm
    def generatePhysicalParamsFromModel(self, z0 = 1500000, c0 = 1500, thickness = 2, zSwitchThreshold = 0.03):

        tti = np.transpose(self.layerModel)[0]
        ri = np.transpose(self.layerModel)[1]
        ti = np.transpose(self.layerModel)[2]

        # calculate layer impedances
        #todo: problem: this impedances to be strictly increasing. R is the absolute value of this function, need to handle
        # +/- z. There does no seem to be a way to tell whether the higher or lower impedance should be used.
        # This could be deduced if using morlets instead of gaussians by the reverse in phase
        zi = [z0]
        # for i in range(len(ri)-1):
        #     zi.append(zi[-1] * ((1 + ri[i])/(1-ri[i])))
        # algorithm for deciding which +/-R to use: when difference between Ri and Ri+1  is above zSwitchThreshold, increase
        # then Z increases. When it is below -zSwitchThreshold, Z decreases. Otherwise, increase or decrease is decided
        # semi-randomly based on whether the layer index is even or odd
        # for i in range(len(ri)-1):
        #     diff = ri[i+1] - ri[i]
        #     # sudden increase in reflection -> use Z increasing formula
        #     if diff > zSwitchThreshold:
        #         zi.append(zi[-1] * ((1 + ri[i])/(1-ri[i])))
        #     # sudden decrease in reflection -> use Z decreasing formula
        #     elif diff < -1 * zSwitchThreshold:
        #         zi.append(zi[-1] * ((1 - ri[i])/(1 + ri[i])))
        #     # otherwise increase if i is even, decrease if i is odd
        #     elif i % 2 == 0:
        #         zi.append(zi[-1] * ((1 + ri[i]) / (1 - ri[i])))
        #     else:
        #         zi.append(zi[-1] * ((1 - ri[i]) / (1 + ri[i])))

        # different algorithm: use value of ri rather than difference. When ri and r(i-1) above threshold: decrease z.
        # when just ri above threshold: increase z
        # todo: this algorithm is flawed: it will treat a gas pocket the same as a piece of metal
        for i in range(0, len(ri)-1):
            prevRi = ri[i-1] if i > 0 else 0
            if ri[i] > zSwitchThreshold and prevRi > zSwitchThreshold:
                zi.append(zi[-1] * ((1 - ri[i]) / (1 + ri[i])))
            elif ri[i] > zSwitchThreshold:
                zi.append(zi[-1] * ((1 + ri[i]) / (1 - ri[i])))
            # otherwise increase if i is even, decrease if i is odd
            elif i % 2 == 0:
                zi.append(zi[-1] * ((1 + ri[i]) / (1 - ri[i])))
            else:
                zi.append(zi[-1] * ((1 - ri[i]) / (1 + ri[i])))

        # not pasta
        # factor of 10**-9 used to convert tti from ns to s
        zitti = np.multiply(zi, (10**-9) * tti)

        # calculate density value
        # 0.001 converts thickness to m, so density is in kg/m^3
        rho = np.sum(zitti[1:]) / (0.001 * thickness)

        # calculate speed of sound and thickness
        ci = [z / rho for z in zi] # m/s
        di = [(10**6) * zt / rho for zt in zitti] # 10^6 converts to um

        # set values of ci[0] and di[0] to match inputs
        ci[0] = c0
        di[0] = 0.001 * tti[0] * c0 # 0.001 converts ns and m to s and um
        # calculate the depth within the cell
        depthi = [np.sum(di[:i+1]) - di[0] for i in range(len(di))]
        # add density to the model even though it is constant
        rhoi = [rho for z in zi]
        rhoi[0] = 1000

        # update layer model
        layerModel = [tti, ri, ti, zi, ci, di, depthi, rhoi]
        self.layerModel = np.transpose(layerModel)

        return self.layerModel

    # plot physical parameters within a cell stack
    # todo: convert self.layerModel to a dict for better referencing
    def plotStackParam(self, paramToPlot: int):

        # collect depths and parameter of interest
        depths = np.transpose(self.layerModel)[6]
        param = np.transpose(self.layerModel)[paramToPlot]
        minParam = np.min(param)
        maxParam = np.max(param)

        # ignore first (water) layer
        plt.vlines(depths[1:], minParam, maxParam, color = "black", linestyles = 'dashed')
        plt.hlines(param[1:], depths[0:-1], depths[1:])
        plt.xlabel("Cell Depth from Surface (um)")
        plt.ylabel("Acoustic Impedance (Rayls: kg/m^2)")

        plt.show()

    # plots the gaussians implied by the output of timeAmplitudeFromStack versus the actual signal to gauge fit level
    def checkModelVersusSignal(self, muArr, ampArr, normalize = True):

        # todo: add normalization to max value - need to calculate full gaussian matrix sum, then compare vs signal max and add as a multiplier to amplitudes
        if normalize:
            gausMatrix = generateGaussianMatrix(ampArr, muArr, self.time, self.sigma, self.sigmaTol)
            modelSum = np.sum(gausMatrix, axis = 0)
            modelMax = np.max(modelSum)
            signalMax = np.max(self.filteredEchoEnvelope)
            normCoeff = signalMax / modelMax
            newAmp = normCoeff * ampArr
        else:
            newAmp = ampArr

        # first show model
        print("Plotting stack model fitting...")
        plotGaussianFit(self.filteredEchoEnvelope, self.time, muArr, newAmp,self.sigma, self.sigmaTol)

        # then show decomposition fit
        print("Plotting gaussian decomposition")
        plotGaussianFit(self.filteredEchoEnvelope, self.time, self.decomp[0], self.decomp[1], self.sigma, self.sigmaTol)

    def plotDecomposition(self):
        plotGaussianFit(self.filteredEchoEnvelope, self.time, self.decomp[0], self.decomp[1], self.sigma, self.sigmaTol)

    # estimates physical properties (c, l, Z, p, E) from the derived properties (tt, rz)
    def calculatePhysicalProperties(self):

        return 0

    # optimizes the fit between two material stack classes. This may need to exist as a separate function (or static method?)
    # will probably need to make a tomography super class that also does things like create a z-stack image from calculated properties + merge and plot images
    def mergeStacks(self):

        return 0
    #
#todo:
# write a final merge function that trims out all gaus below a threshold
# update merge function to ignore pairs outside of a certain range (sigma?)
#   This should probably be used only in later merges, or it gets narrower at each iteration?
# fill out parameters in stack
# write a function that converts a list of reflectances and transit times to gaussian means and amplitudes
#   plot outputs?
# figure out how to merge material stacks (this will be the big challenge)


############################################
#### Baseline Correction ###################
##########################################3

# creater a butterworth low pass filter.
# this should eliminate the signal an leave the background
# update to take transducer freq and timespacing as args
#   this info can be pulled from dataDict['params'] as well
def createButterFilter():
    # N = order of filter. Higher number = slower calculation but steeper cutoff
    # Wn = critical frequency (gain drops by -3 dB vs passband)
    #       For 2.25 MHz transducer, estimate as 500 kHz
    # btype = lowpass (we want to take out the higher frequency signal)
    # analog = False (this is a digital signal)
    # fs = sampling rate (500,000,000 Hz for 2 ns step size)
    return butter(5, 450000, btype = 'highpass', analog = False, fs = 500000000, output = 'sos')

# helper function to generate gaussian arrays from the output of gdecomp
# note: these are y-coors only and were not generated with awareness of the x coors
# times is used to rescale the mu and sigma parameters to match the original signal
def generateFitGaussians(fitParams, times):

    amp = fitParams[0]
    rawMu = fitParams[1]
    rawSigma = fitParams[2]

    # adjust mu by shifting over by t0 + mu * time step
    ts = times[1] - times[0]
    mu = times[0]  + (rawMu * ts)
    # adjust sigma by stretching by time step
    sigma = rawSigma * ts

    # generate data array
    return amp / (np.sqrt(2 * np.pi) * sigma) * np.exp(-(times - mu) ** 2 / (2 * sigma ** 2))

def generateGaussian(a, mu, sigma, times):

    return a * np.exp((-1 * (times - mu) ** 2) / (2 * sigma ** 2))

# generates a matrix of values of gaussians at the specified times
# inputs a list of amplitudes and averages (aArr and muArr) to construct the gaussians, the times (x-coordinates)
# to evaluate the gaussians at, the deviation (sigma) of all of the gaussians, and the number of deviations away from the
# average which will be set to 0 (i.e. sigmaTolerance=3 implies the value of a gaussian 3 sigma from its average is 0)
# returns a matrix with 1 row per gaussian, containing the values of each gaussian in the list at the input times
def generateGaussianMatrix(aArr, muArr, times, sigma, sigmaTolerance = 3):

    # add a check to make sure len(aArr)==len(muArr)
    if len(aArr) != len(muArr):
        print("generateGaussianSum: aArr and muArr have different lengths. Sum failed")
        # todo: this should be turned into an error
        return -1

    outputMatrix = np.zeros((len(muArr), len(times)))

    # iterate through gaussians
    for i in range(len(muArr)):

        # create a list of times within the sigma tolerance window
        currentMu = muArr[i]
        windowMin = currentMu - (sigma * sigmaTolerance)
        windowMax = currentMu + (sigma * sigmaTolerance)
        windowIndices = np.argwhere((windowMin < times) & (times < windowMax)).flatten()
        # find window index min and max so that assignment can be done by slices (faster)
        indMin = int(windowIndices[0])
        indMax = int(windowIndices[-1])
        timeWindow = times[indMin:indMax]

        # calculate that gaussian values within the time window
        gaussianVals = generateGaussian(aArr[i], currentMu, sigma, timeWindow)

        # assign slice of output matrix as coefficients
        outputMatrix[i, indMin:indMax] += gaussianVals

    return outputMatrix


    # create array to hold gaussian components
    # gaussians = np.zeros((len(aArr), len(times)), dtype = np.float64)
    # for i in range(len(aArr)):
    #     gaussians[i] += generateGaussian(aArr[i], muArr[i], sigma, times)
    #
    # return np.sum(gaussians, axis = 0)

# generates a matrix of gaussian coefficients for the purposes of linear least squares regression
# inputs a list of mean values for gaussian decomposition [mu0, mu1, mu2, ...] each corresponding to the gaussians [g0, g1, ...]
# outputs a square array where each row is the values of a non-normalized gaussian (i.e. max = 1) corresponding to each
#    value of the gaussian at the x-value of the mu-value corresponding to the row
#    i.e. [[ g0[mu0], g1[mu0], ...],
#         [ g0[mu1], g1[mu1],...],...]
# to speed calculation, values that are sigmatTolerance * sigma outside of the mu-value of the row are set to 0, resulting in a band matrix
def generateGaussianCoefficientMatrix(muArr, times, sigma, sigmaTolerance = 3):

    # initialize output matrix as zeros
    outputMatrix = np.zeros((len(times), len(muArr)))

    # iterate through times
    for i in range(len(times)):

        # grab mu's within +/- sigma * sigmaTolerance of currentTime and their corresponding index slice.
        currentTime = times[i]
        windowMin = currentTime - (sigma * sigmaTolerance)
        windowMax = currentTime + (sigma * sigmaTolerance)
        windowIndices = np.argwhere((windowMin < muArr) & (muArr < windowMax)).flatten()

        if len(windowIndices) > 0:
            # find window index min and max so that assignment can be done by slices (faster)
            indMin = int(windowIndices[0])
            indMax = int(windowIndices[-1]) + 1
            muWindow = muArr[indMin:indMax]

            # calculate gaussian coefficients of mu's
            gaussCoefficients = gaussianCoefficients(muWindow, sigma, currentTime)

            # assign slice of output matrix as coefficients
            outputMatrix[i, indMin:indMax] += gaussCoefficients
        # if no mu value exists in the time window, it is safe to pass since the output matrix is zeros
        else:
            pass

    return outputMatrix

# generates an array of gaussian coefficients for decomposition linear regression
# given a list of gaussians g0, g1, g2,... each with constant sigma, no normalization or amplitude, and
#   mean value mu0, mu1, mu2,...  this value of each gaussian at a single input point xVal
# inputs an array of gaussian mean values muArr, a constant sigma value, and the xVal to calculate the array
# returns an array of the values of the gaussians at xVal: [g0(xVal), g1(xVal),...]
def gaussianCoefficients(muArr, sigma, xVal):

    return np.exp((-1 * (xVal - muArr) ** 2) / (2 * sigma ** 2))

# runs a linear least squares regressions to optimize the amplitudes of an input list of gaussians to best fit input signal envelope
#   the assumption is that the envelope can be decomposed into a sum of gaussians
#   E = g0 + g1 + g2 + ..., where g0 = A0 exp(-(t - mu0)**2 / 2 sigma**2)
#   Sigma is constant for all gaussians (it is defined by the pulser). We are guessing an input of averages (muArr) and
#   calculating the amplitudes that would correspond to those averages by least squares regression
# input is the envelope and time data calculated from the raw signal, an array of mu's (averages) to run the optimization over
# the value of sigma, and the sigmaTolerance, which sets how many wide we calculate the value of the gaussian before setting it to 0
#   (3 is probably ok, but 4 or 5 may be safer but result in slower calculations)
# the output is the best fits for the amplitudes
def gaussianLeastSquares(envelope, times, muArr, sigma, sigmaTolerance = 3):

    # generate the square matrix of linear coefficients based on the gaussians defined by muArr
    coefficientMatrix = generateGaussianCoefficientMatrix(muArr, times, sigma, sigmaTolerance)

    # run regression. Non-negative least squares used to prevent negative amplitudes
    regressionResult = nnls(coefficientMatrix, envelope, maxiter = 100 * len(muArr))

    return regressionResult

# returns an array of the error**2 at each point as well as the sum of the squared errors
def calculateGaussianFitResidual(envelope, times, muArr, fit, sigma, sigmaTolerance = 3):

    # generate matrix of gaussian values from fit amplitudes and defined averages
    gaussianMatrix = generateGaussianMatrix(fit, muArr, times, sigma, sigmaTolerance)

    # calculate sum of gaussians
    gaussianSum = np.sum(gaussianMatrix, axis = 0)

    # calculate square errors
    err = envelope - gaussianSum
    sqErr = np.square(err)

    return sqErr, np.sum(sqErr)

def plotGaussianFit(envelope, times, muArr, fit, sigma, sigmaTolerance = 3):

    # generate matrix of gaussian values from fit amplitudes and defined averages
    gaussianMatrix = generateGaussianMatrix(fit, muArr, times, sigma, sigmaTolerance)

    # calculate sum of gaussians
    gaussianSum = np.sum(gaussianMatrix, axis=0)

    # iterate through gaussians and plot
    for gaus in gaussianMatrix:
        plt.plot(times, gaus, color = 'black', linestyle = 'dashed')

    plt.plot(times, gaussianSum, label = 'Fit')
    plt.plot(times, envelope, label = 'Envelope')
    plt.show()

# repeatedly runs gaussianLeastSquares and merges the resulting (mu, amp) arrays by mergeFitParams()
# first runs using a muArr defined by timeRange[0] to timeRange[1] in timeStep increments
# the process of optimize - merge is repeated niter number of times
def gausFitBinaryAmplitudeMerge(envelope, times, timeRange, timeStep, niter, sigma, sigmaTolerance, plot = False):

    # generate initial muArr guesses based on the timeRange and timeStep
    muArr = np.linspace(timeRange[0], timeRange[1], math.floor(((timeRange[1] - timeRange[0])/timeStep))+1)
    fitRes = np.zeros(niter)
    fitTimes = np.zeros(niter)

    # todo: implement time range slicing
    # slice the input times based on the input time range. This saves time on optimization by not including points outside
    # of the optimization window
    # fitTimeRange = np.where((times > timeRange[0]) & (times < timeRange[1]))[0]

    # iterate
    for n in range(niter):

        # merge fit parameters if we are not on the first iteration
        if n > 0:
            print(muArr)
            print(fit)
            muArr = mergeFitParams(muArr, fit)

        # run fitting
        start = time.time()
        fit, res = gaussianLeastSquares(envelope, times, muArr, sigma, sigmaTolerance)
        stop = time.time()
        fitTimes[n] = stop - start
        fitRes[n] = res

        # plot fit
        if plot:
            plotGaussianFit(envelope, times, muArr, fit, sigma, sigmaTolerance)
            plt.clf()


    # plot fit time and residuals
    if plot:
        plt.plot(fitTimes)
        plt.show()
        plt.clf()

        plt.plot(fitRes)
        plt.show()
        plt.clf()

    return muArr, fit, res

# define iterative fitting functions for alternating amp fitting - mu expansion, as well as for single elmination optimizations-
# one overcomplete example would be - eliminate 1 gaussian, run a round of expansion/amp fitting, check if residual is lower
#       repeat for each gaussian, eliminate the version with the lowest residual

# wrapper to run a round of mu expansion optimization followed by an amplitude optimization
def gausFitMuExpansionAmplitude(envelope, times, muArr, sigma, sigmaTolerance, subDecompWidth, subDecompNumber):

    newMu = gaussianMuExpansionLeastSquares(envelope, times, muArr, sigma, sigmaTolerance, subDecompWidth, subDecompNumber)

    newAmp, res = gaussianLeastSquares(envelope, times, newMu, sigma, sigmaTolerance)

    return newMu, newAmp, res

# function to merge fitted gaussian into the next iteration of the fitting procedure
# first attempt is a naive weighted merge: new muArray generated by merging adjacent gaussians w/ new mu generated by old mu's weighted by fitted amp
def mergeFitParams(muArr, fitA):

    #todo: check lengths of inputs are equal

    # first replace 0's with very low numbers to avoid weight sums to 0 errors
    # note: we are doing this rather than removing all (mu, amp) pairs where amp = 0 because this procedure results in better fits
    ampNonZero = np.where(fitA == 0, 0.00000001, fitA)

    # handle case where there is only one term (just return)
    if len(muArr) == 1:
        print("mergeFitParams: muArray has been merged to 1 non-zero term. No further merging is possible, returning input value.")
        return muArr

    # if there are an odd number of parameters, first merge the last two by weighted averaging the mu's and summing the A's
    if len(muArr) % 2 == 1:
        finalMu = (muArr[-1] * (ampNonZero[-1]/(ampNonZero[-1] + ampNonZero[-2]))) + (muArr[-2] * (ampNonZero[-2]/(ampNonZero[-1] + ampNonZero[-2])))
        finalA = np.sum(ampNonZero[-2:])
        # cut off the final two values, add the merged values, and reshape to pair adjacent values
        mergeMuArr = np.append(muArr[:-2], finalMu).reshape((-1,2))
        mergeAArr = np.append(ampNonZero[:-2], finalA).reshape((-1,2))
    else:
        # reshape to pair adjacent values
        mergeMuArr = muArr.reshape((-1,2))
        mergeAArr = ampNonZero.reshape((-1,2))

    # merge by averaging along the paired axis and using the amplitudes as weights
    mergedMu = np.average(mergeMuArr, axis = 1, weights = mergeAArr)

    return mergedMu

# method for optimizing the mu-values (averages) given a list of previously calculated amplitudes/merged mu values
# this is an attempt to linearize a nonlinear problem by decomposing each of the gaussians in the fit within a narrow range
# and then reconstructing a new Mu value from the decomposition
# inputs the envelope and time values, the muArr from the latest iteration of gaussianLeastSquares,
# sigma and sigma tolerance. New parameters are subDecompWidth and subDecompNumber: these define how many gaussians each
# constituent gaussian will be divided into, equally spaced around each mu in muArr out to a multiple of sigma determined by
# subDecompWidth. More specifically, this will run a new amplitude optimization with each mu split into
# np.linspace(mu-(sigma*subDecompWidth), mu+(sigma*subDecompWidth), subDecompNumber))
# outputs the regression result (fits + residuals)
# NOTE: this method should only be used when the distance between each mu in muArr is << sigma * subDecompWidth
#todo: try modifying this so that sigma is reduced to sigma/subDecompNumber, then fitting amplitudes to a gaussian
def gaussianMuExpansionLeastSquares(envelope, times, muArr, sigma, sigmaTolerance, subDecompWidth, subDecompNumber):

    # create new list of mu's to decompose each gaussian around
    expandedMuArr = np.array([np.linspace(mu-(sigma*subDecompWidth), mu+(sigma*subDecompWidth), subDecompNumber) for mu in muArr]).flatten()

    # run gaussianLeastSquares with the expanded Mu array
    fit, res = gaussianLeastSquares(envelope, times, expandedMuArr, sigma, sigmaTolerance)

    # gather the fit amplitudes, reshape them into groups of subDecompNumber
    ampFits = fit.reshape((-1, subDecompNumber))

    # replace any zeros in the fits with a low number to allow easier averaging, then run weighted averaging
    ampNonZero = np.where(ampFits == 0, 0.00000001, ampFits)
    mergedMu = np.average(expandedMuArr.reshape((-1, subDecompNumber)), axis = 1, weights = ampNonZero)

    return mergedMu

# attempting in normal order - add one gaussian at a time
# start by adding a gaus w/ mu at the signal maximum and optimizing the amplitude
# calculate the residual, add another gaus at the residual maximum. Do a mu expansion, reoptimize amplitude, repeat
# track residual. keep repeating process of adding one more gaussian until residual is below target or reach max gaussians
# todo: investigate residual tracking. check if functions should be removed. figure out a better version of expansion
def gaussianDecompositionByAdditionExpansion(envelope, times, sigma, sigmaTolerance, expansionWidth, expansionNumber, targetResidual, maxGaussians, plotIntermediateFits = False):

    # fitting data tracking
    muArr = np.array([])
    ampArr = np.array([])
    resArr = np.array([])
    timingArr = np.array([])

    #calculate the width (in array indices) of 2*sigma. This is used in later processing
    filterWidth = math.floor(sigma / (times[1] - times[0])) * 2
    residualSignal = envelope

    # applying a filter to the signal helps separate spikes of large residual vs larger areas to be fit
    filteredRes = uniform_filter1d(residualSignal, filterWidth, mode = 'constant')

    # start adding gaussians
    for i in range(maxGaussians):

        # start timing
        start = time.time()

        # add a new mu value by finding the maximum value of the residual
        maxInd = np.argmax(filteredRes)
        muArr = np.append(muArr, times[maxInd])
        print(muArr)
        # muArr = np.append(muArr, times[find_peaks(residualSignal, height = heightMin, prominence = 1)[0]])

        # repeat cycles of expansion and optimization until the residual changes by <5%
        # while
        # fit mu and amplitude by first optimizing a mu-expansion, followed by an amplitude fit
        muFit, ampFit, res = gausFitMuExpansionAmplitude(envelope, times, muArr, sigma, sigmaTolerance, expansionWidth, expansionNumber)
        print(ampFit)

        # calculate the total fit signal and calculate residual
        fitSignal = np.sum(generateGaussianMatrix(ampFit, muFit, times, sigma, sigmaTolerance), axis = 0)
        residualSignal = np.square(envelope - fitSignal)

        # applying a filter to the signal helps separate spikes of large residual vs larger areas to be fit
        filteredRes = uniform_filter1d(residualSignal, filterWidth, mode='constant')

        # update data arrays
        muArr = muFit
        ampArr = ampFit
        stop = time.time()
        timingArr = np.append(timingArr, stop - start)
        resArr = np.append(resArr, res)

        # plot if requested
        if plotIntermediateFits and i > 15:
            plotGaussianFit(envelope, times, muArr, ampArr, sigma, sigmaTolerance)
            plt.plot(times, residualSignal)
            plt.plot(times, filteredRes)
            plt.show()
            plt.clf()

        # return if residual meets criteria
        if res < targetResidual:
            return muArr, ampArr, resArr

    # plot result, return best fit mu, amp, residual
    plotGaussianFit(envelope, times, muArr, ampArr, sigma, sigmaTolerance)

    plt.plot(resArr)
    plt.show()
    plt.clf()
    plt.plot(timingArr)
    plt.show()
    plt.clf()

    return muArr, ampArr, resArr

