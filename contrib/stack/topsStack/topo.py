#!/usr/bin/env python3

import numpy as np
import argparse
import os
import isce
import isceobj
import datetime
import sys
import s1a_isce_utils as ut
from isceobj.Planet.Planet import Planet
from zerodop.topozero import createTopozero
import multiprocessing as mp
from isceobj.Util.Poly2D import Poly2D


def createParser():
    parser = argparse.ArgumentParser( description='Generates lat/lon/h and los for each pixel')
    parser.add_argument('-m', '--reference', type=str, dest='reference', required=True,
            help='Directory with the reference image')
    parser.add_argument('-d', '--dem', type=str, dest='dem', required=True,
            help='DEM to use for coregistration')
    parser.add_argument('-g', '--geom_referenceDir', type=str, dest='geom_referenceDir', default='geom_reference',
            help='Directory for geometry files of the reference')
    parser.add_argument('-n', '--numProcess', type=int, dest='numProcess', default=1,
            help='Number of parallel processes (default: %(default)s).')
    parser.add_argument('-useGPU', '--useGPU', dest='useGPU',action='store_true', default=False,
            help='Allow App to use GPU when available')

    return parser

def cmdLineParse(iargs=None):
    '''
    Command line parser.
    '''
    parser = createParser()
    return parser.parse_args(args=iargs)


def call_topo(input):

    (dirname, demImage, reference, ind) = input

    burst = reference.bursts[ind]
    latname = os.path.join(dirname, 'lat_%02d.rdr' % (ind + 1))
    lonname = os.path.join(dirname, 'lon_%02d.rdr' % (ind + 1))
    hgtname = os.path.join(dirname, 'hgt_%02d.rdr' % (ind + 1))
    losname = os.path.join(dirname, 'los_%02d.rdr' % (ind + 1))
    maskname = os.path.join(dirname, 'shadowMask_%02d.rdr' % (ind + 1))
    incname = os.path.join(dirname, 'incLocal_%02d.rdr' % (ind + 1))
    #####Run Topo
    planet = Planet(pname='Earth')
    topo = createTopozero()
    topo.slantRangePixelSpacing = burst.rangePixelSize
    topo.prf = 1.0 / burst.azimuthTimeInterval
    topo.radarWavelength = burst.radarWavelength
    topo.orbit = burst.orbit
    topo.width = burst.numberOfSamples
    topo.length = burst.numberOfLines
    topo.wireInputPort(name='dem', object=demImage)
    topo.wireInputPort(name='planet', object=planet)
    topo.numberRangeLooks = 1
    topo.numberAzimuthLooks = 1
    topo.lookSide = -1
    topo.sensingStart = burst.sensingStart
    topo.rangeFirstSample = burst.startingRange
    topo.demInterpolationMethod = 'BIQUINTIC'
    topo.latFilename = latname
    topo.lonFilename = lonname
    topo.heightFilename = hgtname
    topo.losFilename = losname
    topo.maskFilename = maskname
    topo.incFilename = incname
    topo.topo()

    bbox = [topo.minimumLatitude, topo.maximumLatitude, topo.minimumLongitude, topo.maximumLongitude]

    topo = None

    return bbox


def call_topo_gpu(input):
    from iscesys import DateTimeUtil as DTU
    from zerodop.GPUtopozero.GPUtopozero import PyTopozero

    (dirname, demfilename, reference, ind) = input

    burst = reference.bursts[ind]
    latname = os.path.join(dirname, 'lat_%02d.rdr' % (ind + 1))
    lonname = os.path.join(dirname, 'lon_%02d.rdr' % (ind + 1))
    hgtname = os.path.join(dirname, 'hgt_%02d.rdr' % (ind + 1))
    losname = os.path.join(dirname, 'los_%02d.rdr' % (ind + 1))
    maskname = os.path.join(dirname, 'shadowMask_%02d.rdr' % (ind + 1))
    incname = os.path.join(dirname, 'incLocal_%02d.rdr' % (ind + 1))

    demImage = isceobj.createDemImage()
    demImage.load(demfilename + '.xml')
    demImage.setCaster('read', 'FLOAT')
    demImage.createImage()

    width = burst.numberOfSamples
    length = burst.numberOfLines
    dr = burst.rangePixelSize
    dt = burst.azimuthTimeInterval
    r0 = burst.startingRange
    t0 = burst.sensingStart
    wvl = burst.radarWavelength
    pegHdg = np.radians(burst.orbit.getENUHeading(t0))

    polyDoppler = Poly2D(name='topsStack_dopplerPoly')
    polyDoppler.setWidth(width)
    polyDoppler.setLength(length)
    polyDoppler.setNormRange(1.0)
    polyDoppler.setNormAzimuth(1.0)
    polyDoppler.setMeanRange(0.0)
    polyDoppler.setMeanAzimuth(0.0)
    polyDoppler.initPoly(rangeOrder=0,azimuthOrder=0, coeffs=[[0.]])
    polyDoppler.createPoly2D()

    slantRangeImage = Poly2D()
    slantRangeImage.setWidth(width)
    slantRangeImage.setLength(length)
    slantRangeImage.setNormRange(1.0)
    slantRangeImage.setNormAzimuth(1.0)
    slantRangeImage.setMeanRange(0.)
    slantRangeImage.setMeanAzimuth(0.)
    slantRangeImage.initPoly(rangeOrder=1,azimuthOrder=0,coeffs=[[r0,dr]])
    slantRangeImage.createPoly2D()

    latImage = isceobj.createImage()
    latImage.initImage(latname, 'write', width, 'DOUBLE')
    latImage.createImage()

    lonImage = isceobj.createImage()
    lonImage.initImage(lonname, 'write', width, 'DOUBLE')
    lonImage.createImage()

    losImage = isceobj.createImage()
    losImage.initImage(losname, 'write', width, 'FLOAT', bands=2, scheme='BIL')
    losImage.setCaster('write', 'DOUBLE')
    losImage.createImage()

    heightImage = isceobj.createImage()
    heightImage.initImage(hgtname, 'write', width, 'DOUBLE')
    heightImage.createImage()

    incImage = isceobj.createImage()
    incImage.initImage(incname, 'write', width, 'FLOAT', bands=2, scheme='BIL')
    incImage.createImage()

    maskImage = isceobj.createImage()
    maskImage.initImage(maskname, 'write', width, 'BYTE', bands=1, scheme='BIL')
    maskImage.createImage()

    elp = Planet(pname='Earth').ellipsoid
    topo = PyTopozero()
    topo.set_firstlat(demImage.getFirstLatitude())
    topo.set_firstlon(demImage.getFirstLongitude())
    topo.set_deltalat(demImage.getDeltaLatitude())
    topo.set_deltalon(demImage.getDeltaLongitude())
    topo.set_major(elp.a)
    topo.set_eccentricitySquared(elp.e2)
    topo.set_rSpace(dr)
    topo.set_r0(r0)
    topo.set_pegHdg(pegHdg)
    topo.set_prf(1.0/dt)
    topo.set_t0(DTU.seconds_since_midnight(t0))
    topo.set_wvl(wvl)
    topo.set_thresh(.05)
    topo.set_demAccessor(demImage.getImagePointer())
    topo.set_dopAccessor(polyDoppler.getPointer())
    topo.set_slrngAccessor(slantRangeImage.getPointer())
    topo.set_latAccessor(latImage.getImagePointer())
    topo.set_lonAccessor(lonImage.getImagePointer())
    topo.set_losAccessor(losImage.getImagePointer())
    topo.set_heightAccessor(heightImage.getImagePointer())
    topo.set_incAccessor(incImage.getImagePointer())
    topo.set_maskAccessor(maskImage.getImagePointer())
    topo.set_numIter(25)
    topo.set_idemWidth(demImage.getWidth())
    topo.set_idemLength(demImage.getLength())
    topo.set_ilrl(-1)
    topo.set_extraIter(10)
    topo.set_length(length)
    topo.set_width(width)
    topo.set_nRngLooks(1)
    topo.set_nAzLooks(1)
    topo.set_demMethod(5)
    topo.set_orbitMethod(0)

    try:
        stateVectors = burst.orbit.stateVectors.list
    except Exception:
        stateVectors = burst.orbit._stateVectors

    topo.set_orbitNvecs(len(stateVectors))
    topo.set_orbitBasis(1)
    topo.createOrbit()
    for count, sv in enumerate(stateVectors):
        td = DTU.seconds_since_midnight(sv.getTime())
        pos = sv.getPosition()
        vel = sv.getVelocity()
        topo.set_orbitVector(count,td,pos[0],pos[1],pos[2],vel[0],vel[1],vel[2])

    topo.runTopo()

    latImage.finalizeImage()
    latImage.renderHdr()
    lonImage.finalizeImage()
    lonImage.renderHdr()
    heightImage.finalizeImage()
    heightImage.renderHdr()
    losImage.finalizeImage()
    losImage.renderHdr()
    incImage.finalizeImage()
    incImage.renderHdr()
    maskImage.finalizeImage()
    maskImage.renderHdr()
    demImage.finalizeImage()

    if slantRangeImage:
        try:
            slantRangeImage.finalizeImage()
        except Exception:
            pass

    return None


def main(iargs=None):

    inps = cmdLineParse(iargs)

    run_GPU = False
    try:
        from zerodop.GPUtopozero.GPUtopozero import PyTopozero
        from zerodop.GPUgeo2rdr.GPUgeo2rdr import PyGeo2rdr
        run_GPU = True
    except Exception:
        pass

    if inps.useGPU and not run_GPU:
        print('GPU mode requested but no GPU ISCE code found')

    if run_GPU and inps.useGPU:
        print('GPU mode')
        run_topo = call_topo_gpu
    else:
        print('CPU mode')
        run_topo = call_topo
        demImage = isceobj.createDemImage()
        demImage.load(inps.dem + '.xml')

    swathList = ut.getSwathList(inps.reference)

    boxes = []
    inputs = []

    for swath in swathList:
        reference =  ut.loadProduct(os.path.join(inps.reference , 'IW{0}.xml'.format(swath)))
    
        ###Check if geometry directory already exists.
        dirname = os.path.join(inps.geom_referenceDir, 'IW{0}'.format(swath))
        os.makedirs(dirname, exist_ok=True)

        for ind in range(reference.numberOfBursts):
            if run_topo == call_topo_gpu:
                inputs.append((dirname, inps.dem, reference, ind))
            else:
                inputs.append((dirname, demImage, reference, ind))

    if run_topo == call_topo_gpu:
        if inps.numProcess > 1:
            print('GPU mode: ignoring numProcess > 1 and running single process')
        for inp in inputs:
            run_topo(inp)
    else:
        print('running in parallel with {} processes'.format(inps.numProcess))
        pool = mp.Pool(inps.numProcess)
        results = pool.map(run_topo, inputs)
        pool.close()

        for bbox in results:
            boxes.append(bbox)

        boxes = np.array(boxes)
        bbox = [np.min(boxes[:,0]), np.max(boxes[:,1]), np.min(boxes[:,2]), np.max(boxes[:,3])]
        print('bbox : ', bbox)
    

if __name__ == '__main__':

    main()
