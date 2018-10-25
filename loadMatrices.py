#!/usr/local/lcls/package/python/current/bin/python

# Writter by Zimmer, 1/20/2017. Refactored by Lisa
# Sets LTU and UND feedback matrices, used for energy change.

import sys
import pyScore
import time
from os import popen
from epics import caget, caput


################################################################################
# GET AND SET PVs, where the magic happens
################################################################################
def setMatricesAndRestartFeedbacks(scoreData):

    for device, setting in zip(scoreData['desPVs'], scoreData['desVals']):

        if device in ["FBCK:FB03:TR01:FMATRIX", "FBCK:FB03:TR01:GMATRIX",
                      "FBCK:FB03:TR04:FMATRIX", "FBCK:FB03:TR04:GMATRIX",
                      "FBCK:FB02:TR04:FMATRIX", "FBCK:FB02:TR04:GMATRIX"]:

            if 'NaN' in str(setting):
                print 'NaN found; not setting ' + str(device)
                continue

            settingList = setting.split(';')

            try:
                caput(device, [float(x) for x in settingList[:200]])
            except:
                print ("error setting matrices using pyepics - using popen "
                       "instead")
                formattedSetting = '200 '

                for element in settingList:
                    formattedSetting += element + ' '

                popen('caput -a ' + device + ' ' + formattedSetting)

    time.sleep(1.5)

    # Turn off fast LTU
    caput("FBCK:FB03:TR01:STATE", 0)

    # Turn off fast UND
    caput("FBCK:FB03:TR04:STATE", 0)

    # Turn off matlab UND
    caput("FBCK:UND0:1:STATE", 0)

    time.sleep(1)

    fastFeedbackActive = caget("SIOC:SYS0:ML02:AO127")

    # Und fast feedback active
    if fastFeedbackActive:
        # Turn on fast UND
        caput("FBCK:FB03:TR04:STATE", 1)
    else:
        # Let user turn on matlab UND out of paranoia
        pass

    # Turn on fast LTU
    caput("FBCK:FB03:TR01:STATE", 1)


if __name__ == '__main__':
    # Check number of arguments; give error if there are not enough or too many
    if len(sys.argv) != 3:
        print ('ERROR! CANNOT COMPUTE!  I need exactly three arguments: '
               '\n-region (e.g "TD11 to BSY-LEM"; USE quotes)'
               '\n-date (e.g. 2014-10-16; NOT in quotes)'
               '\n-time (e.g. 02:05 or 19:54; NOT in quotes)'
               '\nFor example: matrices_load.bash 2014-10-29 01:34')
        sys.exit()

    # Assign arguments to useful variables
    date = sys.argv[1]
    time = sys.argv[2]
    region = "Feedback-All"

    # Connect to DB and retrieve values#
    score = pyScore.Pyscore()

    try:
        data = score.read_pvs(region, date, time)
    except TypeError:
        print 'Error!  No config found for selected time!!! Exiting'
        sys.exit()

    setMatricesAndRestartFeedbacks(data)

    print 'Set feedback matrices and restarted feedbacks!!! YAY!!!'
    score.exit_score()
    sys.exit()
