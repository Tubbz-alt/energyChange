#!/usr/local/lcls/package/python/current/bin/python

# ONLY GUARANTEED TO WORK WITH GUN-TD11, TD11-BSY, LTU and Undulator Taper
# Regions

import sys
import pyScore
from epics import caput


################################################################################
# GET AND SET PVs, where the magic happens
################################################################################
def setDevices(regionToLoad, scoreData):
    print("Setting devices... ")
    # List to hold pv names that didn't load properly
    errors = []
    for device, setting in zip(scoreData['despvs'], scoreData['desvals']):
        if ('NAN' in str(setting) and (("BDES" in device) or ("KDES" in device)
                                       or ("EDES" in device))):

            # These exist in undulator taper score config?
            if device != 'NA':
                print 'NaN encountered! Not setting NaNs!!!'
                errors.append(device)
            continue

        # Magnets
        if "BDES" in device:
            # Only load quads from Undulator-LEM region
            if (regionToLoad == "Undulator-LEM") and ("QUAD" not in device):
                continue

            attempt = caput(device, setting)
            if device == "BEND:DMP1:400:BDES":

                for ltumag in ["BEND:LTU1:220:BDES", "BEND:LTU1:280:BDES",
                               "BEND:LTU1:420:BDES", "BEND:LTU1:480:BDES"]:
                    # Set LTU bend BDES same as DMP BDES; needed to start doing
                    # this in Aug. 2018?!?
                    caput(ltumag, setting)

            # If put fails, x should be Nonetype
            if not attempt:
                # Add pv to errorlist if didn't load right
                errors.append(device)

            # Trim to BDES
            caput(device[:-4] + 'FUNC', '2')
            # Set BCON so Howard doesn't flip out because the CON doesn't match
            # the DES
            caput(device[:-4] + 'BCON', setting)

        # Undulator segments
        elif "KDES" in device:
            if (":950" not in device and "1650" not in device
                    and "3350" not in device):

                # Set KDES to device
                attempt = caput(device, setting)

                if not attempt:
                    errors.append(device)

                motorVal = scoreData['desvals'][
                    scoreData['despvs'].index(device[:-4]
                                              + 'TM1MOTOR')]

                # Don't trim undulators in if they were out for config (also
                # don't pull them out)
                # TODO why cast to float when comparing to int?
                if float(motorVal) < 70:
                    # Trim to KDES
                    caput(device[:-4] + 'TRIM.PROC', '1')

        # EDES for LEM
        elif ("EDES" in device) and (regionToLoad != "Undulator-LEM"):
            attempt = caput(device, setting)

            if not attempt:
                errors.append(device)

            if 'REFS' not in device:
                # Set ECON
                caput(device[:-4] + 'ECON', setting)

    return errors


if __name__ == '__main__':

    # Check number of arguments; give error if there are not enough or too many
    if len(sys.argv) != 4:
        print ('ERROR! CANNOT COMPUTE!  I need exactly three arguments: '
               '\n-region (e.g "TD11 to BSY-LEM"; USE quotes)'
               '\n-date (e.g. 2014-10-16; NOT in quotes)'
               '\n-time (e.g. 02:05 or 19:54; NOT in quotes)'
               '\nFor example: score_load.bash "TD11 to BSY-LEM" '
               '2014-10-29 01:34')

        sys.exit()

    region = sys.argv[1]
    date = sys.argv[2]

    # Format should be 09:13:49 (i.e. seconds included)
    configtime = sys.argv[3]

    # Connect to DB and retrieve values
    score = pyScore.Pyscore()

    try:
        data = score.read_pvs(region, date, configtime)
    except TypeError:
        print 'Error!  No config found for selected time!!! Exiting'
        sys.exit()

    errorList = setDevices(region, data)

    print 'Error Count:', len(errorList)

    # No errors encountered
    if not errorList:
        print 'SUCCESS'

    # Error(s) encountered; print them out
    else:
        print 'ERROR(s) loading the following devices:', errorList

    score.exit_score()
    sys.exit()
