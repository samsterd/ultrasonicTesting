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
import copy
from itertools import combinations



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

def generateMorlet(a, mu, sigma, freq, times):

    # generate a gaussian then multiply by a sine wave (phase shifted by mu)
    gauss = generateGaussian(a, mu, sigma, times)
    sine = np.sin(2 * np.pi * freq * (times - mu))

    return gauss * sine

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


#######################################################################
########## LEADING/Matching PURSUIT #######################################
#####################################################################

# an alternative approach that combines decomposition and creating the model
# calling it 'leading pursuit' because it was developed initially as a variation on the matching pursuit decomposition
# algorithm. It has since drifted from this inspiration but I need to call it something
# General approach (done on both sets of echo data simulataneously):
# 0.) calculate travel time through the cell using echo + transmission data
# 1.) calculate a sensitive first arrival time
# 2.) optimize a reference wave (transmission through water) to best fit the signal starting at that first arrival time
# 3.) This reference wave is a primary echo. Calculate the layer model paramters (travel time, amplitude, Z) from this data
# 4.) Calculate all higher order reflections that could be generated from the current set of layers in the model. Subtract
#       those from the signal
# 5.) Repeat 1-4 until sum of travel times in model equals the time calculated in step 0
# 6.) Reconcile overlaps of model generated from forward and reverse echoes. Calculate expected higher order contributions
#       to the transmission and reconcile those as well
# 7.) Calculate physical parameters of each layer from the modeling parameters
# 8.) Repeat 0-7 for every pixel in cell
# 9.) Generate a 3D image of the cell using the model at every pixel


def calculateNoiseFloor(signal, noiseIndices = (0, 50)):
    """
    Calculate the noise floor (variance) from a slice of the signal that should have a value of zero

    Args:
        signal (array) : the signal to calculate the noise floor
        noiseIndices (2-tuple) : the boundaries of the section used for calculating the noise. This section should have
            expectation value of 0

    Returns:
        float : standard deviation squared of the designated noise spectrum
    """
    noiseSlice = signal[noiseIndices[0]:noiseIndices[1]]

    return np.var(noiseSlice)

def firstArrivalAbsThreshold(signal, threshold):
    """
    Calculates the first arrival index based on the first value of the absolute value of the signal to exceed a threshold.
    Threshold can be an arbitrary value, but in practice will be calculated as a multiple of the noise floor

    Args:
        signal (array) : the signal to calculate the noise floor
        threshold (float) : the value to exceed to trigger the arrival

    Returns:
        int : the index of the first value to exceed threshold. If no value is found, a warning message is printed and
            -1 is returned
    """
    return np.argmax(abs(signal) >= threshold)

def trimByNoiseFloor(signal, threshold, noiseIndices):
    """
    Cuts off the beginning and end of an input signal based on when they exceed a proportion of the noise floor.

    Args:
        signal (array) : the signal to be trimmed
        threshold (float) : the multiple of the noise floor the signal must exceed to be included
        noiseIndices (2-tuple) : the boundaries of the section used for calculating the noise. This section should have
            expectation value of 0

    Returns:
        array : the signal with the beginning and end removed until the noise threshold is exceeded
    """
    noise = calculateNoiseFloor(signal, noiseIndices)
    thresholdValue = threshold * noise

    start = np.argmax(abs(signal) >= thresholdValue)

    # the endpoint is calculated by flipping the signal and repeating the protocol for the start
    flippedSignal = abs(np.flip(signal))
    stop = len(signal) -  np.argmax(flippedSignal >= thresholdValue) # subtract from len to 'unflip' the index

    return signal[start:stop]

def trimByValue(signal, thresholdValue):
    """
    Cuts off the beginning and end of an input signal based on when their absolute value exceeds a threshold value.

    Args:
        signal (array) : the signal to be trimmed
        threshold (float) : the cutoff value at the beginning and end of the signal

    Returns:
        array : the signal with the beginning and end removed until the threshold value is exceeded
    """
    start = np.argmax(abs(signal) >= thresholdValue)

    # the endpoint is calculated by flipping the signal and repeating the protocol for the start
    flippedSignal = abs(np.flip(signal))
    stop = len(signal) - np.argmax(flippedSignal >= thresholdValue)  # subtract from len to 'unflip' the index

    return signal[start:stop]

def correlationFit(signal, ref):
    """
    Calculates the best fit amplitude and mean squared error of the reference wave at each point on the signal using
    the cross-correlation method

    Args:
        signal (array) : the signal to calculate the noise floor
        ref (array) : the reference wave to cross-correlate with the signal

    Returns:
        array, array : an array of the best fit amplitudes and mean squared errors for the reference at every point on
                        the signal. Output length is len(signal) + len(ref) - 1
    """
    corr = np.correlate(signal, ref, mode = 'full')
    refSqSum = np.sum(np.power(ref, 2))
    sigSqSum = np.sum(np.power(signal, 2))

    fitArr = corr / refSqSum
    mseArr = (sigSqSum - (np.power(corr, 2) / refSqSum)) / len(corr)

    return fitArr, mseArr

def weightedCorrelationFit(signal, ref, weights):
    """
    Calculates the best fit amplitude and mean squared error of the reference wave at each point on the signal using
    the cross-correlation method with a secondary weighting array applied at every point

    Args:
        signal (array) : the signal to calculate the noise floor
        ref (array) : the reference wave to cross-correlate with the signal
        weights (array) : the weighting of the reference array. len(weights) == len(ref)

    Returns:
        array, array : an array of the weighted best fit amplitudes and mean squared errors for the reference at every point on
                        the signal. Output length is len(signal) + len(ref) - 1
    """
    # weights are squared b/c we are optimizing the squared differences
    w2 = np.power(weights, 2)

    # prepare some other arrays that will be used in the calculation
    r2 = np.power(ref, 2)
    s2 = np.power(signal, 2)
    w2r = w2 * ref
    w2r2Sum = np.sum(w2 * r2)

    # need to calculate two cross-correlations: W2Ref * Sig and W2 * Sig
    # in the future, this could probably be sped up using FFTs
    w2Corr = np.correlate(s2, w2, mode = 'full')
    w2rCorr = np.correlate(signal, w2r, mode = 'full')

    amps = w2rCorr / w2r2Sum
    mse = (w2Corr - (np.power(w2rCorr, 2) / w2r2Sum)) / len(w2Corr)

    return amps, mse

def correlationArrival(signal, ref, threshold = 0.05):
    """
    Calculates the first arrival index by cross-correlating the reference wave and the signal and identifying the first value
    in the absolute value of the correlation that exceeds a given fraction of the maximum

    Args:
        signal (array) : the signal to calculate the noise floor
        ref (array) : the reference wave to cross-correlate with the signal
        threshold (float) : the fraction of the correlation maximum that is counted as arrival. 0 < threshold <= 1

    Returns:
        int : the index within the signal of the first arrival
    """
    absCorr = abs(np.correlate(signal, ref, mode = 'full'))
    corrThreshold = threshold * np.max(absCorr)
    corrArrivalIndex = np.argmax(absCorr >= corrThreshold)

    # since the convolution mode is full, the maximum index within the corrolution is shifted the length of the reference
    # with respect to the signal
    return corrArrivalIndex - len(ref)

def derivArrival(signal, threshold = 0.1):
    """
    Calculate arrival index by a threshold of the maximum derivative

    Args:
        signal (array) : signal to calculate the arrival time
        threshold (float) : value from 0 to 1 determining the fraction of the maximum derivative that counts as arrival

    Returns:
        int : the index of the first arrival
    """
    absDeriv = abs(pj.savgolFilter(signal, [0,1], derivOrder = 1))
    derivMax = np.max(absDeriv)
    thresholdValue = threshold * derivMax
    return np.nonzero(absDeriv >= thresholdValue)[0][0]

def trimByDeriv(signal, threshold = 0.1):
    """
    Trims the front and back of an array based on the derivative

    Args:
        signal:
        threshold:

    Returns:

    """
    deriv = abs(pj.savgolFilter(signal, [0,1], derivOrder = 1))
    thresholdValue = threshold * np.max(deriv)
    start = np.argmax(deriv >= thresholdValue)
    stop = len(signal) - np.argmax(np.flip(deriv) >= thresholdValue)

    return signal[start:stop]

def trimByZeros(signal, firstBreakIndex, numberOfZeros):
    """
    Trims the front and back of a signal using the number of zero crossings around a starting point identified
    by another first break algorithm. From the starting point, the algorithm backtracks to the previous zero crossing
    and then takes the data through a number of zeros specified by numberOfZeros. The key advantage of this approach
    is that the first and last elements of the trimmed signal should be close to zero.

    Args:
        signal (array): signal to be trimmed
        firstBreakIndex (int): index to start collecting signal. Should be the approximate first break of the signal
                            0 < firstBreakIndex < len(signal)
        numberOfZeros (int): number of zero-crossings to include in the trimmed signal. Must be greater than 0. If
                             numberOfZeros exceeds the number of zero crossings in the signal after firstBreakIndex,
                             the back of the signal will not be trimmed

    Returns:
        array : the signal trimmed to start and end near zeros.
    """
    # find the zero crossings
    signalX = range(len(signal))
    zeroInds = pj.zeroCrossings(signal, signalX, linearInterp = False)

    # handle case with no zero crossings
    if zeroInds[0] == -1:
        print("trimByZeros: input signal does not have any zero crossings. Returning untrimmed signal.")
        return signal

    # find zero indices after the startingIndex. Note that zeroIndicesAfterStart is an array of indices of indices -
    # zeroInds[zeroIndicesAfterStart[0]] is index of the first signal zero crossing after startingIndex
    zeroIndicesAfterStart = np.nonzero(zeroInds > firstBreakIndex)[0]
    startZeroInd = zeroIndicesAfterStart[0] - 1

    # find the trim starting index
    startZeroInd = zeroIndicesAfterStart[0] - 1
    if startZeroInd < 0:
        # handle case where there is no zero before startingIndex
        print("trimByZeros: there are no zero crossings before the firstBreakIndex. The front of the signal will not be trimmed.")
        start = 0
    else:
        start = zeroInds[startZeroInd]

    # find the trim stopping index
    stopZeroInd = numberOfZeros - 1 # minus 1 since we already include a zero in the start
    if stopZeroInd > len(zeroIndicesAfterStart) - 1:
        # handle case where there are fewer zeros than numberOfZeros after the first break index
        stop = len(signal)
    else:
        stop = zeroInds[zeroIndicesAfterStart[stopZeroInd]]

    return signal[start : stop]

# this function is using the rightmost index for historical reasons (using output of correlation function), but it would
# be much more intuitive to use the leftmost index
def padAndInterpolateReferenceWave(ref, signalLen, shift):
    """
    Generates an array of the reference wave zero padded such that it is the same length as the signal and shifted by
    an input value. If the shift is not an integer, the reference signal will be interpolated

    Args:
        ref (array) : the reference signal for decomposition (i.e. the transducer wave form)
        signalLen (int) : the length of the signal to be decomposed. signalLen >= len(ref)
        shift (int or float) : the rightmost index on the signal which the ref will be shifted to
            If shift is a float, linear interpolation will be performed since only integer indices are possible

    Returns:
        array : the zero-padded and interpolated reference. len(return) = len(signal)
    """
    flooredShift = max(math.floor(shift), 0) # there are very rare edge cases where the shift is a small negative number
    refLen = len(ref)

    # determine if linear interpolation should be done
    # output of this step is refInterp even if no interpolation is done
    if type(shift) == float:

        # determine the amount to interpolate
        # since the padding handles the integer shifts, interpolation is used to calculate the values between the integer
        # indices. In order to convert between 'interpolation space' and 'signal space', we need to interpolate the values
        # that are (1 - shift decimal)
        # A more concrete example: If the shift is 100.4, we need to imagine the reference placed over the signal with its
        # right side on x = 100.4 and left side on x = 100.4 - len(ref). Within the space of the ref, the points we interpolate
        #   are 0.6, 1.6, ...
        # the result will be padded with a zero on the left side as appropriate to maintain the same length as ref
        shiftDecimal = shift - flooredShift # get the decimal part of the shift
        interpSpace = np.linspace(0-shiftDecimal, refLen - shiftDecimal - 1, refLen)
        xSpace = np.linspace(0, refLen - 1, refLen)
        refInterp = np.interp(interpSpace, xSpace, ref, left = 0)

    # no interpolation needed, leave ref as it
    else:
        refInterp = ref

    # gather safe bounds to cut off ref if shift is outside of signalLen
    # output of this step is refSlice even if no cut off is done
    if flooredShift > signalLen:
        # shift is greater than the signal length. Need to cut off the last flooredShift - signalLen digits of refInterp
        refSlice = refInterp[:signalLen - flooredShift]
    elif flooredShift < refLen:
        # shift is smaller than the length of the ref wave. Need to cut off the first refLen - flooredShift digits
        refSlice = refInterp[refLen - flooredShift:]
    else:
        refSlice = refInterp

    # now finally zero pad
    leftPadding = max(flooredShift - refLen, 0)
    rightPadding = max(signalLen - flooredShift, 0)

    return np.pad(refSlice, (leftPadding, rightPadding), 'constant', constant_values = (0,0))

def generateSignalFromShiftAmp(ref, signalLen, shiftList, ampList):
    """
    Generates a signal from the sum of a set of shifted reference waves with given amplitudes.

    Args:
        ref (array) : the reference signal for decomposition (i.e. the transducer wave form)
        signalLen (int) : the length of the signal to be decomposed. signalLen >= len(ref)
        shiftList (list of ints or floats) : a list of the rightmost indices on the signal which the ref will be shifted
            If shift is a float, linear interpolation will be performed since only integer indices are possible
            Index matched to ampList
        ampList (list of floats) : a list of the amplitudes of each reference wave. Index matched to shiftList

    Returns:
        array : returns an array of signalLen with the sum of the specified shifted and stretched reference waves
    """
    decompMatrix = np.zeros((len(shiftList), signalLen))

    for i in range(len(shiftList)):

        decompMatrix[i] = ampList[i] * padAndInterpolateReferenceWave(ref, signalLen, shiftList[i])

    decompSum = np.sum(decompMatrix, axis = 0)

    return decompSum

def generateSignalFromModel(ref, refTime, model, mode = 'echo', direction = 'forward', startingAmplitude = 1,
                           ampCutoff = 0.01, timeCutoff = 100, transducerZ = -1):
    """
    Generates simulated ultrasound signal from a specified slab model (transit time, attenuation, and impedance for each layer)

    Args:
        ref (array): the reference wave to use as the basis set for generating the signal
        refTime (array): the x-axis of the ref (i.e. time, in ns)
        model (array of 3-tuples of positive floats) : the layer model used to generate the signal
            The tuples specify the impedance, loss coefficient, and travel time of the layer
        mode (str) : 'echo', 'transmission', 'both' - the acoustic signal type to generate
        direction (str) : 'forward', 'reverse', 'both' - the direction of the ultrasound through the model
        startingAmplitude (float) : value of the maximum of ref
        ampCutoff (positive float) : threshold fraction of the starting amplitude below which a wave stops being tracked
        timeCutoff (float) : maximum transit time for a wave before it stops being tracked
        transducerZ (float): acoustic impedance of the transducers. Setting to -1 means it will match the impedance of the
            ends of the model (i.e. perfect transmission through the transducer)

    Returns:
        dict of arrays : keys are the 'mode_direction'  values are the ultrasound signal of the model constructed from
            the ref in the specified mode and direction
    """
    # generate the reflection and transmission coefficients from the model
    trCoeffs = calculateReflectionAndTransmissionCoeffs(model, transducerZ)

    # run simulations for each combination of mode and direction
    res = {}
    if direction == 'forward' or direction == 'both':

        # forward starts at layer 0 in the fwd (1) direction, starting amp, and travel time of 0
        startWave = [0, 1, startingAmplitude, 0]

        if mode == 'echo' or mode == 'both':
            measureInterface = 0
            res['echo_forward'] = propagateWavesThroughLayers(startWave, model, trCoeffs, measureInterface, ampCutoff, timeCutoff)
        if mode == 'transmission' or mode == 'both':
            measureInterface = -1
            res['transmission_forward'] = propagateWavesThroughLayers(startWave, model, trCoeffs, measureInterface, ampCutoff, timeCutoff)

    if direction == 'reverse' or direction == 'both':
        # reverse starts at last layer in the rev (-1) direction, starting amp, and travel time of 0
        startWave = [len(model) - 1, -1, startingAmplitude, 0]

        if mode == 'echo' or mode == 'both':
            measureInterface = -1
            res['echo_forward'] = propagateWavesThroughLayers(startWave, model, trCoeffs, measureInterface, ampCutoff,
                                                              timeCutoff)
        if mode == 'transmission' or mode == 'both':
            measureInterface = 0
            res['transmission_forward'] = propagateWavesThroughLayers(startWave, model, trCoeffs, measureInterface,
                                                                      ampCutoff, timeCutoff)

    # generate the signals from results

    return res

def calculateReflectionAndTransmissionCoeffs(model,  transducerZ = -1):
    """
    Calculates the reflection and transmission coefficients for each interface in a model based on the acoustic impedances

    Args:
        model (array of 3-tuples of positive floats) : the layer model used to generate the signal
        transducerZ (float): acoustic impedance of the transducers. Setting to -1 means it will match the impedance of the
            ends of the model (i.e. perfect transmission through the transducer)

    Returns:
        array of len 4 arrays: transmission and reflection coefficients at each interface in forward and reverse directions.
            len is len(model) + 1 because of the added interfaces with the transducers
            Format is (fwd trans, fwd ref, rev trans, rev ref)
    """
    # gather a list of the impedances with the transducer values at the ends
    modelZ = [layer[0] for layer in model]
    zList = modelZ.insert(0, transducerZ).append(transducerZ) # this is a silly way to do this

    # initialize the coefficient matrix
    coeffMatrix = np.zeros((len(zList) - 1), 4)

    # iterate through zList and populate coeffMatrix
    for i in range(len(zList) - 2):

        z1 = zList[i]
        z2 = zList[i+1]
        coeffMatrix[i, 0] = calcR(z1, z2)
        coeffMatrix[i, 1] = calcT(z1, z2)
        coeffMatrix[i, 2] = calcR(z2, z1)
        coeffMatrix[i, 3] = calcT(z2, z1)

    return coeffMatrix

def calcR(z1, z2):
    return (z1 - z2) / (z1 + z2)

def calcT(z1, z2):
    return (2 * z1) / (z1 + z2)

def propagateWaveThroughLayer(inputWave, layerTuple, tr):
    """
    Updates a wave parameters (layer, direction, amplitude, travel time) after travelling through the specified layer
    and interacting with the interface of the next layer

    Args:
        inputWave (len 4 list) : specifies the current state of the wave
            layer number (int), direction (+1 or -1), amplitude (float), total travel time (float)
        layerTuple (3-tuple): tuple of the current layer properties
        tr (float, float) : the transmission and reflection coefficients corresponding to the direction of travel

    Returns:
        outputWave, outputWave : two new wave len 4 lists corresponding to the transmitted and reflected waves
    """
    return 0

def propagateWavesThroughLayers(startWave, model, trCoeffs, measureInterface, ampCutoff, timeCutoff):
    """
    Given a starting wave and a fully specified model and experiment, generates all of the (time, amplitude) waves that
    are measured within the time and amplitude cutoffs

    Args:
        startWave: specifies the first pulse of the experiment
            layer number (int), direction (+1 or -1), amplitude (float), total travel time (float)
        model (array of 3-tuples): the layer model used to generate the signal
        trCoeffs (array of 2-tuples): array of transmission and reflection coefficients
        measureInterface (int): specifies which interface is the measuring transducer. 0 for first, -1 for last
        ampCutoff (float): cutoff of amplitude below which the wave is no longer tracked
        timeCutoff (float): cutoff of time above which the wave is no longer tracked

    Returns:
        array, array : the travel time and amplitude of each wave that is measured
    """


    return 0

def plotFits(decomp, signal, shifts, ampsList, suppressPlot = False):
    """
    Plots the results of a fit given the decomposition reference, the signal to fit, and the shifts and amplitudes of the
    best fit

    TODO: for now this is just a modified copy of fitDecompAmplitudes with the fitting step removed
    a better version will include a helper function for calculating bounds / padding arrays that will be used for both functions
    """
    # initialize matrix holding all of the decompositions
    signalLen = len(signal)
    decompMatrix = np.zeros((len(shifts), signalLen))

    # iterate through shifts and populate the coeff matrix
    for i in range(len(shifts)):

        decompMatrix[i] = padAndInterpolateReferenceWave(decomp, signalLen, shifts[i])

    # calculate normalized residual
    fitArray = decompMatrix * np.array([ampsList]).T # multiply each row (shifted decomp) by its corresponding fitted amplitude
    fitSum = np.sum(fitArray, axis = 0) # vertical sum of decomps gives the total fit
    # res = np.sum(abs(signalSlice - fitSum)) / fitLen # subtract fit from signal and normalize by the signal length

    if not(suppressPlot):
        for i in range(len(ampsList)):
            plt.plot(fitArray[i], color = 'black', linestyle = 'dashed')
        plt.plot(fitSum, label = "Fit")
        plt.plot(signal, label = "Signal")
        plt.legend()
        plt.show()

    return fitSum

def linearFitRefWaveNN(ref, signal, shifts, polarities):
    """
    Performs a non-negative linear least squares regression to optimize the amplitudes of a series of reference waves and time shifts
    in order to decompose the signal

    Args:
        ref (array) : reference wave for decomposition
        signal (array) : the signal to be decomposed
        shifts (list) : the calculated time-shift of each fitted wave
        polarities (list) : the polarity (1 or -1) of each fitted wave. Must be index matched to shifts
    Returns:
        list, float : a list of optimized amplitudes and the best fit residual
        If the regression step fails to converge, np.inf is returned for all values
    """

    # calculate bounds of the signal from the shifts
    maxShift = max(shifts)
    minShift = min(shifts)
    refLen = len(ref)
    signalLen = len(signal)

    # initialize a fitting matrix
    fittingCoeffMatrix = np.zeros((len(shifts), signalLen))

    # populate the matrix with interpolated + zero padded reference waves
    for i in range(len(shifts)):

        fittingCoeffMatrix[i,:] = padAndInterpolateReferenceWave(polarities[i] * ref, signalLen, shifts[i])

    # perform the fitting
    #todo: put this in a try/except and handle max iterations separately
    #todo: formalize the atol value based on the data noise floor?
    try:
        fit = nnls(fittingCoeffMatrix.T, signal, maxiter = 100 * len(shifts), atol = 0.001)
    except RuntimeError:
        fit = -1
        print("linearFitRefWave Warning: optimization did not converge, returning np.inf.")
        return [np.inf], [np.inf], np.inf

    # calculate residual manually
    fitArray = fittingCoeffMatrix * fit[0].reshape((len(fit[0]),1)) # multiply the shifted/padded refs by their associated amplitude
    fitSum = np.sum(fitArray, axis = 0) # vertical sum to calculate the total signal
    res = np.sum(abs(signal - fitSum))

    return fit[0], fit[1], res

def weightedLinearFitRefWave(ref, signal, shift, weights = -1, rcond = -1):
    """
    Performs a single linear least squares regression to optimize the amplitude of a reference wave at a point on the
    signal with (optional) weights. Note that this method does not handle interpolation at this time, so shifts must be
    integer values.

    Args:
        ref (array) : reference wave for decomposition
        signal (array) : the signal to be decomposed
        shift (int) : the LEFT-most index of the ref when overlaid on the signal. Must be between -len(ref) and len(signal) - 1
        weights (array) : weights for the reference, if performing a weighted fit.
            Default value of -1 performs an unweighted fit
            If using an array, it must be the same length as ref
        rcond (float) : rounding condition. See documentation for np.linalg.lstsq. Default value uses machine precision
    Returns:
        float, float, float, float, float: optimized amplitude, weighted and unweighted local residual, and the global unweighted mean squared error
    """

    # calculate bounds of the signal from the shifts
    refLen = len(ref)
    signalLen = len(signal)

    # calculate slice indices for the signal and ref to handle cases where shift includes out-of-bounds values
    safeSignalMax = min(shift + refLen - 1, signalLen - 1)
    safeSignalMin = max(shift, 0)
    refMax = min(refLen - 1, signalLen - shift - 1)
    refMin = max(0, -1 * shift)

    signalSliceLen = safeSignalMax - safeSignalMin + 1
    refSliceLen = refMax - refMin + 1
    if signalSliceLen != refSliceLen:
        raise ValueError("weightedLinearFitRefWave: ref and signal slices do not have equal lengths. This is a bug.")

    # create weighting matrices
    if type(weights) == int and weights == -1:
        sqrtWeight = np.ones(refSliceLen)
    elif type(weights) != np.ndarray:
        raise TypeError("weightedLinearFitRefWave: weights must either be an ndarray or -1.")
    elif len(weights) == refLen:
        # sqrt is used so that the weighting is applied linearly with the residuals, which are calculated by squaring
        # the difference between predicted and actual values. Sqrt(weight) -> weight * residual in fitting
        sqrtWeight = np.sqrt(weights)
    else:
        raise ValueError("weightedLinearFitRefWave: length of weights array must equal length of reference array.")

    # prepare inputs for fitting. lstsq requires two columns, so populate with a dummy column of zeros
    fittingCoeffMatrix = np.zeros((2, signalSliceLen))
    refSlice = copy.copy(ref[refMin:refMax + 1])
    fittingCoeffMatrix[0,:] = refSlice * sqrtWeight
    signalSlice = copy.copy(signal[safeSignalMin : safeSignalMax + 1])
    weightedSignal = signalSlice * sqrtWeight

    # perform the fitting
    try:
        fit = np.linalg.lstsq(fittingCoeffMatrix.T, weightedSignal, rcond = rcond)
    except RuntimeError:
        fit = -1
        print("linearFitRefWave Warning: optimization did not converge, returning np.inf.")
        return [np.inf], [np.inf], np.inf

    # calculate residual manually
    fitArray = refSlice * fit[0][0] # multiply the shifted/padded refs by their associated amplitude
    res = np.sum(np.power(signalSlice - fitArray, 2))
    # calculate weighted residuals
    wfitSum = sqrtWeight * fitArray
    wres = np.sum(np.power(weightedSignal - wfitSum, 2))
    # calculate global residual
    paddedFit = fit[0][0] * padAndInterpolateReferenceWave(ref, signalLen, shift)
    gres = np.sum(np.power(signal - paddedFit, 2))
    mse = gres / signalLen

    return fit[0][0], wres, res, gres, mse

def constantCutoffWeight(refLen, frontLen, frontWeight, backWeight = 1):
    """
    Generate a weighting function that increases the weighting on the first n elements of an array

    Args:
        refLen (int): length of the weighting array
        frontLen (int): length of the array to have increased weight
        frontWeight (float): weighting of front elements of array
        backWeight (float) : weighting of the elements after frontLen

    Returns:
        array : an array of length refLen where the first frontLen elements have value frontWeight, the rest have value backWeight
    """
    weights = backWeight * np.ones(refLen)
    weights[:frontLen] = frontWeight
    return weights

def expDecayWeight(refLen, decayLen, leadingWeight = 1):
    """
    Generates a weighting function that exponentially decays from the start.

    Args:
        refLen (int): length of the weighting array
        decayLen (float): characteristic length scale of the exponential decay exp(-x/decayLen)
        leadingWeight (float) : value of weights[0]

    Returns:
        array : an array of length refLen whose values exponentially decay starting at leadingWeight
    """
    weightX = np.linspace(0, refLen, refLen)
    return leadingWeight * np.exp(-1 * weightX / decayLen)

#todo: modify to allow arbitrary weighting input
def backtrackFitting(ref, signal, startingShift, weights = -1, backtrackLen = 10, rcond = -1):
    """
    Attempts to fit the leading edge of a signal using a reference wave with an exponential dropoff. Attempts the fit
    at each increment up to weightingDropoff to the left of startingShift and returns the shift and amplitude of best fit.
    The motivation for this method is to improve the matching of the reference to the leading edge of the signal when the
    ToF algorithm has errors and the start of the signal may have noise.

    Args:
        ref (array) : reference wave for decomposition
        signal (array) : the signal to be decomposed
        startingShift (int) : the LEFT-most index of the ref when overlaid on the signal. Must be between -len(ref) and len(signal) - 1.
        weights (array) : an array of length = len(ref) specifying the weighting in the least squares fitting. If set to -1, no weighting is performed
        backtrackLen (int): the number of indices that will to tried to the left of startingShift
        rcond (float) : rounding condition. See documentation for np.linalg.lstsq. Default value uses machine precision
    Returns:
        float, float, int : the best fit amplitude, unweighted residual, and optimal shift value
    """

    # generate list of shifts to attempt fitting
    shiftList = range(startingShift, startingShift - backtrackLen, -1)

    if type(weights) == int and weights == -1:
        weightArray = np.ones(len(ref))
    elif type(weights) != np.ndarray:
        raise TypeError("backtrackFitting: weights parameters must either be a numpy array or -1.")
    elif len(weights) != len(ref):
        raise ValueError("backtrackFitting: weights array must be the same length as ref array.")
    else:
        weightArray = weights

    # initialize trackers
    amps = []
    res = []

    # iterate through shifts
    for i in range(len(shiftList)):

        # pad the reference wave with zeros to fit over the correct range
        paddedRef = np.pad(ref, (0, i), 'constant', constant_values = (0,0))
        # pad the weight array with a repeat of the final value
        paddedWeight = np.pad(weightArray, (0, i), 'constant', constant_values = (0, weightArray[-1]))

        # fit and save results to trackers
        fit = weightedLinearFitRefWave(paddedRef, signal, shiftList[i], paddedWeight)
        # print(shiftList[i])
        # if i%10 == 0:
        #     plotFits(paddedRef, signal, [shiftList[i] + len(paddedRef)], [fit[0]])
        # fit[0][0], wres, res, gres, mse
        amps.append(fit[0])
        res.append(fit[1] / len(paddedRef))  # res needs to be normalized by the length to avoid biasing against further shifts
        # res.append(fit[1])

    # find index of minimal residual, return values
    minInd = np.argmin(np.array(res))

    return amps[minInd], res[minInd], shiftList[minInd]

# todo: add a weights option
# todo: determine rcond based on noise or add an rcond parameter (default to -1)
def linearFitRefWave(ref, signal, shifts):
    """
    Performs a linear least squares regression to optimize the amplitudes of a series of reference waves and time shifts
    in order to decompose the signal

    Args:
        ref (array) : reference wave for decomposition
        signal (array) : the signal to be decomposed
        shifts (list) : the calculated time-shift of each fitted wave
    Returns:
        list, float : a list of optimized amplitudes and the best fit residual
        If the regression step fails to converge, np.inf is returned for all values
    """

    # calculate bounds of the signal from the shifts
    maxShift = max(shifts)
    minShift = min(shifts)
    refLen = len(ref)
    signalLen = len(signal)

    # create weighted matrices
    # todo: check if the signal needs to be weighted. If so, then this must be performed in a window (rather than global!)

    # initialize a fitting matrix, handling case where len(shifts) == 1 so we must populate with a dummy column of zeros
    fittingCoeffMatrix = np.zeros((max(len(shifts), 2), signalLen))

    # populate the matrix with interpolated + zero padded reference waves
    for i in range(len(shifts)):

        fittingCoeffMatrix[i,:] = padAndInterpolateReferenceWave(ref, signalLen, shifts[i])

    # perform the fitting
    #todo: put this in a try/except and handle max iterations separately
    #todo: formalize the atol value based on the data noise floor?
    try:
        fit = np.linalg.lstsq(fittingCoeffMatrix.T, signal, rcond = 0.0001 * np.max(signal))
    except RuntimeError:
        fit = -1
        print("linearFitRefWave Warning: optimization did not converge, returning np.inf.")
        return [np.inf], [np.inf], np.inf

    # calculate residual manually
    fitArray = fittingCoeffMatrix * fit[0].reshape((len(fit[0]),1)) # multiply the shifted/padded refs by their associated amplitude
    fitSum = np.sum(fitArray, axis = 0) # vertical sum to calculate the total signal
    res = np.sum(np.power(signal - fitSum, 2))

    return fit[0], fit[1], res

def parabolaInterpolate(xPts, yPts):
    """
    Given an array of x and y points, calculates the parabola that fits those points and returns the x-value of the extremum
    (minimum for a positive parabola, maximum for a negative parabola). Accepts more or less than three points, but the
    answer is only uniquely defined for three input points.

    Args:
        xPts (array) : the x-values to interpolate. All x-values must be unique (i.e. no repeat values)
        yPts (array) : the y-values to interpolate. len(xPts) == len(yPts)

    Returns:
        float : the x-value of the extremum
    """
    lenPts = len(xPts)
    if lenPts != len(yPts):
        raise ValueError("parabolaInterpolate: length of input arrays must be equal.")

    # check that there are no repeats in the xPts
    if lenPts != len(np.unique(xPts)):
        raise ValueError("parabolaInterpolate: all x-values must be unique.")

    # handle different length cases
    if lenPts == 1:
        # trivial case - cannot interpolate, just return input value and print a warning
        return xPts[0]

    elif lenPts == 2:
        # two points given. This is underdefined, so the midpoint is returned
        return (xPts[1] - xPts[0]) / 2

    else:
        # for 3 or more points we will use a similar linear algebra approach. The matrix construction is the same in both
        # cases, but for 3 points we can exactly solve it while >3 points requires linear regression

        # first generate a matrix of [[x0**2, x0, 1], [x1**2, x1, 1],...]
        fittingMatrix = np.zeros((lenPts, 3))
        for i in range(lenPts):
            fittingMatrix[i, :] = np.array([xPts[i] ** 2, xPts[i], 1])

        # next calculate the coefficients of the parabola y = Ax**2 + Bx + C that fits the data
        if lenPts == 3:
            # for three points we solve exactly
            coeffs = np.linalg.solve(fittingMatrix, yPts)
        else:
            coeffs = np.linalg.lstsq(fittingMatrix, yPts)[0]

        # finally solve for the zero of the derivative, handling the case where A = 0 (the input was a line)
        if coeffs[0] == 0:
            print("parabolaInterpolate Warning: interpolating resulted in a divide by 0. This implies the input points"
                  "are on a line and cannot be fit to a parabola. Returning the averaged x-points instead.")
            return np.mean(xPts)
        else:
            return -0.5 * coeffs[1] / coeffs[0]

# def leadingPursuitDecomposition(ref, signal, )

def matchingPursuitDecomposition(ref, signal, normResThreshold=1, maxIterations=100, shiftMethod='standard',
                                 plotSteps=False, plotResult=True, **kwargs):
    """
    Decompose the signal into a series of shifted and stretched reference waves using a mathing pursuit type algorithm.

    Args:
        ref (array) : the reference wave to decompose the signal into
        signal (array) : the data to decompose
        normResThreshold (float) : the target residual / len(signal). Decomposition  functions are added until either the
            normalized residual is less than the threshold or maxIterations is reached
        maxIterations (int) : the maximum number of decomposition iterations to perform if the residual threshold is not reached
            If normResThreshold is set to zero or below, the decomposition will iterate until maxIterations
        shiftMethod (str) : the method used to find the x-shift of each decomposition
            'standard': the index of the maximum of the correlation function is used
            'interp' : the maximum is interpolated by fitting a parabola to the neighborhood of the correlation maximum
            'pairwise' : interpolation is performed, then fitting is performed on all pairwise decompositions near the
                maximum. The single decomposition or pair with the lowest residual is used at that decomposition step
                NOTE: this may result in a greater number of decompositions than specified by maxIterations
        plotSteps (bool) : plots each iteration of the fitting. Only recommended for debugging purposes
        plotResult (bool) : plots the input signal, the total decomposition, and each individual decomposition wave
        kwargs: additional keyword arguments used to specify parameters for a specific shift method
            'pairwise': width (float) - defines the size of the search neighborhood for the pairwise fits
                        numberOfSteps (int) - defines the step size of the neighborhood search
                        Search is performed in all unique pairs of values within linspace(-width, width, numberOfSteps)
                        The time of this step scales as numberOfSteps**2
    Returns:
        list, list, list: results of the fitting iterations
            list0 is the shift values
            list1 is the best fit amplitudes at each shift
            list2 is the residual after each iteration
        NOTE: len(list0) == len(list1) but list2 may be a different length if 'pairwise' fitting is used
    """
    # error check that the correct kwargs are present for 'pairwise' method
    if shiftMethod == 'pairwise':
        if 'width' not in kwargs.keys() or 'numberOfSteps' not in kwargs.keys():
            raise ValueError("matchingPursuitDecomposition: missing keyword arguments \"width\" and \"numberOfSteps\"."
                             "These are required when shiftMethod is set to 'pairwise'. Either provide the required"
                             "kwargs or use shiftMethod = 'standard' or 'interp'. ")

    currentSignal = copy.copy(signal)
    refLen = len(ref)
    signalLen = len(signal)

    # initialize results lists
    shifts = []
    pols = []
    res = []
    amps = []

    # flow control to enable either set iterations or a while loop
    iter = 0
    continueIter = True

    while continueIter:

        # first find the max or min of the cross correlation function
        corr = np.correlate(currentSignal, ref, mode='full')
        corrMaxInd = np.argmax(corr)
        corrMinInd = np.argmin(corr)
        corrMax = corr[corrMaxInd]
        corrMin = corr[corrMinInd]

        # determine whether to use the max or min and add the corresponding result to the polarities list
        if corrMax >= abs(corrMin):
            pols.append(1)
            maxInd = corrMaxInd
        else:
            pols.append(-1)
            maxInd = corrMinInd

        # set the corresponding shift(s) according to 'shiftMethod'
        match shiftMethod:

            case 'standard':
                # no further processing needed for standard
                shifts.append(maxInd)

            case 'interp':
                # interpolate a parabola using the points surrounding maxInd and use that as the shift
                if maxInd == 0 or maxInd == len(corr) - 1:
                    # first handle the edge cases - do not interpolate at an edge
                    fitInd = maxInd
                else:
                    interpX = np.array([maxInd - 1, maxInd, maxInd + 1])
                    interpY = corr[interpX]
                    shifts.append(parabolaInterpolate(interpX, interpY))

            case 'pairwise':
                # the logic behind this method is that the greedy matching pursuit algorithm will miss a global optimum
                # decomposition if it is two nearby functions, instead representing it as one single function. This method
                # searches the neighborhood of the local optimum to see if there are any close pairs that result in a better fit

                # generate a list of combinations of indices in the neighborhood of maxInd specified by the kwargs
                width = kwargs['width']
                numberOfSteps = kwargs['numberOfSteps']
                shiftList = list(combinations(np.linspace(maxInd - width, maxInd + width, numberOfSteps), 2))
                shiftList.append([maxInd])

                # iterate through the shift list, calculating the fit and residual at each set of shifts
                pairwiseAmps = []
                pairwiseRes = []
                pairwiseResScaled = []
                for shift in shiftList:

                    pairwiseFit = linearFitRefWaveNN(ref, currentSignal, shift, [pols[-1], pols[-1]])
                    pairwiseAmps.append(pairwiseFit[0])
                    pairwiseRes.append(pairwiseFit[2])
                    # need to scale the residuals by the width they cover, otherwise we are biasing towards more spread functions
                    # assuming shift is a list of length 1 or 2
                    if len(shift) == 2:
                        pairwiseFitWidth = refLen + abs(shift[0] - shift[1])
                    else:
                        pairwiseFitWidth = refLen
                    pairwiseResScaled.append(pairwiseFit[2] / pairwiseFitWidth)

                # identify the optimal (lowest res) fit and use those values
                # NOTE: this may append either a number or a list of numbers depending on the optimum. Will need to flatten
                # the results before returning them
                pairwiseBestFitIndex = np.argmin(pairwiseResScaled)
                res.append(pairwiseRes[pairwiseBestFitIndex])
                shifts.append(list(shiftList[pairwiseBestFitIndex]))
                amps.append(list(pairwiseAmps[pairwiseBestFitIndex]))

        # find the optimal amplitude for the given shift
        if shiftMethod == 'pairwise':
            # we've already done this for the pairwise method
            pass
        else:
            fit = linearFitRefWaveNN(ref, currentSignal, [shifts[-1]], [pols[-1]])
            amps.append(fit[0][0])

        # subtract the fit, calculate the residual for this step
        oldSignal = copy.copy(currentSignal)

        # first handle a single fit
        if type(amps[-1]) != list:
            # not a list -> float or int
            currentSignal = oldSignal - amps[-1] * pols[-1] * padAndInterpolateReferenceWave(ref, signalLen, shifts[-1])
            if plotSteps:
                plotFits(ref, oldSignal, [shifts[-1]], [pols[-1] * amps[-1]])
        else:
            # two or more shifts/amps were added - the end of the amps and shifts list is a len=2 list
            fitSum = np.zeros(signalLen)
            for i in range(len(shifts[-1])):
                fitSum = fitSum + amps[-1][i] * pols[-1] * padAndInterpolateReferenceWave(ref, signalLen, shifts[-1][i])
            currentSignal = oldSignal - fitSum
            if plotSteps:
                plotFits(ref, oldSignal, shifts[-1], [pols[-1] * amp for amp in amps[-1]])

        # original signal - currentSignal gives the sum of all fits so far. The residual is signal - sum of fits, or
        # signal - (signal - currentSignal) = currentSignal. The residual is therefor just the sum of the magnitude of currentSignal
        res.append(np.sum(abs(currentSignal)))

        # determine whether to break the while loop depending on number of iterations or residual threshold
        iter += 1
        normRes = res[-1] / signalLen
        if normRes <= normResThreshold:
            continueIter = False
        elif iter >= maxIterations:
            continueIter = False

    # combine the polarity and amplitudes to give signed amplitudes
    # this needs to handle amps being a list of numbers and a list of lists
    if type(amps[-1]) == list:
        # I have made bad choices in life to end up writing a line of code like this
        ampPols = np.array([np.array([pols[i] * amp for amp in amps[i]]) for i in range(len(amps))])
    else:
        ampPols = np.array(amps) * np.array(pols)

    # flatten the amps and shifts lists in case pairs of values were added
    # for ease I'm just going to go into numpy and back
    flatAmps = list(ampPols.flatten())
    flatShifts = list(np.array(shifts).flatten())

    # plot the total fit
    if plotResult:
        plotFits(ref, signal, flatShifts, flatAmps)

    return flatShifts, flatAmps, res



