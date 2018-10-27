import time
from os import popen
from epics import caget, caput

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
