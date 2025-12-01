#!/usr/bin/env python3

# Author: Cunren Liang
# Copyright 2021

import isce
import isceobj
import stdproc
from stdproc.stdproc import crossmul
import numpy as np
from isceobj.Util.Poly2D import Poly2D
import argparse
import os
import copy
import s1a_isce_utils as ut
from isceobj.Sensor.TOPS import createTOPSSwathSLCProduct


def createParser():
    parser = argparse.ArgumentParser( description='bandpass filtering and resampling burst by burst SLCs ')

    parser.add_argument('-m', '--reference', dest='reference', type=str, required=True,
            help='Directory with reference acquisition')

    parser.add_argument('-s', '--secondary', dest='secondary', type=str, required=True,
            help='Directory with secondary acquisition')

    parser.add_argument('-o', '--coregdir', dest='coreg', type=str, default='coreg_secondary',
            help='Directory with coregistered SLCs and IFGs')

    parser.add_argument('-useGPU', '--useGPU', dest='useGPU',action='store_true', default=False,
            help='Allow App to use GPU when available')

    parser.add_argument('-a', '--azimuth_misreg', dest='misreg_az', type=str, default=0.0,
            help='File name with the azimuth misregistration')

    parser.add_argument('-r', '--range_misreg', dest='misreg_rng', type=str, default=0.0,
            help='File name with the range misregistration')

    parser.add_argument('--noflat', dest='noflat', action='store_true', default=False,
            help='To turn off flattening. False: flattens the SLC. True: turns off flattening.')

    return parser

def cmdLineParse(iargs = None):
    parser = createParser()
    return parser.parse_args(args=iargs)

def resampSecondaryCPU(mas, slv, rdict, outname, flatten):
    '''
    Resample burst by burst.
    '''

    azpoly = rdict['azpoly']
    rgpoly = rdict['rgpoly']
    azcarrpoly = rdict['carrPoly']
    dpoly = rdict['doppPoly']

    rngImg = isceobj.createImage()
    rngImg.load(rdict['rangeOff'] + '.xml')
    rngImg.setAccessMode('READ')

    aziImg = isceobj.createImage()
    aziImg.load(rdict['azimuthOff'] + '.xml')
    aziImg.setAccessMode('READ')

    inimg = isceobj.createSlcImage()
    inimg.load(slv.image.filename + '.xml')
    inimg.setAccessMode('READ')


    rObj = stdproc.createResamp_slc()
    rObj.slantRangePixelSpacing = slv.rangePixelSize
    rObj.radarWavelength = slv.radarWavelength
    rObj.azimuthCarrierPoly = azcarrpoly
    rObj.dopplerPoly = dpoly

    rObj.azimuthOffsetsPoly = azpoly
    rObj.rangeOffsetsPoly = rgpoly
    rObj.imageIn = inimg

    ####Setting reference values
    rObj.startingRange = sec.startingRange
    rObj.referenceSlantRangePixelSpacing = ref.rangePixelSize
    rObj.referenceStartingRange = ref.startingRange
    rObj.referenceWavelength = ref.radarWavelength

    width = mas.numberOfSamples
    length = mas.numberOfLines
    imgOut = isceobj.createSlcImage()
    imgOut.setWidth(width)
    imgOut.filename = outname
    imgOut.setAccessMode('write')

    rObj.outputWidth = width
    rObj.outputLines = length
    rObj.residualRangeImage = rngImg
    rObj.residualAzimuthImage = aziImg
    rObj.flatten = flatten
    print(rObj.flatten)
    rObj.resamp_slc(imageOut=imgOut)

    imgOut.renderHdr()
    imgOut.renderVRT()
    return imgOut


def convertPoly2D(poly):
    '''
    Convert a isceobj.Util.Poly2D {poly} into zerodop.GPUresampslc.GPUresampslc.PyPloy2d
    '''
    from zerodop.GPUresampslc.GPUresampslc import PyPoly2d
    import itertools

    # get parameters from poly
    azimuthOrder = poly.getAzimuthOrder()
    rangeOrder = poly.getRangeOrder()
    azimuthMean = poly.getMeanAzimuth()
    rangeMean = poly.getMeanRange()
    azimuthNorm = poly.getNormAzimuth()
    rangeNorm = poly.getNormRange()

    # create the PyPoly2d object
    pPoly = PyPoly2d(azimuthOrder, rangeOrder, azimuthMean, rangeMean, azimuthNorm, rangeNorm)
    # copy the coeffs, need to flatten into 1d list
    pPoly.coeffs = list(itertools.chain.from_iterable(poly.getCoeffs()))

    # all done
    return pPoly


def resampSecondaryGPU(ref, sec, rdict, outname, flatten):
    '''
    Resample burst by burst with GPU
    '''

    # import the GPU module
    import zerodop.GPUresampslc

    # get Poly2D objects from rdict and convert them into PyPoly2d objects
    azpoly = convertPoly2D(rdict['azpoly'])
    rgpoly = convertPoly2D(rdict['rgpoly'])

    azcarrpoly = convertPoly2D(rdict['carrPoly'])
    dpoly = convertPoly2D(rdict['doppPoly'])

    rngImg = isceobj.createImage()
    rngImg.load(rdict['rangeOff'] + '.xml')
    rngImg.setCaster('read', 'FLOAT')
    rngImg.createImage()

    aziImg = isceobj.createImage()
    aziImg.load(rdict['azimuthOff'] + '.xml')
    aziImg.setCaster('read', 'FLOAT')
    aziImg.createImage()

    inimg = isceobj.createSlcImage()
    inimg.load(sec.image.filename + '.xml')
    inimg.setAccessMode('READ')
    inimg.createImage()

    # create a GPU resample processor
    rObj = zerodop.GPUresampslc.createResampSlc()

    # set parameters
    rObj.slr = sec.rangePixelSize
    rObj.wvl = sec.radarWavelength

    # set polynomials
    rObj.azCarrier = azcarrpoly
    rObj.dopplerPoly = dpoly
    rObj.azOffsetsPoly = azpoly
    rObj.rgOffsetsPoly = rgpoly
    # need to create an empty rgCarrier poly
    rgCarrier = Poly2D()
    rgCarrier.initPoly(rangeOrder=0, azimuthOrder=0, coeffs=[[0.]])
    rgCarrier = convertPoly2D(rgCarrier)
    rObj.rgCarrier = rgCarrier

    # input secondary image
    rObj.slcInAccessor = inimg.getImagePointer()
    rObj.inWidth = inimg.getWidth()
    rObj.inLength = inimg.getLength()

    ####Setting reference values
    rObj.r0 = sec.startingRange
    rObj.refr0 = ref.startingRange
    rObj.refslr = ref.rangePixelSize
    rObj.refwvl = ref.radarWavelength

    # set output image
    width = ref.numberOfSamples
    length = ref.numberOfLines

    imgOut = isceobj.createSlcImage()
    imgOut.setWidth(width)
    imgOut.filename = outname
    imgOut.setAccessMode('write')
    imgOut.createImage()
    rObj.slcOutAccessor = imgOut.getImagePointer()

    rObj.outWidth = width
    rObj.outLength = length
    rObj.residRgAccessor = rngImg.getImagePointer()
    rObj.residAzAccessor = aziImg.getImagePointer()
    rObj.flatten = flatten
    print(rObj.flatten)

    # need to specify data type, only complex is currently supported
    rObj.isComplex = (inimg.dataType == 'CFLOAT')
    # run resampling
    rObj.resamp_slc()

    # finalize images
    inimg.finalizeImage()
    imgOut.finalizeImage()
    rngImg.finalizeImage()
    aziImg.finalizeImage()

    imgOut.renderHdr()
    imgOut.renderVRT()
    return imgOut


def subband(burst, nout, outputfile, bw, bc, rgRef, virtual):
    '''
    burst:      input burst object
    nout:       number of output files
    outputfile: [value_of_out_1, value_of_out_2, value_of_out_3...] output files
    bw:         [value_of_out_1, value_of_out_2, value_of_out_3...] filter bandwidth divided by sampling frequency [0, 1]
    bc:         [value_of_out_1, value_of_out_2, value_of_out_3...] filter center frequency divided by sampling frequency
    rgRef:      reference range for moving center frequency to zero
    virtual: True or False
    '''

    from isceobj.Constants import SPEED_OF_LIGHT
    from isceobj.TopsProc.runIon import removeHammingWindow
    from contrib.alos2proc.alos2proc import rg_filter

    tmpFilename = burst.image.filename + '.tmp'

    #removing window
    rangeSamplingRate = SPEED_OF_LIGHT / (2.0 * burst.rangePixelSize)
    if burst.rangeWindowType == 'Hamming':
        removeHammingWindow(burst.image.filename, tmpFilename, burst.rangeProcessingBandwidth, rangeSamplingRate, burst.rangeWindowCoefficient, virtual=virtual)  
    else:
        raise Exception('Range weight window type: {} is not supported yet!'.format(burst.rangeWindowType))
    
    #subband
    rg_filter(tmpFilename,
              #burst.numberOfSamples,
              nout,
              outputfile,
              bw,
              bc,
              129,
              512,
              0.1,
              0,
              (burst.startingRange - rgRef) / burst.rangePixelSize
        )

    os.remove(tmpFilename)
    os.remove(tmpFilename+'.vrt')
    os.remove(tmpFilename+'.xml')


def main(iargs=None):
    '''
    Create coregistered overlap secondarys.
    '''
    inps = cmdLineParse(iargs)

    # see if the user compiled isce with GPU enabled
    run_GPU = False
    try:
        from zerodop.GPUresampslc.GPUresampslc import PyResampSlc
        run_GPU = True
    except:
        pass

    if inps.useGPU and not run_GPU:
        print("GPU mode requested but no GPU ISCE code found")

    # setting the respective version of resampSecondary for CPU and GPU
    if run_GPU and inps.useGPU:
        print('GPU mode')
        resampSecondary = resampSecondaryGPU
    else:
        print('CPU mode')
        resampSecondary = resampSecondaryCPU


    referenceSwathList = ut.getSwathList(inps.reference)
    secondarySwathList = ut.getSwathList(inps.secondary)

    swathList = list(sorted(set(referenceSwathList+secondarySwathList)))

    #if os.path.abspath(inps.reference) == os.path.abspath(inps.secondary):
    #    print('secondary is the same as reference, only performing subband filtering')

    for swath in swathList:
    
        ####Load secondary metadata
        reference = ut.loadProduct( os.path.join(inps.reference , 'IW{0}.xml'.format(swath)))
        secondary = ut.loadProduct( os.path.join(inps.secondary , 'IW{0}.xml'.format(swath)))


        if os.path.exists(str(inps.misreg_az)):
             with open(inps.misreg_az, 'r') as f:
                misreg_az = float(f.readline())
        else:
             misreg_az = 0.0

        if os.path.exists(str(inps.misreg_rng)):
             with open(inps.misreg_rng, 'r') as f:
                misreg_rg = float(f.readline())
        else:
             misreg_rg = 0.0

        ###Output directory for coregistered SLCs
        outdir = os.path.join(inps.coreg,'IW{0}'.format(swath))
        offdir = os.path.join(inps.coreg,'IW{0}'.format(swath))
        os.makedirs(outdir, exist_ok=True)

    
        ####Indices w.r.t reference
        burstoffset, minBurst, maxBurst = reference.getCommonBurstLimits(secondary)
        secondaryBurstStart = minBurst +  burstoffset
        secondaryBurstEnd = maxBurst
    
        relShifts = ut.getRelativeShifts(reference, secondary, minBurst, maxBurst, secondaryBurstStart)

        print('Shifts: ', relShifts)
    
        ####Can corporate known misregistration here
    
        apoly = Poly2D()
        apoly.initPoly(rangeOrder=0,azimuthOrder=0,coeffs=[[0.]])
    
        rpoly = Poly2D()
        rpoly.initPoly(rangeOrder=0,azimuthOrder=0,coeffs=[[0.]])

    
        #slvCoreg = createTOPSSwathSLCProduct()
        slvCoreg = ut.coregSwathSLCProduct()
        slvCoreg.configure()


        for ii in range(minBurst, maxBurst):

            outname = os.path.join(outdir, 'burst_%02d.slc'%(ii+1))  
            outnameLower = os.path.splitext(outname)[0]+'_lower.slc'
            outnameUpper = os.path.splitext(outname)[0]+'_upper.slc'
            if os.path.exists(outnameLower) and os.path.exists(outnameLower+'.vrt') and os.path.exists(outnameLower+'.xml') and \
               os.path.exists(outnameUpper) and os.path.exists(outnameUpper+'.vrt') and os.path.exists(outnameUpper+'.xml'):
                print('burst %02d already processed, skip...'%(ii+1))
                continue

            jj = secondaryBurstStart + ii - minBurst

            masBurst = reference.bursts[ii]
            slvBurst = secondary.bursts[jj]

            #####Top burst processing
            try:
                offset = relShifts[jj]
            except:
                raise Exception('Trying to access shift for secondary burst index {0}, which may not overlap with reference'.format(jj))

        
            ####Setup initial polynomials
            ### If no misregs are given, these are zero
            ### If provided, can be used for resampling without running to geo2rdr again for fast results
            rdict = {'azpoly' : apoly,
                 'rgpoly' : rpoly,
                  'rangeOff' : os.path.join(offdir, 'range_%02d.off'%(ii+1)),
                  'azimuthOff': os.path.join(offdir, 'azimuth_%02d.off'%(ii+1))}
                 

            ###For future - should account for azimuth and range misreg here .. ignoring for now.
            azCarrPoly, dpoly = secondary.estimateAzimuthCarrierPolynomials(slvBurst, offset = -1.0 * offset)
    
            rdict['carrPoly'] = azCarrPoly
            rdict['doppPoly'] = dpoly
    

            #subband filtering
            from Stack import ionParam
            from isceobj.Constants import SPEED_OF_LIGHT
            rangeSamplingRate = SPEED_OF_LIGHT / (2.0 * slvBurst.rangePixelSize)

            ionParamObj=ionParam()
            ionParamObj.configure()
            lower_tmpfile = os.path.splitext(slvBurst.image.filename)[0]+'_lower_tmp.slc'
            upper_tmpfile = os.path.splitext(slvBurst.image.filename)[0]+'_upper_tmp.slc'
            outputfile = [lower_tmpfile, upper_tmpfile]
            bw = [ionParamObj.rgBandwidthSub / rangeSamplingRate, ionParamObj.rgBandwidthSub / rangeSamplingRate]
            bc = [-ionParamObj.rgBandwidthForSplit / 3.0 / rangeSamplingRate, ionParamObj.rgBandwidthForSplit / 3.0 / rangeSamplingRate]
            rgRef = ionParamObj.rgRef
            subband(slvBurst, 2, outputfile, bw, bc, rgRef, True)

            #resampling
            slvBurst.radarWavelength = ionParamObj.radarWavelengthLower
            slvBurst.image.filename = lower_tmpfile
            outnameSubband = outnameLower
            outimg = resampSecondary(masBurst, slvBurst, rdict, outnameSubband, (not inps.noflat))

            slvBurst.radarWavelength = ionParamObj.radarWavelengthUpper
            slvBurst.image.filename = upper_tmpfile
            outnameSubband = outnameUpper
            outimg = resampSecondary(masBurst, slvBurst, rdict, outnameSubband, (not inps.noflat))

            #remove original subband images
            os.remove(lower_tmpfile)
            os.remove(lower_tmpfile+'.vrt')
            os.remove(lower_tmpfile+'.xml')

            os.remove(upper_tmpfile)
            os.remove(upper_tmpfile+'.vrt')
            os.remove(upper_tmpfile+'.xml')


# share IW*.xml with full band images, these are no longer required.
#########################################################################################################################################
        #     minAz, maxAz, minRg, maxRg = ut.getValidLines(slvBurst, rdict, outname,
        #         misreg_az = misreg_az - offset, misreg_rng = misreg_rg)
            

        #     copyBurst = copy.deepcopy(masBurst)
        #     ut.adjustValidSampleLine_V2(copyBurst, slvBurst, minAz=minAz, maxAz=maxAz,
        #                              minRng=minRg, maxRng=maxRg)
        #     copyBurst.image.filename = outimg.filename
        #     print('After: ', copyBurst.firstValidLine, copyBurst.numValidLines)
        #     slvCoreg.bursts.append(copyBurst)

 
        # slvCoreg.numberOfBursts = len(slvCoreg.bursts)
        # slvCoreg.source = ut.asBaseClass(secondary)
        # slvCoreg.reference = reference
        # ut.saveProduct(slvCoreg, outdir + '.xml')    

if __name__ == '__main__':
    '''
    Main driver.
    '''
    # Main Driver
    main()



