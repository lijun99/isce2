#!/usr/bin/env python3
########################
#Author: Heresh Fattahi
#Copyright 2016
######################
import argparse
import isce
import isceobj
import os
import sys
import numpy as np
from osgeo import gdal
import xml.etree.ElementTree as ET

def createParser():
    '''
    Create command line parser.
    '''

    parser = argparse.ArgumentParser( description='Create DEM simulation for merged images')
    parser.add_argument('-l','--lat', dest='latFile', type=str, required=True,
            help = 'latitude file in radar coordinate')
    parser.add_argument('-L','--lon', dest='lonFile', type=str, required=True,
            help = 'longitude file in radar coordinate')
    parser.add_argument('-f', '--filelist', dest='prodlist', type=str, required=True,
            help='Input file to be geocoded')
    parser.add_argument('-b', '--bbox', dest='bbox', type=str, default=None,
            help='Bounding box (SNWE); auto-derived from lat/lon files if not provided')
    parser.add_argument('-x', '--lon_step', dest='lonStep', type=str, default=0.001,
            help='output pixel size (longitude) in degrees. Default 0.001')
    parser.add_argument('-y', '--lat_step', dest='latStep', type=str, default=0.001,
            help='output pixel size (latitude) in degrees. Default 0.001')
    parser.add_argument('-o', '--xoff', dest='xOff', type=int, default=0,
            help='Offset from the begining of geometry files in x direction. Default 0.0')
    parser.add_argument('-p', '--yoff', dest='yOff', type=int, default=0,
            help='Offset from the begining of geometry files in y direction. Default 0.0')
    parser.add_argument('-r', '--resampling_method', dest='resamplingMethod', type=str, default='near',
            help='Resampling method (gdalwarp resamplin methods)')

    return parser

def cmdLineParse(iargs = None):
    '''
    Command line parser.
    '''

    parser = createParser()
    inps =  parser.parse_args(args = iargs)

    if inps.bbox is not None:
        inps.bbox = [val for val in inps.bbox.split()]
        if len(inps.bbox) != 4:
            raise Exception('Bbox should contain 4 floating point values')
    else:
        inps.bbox = _bbox_from_lat_lon(inps.latFile, inps.lonFile)

    inps.prodlist = inps.prodlist.split()
    return inps


def _bbox_from_lat_lon(lat_file, lon_file):
    """Derive SNWE bbox from lat.rdr/lon.rdr at execution time."""
    for f in [lat_file, lat_file + '.xml', lon_file, lon_file + '.xml']:
        if not os.path.exists(f):
            print('ERROR: {} not found.'.format(f))
            print('The reference geometry step must complete before geocoding.')
            print('Re-run stackStripMap.py with --geocode after the reference step,')
            print('or provide the bounding box explicitly with --geocode_bbox "S N W E".')
            sys.exit(1)

    lat_img = isceobj.createImage()
    lat_img.load(lat_file + '.xml')
    width = lat_img.getWidth()
    length = lat_img.getLength()
    dtype = lat_img.toNumpyDataType()

    lat = np.fromfile(lat_file, dtype=dtype).reshape(length, width)
    lon = np.fromfile(lon_file, dtype=dtype).reshape(length, width)

    valid = np.isfinite(lat) & (lat != 0)
    bbox = ['{:.4f}'.format(lat[valid].min()),
            '{:.4f}'.format(lat[valid].max()),
            '{:.4f}'.format(lon[valid].min()),
            '{:.4f}'.format(lon[valid].max())]
    print('Geocode bounding box (SNWE) derived from {}: {}'.format(
        os.path.dirname(lat_file), ' '.join(bbox)))
    return bbox

def prepare_lat_lon(inps):

    latFile = os.path.abspath(inps.latFile)
    lonFile = os.path.abspath(inps.lonFile)
    cmd = 'isce2gis.py vrt -i ' + latFile
    os.system(cmd)
    cmd = 'isce2gis.py vrt -i ' + lonFile
    os.system(cmd)
    
    width, length =  getSize(latFile)
    widthFile , lengthFile = getSize(inps.prodlist[0])
    
    xOff = inps.xOff
    yOff = inps.yOff

    tempLat = os.path.join(os.path.dirname(inps.prodlist[0]), 'tempLAT.vrt')
    tempLon = os.path.join(os.path.dirname(inps.prodlist[0]), 'tempLON.vrt')

    cmd = 'gdal_translate -of VRT -srcwin ' + str(xOff) + ' ' + str(yOff) \
           +' '+ str(width - xOff) +' '+ str(length - yOff) +' -outsize ' + str(widthFile) + \
           ' '+ str(lengthFile)  + ' -a_nodata 0 ' + latFile +'.vrt ' +  tempLat

    os.system(cmd)

    cmd = 'gdal_translate -of VRT -srcwin ' + str(xOff) + ' ' + str(yOff) \
          +' '+ str(int(width-xOff)) +' '+ str(int(length-yOff)) +' -outsize ' + str(widthFile) +\
           ' '+ str(lengthFile)  + ' -a_nodata 0 ' + lonFile +'.vrt ' +  tempLon

    os.system(cmd)

    return tempLat, tempLon

    # gdal_translate -of VRT -srcwin  384 384 64889 12785 -outsize 1013 199 ../../COMBINED/GEOM_REFERENCE/LAT.rdr LAT_off.vrt
    

def writeVRT(infile, latFile, lonFile):
#This function is modified from isce2gis.py
            latFile = os.path.abspath(latFile)
            lonFile = os.path.abspath(lonFile)
            infile = os.path.abspath(infile)
            cmd = 'isce2gis.py vrt -i ' + infile
            os.system(cmd)

            tree = ET.parse(infile + '.vrt')
            root = tree.getroot()

            meta = ET.SubElement(root, 'metadata')
            meta.attrib['domain'] = "GEOLOCATION"
            meta.tail = '\n'
            meta.text = '\n    '


            #rdict = { 'Y_DATASET' : os.path.relpath(latFile , os.path.dirname(infile)),
            #          'X_DATASET' :  os.path.relpath(lonFile , os.path.dirname(infile)),

            rdict = { 'Y_DATASET' : latFile ,
                      'X_DATASET' :  lonFile ,
                      'X_BAND' : "1",
                      'Y_BAND' : "1",
                      'PIXEL_OFFSET': "0",
                      'LINE_OFFSET' : "0",
                      'LINE_STEP' : "1",
                      'PIXEL_STEP' : "1" }

            for key, val in rdict.items():
                data = ET.SubElement(meta, 'mdi')
                data.text = val
                data.attrib['key'] = key
                data.tail = '\n    '

            data.tail = '\n'
            tree.write(infile + '.vrt')


def runGeo(inps):

    for rfile in inps.prodlist:
       cmd = 'isce2gis.py envi -i ' + rfile
       os.system(cmd)

    WSEN = str(inps.bbox[2]) + ' ' + str(inps.bbox[0]) + ' ' + str(inps.bbox[3]) + ' ' + str(inps.bbox[1])
    latFile, lonFile = prepare_lat_lon(inps)
    
    for rfile in inps.prodlist:
       rfile = os.path.abspath(rfile)
       print ('geocoding ' + rfile)
       #cmd = 'isce2gis.py vrt -i '+ rfile + ' --lon ' + lonFile + ' --lat '+ latFile
       #os.system(cmd)
       writeVRT(rfile, latFile, lonFile)

       cmd = 'gdalwarp -overwrite -of ENVI -co INTERLEAVE=BIL -geoloc  -te '+ WSEN + ' -tr ' + str(inps.latStep) + ' ' + str(inps.lonStep) + ' -srcnodata 0 -dstnodata 0 ' + ' -r ' +inps.resamplingMethod +' ' + rfile +'.vrt ' + rfile + '.geo'
       print (cmd)
       os.system(cmd)
       write_xml(rfile + '.geo', rfile)

def getSize(f):

    ds=gdal.Open(f, gdal.GA_ReadOnly)
    b=ds.GetRasterBand(1)
    width = b.XSize
    length = b.YSize
    ds = None
    return width, length
       
def get_lat_lon(f):

    ds=gdal.Open(f, gdal.GA_ReadOnly)
    b=ds.GetRasterBand(1)
    width  = b.XSize
    length = b.YSize
    minLon = ds.GetGeoTransform()[0]
    deltaLon = ds.GetGeoTransform()[1]
    maxLat = ds.GetGeoTransform()[3]
    deltaLat = ds.GetGeoTransform()[5]
    minLat = maxLat + (b.YSize)*deltaLat
    nbands = ds.RasterCount
    _gdal_to_isce = {'BAND': 'BSQ', 'LINE': 'BIL', 'PIXEL': 'BIP'}
    gdal_interleave = ds.GetMetadataItem('INTERLEAVE', 'IMAGE_STRUCTURE') or 'BAND'
    interleave = _gdal_to_isce.get(gdal_interleave, 'BSQ')
    ds = None
    return maxLat, deltaLat, minLon, deltaLon, width, length, nbands, interleave

_IMAGE_FACTORIES = {
    'unw': isceobj.Image.createUnwImage,
    'int': isceobj.createIntImage,
    'slc': isceobj.createSlcImage,
    'dem': isceobj.createDemImage,
}

def _load_src_meta(srcFile):
    """Read image_type, number_bands, scheme, data_type from source XML."""
    meta = {}
    srcXml = srcFile + '.xml'
    if not os.path.exists(srcXml):
        return meta
    tree = ET.parse(srcXml)
    for p in tree.getroot().iter('property'):
        v = p.find('value')
        if v is not None:
            meta[p.get('name')] = v.text
    return meta

def write_xml(outFile, srcFile=None):

    maxLat, deltaLat, minLon, deltaLon, width, length, nbands, interleave = get_lat_lon(outFile)

    # Inherit only image_type and data_type from source XML;
    # bands and scheme come from the actual geocoded file (gdalwarp may change interleave)
    src = _load_src_meta(srcFile) if srcFile else {}
    image_type = src.get('image_type')
    src_dtype  = src.get('data_type', 'FLOAT').upper()

    factory = _IMAGE_FACTORIES.get(image_type, isceobj.createImage)
    outImage = factory()
    outImage.setFilename(outFile)
    outImage.setWidth(width)
    outImage.setLength(length)
    outImage.bands = nbands
    outImage.scheme = interleave
    outImage.dataType = src_dtype
    outImage.setAccessMode('read')

    outImage.coord2.coordDescription = 'Latitude'
    outImage.coord2.coordUnits = 'degree'
    outImage.coord2.coordStart = maxLat
    outImage.coord2.coordDelta = deltaLat
    outImage.coord1.coordDescription = 'Longitude'
    outImage.coord1.coordUnits = 'degree'
    outImage.coord1.coordStart = minLon
    outImage.coord1.coordDelta = deltaLon

    outImage.renderHdr()
    outImage.renderVRT()

def main(iargs=None):
    '''
    Main driver.
    '''
    inps = cmdLineParse(iargs)
    runGeo(inps)
 
   
if __name__ == '__main__':
    main()


