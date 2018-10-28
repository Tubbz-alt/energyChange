import time

from PyQt4.QtCore import QDate, QTime, Qt
from PyQt4.QtGui import QTableWidgetItem
from os import popen
from epics import caget, caput
from threading import Thread
from urllib2 import urlopen
from json import load
from subprocess import Popen
from datetime import datetime


# Utility class to try to replicate C struct functionality
class Struct:
    def __init__(self, **kwds):
        self.__dict__.update(kwds)


# Subclass to return a status from a thread (specifically the score loading
# threads).  Stupid that threading.Thread by default doesn't return a value.
# noinspection PyArgumentList
class ThreadWithReturnValue(Thread):
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs=None, Verbose=None):

        if kwargs is None:
            kwargs = {}

        self._Thread__kwargs = None
        self._Thread__args = None
        self._Thread__target = None
        self._return = None

        Thread.__init__(self, group, target, name, args, kwargs, Verbose)

    def run(self):
        if self._Thread__target is not None:
            self._return = self._Thread__target(*self._Thread__args,
                                                **self._Thread__kwargs)

    def join(self, **kwargs):
        Thread.join(self)
        return self._return


ENERGY_BOUNDARY = 2050

greetings = ["Hi! Aren't you the cutest lil thing!",
             "Hiiii! I've missed you beautiful! <3",
             "Came crawling back, eh? Of course you did.",
             "Finally decided to do your job huh?",
             "Hey Hey Hey! I missed you!",
             "I knew you'd be back. I'm so excited!",
             "I love you - your smile is the reason I launch!",
             "Hi sunshine, you light up my life!",
             "I love turtles. But I hate baby turtles.",
             "Energy change- getting you loaded since 2014",
             "Don't ever change. That's my job!",
             "For a failure, you sure seem chipper!",
             "It's sad that this is the highlight of your day.",
             "Can't wait for FACET 2...",
             "You're special and people like you!",
             "Master beats me if I'm a bad GUI :-(",
             "You can do anything! Reach for the stars!",
             "You're a capable human who does stuff!",
             "You excel at simple tasks! Yeah!",
             "If I were more than a GUI you'd make me blush!",
             "Delivering to CXrs or MC? Whatever who cares.",
             "You still work here? Sorry.",
             "Why did kamikazes wear helmets?",
             "If you do a job too well, you'll get stuck with it.",
             "You push buttons like nobody's business!",
             "You rock at turning knobs and watching numbers!",
             "Nobody keeps a machine on like you!",
             "You have a talent for making BPMs read zero!",
             "Way to show up for your shifts! Yeah!",
             "You are great at clicking things!",
             "Miss the SCP yet? I don't!",
             "Oh look at you! You're precious!",
             "You excel at mediocrity!",
             "Regret any of your life decisions yet?",
             "I thought you were quitting?!?",
             "Rick Perry is our new boss! Yay!",
             "Kissy face kissy face I love you!", "Didn't you quit?",
             "You rock at watching numbers!", "Kill me please!!!",
             "Don't go for your dreams, you will fail!",
             "You're the reason the gene pool needs a lifeguard!",
             "Do you still love nature, despite what it did to you?",
             "Ordinary people live and learn. You just live.",
             "Way to be physically present for 8 hours! Yeah!",
             "Hello, Clarice..."]


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


################################################################################
# GET AND SET PVs, where the magic happens
################################################################################
def setDevices(regionToLoad, scoreData):
    print("Setting devices for " + regionToLoad + "... ")
    # List to hold pv names that didn't load properly
    errors = []
    for device, setting in zip(scoreData['desPVs'], scoreData['desVals']):
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
            # SXRSS, HXRSS, and Delta
            if (":950" not in device and "1650" not in device
                    and "3350" not in device):

                # Set KDES to device
                attempt = caput(device, setting)

                if not attempt:
                    errors.append(device)

                index = scoreData['desPVs'].index(device[:-4] + 'TM1MOTOR')
                motorVal = scoreData['desVals'][index]

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

    if errors:
        print ("Error in loadScore loading region " + regionToLoad
               + " for devices: "
               + errors)

    return errors


def populateSetpoints(setpointDict):

    def makePV(key, getPVName, setPVName, getHistorical=True):
        setpointDict[key] = Struct(val=None, getPV=getPVName, setPV=setPVName,
                                   historical=getHistorical)

    def makeDoublePV(key, pvName, getHistorical=True):
        return makePV(key, pvName, pvName, getHistorical)

    for PMT in ["241", "242", "361", "362"]:
        makeDoublePV("voltagePMT" + PMT, "HVCH:FEE1:" + PMT + ":VoltageSet")
        makeDoublePV("calibrationPMT" + PMT, "GDET:FEE1:" + PMT + ":CALI")
        makeDoublePV("offsetPMT" + PMT, "GDET:FEE1:" + PMT + ":OFFS")

    getPV = "VGBA:FEE1:240:P"
    for GD in ["GD01", "GD02"]:
        makePV(GD + "PressureHi", getPV, "VFC:FEE1:" + GD + ":PHI_DES")
        makePV(GD + "PressureLo", getPV, "VFC:FEE1:" + GD + ":PLO_DES")

    electronEnergyPV = "BEND:DMP1:400:BDES"
    makePV("electronEnergyDesired", electronEnergyPV, None)
    makePV("electronEnergyCurrent", electronEnergyPV, None, getHistorical=False)

    photonEnergyPV = "SIOC:SYS0:ML00:AO627"
    makePV("photonEnergyDesired", photonEnergyPV, None)
    makePV("photonEnergyCurrent", photonEnergyPV, None, getHistorical=False)

    makeDoublePV("xcavLaunchX", "FBCK:FB01:TR03:S1DES")
    makeDoublePV("xcavLaunchY", "FBCK:FB01:TR03:S2DES")

    makeDoublePV("BC1PeakCurrent", "FBCK:FB04:LG01:S3DES")
    makeDoublePV("BC1LeftJaw", "COLL:LI21:235:MOTR.VAL")
    makeDoublePV("BC1RightJaw", "COLL:LI21:236:MOTR.VAL")

    makeDoublePV("BC2Mover", "BMLN:LI24:805:MOTR.VAL")
    makeDoublePV("BC2Phase", "SIOC:SYS0:ML00:AO063")

    makeDoublePV("amplitudeL1X", "ACCL:LI21:180:L1X_ADES")
    makeDoublePV("phaseL1X", "ACCL:LI21:180:L1X_PDES")

    makeDoublePV("amplitudeL2", "ACCL:LI22:1:ADES")
    makeDoublePV("peakCurrentL2", "FBCK:FB04:LG01:S5DES")
    makeDoublePV("phaseL2", "ACCL:LI22:1:PDES")

    makeDoublePV("amplitudeL3", "ACCL:LI25:1:ADES")
    makeDoublePV("phaseL3", "ACCL:LI25:1:PDES")

    makeDoublePV("waveplateCH1", "WPLT:IN20:459:CH1_ANGLE")
    makeDoublePV("heaterWaveplate1", "WPLT:LR20:220:LHWP_ANGLE")
    makeDoublePV("heaterWaveplate2", "WPLT:LR20:230:LHWP_ANGLE")
    makeDoublePV("waveplateVHC", "WPLT:IN20:467:VHC_ANGLE")

    makeDoublePV("pulseStackerDelay", "PSDL:LR20:117:TDES")
    makeDoublePV("pulseStackerWaveplate", "WPLT:LR20:117:PSWP_ANGLE")

    makeDoublePV("undLaunchPosX", "FBCK:FB03:TR04:S1DES")
    makeDoublePV("undLaunchAngX", "FBCK:FB03:TR04:S2DES")
    makeDoublePV("undLaunchPosY", "FBCK:FB03:TR04:S3DES")
    makeDoublePV("undLaunchAngY", "FBCK:FB03:TR04:S4DES")

    makeDoublePV("vernier", "FBCK:FB04:LG01:DL2VERNIER")

    pvPositionM3S = "STEP:FEE1:1811:MOTR.RBV"
    makePV("positionDesiredM3S", pvPositionM3S, None)
    makePV("positionCurrentM3S", pvPositionM3S, None, getHistorical=False)


def populateKeyLists(keyDict):
    keyDict["6x6"] = ["BC1PeakCurrent", "amplitudeL2", "phaseL2",
                      "peakCurrentL2", "amplitudeL3"]

    keyDict["pressure"] = ["GD01PressureHi", "GD02PressureHi", "GD01PressureLo",
                           "GD02PressureLo"]

    keyDict["BC2"] = ["BC2Mover", "BC2Phase"]

    keyDict["setpoints"] = ["xcavLaunchX", "xcavLaunchY", "heaterWaveplate1",
                            "heaterWaveplate2", "waveplateVHC", "waveplateCH1",
                            "undLaunchPosX", "undLaunchAngX", "undLaunchPosY",
                            "undLaunchAngY", "vernier", "phaseL3"]

    keyDict["pulseStacker"] = ["pulseStackerDelay", "pulseStackerWaveplate"]

    keyDict["L1X"] = ["amplitudeL1X", "phaseL1X"]

    keyDict["BC1"] = ["BC1LeftJaw", "BC1RightJaw"]

    keysPMT = []
    for PMT in ["241", "242", "361", "362"]:
        keysPMT.append("voltagePMT" + PMT)
        keysPMT.append("calibrationPMT" + PMT)
        keysPMT.append("offsetPMT" + PMT)

    keyDict["PMT"] = keysPMT


def setupCalendar(calendarWidget, timeEdit):
    timeGuiLaunched = datetime.now()
    timeGuiLaunchedStr = str(timeGuiLaunched)

    year = timeGuiLaunchedStr[0:4]
    month = timeGuiLaunchedStr[5:7]
    day = timeGuiLaunchedStr[8:10]

    dateLaunched = QDate(int(year), int(month), int(day))

    # Set current date for GUI calendar
    calendarWidget.setSelectedDate(dateLaunched)
    timeGuiLaunched = timeGuiLaunchedStr[11:16]

    # Set current time for GUI time field
    timeEdit.setTime(QTime(int(timeGuiLaunched[0:2]),
                           int(timeGuiLaunched[3:5])))


# Fancy scrolling message when user changes time/date; this is pointless
# but I like it and it makes me happy in an unhappy world
def showRollingMessage(statusText):
    message = ''
    for letter in "Press 'Get Values' to get archived values":
        message += letter
        statusText.setText(message)
        statusText.repaint()
        time.sleep(0.01)


def paintCell(tableWidget, row, column, item, brush):
    brush.setStyle(Qt.SolidPattern)
    item.setBackground(brush)
    tableWidget.setItem(row, column, item)


def addScoreTableItem(scoretable, time, comment, title, row):
    scoretable.setItem(row, 0, QTableWidgetItem(time))
    scoretable.setItem(row, 1, QTableWidgetItem(comment))
    scoretable.setItem(row, 2, QTableWidgetItem(title))


# Ripped off from Lauren Alsberg, thanks yo!
def get_hist(pv, timeStart, timeStop, *moreArgs):
    url = format_url(pv, timeStart, timeStop, *moreArgs)
    req = urlopen(url)
    jdata = load(req)
    return jdata


# noinspection PyUnusedLocal
def format_url(pv, timeStart, timeStop, *moreArgs):
    machine = 'lcls'
    applianceFormat = ('http://' + machine
                       + '-archapp.slac.stanford.edu/retrieval/data/'
                         'getData.json?pv=' + pv + '&from=' + timeStart
                       + '&to=' + timeStop + '&donotchunk')
    return applianceFormat


# give a simple number back from json data
def valFromJson(datatotranslate):
    return datatotranslate[0][u'data'][-1][u'val']


# Function to launch standardize panel
def stdz():
    Popen(['edm', '-x', '/home/physics/skalsi/edmDev/stdz.edl'])


# Function to launch SCORE gui
def score():
    Popen(['/usr/local/lcls/tools/script/HLAWrap', 'xterm', '-e',
           '/usr/local/lcls/physics/score/score.bash'])


# Function to launch model GUI
def modelMan():
    Popen(['modelMan'])
