#!/usr/local/lcls/package/python/current/bin/python
# Author- Zimmer (Lil CZ), Editor - Lisa
# Loads scores; changes GDET Pressures, Recipes, PMT Voltages, Calibrations,
# Offsets; 6x6 stuff (including BC1 Peak Current); XCAV and Und Launch feedback
# setpoints; Laser Heater Waveplate; klystron complement; BC2 chicane mover;
# BC1 collimators BC2 phase PV (SIOC:SYS0:ML00:AO063) for different R56;
# moves mirrors; standardizes and sets vernier/L3 Phase along with UND/LTU
# feedback matrices and other things I haven't documented yet.

from sys import exit, argv
from PyQt4.QtCore import QTime, QDate, QString
from PyQt4.QtGui import QApplication, QMainWindow
from epics import caget, caput
from PyQt4 import QtCore, QtGui
from time import sleep
from datetime import datetime, timedelta
from dateutil import parser
from subprocess import Popen
# noinspection PyCompatibility
from urllib2 import urlopen
from json import load
from threading import Thread
from pytz import utc, timezone
from message import log
from random import randint
from pyScore import Pyscore
from copy import deepcopy
from loadScore import setDevices
from loadMatrices import setMatricesAndRestartFeedbacks

from energyChange_UI import echg_UI

ENERGY_BOUNDARY = 2050

# Where the magic happens, the main class that runs this baby!
# noinspection PyCompatibility,PyArgumentList,PyTypeChecker
class EnergyChange(QMainWindow):
    def __init__(self, parent=None):
        QMainWindow.__init__(self, parent)
        self.cssfile = "/usr/local/lcls/tools/python/toolbox/echg/style.css"
        self.ui = echg_UI()
        self.ui.setupUi(self)
        self.ui.scoretable.setSelectionMode(QtGui.QAbstractItemView
                                            .SingleSelection)
        self.setWindowTitle('Energy Change!')

        # Blank out 24-7 with 3 lines on klystron complement table (it doesn't
        # exist!)
        item = QtGui.QTableWidgetItem()
        item.setText('---')
        self.ui.tableWidget.setItem(6, 3, item)

        self.ui.textBrowser.append('Energy Change Initialized.  Pick a time.')

        # Button for restoring klystron complement as found in archiver;
        # want disabled initially as nothing has been loaded yet
        self.ui.restoreButton.setDisabled(True)

        timeGuiLaunched = datetime.now()
        timeGuiLaunchedStr = str(timeGuiLaunched)

        year = timeGuiLaunchedStr[0:4]
        month = timeGuiLaunchedStr[5:7]
        day = timeGuiLaunchedStr[8:10]

        calendaradj = QDate(int(year), int(month), int(day))

        # Set current date for GUI calendar
        self.ui.calendarWidget.setSelectedDate(calendaradj)

        timeGuiLaunched = timeGuiLaunchedStr[11:16]

        # Set current time for GUI time field
        self.ui.timeEdit.setTime(QTime(int(timeGuiLaunched[0:2]),
                                       int(timeGuiLaunched[3:5])))

        # Instatiate Tony's python score class
        self.scoreObject = Pyscore()

        greetings = ["Hi! Aren't you the cutest lil thing!",
                     "Hiiii!  I've missed you beautiful! <3",
                     "Came crawling back, eh?  Of course you did.",
                     "Finally decided to do your job huh?",
                     "Hey Hey Hey! I missed you!",
                     "I knew you'd be back.  I'm so excited!",
                     "I love you- your smile is the reason I launch!",
                     "Hi sunshine, you light up my life!",
                     "I love turtles.  But I hate baby turtles.",
                     "Energy change- getting you loaded since 2014",
                     "Don't ever change.  That's my job!",
                     "For a failure, you sure seem chipper!",
                     "It's sad that this is the highlight of your day.",
                     "Can't wait for FACET 2...",
                     "You're special and people like you!",
                     "Master beats me if I'm a bad GUI :-(",
                     "You can do anything!  Reach for the stars!",
                     "You're a capable human who does stuff!",
                     "You excel at simple tasks!  Yeah!",
                     "If I were more than a GUI you'd make me blush!",
                     "Delivering to CXrs or MC?  Whatever who cares.",
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
                     "Oh look at you!  You're precious!",
                     "You excel at mediocrity!",
                     "Regret any of your life decisions yet?",
                     "I thought you were quitting?!?",
                     "Rick Perry is our new boss! Yay!",
                     "Kissy face kissy face I love you!", "Didn't you quit?",
                     "You rock at watching numbers!", "Kill me please!!!",
                     "Don't go for your dreams, you will fail!",
                     "You're the reason the gene pool needs a lifeguard!",
                     "Do you still love nature, despite what it did to you?",
                     "Ordinary people live and learn.  You just live.",
                     "Way to be physically present for 8 hours!  Yeah!",
                     "Hello, Clarice..."]

        self.ui.statusText.setText(greetings[randint(0, 45)])
        self.loadStyleSheet()

        self.setpoint = {"GD1PressureHi": None, "GD1PressureLo": None,
                         "voltagePMT241": None, "voltagePMT242": None,
                         "GD2PressureHi": None, "GD2PressureLo": None,
                         "voltagePMT361": None, "voltagePMT362": None,
                         "calibrationPMT241": None, "calibrationPMT242": None,
                         "calibrationPMT361": None, "calibrationPMT362": None,
                         "offsetPMT241": None, "offsetPMT242": None,
                         "offsetPMT361": None, "offsetPMT362": None,
                         "electronEnergyDesired": None,
                         "electronEnergyNow": None,
                         "photonEnergyDesired": None, "photonEnergyNow": None,
                         "xcavLaunchX": None, "xcavLaunchY": None,
                         "BC1PeakCurrent": None, "BC1LeftJaw": None,
                         "BC1RightJaw": None, "BC2Mover": None,
                         "BC2Phase": None, "amplitudeL1X": None,
                         "phaseL1X": None, "amplitudeL2": None,
                         "peakCurrentL2": None, "phaseL2": None,
                         "energyL3": None, "phaseL3": None,
                         "waveplateCH1": None, "heaterWaveplate1": None,
                         "heaterWaveplate2": None, "waveplateVHC": None,
                         "pulseStackerDelay": None,
                         "pulseStackerWaveplate": None, "undLaunchPosX": None,
                         "undLaunchPosY": None, "undLaunchAngX": None,
                         "undLaunchAngY": None, "vernier": None}

        self.scoreInfo = {"comments": None, "titles": None, "times": None,
                          "dateChosen": None, "timeChosen": None}

        self.klystronComplement = {"desired": {}, "original": {}}

        self.mirror = {"needToChangeM1": False, "hardPositionNeeded": False, 
                       "softPositionNeeded": False,
                       "needToChangeM3": False, "amoPositionNeeded": False,
                       "sxrPositionNeeded": False}

        self.timestamp = {"requested": None, "archiveStart": None,
                          "archiveStop": None, "changeStarted": None}

        # valsObtained is boolean representing whether user has obtained archive
        # data for selected time.  Scoreproblem is boolean representing if
        # there was a problem loading some BDES.  Abort isn't used!?!?
        # progress keeps track of progress number (between 0 and 100)
        self.diagnostics = {"progress": 0, "valsObtained": False,
                            "scoreProblem": False, "threads": []}

        # Set progress bar to zero on GUI opening
        self.ui.progbar.setValue(0)

        # Get list of recent configs and populate GUI score table
        self.GetScores()
        self.MakeConnections()

    # Connect GUI elements to functions
    def MakeConnections(self):
        self.ui.startButton.clicked.connect(self.Start)

        # Opens STDZ GUI
        self.ui.stdzButton.clicked.connect(self.Stdz)

        # Opens SCORE GUI
        self.ui.scoreButton.clicked.connect(self.Score)

        # Opens Model Manager GUI
        self.ui.modelButton.clicked.connect(self.ModelMan)

        # Restores displayed complement to archived complement
        self.ui.restoreButton.clicked.connect(self.RestoreComp)

        # reinitButton grabs score configs from selected time -14days and
        # updates config list with configs that are found
        self.ui.reinitButton.clicked.connect(self.GetScores)

        # If user selects new date, go back to initial mode in order to gather
        # new archive data for new date
        self.ui.calendarWidget.clicked.connect(self.UserChange)

        # Same if user changes time
        self.ui.timeEdit.timeChanged.connect(self.UserChange)

        # Set klytron table non-editable
        self.ui.tableWidget.setEditTriggers(
            QtGui.QAbstractItemView.NoEditTriggers)

        # Set klystron table so that user can't highlight items
        self.ui.tableWidget.setSelectionMode(
            QtGui.QAbstractItemView.NoSelection)

        self.ui.scoretable.setEditTriggers(
            QtGui.QAbstractItemView.NoEditTriggers)

        # If user clicks score table, update GUI with correct date/time
        self.ui.scoretable.itemSelectionChanged.connect(self.setScoreTime)

        # Handle user clicking stations to change complement
        self.ui.tableWidget.cellClicked.connect(self.changeComp)

        self.ui.PhotonEnergyEdit.returnPressed.connect(self.GetScores)
        self.ui.ElectronEnergyEdit.returnPressed.connect(self.GetScores)

    # Make gui SO PRETTY!
    def loadStyleSheet(self):
        try:
            with open(self.cssfile, "r") as f:
                self.setStyleSheet(f.read())

        # If my file disappears for some reason, load crappy black color scheme
        except IOError:
            print 'No style sheet found!'
            palette = QtGui.QPalette()
            brush = QtGui.QBrush(QtGui.QColor(0, 0, 0))
            brush.setStyle(QtCore.Qt.SolidPattern)
            palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.Text, brush)
            brush = QtGui.QBrush(QtGui.QColor(0, 0, 0))
            brush.setStyle(QtCore.Qt.SolidPattern)
            palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.Text,
                             brush)
            self.ui.textBrowser.setPalette(palette)

    # Fancy scrolling message when user changes time/date; this is pointless
    # but I like it and it makes me happy in an unhappy world
    def showMessage(self):
        message = ''
        for letter in "Press 'Get Values' to get archived values":
            message += letter
            self.ui.statusText.setText(message)
            self.ui.statusText.repaint()
            sleep(0.01)

    # Function that is called when user presses main button (button could say
    # 'get values' or 'start the change' depending on what state GUI is in)
    def Start(self):

        # valsObtained variable is used to tell if user has gotten archived
        # values from a certain time yet.  This section simply grabs values and
        # doesn't change anything (runs when button says 'get values')
        if not self.diagnostics["valsObtained"]:
            return self.getValues()

        else:
            return
            self.changeEnergy()

    ########################################################################
    # Where the magic happens (user has obtained values, time to do the
    # actual change).
    ########################################################################
    def changeEnergy(self):
        return

        self.setupUiAndDiagnostics()
        self.implementSelectedChanges()

        # Set gas detector recipe/pressures/PMTs: conditional statements
        # are contained in function (e.g. user doesn't want PMTs set)
        self.SetGdet()
        self.updateProgress(5)
        self.SetAllTheSetpoints()
        self.updateProgress(10)

        # Get results of score load, make sure it worked
        self.CheckScoreLoads()

        self.checkAndStandardize()

        if self.mirror["needToChangeM1"] or self.mirror["needToChangeM3"]:
            # Check to make sure that mirror gets to where it should
            self.CheckMirrors()

        self.updateProgress(100 - self.diagnostics["progress"])

        # Reinitialize button to proper state - we're done with energy
        # change!
        self.ui.startButton.setText("Get Values")

        # Everything went fine- woohoo!
        if not self.diagnostics["scoreProblem"]:
            self.printStatusMessage("DONE- remember CAMs!")

        # If there was some problem loading scores, inform the user.
        else:
            self.printStatusMessage("DONE - problem loading scores, SEE XTERM")

        self.logTime()

    def checkAndStandardize(self):
        if self.ui.stdz_cb.isChecked():
            # TODO why is this relevant information?
            # sometimes archive appliance returns ridiculous # of digits-
            # i.e. 3.440000000000000013 instead of 3.44
            energyDiff = (self.setpoint["electronEnergyNow"]
                          - self.setpoint["electronEnergyDesired"])

            if energyDiff > 0.005 and not self.diagnostics["scoreProblem"]:
                # Standardize magnets if going down in energy and there
                # wasn't some problem loading scores
                self.StdzMags()

            if energyDiff > 0 and self.diagnostics["scoreProblem"]:
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> "
                                           + "Skipping STDZ- problem "
                                             "loading scores")

    def logTime(self):
        try:
            # Time logging
            curtime = datetime.now()
            elapsed = curtime - self.timestamp["changeStarted"]
            old_value = caget('SIOC:SYS0:ML03:AO707')
            caput('SIOC:SYS0:ML03:AO707', old_value + elapsed.total_seconds())

            # Write textBrowser text to a file so I can diagnose the basics
            # when something goes wrong
            fh = open("/home/physics/zimmerc/python/echg_log.txt", "a")

            curtime = datetime.now()
            # Include time GUI was run and what score config was loaded
            fh.write("\n\n" + self.scoreInfo["dateChosen"] + " " +
                     self.scoreInfo["timeChosen"] + "\n"
                     + str(curtime)[0:10] + " " + str(curtime)[11:16] + "\n"
                     + self.ui.textBrowser.toPlainText())

            fh.close()

        except:
            print 'problem with time logging or log writing'

    def printStatusMessage(self, message, printToStatus=True):
        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                   + "-</i> " + message)
        if printToStatus:
            self.ui.statusText.setText(message)

    def implementSelectedChanges(self):
        if self.ui.stopper_cb.isChecked():
            # Insert stoppers and disable feedback
            self.DisableFB()

        # Set mirrors immediately so they can start moving as they take
        # time (will check mirrors at end of calling function using
        # self.CheckMirrors)
        if self.mirror["needToChangeM1"] or self.mirror["needToChangeM3"]:
            self.SetMirrors()

        self.updateProgress(10)

        # Load scores if user wants
        if (self.ui.score_cb.isChecked() or self.ui.injector_cb.isChecked()
                or self.ui.taper_cb.isChecked()):
            self.LoadScores()

        else:
            # TODO this doesn't seem to be done in LoadScores...
            # Add progress to progress bar; this is done in LoadScores but
            # needs to be done here if no scores are loaded
            self.updateProgress(35)

        if self.ui.klystron_cb.isChecked():
            # Set klystron complement
            self.SetKlys()

        else:
            # Make up missing progress if klystrons are not set by this GUI
            self.updateProgress(25)

        if self.ui.fast6x6_cb.isChecked():
            # Set 6x6 parameters and feedback matrices
            self.Set6x6()
            self.updateProgress(5)

    def updateProgress(self, increment):
        self.diagnostics["progress"] += increment
        self.ui.progbar.setValue(self.diagnostics["progress"])

    def setupUiAndDiagnostics(self):
        # for time logging
        self.timestamp["changeStarted"] = datetime.now()

        # Variable to determine if there was some sort of problem loading
        # scores; should be false every time we start a change
        self.diagnostics["scoreProblem"] = False

        self.printStatusMessage("<b>Setting values...</b>", False)

        # Set to false so that the user will be in initial state after
        # energy change (in case user wants to use again)
        self.diagnostics["valsObtained"] = False

        self.ui.startButton.setText("Working...")
        self.ui.statusText.setText("Working...")

        QApplication.processEvents()

        self.ui.statusText.repaint()
        self.updateProgress(5 - self.diagnostics["progress"])

    def getValues(self):

        self.ui.restoreButton.setDisabled(True)
        self.FormatTime()

        self.printStatusMessage("<b>Getting values...</b>")
        self.updateProgress(5 - self.diagnostics["progress"])

        QApplication.processEvents()

        self.ui.statusText.repaint()
        self.GetEnergy()
        self.Get6x6()
        self.GetKlys()
        self.GetGdet()

        # Gets random setpoints- feedback setpoints, pulse stacker,
        # laser heater waveplate etc.
        self.GetSetpoints()

        self.GetBC2Mover()
        self.GetMirrors()
        self.diagnostics["valsObtained"] = True

        energyDiff = (self.setpoint["electronEnergyNow"]
                      - self.setpoint["electronEnergyDesired"])

        if (energyDiff > 0 and self.ui.stdz_cb.isChecked()
                and energyDiff > 0.005):
            self.printStatusMessage("<b>I will standardize!!!</b>", False)

        self.ui.startButton.setText("Start the change!")

        message = ("Will switch to "
                   + str(round(self.setpoint["photonEnergyDesired"], 1))
                   + "eV ("
                   + str(round(self.setpoint["electronEnergyDesired"], 2))
                   + "GeV)")

        self.ui.statusText.setText(message)

        # We have values and are ready for the energy change;
        # set this flag to True
        self.diagnostics["valsObtained"] = True
        return

    # If user clicks calendar or changes time, revert to initial state where
    # pressing button will only get archived values in preparation for energy
    # change
    def UserChange(self):

        # Reinitialize variable so the GUI will grab new data
        self.diagnostics["valsObtained"] = False

        # Reinitialize main button
        self.ui.startButton.setText('Get Values')

        # Format user time so it is ready to pass to Archiver
        self.FormatTime()

        self.updateProgress(-self.diagnostics["progress"])

        # Disable restore complement button
        self.ui.restoreButton.setDisabled(True)
        self.showMessage()
        self.ui.statusText.setText("Press 'Get Values' to get archived values")

    # Handles user click of complement table in order to juggle stations
    def changeComp(self, row, column):
        station = row + 1
        sector = column + 21

        try:
            klysStatus = self.klystronComplement["desired"][sector][station]
            item = QtGui.QTableWidgetItem()

            if klysStatus == 1:
                self.klystronComplement["desired"][sector][station] = 0
                brush = QtGui.QBrush(QtGui.QColor(255, 0, 0))
            elif klysStatus == 0:
                self.klystronComplement["desired"][sector][station] = 1
                brush = QtGui.QBrush(QtGui.QColor(100, 255, 100))

            brush.setStyle(QtCore.Qt.SolidPattern)
            item.setBackground(brush)
            self.ui.tableWidget.setItem(row, column, item)

            self.ui.restoreButton.setDisabled(False)

        # User hasn't gotten values yet, hence
        # self.klystronComplement["desired"] doesn't yet exist so just ignore
        # this error
        except AttributeError:
            print "Error changing " + str(sector) + "-" + str(station)
            pass

    # Restores original complement (the displayed complement to load will be
    # reverted to what it was from the archive)
    def RestoreComp(self):

        # Set master klystron list to be a copy of the original klystron
        # complement (this variable created in GetKlys function when archived
        # data is retrieved)
        self.klystronComplement["desired"] = \
            deepcopy(self.klystronComplement["original"])

        for sector in xrange(21, 31):
            for station in xrange(1, 9):
                klysStatus = self.klystronComplement["desired"][sector][station]
                item = QtGui.QTableWidgetItem()

                if klysStatus == 0:
                    brush = QtGui.QBrush(QtGui.QColor(255, 0, 0))
                elif klysStatus == 1:
                    brush = QtGui.QBrush(QtGui.QColor(100, 255, 100))

                brush.setStyle(QtCore.Qt.SolidPattern)
                item.setBackground(brush)
                self.ui.tableWidget.setItem(station - 1, sector - 21, item)

        self.ui.restoreButton.setDisabled(True)

    # Function to launch standardize panel
    @staticmethod
    def Stdz():
        Popen(['edm', '-x', '/home/physics/skalsi/edmDev/stdz.edl'])

    # Function to launch SCORE gui
    @staticmethod
    def Score():
        Popen(['/usr/local/lcls/tools/script/HLAWrap', 'xterm', '-e',
               '/usr/local/lcls/physics/score/score.bash'])

    # Function to launch model GUI
    @staticmethod
    def ModelMan():
        Popen(['modelMan'])

    # Take date/time from GUI and put it into format suitable for passing to
    # archiver
    def FormatTime(self):
        # Add zeroes to keep formatting consistent (i.e. 0135 for time
        # instead of 135)
        def reformat(val):
            return '0' + val if len(val) == 1 else val

        chosendate = self.ui.calendarWidget.selectedDate()

        chosenday = reformat(str(chosendate.day()))
        chosenmonth = reformat(str(chosendate.month()))
        chosenyear = str(chosendate.year())

        chosentime = self.ui.timeEdit.time()
        chosenhour = reformat(str(chosentime.hour()))

        # Get selected date/time from GUI
        chosenminute = reformat(str(chosentime.minute()))

        userchoice = (chosenyear + '-' + chosenmonth + '-' + chosenday + ' '
                      + chosenhour + ':' + chosenminute + ':00')

        self.scoreInfo["dateChosen"] = userchoice[0:10]
        self.scoreInfo["timeChosen"] = userchoice[-8:-3]

        self.timestamp["requested"] = parser.parse(userchoice)
        local = timezone("America/Los_Angeles")

        # These 5 lines to convert to UTC (for archiver);
        # also deals with DST automatically
        local_datetime = local.localize(self.timestamp["requested"],
                                        is_dst=True)

        utc_datetime = local_datetime.astimezone(utc)
        self.timestamp["archiveStart"] = (utc_datetime.replace(tzinfo=None)
                                          - timedelta(minutes=1))

        # TODO I don't know what this is
        minutes = self.timestamp["archiveStart"] + timedelta(minutes=1)
        self.timestamp["archiveStop"] = (str(datetime.isoformat(minutes))
                                         + '.000Z')

        # self.timestamp["archiveStart"] and self.timestamp["archiveStop"] are
        # the times used to grab archive data
        self.timestamp["archiveStart"] = str(datetime.isoformat(
            self.timestamp["archiveStart"])) + '.000Z'

    def filterScores(self, selectedEnergy, photonColor, electronColor,
                     delta, fourWeeksBack, end, columnLst):

        scoreData = self.scoreObject.read_dates(est_energy=selectedEnergy,
                                                edelta=delta,
                                                beg_date=fourWeeksBack,
                                                end_date=end,
                                                sample_snaps=600,
                                                columns=columnLst)

        self.ui.PhotonEnergyLabel.setStyleSheet(photonColor)
        self.ui.ElectronEnergyLabel.setStyleSheet(electronColor)
        return scoreData

    # Get recent score configs and display on gui score table
    def GetScores(self):
        self.ui.scoretable.setDisabled(False)

        # Gets selected time from GUI and puts into usable format
        self.FormatTime()

        # Clean slate!
        self.ui.scoretable.clearContents()

        fourWeeksBack = str(self.timestamp["requested"]
                            - timedelta(days=28)).split('.')[0]

        end = str(self.timestamp["requested"] + timedelta(minutes=1))
        columnLst = ["mod_dte", "config_title", "descr"]

        try:
            photonEnergyText = self.ui.PhotonEnergyEdit.text()
            electronEnergyText = self.ui.ElectronEnergyEdit.text()

            if photonEnergyText:
                photonEnergy = float(photonEnergyText)
                if photonEnergy < 350:
                    self.ui.PhotonEnergyEdit.setText('350')

                scoreData = self.filterScores(photonEnergy,
                                              "color: rgb(100,255,100)",
                                              "color: red", 300, fourWeeksBack,
                                              end, columnLst)

            elif electronEnergyText:
                scoreData = self.filterScores(float(electronEnergyText),
                                              "color: red",
                                              "color: rgb(100,255,100)", 0.5,
                                              fourWeeksBack, end, columnLst)

            else:
                scoreData = self.filterScores(None, "color: red", "color: red",
                                              None, fourWeeksBack, end,
                                              columnLst)

        except:
            print "Unable to filter SCORE's"
            self.ui.PhotonEnergyEdit.setText('')
            self.ui.ElectronEnergyEdit.setText('')
            scoreData = self.scoreObject.read_dates(beg_date=fourWeeksBack,
                                                    end_date=end,
                                                    sample_snaps=600,
                                                    columns=columnLst)

        self.scoreInfo["times"] = scoreData['MOD_DTE']
        self.scoreInfo["titles"] = scoreData['CONFIG_TITLE']
        self.scoreInfo["comments"] = scoreData['DESCR']

        self.PopulateScoreTable()

        # Make sure configs returned from SCORE don't get bungled; ensure number
        # of timestamps/comments/titles is consistent
        if (len(self.scoreInfo["times"]) != len(self.scoreInfo["comments"])
                or len(self.scoreInfo["times"]) != len(
                    self.scoreInfo["titles"])):
            self.ScoreTableProblem()

    def addScoreTableItem(self, txt, row, column):
        item = QtGui.QTableWidgetItem()
        item.setText(txt)
        self.ui.scoretable.setItem(row, column, item)

    def PopulateScoreTable(self):

        for idx, time in enumerate(self.scoreInfo["times"]):
            try:
                self.addScoreTableItem(str(time), idx, 0)
                self.addScoreTableItem(self.scoreInfo["comments"][idx], idx, 1)
                self.addScoreTableItem(self.scoreInfo["titles"][idx], idx, 2)

            # A safety if there is some mismatch among titles/comments/times
            # returned from score API and processed by this GUI (e.g. not the
            # same total number of each)
            except:
                self.ScoreTableProblem()

    # Notify user that reading database had problem; set time/date manually
    def ScoreTableProblem(self):
        self.ui.scoretable.clearContents()

        self.addScoreTableItem('Problem reading scores.', 0, 0)
        self.addScoreTableItem('Set date/time manually!', 0, 1)

    # Pull time from score config that was clicked and set gui date/time
    def setScoreTime(self):
        self.ui.scoretable.repaint()
        QApplication.processEvents()

        try:
            row = self.ui.scoretable.selectedIndexes()[0].row()
            time = self.scoreInfo["times"][row]
            # Split string into date and time
            time = str(time).split()
            date = time[0].split('-')

            year = str(date[0])
            month = str(date[1])
            day = str(date[2])

            calendaradj = QDate(int(year), int(month), int(day))

            self.ui.calendarWidget.setSelectedDate(calendaradj)
            self.ui.timeEdit.setTime(QTime(int(time[1][:2]), int(time[1][3:5])))

        # User clicked a blank cell, stop here
        except IndexError:
            self.ui.statusText.setText("Error reading selected SCORE")

    # give a simple number back from json data
    @staticmethod
    def valFromJson(datatotranslate):
        return datatotranslate[0][u'data'][-1][u'val']

    # Get current/desired electron and photon energies
    def GetEnergy(self):
        self.setpoint["photonEnergyNow"] = caget('SIOC:SYS0:ML00:AO627')
        self.getAndLogHistory('SIOC:SYS0:ML00:AO627', 'photonEnergyDesired')

        self.setpoint["electronEnergyNow"] = caget('BEND:DMP1:400:BDES')
        self.getAndLogHistory('BEND:DMP1:400:BDES', 'electronEnergyDesired')

        self.updateProgress(10)

        self.printStatusMessage("Current Electron Energy:"
                                + str(self.setpoint["electronEnergyNow"]))
        self.printStatusMessage("Current Photon Energy:"
                                + str(self.setpoint["photonEnergyNow"]))

    # Get important 6x6 parameters from time of interest
    def Get6x6(self):
        QApplication.processEvents()

        self.getAndLogHistory('FBCK:FB04:LG01:S3DES', "BC1PeakCurrent")
        self.getAndLogHistory('ACCL:LI22:1:ADES', "amplitudeL2")
        self.getAndLogHistory('ACCL:LI22:1:PDES', "phaseL2")
        self.getAndLogHistory('FBCK:FB04:LG01:S5DES', "peakCurrentL2")
        self.getAndLogHistory('ACCL:LI25:1:ADES', "energyL3")

        self.updateProgress(10)

    # Get klystron complement from time of interest
    # TODO figure out full complement PV
    # CUDKLYS:MCC0:ONBC1SUMY
    def GetKlys(self):
        QApplication.processEvents()
        self.klystronComplement["desired"] = {}
        for sector in xrange(21, 31):
            stations = {}
            for station in xrange(1, 9):
                try:
                    klysStatus = self.get_hist('KLYS:LI' + str(sector) + ':'
                                               + str(station) + '1'
                                               + ':BEAMCODE1_TCTL',
                                               self.timestamp["archiveStart"],
                                               self.timestamp["archiveStop"],
                                               'json')
                    isOnBeam = self.valFromJson(klysStatus)
                    stations[station] = isOnBeam
                    item = QtGui.QTableWidgetItem()

                    if isOnBeam:
                        # If station on, make light green
                        brush = QtGui.QBrush(QtGui.QColor(100, 255, 100))
                    else:
                        brush = QtGui.QBrush(QtGui.QColor(255, 0, 0))

                    brush.setStyle(QtCore.Qt.SolidPattern)
                    item.setBackground(brush)
                    self.ui.tableWidget.setItem(station - 1, sector - 21, item)
                except:
                    stations[station] = None

            self.klystronComplement["desired"][sector] = deepcopy(stations)
            self.updateProgress(5)

        # Copy list to have an 'original' list to revert to if user changes
        # complement and then wants to go back to original
        self.klystronComplement["original"] = \
            deepcopy(self.klystronComplement["desired"])

    # Get gas detector pressure PVs and pmt voltages from time of interest
    def GetGdet(self):
        QApplication.processEvents()
        self.updateProgress(5)
        try:
            self.getPressureSetpoints()

            self.updateProgress(5)

            for PMT in ["241", "242", "361", "362"]:
                self.getAndLogHistory('GDET:FEE1:' + PMT + ':CALI',
                                      "calibration" + PMT)
                self.getAndLogHistory('GDET:FEE1:' + PMT + ':OFFS',
                                      "offset" + PMT)

            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> "
                                       + "Got PMT calibration/offset values")
            self.updateProgress(5)
            self.ui.pressure_cb.setDisabled(False)
            self.ui.recipe_cb.setDisabled(False)
            self.ui.pmt_cb.setDisabled(False)

        except:
            # Sometimes have trouble getting gas detector stuff due to channel
            # archiver on photon side


            message = ('Problem retrieving gas detector PVs; possible photon '
                       'appliance issue.  Will NOT change '
                       'pressure/recipe/voltages/calibration/offset')

            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> " + message)
            print (message)

            self.ui.pressure_cb.setChecked(False)
            self.ui.pressure_cb.setDisabled(True)
            self.ui.recipe_cb.setChecked(False)
            self.ui.recipe_cb.setDisabled(True)
            self.ui.pmt_cb.setChecked(False)
            self.ui.pmt_cb.setDisabled(True)
            self.updateProgress(10)

    def getAndLogHistory(self, pv, key, updateSetpoint=True):
        hist = self.get_hist(pv, self.timestamp["archiveStart"],
                             self.timestamp["archiveStop"], 'json')
        hist = self.valFromJson(hist)

        if updateSetpoint:
            self.setpoint[key] = hist
            self.printStatusMessage(key + ": " + str(hist))

        return hist

    def getPressureSetpoints(self):

        self.getAndLogHistory('VGBA:FEE1:240:P', "GD1PressureHi")
        self.getAndLogHistory('VGBA:FEE1:240:P', "GD1PressureLo")
        self.getAndLogHistory('VGBA:FEE1:360:P', "GD2PressureHi")
        self.getAndLogHistory('VGBA:FEE1:360:P', "GD2PressureLo")

        for PMT in ["241", "242", "361", "362"]:
            self.getAndLogHistory('HVCH:FEE1:' + PMT + ':VoltageSet',
                                  "voltagePMT" + PMT)

    # Random setpoints we also want to load.  Grab them from archive appliance
    def GetSetpoints(self):

        self.getAndLogHistory('FBCK:FB01:TR03:S1DES', "xcavLaunchX")
        self.getAndLogHistory('FBCK:FB01:TR03:S2DES', "xcavLaunchY")

        try:
            self.getAndLogHistory('WPLT:LR20:220:LHWP_ANGLE',
                                  "heaterWaveplate1")
            self.getAndLogHistory('WPLT:LR20:230:LHWP_ANGLE',
                                  "heaterWaveplate2")

        except:
            message = ('Could not retrieve heater waveplate values, '
                       'will not load')
            print message
            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> " + message)

        self.getAndLogHistory('WPLT:IN20:467:VHC_ANGLE', "waveplateVHC")
        self.getAndLogHistory('WPLT:IN20:459:CH1_ANGLE', "waveplateCH1")

        self.getAndLogHistory('FBCK:FB03:TR04:S1DES', "undLaunchPosX")
        self.getAndLogHistory('FBCK:FB03:TR04:S2DES', "undLaunchAngX")
        self.getAndLogHistory('FBCK:FB03:TR04:S3DES', "undLaunchPosY")
        self.getAndLogHistory('FBCK:FB03:TR04:S4DES', "undLaunchAngY")

        self.getAndLogHistory('FBCK:FB04:LG01:DL2VERNIER', "vernier")

        self.getAndLogHistory('ACCL:LI25:1:PDES', "phaseL3")

        self.getAndLogHistory('ACCL:LI21:180:L1X_ADES', "amplitudeL1X")
        self.getAndLogHistory('ACCL:LI21:180:L1X_PDES', "phaseL1X")

        self.getAndLogHistory('PSDL:LR20:117:TDES', "pulseStackerDelay")
        self.getAndLogHistory('WPLT:LR20:117:PSWP_ANGLE',
                              "pulseStackerWaveplate")

        self.getAndLogHistory('COLL:LI21:235:MOTR.VAL', "BC1LeftJaw")
        self.getAndLogHistory('COLL:LI21:236:MOTR.VAL', "BC1RightJaw")

    # Get chicane mover value and phase value
    def GetBC2Mover(self):
        self.getAndLogHistory('BMLN:LI24:805:MOTR.VAL', "BC2Mover")
        self.getAndLogHistory('SIOC:SYS0:ML00:AO063', "BC2Phase")

    # Get mirror positions from time of interest
    def GetMirrors(self):

        goingFromHardToSoft = (self.setpoint["photonEnergyNow"]
                               > ENERGY_BOUNDARY
                               > self.setpoint["photonEnergyDesired"])

        goingFromSoftToHard = (self.setpoint["photonEnergyDesired"]
                               > ENERGY_BOUNDARY
                               > self.setpoint["photonEnergyNow"])

        self.mirror["needToChangeM1"] = (goingFromHardToSoft
                                         or goingFromSoftToHard)

        wantHardXrays = self.setpoint["photonEnergyDesired"] > ENERGY_BOUNDARY

        self.mirror["hardPositionNeeded"] = wantHardXrays
        self.mirror["softPositionNeeded"] = not wantHardXrays

        if self.mirror["needToChangeM1"]:
            self.printStatusMessage('Soft/Hard mirror change needed')

            if self.mirror["hardPositionNeeded"]:
                self.printStatusMessage('Will change M1 mirror to Hard')

            else:
                self.printStatusMessage('Will change M1 mirror to Soft')

        try:
            positionDesiredM3S = self.getAndLogHistory('STEP:FEE1:1811:MOTR.RBV',
                                                       None, False)

        except:
            # Channel archiver issues crop up from time to time
            message = ('Could not determine M3 position at requested time '
                       '(Archive Appliance error). Soft mirror will NOT be '
                       'changed.')
            print message
            self.printStatusMessage(message)

            self.mirror["needToChangeM3"] = False
            self.ui.m3_cb.setChecked(False)
            self.ui.m3_cb.setDisabled(True)
            self.updateProgress(10)
            return

        self.ui.m3_cb.setDisabled(False)
        positionNowM3S = caget('STEP:FEE1:1811:MOTR.RBV')

        # The setpoints are 4501um for AMO and -4503um for SXR
        self.mirror["amoPositionNeeded"] = positionDesiredM3S > 0

        if self.mirror["softPositionNeeded"]:
            txt = ("<P><FONT COLOR='#FFF'>Select desired soft x-ray hutch"
                   "</FONT></P>")
            desiredSoftHutch = QtGui.QMessageBox.question(self,
                                                          "Hutch Selector", txt,
                                                          "AMO", "SXR")
            if desiredSoftHutch == 0:
                self.mirror["amoPositionNeeded"] = True
                positionDesiredM3S = 4501
            else:
                positionDesiredM3S = -4503

        self.mirror["sxrPositionNeeded"] = not self.mirror["amoPositionNeeded"]

        goingFromSXRToAMO = positionDesiredM3S > 0 > positionNowM3S
        goingFromAMOToSXR = positionDesiredM3S < 0 < positionNowM3S

        self.mirror["needToChangeM3"] = goingFromSXRToAMO or goingFromAMOToSXR

        if goingFromSXRToAMO:
            self.printStatusMessage('M3 will be changed to provide beam to '
                                    'AMO (unless beam will be going down '
                                    'hard line)')

        if goingFromAMOToSXR:
            self.printStatusMessage('M3 will be changed to provide beam to '
                                    'SXR (unless beam will be going down '
                                    'hard line)')

        self.updateProgress(10)

    # Disable BC2 longitudinal, DL2 energy, transverse feedbacks downstream of
    # XCAV
    def DisableFB(self):
        QApplication.processEvents()

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + 'Inserting stoppers, disabling feedbacks')

        if self.ui.fast6x6_cb.isChecked():
            caput('FBCK:FB04:LG01:STATE', '0')

        if self.ui.injector_cb.isChecked():
            caput('IOC:BSY0:MP01:MSHUTCTL', '0')

        pvs = ['DUMP:LI21:305:TD11_PNEU', 'IOC:BSY0:MP01:BYKIKCTL',
               'DUMP:LTU1:970:TDUND_PNEU', 'FBCK:FB04:LG01:S4USED',
               'FBCK:FB04:LG01:S5USED', 'FBCK:FB04:LG01:S6USED',
               'FBCK:FB01:TR04:MODE', 'FBCK:FB01:TR05:MODE',
               'FBCK:FB03:TR04:MODE', 'FBCK:L2L0:1:ENABLE',
               'FBCK:FB02:TR01:MODE', 'FBCK:FB02:TR02:MODE',
               'FBCK:FB02:TR03:MODE', 'FBCK:FB03:TR01:MODE',
               'FBCK:UND0:1:ENABLE']

        for pv in pvs:
            # Insert stoppers
            caput(pv, '0')

        self.printStatusMessage('Stoppers inserted and feedbacks disabled')

    # Load scores for selected region(s). Use threading to speed things up
    # (calls ScoreThread function which is defined below)
    def LoadScores(self):
        self.printStatusMessage('Loading Scores...')

        QApplication.processEvents()
        self.ui.textBrowser.repaint()

        self.diagnostics["threads"] = []
        regionList = []

        if self.ui.injector_cb.isChecked():
            regionList.append('"Gun to TD11-LEM"')

        if self.ui.score_cb.isChecked():
            regionList.extend(('"Cu Linac-LEM"', '"Hard BSY thru LTUH-LEM"'))

        if self.ui.taper_cb.isChecked():
            regionList.extend(('"Undulator Taper"', '"Undulator-LEM"'))

        # Put message in message log that scores are being loaded
        log("facility=pythonenergychange Loading SCORE from "
            + self.scoreInfo["dateChosen"] + " " + self.scoreInfo["timeChosen"]
            + " for regions " + ", ".join(regionList))

        for region in regionList:
            # Have a thread subclass to handle this (defined at bottom of this
            # file); normal threading class returns NONE
            t = ThreadWithReturnValue(target=self.ScoreThread, args=(region,))
            self.diagnostics["threads"].append(t)

        for thread in self.diagnostics["threads"]:
            thread.start()

    def CheckScoreLoads(self):
        try:
            for thread in self.diagnostics["threads"]:
                # I want to wait for each thread to finish execution so the
                # score completion/failure messages come out together
                # TODO what does join return?
                status, region = thread.join()
                if status[-8:-1] == 0:
                    self.printStatusMessage('Set/trimmed devices for ' + region)
                else:
                    self.printStatusMessage('Error loading ' + region
                                            + ' region (see xterm)')
                    print status

                    # This flags the program to inform the user at end of change
                    #  that there was a problem
                    self.diagnostics["scoreProblem"] = True

                QApplication.processEvents()
                self.updateProgress(35)

        # User doesn't want scores loaded
        except AttributeError:
            self.updateProgress(35)

    # Thread function for loading each individual score region
    def ScoreThread(self, region):
        data = self.scoreObject.read_pvs(region, self.scoreInfo["dateChosen"],
                                         self.scoreInfo["timeChosen"] + ':00')
        return len(setDevices(region, data)), region

    # Check that bend dump has finished trimming and then start standardize
    def StdzMags(self):
        # Set LTU region to be standardized
        caput('SIOC:SYS0:ML01:AO405', '1')

        # NO L3,L2,L1,L0 STDZ.  Also, don't include QMs to Design and don't
        # include UND to Matched Design
        regions = ['SIOC:SYS0:ML01:AO404', 'SIOC:SYS0:ML01:AO403',
                   'SIOC:SYS0:ML01:AO402', 'SIOC:SYS0:ML01:AO401',
                   'SIOC:SYS0:ML01:AO065', 'SIOC:SYS0:ML01:AO064']

        for region in regions:
            caput(region, '0')

        status = caget('BEND:DMP1:400:CTRL')
        self.printStatusMessage('Waiting for BEND:DMP1:400:CTRL to read '
                                '"Ready"...')

        # Simple loop to wait for this supply to finish trimming (this supply
        # takes longest; how kalsi determines when to start stdz)
        while status != 0:
            status = caget('BEND:DMP1:400:CTRL')
            QApplication.processEvents()
            sleep(0.2)

        # Paranoid sleep, sometimes one of the BSY quads wasn't standardizing
        sleep(3)

        self.printStatusMessage('Starting STDZ')

        # Was QUAD:BSY0:1, 28 before BSY reconfig. Weren't in LEM. Unsure if
        # new devices will be.
        for bsyquad in ['QUAD:CLTH:140:CTRL', 'QUAD:CLTH:170:CTRL']:
            caput(bsyquad, '9')

        Popen('StripTool /u1/lcls/tools/StripTool/config/byd_by1_stdz.stp &',
              shell=True)

        # STDZ to LEM command through LEMServer
        caput('SIOC:SYS0:ML01:AO143', '3')

    # Set klystron complement to archived values (or user selection if user
    # changed GUI complement map- in which case
    # self.klystronComplement["desired"] was updated at the time they made the
    # changes)
    def SetKlys(self):
        QApplication.processEvents()
        self.printStatusMessage('Imma do the klystron complement')

        for sector in xrange(21, 31):
            for station in xrange(1, 9):
                klysStatus = self.klystronComplement["desired"][sector][station]
                if klysStatus is not None:
                    caput('KLYS:LI' + str(sector) + ':' + str(station) + '1'
                          + ':BEAMCODE1_TCTL', klysStatus)

        self.printStatusMessage('Done messing with klystrons')
        self.updateProgress(25)

    # Sets 6x6 feedback and also loads matrices for LTU(fast only; slow not in
    # score) and UND(fast+slow) feedbacks
    def Set6x6(self):

        self.printStatusMessage('Setting 6x6 Parameters and LTU/UND '
                                'feedback matrices')

        caput('FBCK:FB04:LG01:STATE', '0')

        caput('FBCK:FB04:LG01:S3DES', self.setpoint["BC1PeakCurrent"])

        caput('ACCL:LI22:1:ADES', self.setpoint["amplitudeL2"])

        caput('ACCL:LI22:1:PDES', self.setpoint["phaseL2"])

        caput('FBCK:FB04:LG01:S5DES', self.setpoint["peakCurrentL2"])

        caput('ACCL:LI25:1:ADES', self.setpoint["energyL3"])

        sleep(.2)

        caput('FBCK:FB04:LG01:STATE', '1')

        self.printStatusMessage('Setting 6x6 complete')

    def SetAllTheSetpoints(self):
        if self.ui.matrices_cb.isChecked():
            data = self.scoreObject.read_pvs("Feedback-All",
                                             self.scoreInfo["dateChosen"],
                                             self.scoreInfo["timeChosen"]
                                             + ':00')
            setMatricesAndRestartFeedbacks(data)
            self.printStatusMessage('Sent LTU/UND matrices to feedbacks and '
                                    'stopped/started')

        # Set BC2 chicane mover and phase (magnet strength is set in
        # LoadScores())
        if self.ui.BC2_cb.isChecked():
            self.SetBC2Mover()

        # Set feedback setpoints, laser heater, L3 phase, laser heater camera
        # waveplates, vernier etc.
        if self.ui.setpoints_cb.isChecked():
            self.SetSetpoints()

        if self.ui.pstack_cb.isChecked():
            caput('PSDL:LR20:117:TDES', self.setpoint["pulseStackerDelay"])

            caput('WPLT:LR20:117:PSWP_ANGLE',
                  self.setpoint["pulseStackerWaveplate"])

            self.printStatusMessage('Set pulse stacker delay and waveplate')

        if self.ui.l1x_cb.isChecked():
            caput('ACCL:LI21:180:L1X_ADES', self.setpoint["amplitudeL1X"])
            caput('ACCL:LI21:180:L1X_PDES', self.setpoint["phaseL1X"])
            self.printStatusMessage('Set L1X phase and amplitude')

        if self.ui.bc1coll_cb.isChecked():
            caput('COLL:LI21:235:MOTR.VAL', self.setpoint["BC1LeftJaw"])
            caput('COLL:LI21:236:MOTR.VAL', self.setpoint["BC1RightJaw"])
            self.printStatusMessage('Set BC1 collimators')

    # Set mirrors to desired positions
    def SetMirrors(self):
        QApplication.processEvents()

        caput('MIRR:FEE1:1560:LOCK', '1')
        sleep(.3)

        if self.mirror["hardPositionNeeded"]:
            if self.ui.m1_cb.isChecked():
                self.printStatusMessage('Setting M1 for Hard')
                caput('MIRR:FEE1:1561:MOVE', '1')

        elif self.mirror["softPositionNeeded"]:
            if self.ui.m1_cb.isChecked():
                self.printStatusMessage('Setting M1 for Soft')
                caput('MIRR:FEE1:0561:MOVE', '1')

            if self.ui.m3_cb.isChecked():
                caput('MIRR:FEE1:1810:LOCK', '1')
                sleep(.3)

                if self.mirror["sxrPositionNeeded"]:
                    self.printStatusMessage('Setting M3 for SXR')
                    caput('MIRR:FEE1:2811:MOVE', '1')

                elif self.mirror["amoPositionNeeded"]:
                    self.printStatusMessage('Setting M3 for AMO')
                    caput('MIRR:FEE1:1811:MOVE', '1')

    def waitForMirror(self, statusPV, lockPV, mirror, desiredPosition):
        self.printStatusMessage('Checking ' + mirror + ' Mirror Position for '
                                + desiredPosition + '...')

        while not caget(statusPV):
            QApplication.processEvents()
            sleep(1)
        self.printStatusMessage('Detected '+ mirror + ' Mirror in '
                                + desiredPosition + ' Position')
        caput(lockPV, '0')

    # Check that mirrors reach their desired positions
    def CheckMirrors(self):
        QApplication.processEvents()

        if self.mirror["hardPositionNeeded"]:
            if self.ui.m1_cb.isChecked():
                self.waitForMirror('MIRR:FEE1:1561:POSITION',
                                   'MIRR:FEE1:1560:LOCK', "M1", "Hard")

        elif self.mirror["softPositionNeeded"]:
            if self.ui.m1_cb.isChecked():
                self.waitForMirror('MIRR:FEE1:0561:POSITION',
                                   'MIRR:FEE1:1560:LOCK', "M1", "Soft")

            if self.ui.m3_cb.isChecked():
                if self.mirror["sxrPositionNeeded"]:
                    self.waitForMirror('MIRR:FEE1:2811:POSITION',
                                       'MIRR:FEE1:1810:LOCK', "M3", "SXR")

                elif self.mirror["amoPositionNeeded"]:
                    self.waitForMirror('MIRR:FEE1:1811:POSITION',
                                       'MIRR:FEE1:1810:LOCK', "M3", "AMO")

    # Score loading should set Magnet to proper value, this will set chicane
    # mover and chicane phase which makes sure R56 is right.
    def SetBC2Mover(self):
        BC2MoverNow = caget('BMLN:LI24:805:MOTR.VAL')
        BC2PhaseNow = caget('SIOC:SYS0:ML00:AO063')

        if (BC2MoverNow == self.setpoint["BC2Mover"]
                and BC2PhaseNow == self.setpoint["BC2Phase"]):
            self.printStatusMessage('BC2 Mover/Phase look the same, '
                                    'not sending values')
            return

        self.printStatusMessage('Setting BC2 Mover and Phase')

        caput('BMLN:LI24:805:MOTR.VAL', self.setpoint["BC2Mover"])
        caput('SIOC:SYS0:ML00:AO063', self.setpoint["BC2Phase"])

        self.printStatusMessage('Set BC2 Mover and Phase')

    # Set random setpoints (xcav, und launch, lhwp etc.)
    def SetSetpoints(self):
        self.printStatusMessage('Setting Xcav, LHWP, Und Launch, L3P and '
                                'vernier')

        caput('FBCK:FB01:TR03:S1DES', self.setpoint["xcavLaunchX"])
        caput('FBCK:FB01:TR03:S2DES', self.setpoint["xcavLaunchY"])

        try:
            caput('WPLT:LR20:220:LHWP_ANGLE', self.setpoint["heaterWaveplate1"])
            caput('WPLT:LR20:230:LHWP_ANGLE', self.setpoint["heaterWaveplate2"])

        except:
            print 'Unable to set heater waveplate(s)'
            self.printStatusMessage('Unable to set heater power waveplates')

        caput('WPLT:IN20:467:VHC_ANGLE', self.setpoint["waveplateVHC"])
        caput('WPLT:IN20:459:CH1_ANGLE', self.setpoint["waveplateCH1"])
        caput('FBCK:FB03:TR04:S1DES', self.setpoint["undLaunchPosX"])
        caput('FBCK:FB03:TR04:S2DES', self.setpoint["undLaunchAngX"])
        caput('FBCK:FB03:TR04:S3DES', self.setpoint["undLaunchPosY"])
        caput('FBCK:FB03:TR04:S4DES', self.setpoint["undLaunchAngY"])
        caput('FBCK:FB04:LG01:DL2VERNIER', self.setpoint["vernier"])
        caput('ACCL:LI25:1:PDES', self.setpoint["phaseL3"])

        self.printStatusMessage('Set Xcav, LHWP, Und Launch, L3 Phase and '
                                'Vernier')

    ############################################################################
    # HHHHHHHHHIIIIIIIIIIIIIIIIIIIIII
    # ZIIIIIMMMMMMMMMMMMMMMMMMMMMMMEEEEEEEEERRRRRRRRRRRRRRRRRRRRRRRR
    ############################################################################

    # Set gas detector recipe/pressure and pmt voltages
    def SetGdet(self):
        def caputSetpoint(pv, key):
            caput(pv, self.setpoint[key])

        if self.ui.pmt_cb.isChecked():
            self.printStatusMessage('Setting PMT voltages/Calibration/Offset')
            QApplication.processEvents()

            for PMT in ["241", "242", "361", "362"]:
                caputSetpoint('HVCH:FEE1:' + PMT + ':VoltageSet',
                              "voltagePMT" + PMT)

                caputSetpoint('GDET:FEE1:' + PMT + ':CALI',
                              "calibrationPMT" + PMT)

                caputSetpoint('GDET:FEE1:' + PMT + ':OFFS', "offsetPMT" + PMT)

            self.printStatusMessage('Set PMT voltages/Calibration/Offset')

        self.setPressuresForHardMirrorChange()
        self.setPressuresForSoftMirrorChange()

        # No recipe change needed, not switching between hard/soft xrays
        if not self.mirror["needToChangeM1"]:
            if self.ui.pressure_cb.isChecked():
                self.printStatusMessage('Setting pressures')
                QApplication.processEvents()

                caputSetpoint('VFC:FEE1:GD01:PLO_DES', "GD1PressureLo")
                caputSetpoint('VFC:FEE1:GD02:PLO_DES', "GD2PressureLo")
                caputSetpoint('VFC:FEE1:GD01:PHI_DES', "GD1PressureHi")
                caputSetpoint('VFC:FEE1:GD02:PHI_DES', "GD2PressureHi")

    def setPressuresForSoftMirrorChange(self):
        # Mirror change to soft setting
        if self.mirror["needToChangeM1"] and self.mirror["softPositionNeeded"]:
            if self.ui.recipe_cb.isChecked():
                self.printStatusMessage('Changing recipe from high to low')
                QApplication.processEvents()

                caput('VFC:FEE1:GD01:PHI_DES', '0')
                caput('VFC:FEE1:GD02:PHI_DES', '0')
                sleep(14)
                caput('VFC:FEE1:GD01:RECIPE_DES', '4')
                caput('VFC:FEE1:GD02:RECIPE_DES', '4')
                sleep(1.5)

            if self.ui.pressure_cb.isChecked():
                self.printStatusMessage('Setting pressures')
                QApplication.processEvents()

                caput('VFC:FEE1:GD01:PLO_DES', self.setpoint["GD1PressureLo"])
                caput('VFC:FEE1:GD02:PLO_DES', self.setpoint["GD2PressureLo"])

    def setPressuresForHardMirrorChange(self):
        # Mirror change required, and changing to hard xray setting; or somehow
        # are running hard xrays with low recipe (has happened and then OPS
        # thinks there is no FEL)
        if self.mirror["hardPositionNeeded"]:
            if self.ui.recipe_cb.isChecked():
                self.printStatusMessage('Going to high recipe')
                QApplication.processEvents()
                
                caput('VFC:FEE1:GD01:RECIPE_DES', '3')
                caput('VFC:FEE1:GD02:RECIPE_DES', '3')
                sleep(1.5)

            if self.ui.pressure_cb.isChecked():
                self.printStatusMessage('Setting pressures')
                QApplication.processEvents()

                caput('VFC:FEE1:GD01:PLO_DES', 0.0)
                caput('VFC:FEE1:GD02:PLO_DES', 0.0)

                caput('VFC:FEE1:GD01:PHI_DES', self.setpoint["GD1PressureHi"])
                caput('VFC:FEE1:GD02:PHI_DES', self.setpoint["GD2PressureHi"])

    # Ripped off from Lauren Alsberg, thanks yo!
    def get_hist(self, pv, timeStart, timeStop, *moreArgs):
        url = self.format_url(pv, timeStart, timeStop, *moreArgs)
        req = urlopen(url)
        jdata = load(req)
        return jdata

    @staticmethod
    def format_url(pv, timeStart, timeStop, *moreArgs):
        machine = 'lcls'
        applianceFormat = ('http://' + machine
                           + '-archapp.slac.stanford.edu/retrieval/data/'
                             'getData.json?pv=' + pv + '&from=' + timeStart
                           + '&to=' + timeStop + '&donotchunk')
        return applianceFormat


# Subclass to return a status from a thread (specifically the score loading
# threads).  Stupid that threading.Thread by default doesn't return a value.
class ThreadWithReturnValue(Thread):
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs={}, Verbose=None):
        Thread.__init__(self, group, target, name, args, kwargs, Verbose)
        self._return = None

    def run(self):
        if self._Thread__target is not None:
            self._return = self._Thread__target(*self._Thread__args,
                                                **self._Thread__kwargs)

    def join(self):
        Thread.join(self)
        return self._return


def main():
    app = QApplication(argv)
    window = EnergyChange()

    # Close the SCORE connection
    app.aboutToQuit.connect(window.scoreObject.exit_score)

    window.show()
    exit(app.exec_())


if __name__ == "__main__":
    main()
