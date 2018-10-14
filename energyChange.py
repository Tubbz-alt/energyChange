#!/usr/local/lcls/package/python/current/bin/python
# Author- Zimmer (Lil CZ)
# Editor - Lisa
# Loads scores; changes GDET Pressures, Recipes, PMT Voltages, Calibrations,
# Offsets; 6x6 stuff (including BC1 Peak Current); XCAV and Und Launch feedback
# setpoints; Laser Heater Waveplate; klystron complement; BC2 chicane mover;
# BC1 collimators BC2 phase PV (SIOC:SYS0:ML00:AO063) for different R56;
# moves mirrors; standardizes and sets vernier/L3 Phase along with UND/LTU
# feedback matrices and other things I haven't documented yet.

from sys import exit, argv
from PyQt4.QtCore import QString, QTime, QDate
from PyQt4.QtGui import QApplication, QMainWindow
from epics import caget, caput
from PyQt4 import QtCore, QtGui
from time import sleep
from datetime import datetime, timedelta
from dateutil import parser
from subprocess import Popen, PIPE
# noinspection PyCompatibility
from urllib2 import urlopen
from json import load
from threading import Thread
from pytz import utc, timezone
from message import log
from random import randint
from pyScore import Pyscore
from copy import deepcopy

from energyChange_UI import echg_UI


# Where the magic happens, the main class that runs this baby!
# noinspection PyCompatibility,PyArgumentList,PyTypeChecker
class EnergyChange(QMainWindow):
    def __init__(self, parent=None):
        QMainWindow.__init__(self, parent)
        self.cssfile = "/usr/local/lcls/tools/python/toolbox/echg/style.css"
        self.ui = echg_UI()
        self.ui.setupUi(self)
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
        
        self.gdetData = {"GD1PressureHi": None, "GD1PressureLo": None, 
                         "voltagePMT241": None, "voltagePMT242": None, 
                         "GD2PressureHi": None, "GD2PressureLo": None,
                         "voltagePMT361": None, "voltagePMT362": None,
                         "calibrationPMT241": None, "calibrationPMT242": None, 
                         "calibrationPMT361": None, "calibrationPMT362": None,
                         "offsetPMT241": None, "offsetPMT242": None, 
                         "offsetPMT361": None, "offsetPMT362": None}

        self.BC1 = {"current": None, "leftJaw": None, "rightJaw": None}
        self.BC2 = {"mover": None, "phase": None}

        self.scoreInfo = {"comments": None, "titles": None, "times": None,
                          "dateChosen": None, "timeChosen": None}

        self.electron = {"energy": None, "energyNow": None}
        self.photon = {"energy": None, "energyNow": None}

        self.klystronComplement = {"desired": {}, "original": {}}

        self.L1X = {"amplitude": None, "phase": None}
        self.L2 = {"amplitude": None, "peakCurrent": None, "phase": None}
        self.L3 = {"energy": None, "phase": None}

        self.laser = {"CH1WP": None, "LHWP1": None, "LHWP2": None,
                      "VHCWP": None, "pulseStackerDelay": None,
                      "pulseStackerWP": None}

        self.mirror = {"change": False, "hard": False, "soft": False,
                       "softSwitch": False, "AMO": False, "SXR": False}

        self.timestamp = {"requested": None, "archiveStart": None,
                          "archiveStop": None, "changeStarted": None}

        self.undLaunch = {"xPos": None, "xAng": None, "yPos": None,
                          "yAng": None}

        # valsObtained is boolean representing whether user has obtained archive
        # data for selected time.  Scoreproblem is boolean representing if
        # there was a problem loading some BDES.  Abort isn't used!?!?
        # progress keeps track of progress number (between 0 and 100)
        self.diagnostics = {"progress": 0, "valsObtained": False,
                            "scoreProblem": False}

        self.xcav = {"x": None, "y": None}

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
            self.changeEnergy()

    ########################################################################
    # Where the magic happens (user has obtained values, time to do the
    # actual change).
    ########################################################################
    def changeEnergy(self):

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

        if self.mirror["change"] or self.mirror["softSwitch"]:
            # Check to make sure that mirror gets to where it should
            self.CheckMirrors()

        self.updateProgress(100 - self.diagnostics["progress"])

        # Reinitialize button to proper state - we're done with energy
        # change!
        self.ui.startButton.setText("Get Values")

        self.printStatus()

        self.logTime()

    def checkAndStandardize(self):
        if self.ui.stdz_cb.isChecked():
            # TODO why is this relevant information?
            # sometimes archive appliance returns ridiculous # of digits-
            # i.e. 3.440000000000000013 instead of 3.44
            energyDiff = self.electron["energyNow"] - self.electron["energy"]

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

    def printStatus(self):

        # Everything went fine- woohoo!
        if not self.diagnostics["scoreProblem"]:
            self.printStatusMessage("DONE- remember CAMs!")

        # If there was some problem loading scores, inform the user.
        else:
            self.printStatusMessage("DONE - problem loading scores, SEE XTERM")

    def implementSelectedChanges(self):
        if self.ui.stopper_cb.isChecked():
            # Insert stoppers and disable feedback
            self.DisableFB()

        # Set mirrors immediately so they can start moving as they take
        # time (will check mirrors at end of calling function using
        # self.CheckMirrors)
        if self.mirror["change"] or self.mirror["softSwitch"]:
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

        energyDiff = (self.electron["energyNow"] - self.electron["energy"])

        if (energyDiff > 0 and self.ui.stdz_cb.isChecked()
                and energyDiff > 0.005):
            self.printStatusMessage("<b>I will standardize!!!</b>", False)

        self.ui.startButton.setText("Start the change!")

        self.ui.statusText.setText("Will switch to "
                                   + str(round(self.photon["energy"], 1))
                                   + "eV ("
                                   + str(round(self.electron["energy"], 2))
                                   + "GeV)")

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
        chosendate = self.ui.calendarWidget.selectedDate()

        chosenday = str(chosendate.day())
        chosenmonth = str(chosendate.month())
        chosenyear = str(chosendate.year())

        chosentime = self.ui.timeEdit.time()
        chosenhour = str(chosentime.hour())

        # Get selected date/time from GUI
        chosenminute = str(chosentime.minute())

        # Add zeroes to keep formatting consistent (i.e. 0135 for time
        # instead of 135)
        if len(str(chosenhour)) == 1:
            chosenhour = '0' + chosenhour
        if len(str(chosenminute)) == 1:
            chosenminute = '0' + chosenminute
        if len(str(chosenmonth)) == 1:
            chosenmonth = '0' + chosenmonth
        if len(str(chosenday)) == 1:
            chosenday = '0' + chosenday

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
            photonEnergyText = str(self.ui.PhotonEnergyEdit.text())
            electronEnergyText = str(self.ui.ElectronEnergyEdit.text())

            if photonEnergyText:
                if int(self.ui.PhotonEnergyEdit.text()) < 350:
                    self.ui.PhotonEnergyEdit.setText('350')

                scoreData = self.filterScores(photonEnergyText + "eV",
                                              "color: rgb(100,255,100)",
                                              "color: red", 300, fourWeeksBack,
                                              end, columnLst)

                self.ui.ElectronEnergyEdit.setText('')

            elif electronEnergyText:
                scoreData = self.filterScores(electronEnergyText + "eV",
                                              "color: red",
                                              "color: rgb(100,255,100)", 0.5,
                                              fourWeeksBack, end, columnLst)

            else:
                scoreData = self.filterScores(None, "color: red", "color: red",
                                              None, fourWeeksBack, end,
                                              columnLst)

        except:
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

    def PopulateScoreTable(self):
        for i in xrange(0, len(self.scoreInfo["times"])):
            try:
                item = QtGui.QTableWidgetItem()
                item.setText(str(self.scoreInfo["times"][i]))
                self.ui.scoretable.setItem(i, 0, item)
                item = QtGui.QTableWidgetItem()
                item.setText(self.scoreInfo["comments"][i])
                self.ui.scoretable.setItem(i, 1, item)
                item = QtGui.QTableWidgetItem()
                item.setText(self.scoreInfo["titles"][i])
                self.ui.scoretable.setItem(i, 2, item)

            # A safety if there is some mismatch among titles/comments/times
            # returned from score API and processed by this GUI (e.g. not the
            # same total number of each)
            except:
                self.ScoreTableProblem()

    # Notify user that reading database had problem; set time/date manually
    def ScoreTableProblem(self):
        self.ui.scoretable.clearContents()
        item = QtGui.QTableWidgetItem()
        item.setText('Problem reading scores.')
        self.ui.scoretable.setItem(0, 0, item)
        item = QtGui.QTableWidgetItem()
        item.setText('Set date/time manually!')
        self.ui.scoretable.setItem(0, 1, item)

    # Pull time from score config that was clicked and set gui date/time
    def setScoreTime(self):
        self.ui.scoretable.repaint()
        QApplication.processEvents()
        rows = sorted(set(index.row()
                          for index
                          in self.ui.scoretable.selectedIndexes()))

        if len(rows) == 0:
            return

        if len(rows) > 1:
            self.ui.statusText.setText("Select one row only dummy!")

        r = rows[0]
        try:
            time = self.scoreInfo["times"][r]

        # User clicked a blank cell, stop here
        except IndexError:
            return

        # Split string into date and time
        time = str(time).split()
        year = str(time[0].split('-')[0])
        month = str(time[0].split('-')[1])
        day = str(time[0].split('-')[2])
        calendaradj = QDate(int(year), int(month), int(day))
        self.ui.calendarWidget.setSelectedDate(calendaradj)
        self.ui.timeEdit.setTime(QTime(int(time[1][:2]), int(time[1][3:5])))

    # give a simple number back from json data
    @staticmethod
    def ValfromJson(datatotranslate):
        return datatotranslate[0][u'data'][-1][u'val']

    # Get current/desired electron and photon energies
    def GetEnergy(self):
        self.photon["energyNow"] = caget('SIOC:SYS0:ML00:AO627')

        self.photon["energy"] = self.get_hist('SIOC:SYS0:ML00:AO627',
                                              self.timestamp["archiveStart"],
                                              self.timestamp["archiveStop"],
                                              'json')

        self.photon["energy"] = self.ValfromJson(self.photon["energy"])
        self.electron["energyNow"] = caget('BEND:DMP1:400:BDES')

        self.electron["energy"] = self.get_hist('BEND:DMP1:400:BDES',
                                                self.timestamp["archiveStart"],
                                                self.timestamp["archiveStop"],
                                                'json')

        self.electron["energy"] = self.ValfromJson(self.electron["energy"])
        self.updateProgress(10)

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "Current Electron Energy:"
                                   + str(self.electron["energyNow"]))

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "Current Photon Energy:"
                                   + str(self.photon["energyNow"]))

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "Desired Electron Energy"
                                   + str(self.electron["energy"]))

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "Desired Photon Energy:"
                                   + str(self.photon["energy"]))

    # Get important 6x6 parameters from time of interest
    def Get6x6(self):
        QApplication.processEvents()
        self.BC1["current"] = self.get_hist('FBCK:FB04:LG01:S3DES',
                                            self.timestamp["archiveStart"],
                                            self.timestamp["archiveStop"],
                                            'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "BC1 IPk:"
                                   + str(self.ValfromJson(self.BC1["current"])))

        self.L2["amplitude"] = self.get_hist('ACCL:LI22:1:ADES',
                                             self.timestamp["archiveStart"],
                                             self.timestamp["archiveStop"],
                                             'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "L2 Ampl:"
                                   + str(
            self.ValfromJson(self.L2["amplitude"])))

        self.L2["phase"] = self.get_hist('ACCL:LI22:1:PDES',
                                         self.timestamp["archiveStart"],
                                         self.timestamp["archiveStop"], 'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "L2 Phase:"
                                   + str(self.ValfromJson(self.L2["phase"])))

        self.L2["peakCurrent"] = self.get_hist('FBCK:FB04:LG01:S5DES',
                                               self.timestamp["archiveStart"],
                                               self.timestamp["archiveStop"],
                                               'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "L2 IPk:"
                                   + str(
            self.ValfromJson(self.L2["peakCurrent"])))

        self.L3["energy"] = self.get_hist('ACCL:LI25:1:ADES',
                                          self.timestamp["archiveStart"],
                                          self.timestamp["archiveStop"], 'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "L3 Energy:"
                                   + str(self.ValfromJson(self.L3["energy"])))
        self.updateProgress(10)

    # Get klystron complement from time of interest
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
                    isOnBeam = self.ValfromJson(klysStatus)
                    stations[station] = isOnBeam
                    item = QtGui.QTableWidgetItem()

                    if isOnBeam:
                        # If station on, make light green
                        brush = QtGui.QBrush(QtGui.QColor(100, 255, 100))
                    else:
                        brush = QtGui.QBrush(QtGui.QColor(255, 0, 0))

                    brush.setStyle(QtCore.Qt.SolidPattern)
                    item.setBackground(brush)
                    self.ui.tableWidget.setItem(station - 1, sector - 21,  item)
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
                self.getHistFromArchiveTime('GDET:FEE1:' + PMT + ':CALI',
                                            "calibration" + PMT)
                self.getHistFromArchiveTime('GDET:FEE1:' + PMT + ':OFFS',
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
            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> "
                                       + "Problem retrieving gas detector PVs; "
                                         "will not change pressures/recipe/"
                                         "voltages/calibration/offset")

            print ('Problem retrieving gas detector PVs; possible photon '
                   'appliance issue.  Will NOT change '
                   'pressure/recipe/voltages/calibration/offset')

            self.ui.pressure_cb.setChecked(False)
            self.ui.pressure_cb.setDisabled(True)
            self.ui.recipe_cb.setChecked(False)
            self.ui.recipe_cb.setDisabled(True)
            self.ui.pmt_cb.setChecked(False)
            self.ui.pmt_cb.setDisabled(True)
            self.updateProgress(10)

    def getHistFromArchiveTime(self, pv, setpoint):
        hist = self.get_hist(pv, self.timestamp["archiveStart"],
                             self.timestamp["archiveStop"], 'json')
        self.gdetData[setpoint] = hist
        return hist

    def getPressureSetpoints(self):

        def getAndLogPressure(pv, setpoint):
            hist = self.getHistFromArchiveTime(pv, setpoint)
            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> " + setpoint
                                       + str(self.ValfromJson(hist)))

        getAndLogPressure('VGBA:FEE1:240:P', "GD1PressureHi")
        getAndLogPressure('VGBA:FEE1:240:P', "GD1PressureLo")
        getAndLogPressure('VGBA:FEE1:360:P', "GD2PressureHi")
        getAndLogPressure('VGBA:FEE1:360:P', "GD2PressureLo")

        for PMT in ["241", "242", "361", "362"]:
            getAndLogPressure('HVCH:FEE1:' + PMT + ':VoltageSet',
                              "voltagePMT" + PMT)

    # Random setpoints we also want to load.  Grab them from archive appliance
    def GetSetpoints(self):

        self.xcav["x"] = self.get_hist('FBCK:FB01:TR03:S1DES',
                                       self.timestamp["archiveStart"],
                                       self.timestamp["archiveStop"], 'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "Xcav X Setpoint:"
                                   + str(self.ValfromJson(self.xcav["x"])))

        self.xcav["y"] = self.get_hist('FBCK:FB01:TR03:S2DES',
                                       self.timestamp["archiveStart"],
                                       self.timestamp["archiveStop"], 'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "Xcav Y Setpoint:"
                                   + str(self.ValfromJson(self.xcav["y"])))

        try:
            self.laser["LHWP1"] = self.get_hist('WPLT:LR20:220:LHWP_ANGLE',
                                                self.timestamp[
                                                    "archiveStart"],
                                                self.timestamp["archiveStop"],
                                                'json')

            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> " + "LH Waveplate 1:"
                                       + str(
                self.ValfromJson(self.laser["LHWP1"])))

            self.laser["LHWP2"] = self.get_hist('WPLT:LR20:230:LHWP_ANGLE',
                                                self.timestamp[
                                                    "archiveStart"],
                                                self.timestamp["archiveStop"],
                                                'json')

            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> " + "LH Waveplate 2:"
                                       + str(
                self.ValfromJson(self.laser["LHWP2"])))

        except:
            print 'Could not retrieve heater waveplate values, will not load'
            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> "
                                       + 'Could not retrieve heater '
                                         'waveplate(s), will not set')

        self.laser["VHCWP"] = self.get_hist('WPLT:IN20:467:VHC_ANGLE',
                                            self.timestamp["archiveStart"],
                                            self.timestamp["archiveStop"],
                                            'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "VHC Waveplate:"
                                   + str(self.ValfromJson(self.laser["VHCWP"])))

        self.laser["CH1WP"] = self.get_hist('WPLT:IN20:459:CH1_ANGLE',
                                            self.timestamp["archiveStart"],
                                            self.timestamp["archiveStop"],
                                            'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "CH1 Waveplate:"
                                   + str(
            self.ValfromJson(self.laser["CH1WP"])))

        self.undLaunch["xPos"] = self.get_hist('FBCK:FB03:TR04:S1DES',
                                               self.timestamp["archiveStart"],
                                               self.timestamp["archiveStop"],
                                               'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "Und Launch X Setpoint:"
                                   + str(
            self.ValfromJson(self.undLaunch["xPos"])))

        self.undLaunch["xAng"] = self.get_hist('FBCK:FB03:TR04:S2DES',
                                               self.timestamp["archiveStart"],
                                               self.timestamp["archiveStop"],
                                               'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "Und Launch X' Setpoint:"
                                   + str(
            self.ValfromJson(self.undLaunch["xAng"])))

        self.undLaunch["yPos"] = self.get_hist('FBCK:FB03:TR04:S3DES',
                                               self.timestamp["archiveStart"],
                                               self.timestamp["archiveStop"],
                                               'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "Und Launch Y Setpoint:"
                                   + str(
            self.ValfromJson(self.undLaunch["yPos"])))

        self.undLaunch["yAng"] = self.get_hist('FBCK:FB03:TR04:S4DES',
                                               self.timestamp["archiveStart"],
                                               self.timestamp["archiveStop"],
                                               'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "Und Launch Y' Setpoint:"
                                   + str(
            self.ValfromJson(self.undLaunch["yAng"])))

        self.vernier = self.get_hist('FBCK:FB04:LG01:DL2VERNIER',
                                     self.timestamp["archiveStart"],
                                     self.timestamp["archiveStop"], 'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "Vernier:"
                                   + str(self.ValfromJson(self.vernier)))

        self.L3["phase"] = self.get_hist('ACCL:LI25:1:PDES',
                                         self.timestamp["archiveStart"],
                                         self.timestamp["archiveStop"], 'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "L3 Phase:"
                                   + str(self.ValfromJson(self.L3["phase"])))

        self.L1X["amplitude"] = self.get_hist('ACCL:LI21:180:L1X_ADES',
                                              self.timestamp["archiveStart"],
                                              self.timestamp["archiveStop"],
                                              'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "L1X Amp:"
                                   + str(
            self.ValfromJson(self.L1X["amplitude"])))

        self.L1X["phase"] = self.get_hist('ACCL:LI21:180:L1X_PDES',
                                          self.timestamp["archiveStart"],
                                          self.timestamp["archiveStop"], 'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "L1X Phase:"
                                   + str(self.ValfromJson(self.L1X["phase"])))

        self.laser["pulseStackerDelay"] = self.get_hist('PSDL:LR20:117:TDES',
                                                        self.timestamp[
                                                            "archiveStart"],
                                                        self.timestamp[
                                                            "archiveStop"],
                                                        'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "Stacker Delay:"
                                   + str(
            self.ValfromJson(self.laser["pulseStackerDelay"])))

        self.laser["pulseStackerWP"] = self.get_hist('WPLT:LR20:117:PSWP_ANGLE',
                                                     self.timestamp[
                                                         "archiveStart"],
                                                     self.timestamp[
                                                         "archiveStop"], 'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "Stacker Wavepl:"
                                   + str(
            self.ValfromJson(self.laser["pulseStackerWP"])))

        self.BC1["leftJaw"] = self.get_hist('COLL:LI21:235:MOTR.VAL',
                                            self.timestamp["archiveStart"],
                                            self.timestamp["archiveStop"],
                                            'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "BC1 left jaw:"
                                   + str(self.ValfromJson(self.BC1["leftJaw"])))

        self.BC1["rightJaw"] = self.get_hist('COLL:LI21:236:MOTR.VAL',
                                             self.timestamp["archiveStart"],
                                             self.timestamp["archiveStop"],
                                             'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "BC1 right jaw:"
                                   + str(
            self.ValfromJson(self.BC1["rightJaw"])))

    # Get chicane mover value and phase value
    def GetBC2Mover(self):
        self.BC2["mover"] = self.get_hist('BMLN:LI24:805:MOTR.VAL',
                                          self.timestamp["archiveStart"],
                                          self.timestamp["archiveStop"], 'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "BC2 Mover Pos:"
                                   + str(self.ValfromJson(self.BC2["mover"])))

        self.BC2["phase"] = self.get_hist('SIOC:SYS0:ML00:AO063',
                                          self.timestamp["archiveStart"],
                                          self.timestamp["archiveStop"], 'json')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + "BC2 Phase:"
                                   + str(self.ValfromJson(self.BC2["phase"])))

    # Get mirror positions from time of interest
    def GetMirrors(self):
        # M1S change needed variable
        self.mirror["change"] = False

        # Changing M1S to hard variable
        self.mirror["hard"] = False

        # Changing M1S to soft variable
        self.mirror["soft"] = False

        # M3S change needed variable
        self.mirror["softSwitch"] = False

        # Changing M3S to AMO variable
        self.mirror["AMO"] = False

        # Changing M3S to SXR variable
        self.mirror["SXR"] = False

        # TODO maybe these were cast as floats for a reason
        if ((self.photon["energyNow"] > 2050 > self.photon["energy"])
                or (self.photon["energy"] > 2050 > self.photon["energyNow"])):

            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> "
                                       + 'Soft/Hard mirror change needed')
            self.mirror["change"] = True

            if float(self.photon["energy"]) > 2050:
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> "
                                           + 'Will change M1 mirror to Hard')
                self.mirror["hard"] = True

            else:
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> "
                                           + 'Will change M1 mirror to Soft')
                self.mirror["soft"] = True

        try:
            # TODO what does it mean to have a pass first thing in a try?
            pass
            M3SposThen = self.get_hist('STEP:FEE1:1811:MOTR.RBV',
                                       self.timestamp["archiveStart"],
                                       self.timestamp["archiveStop"], 'json')
            M3SposThen = self.ValfromJson(M3SposThen)

        except:
            # Channel archiver issues crop up from time to time
            print ('Could not determine M3 position at requested time (Archive '
                   'Appliance error).  Soft mirror will NOT be changed.')

            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> "
                                       + 'M3 movement disabled; problem '
                                         'retrieving position from archive '
                                         'appliance')
            self.mirror["softSwitch"] = False
            self.ui.m3_cb.setChecked(False)
            self.ui.m3_cb.setDisabled(True)
            self.updateProgress(10)
            return

        self.ui.m3_cb.setDisabled(False)
        M3SposNow = caget('STEP:FEE1:1811:MOTR.RBV')

        try:
            # TODO maybe these were also cast as floats for a reason
            if (M3SposThen > 0) and (M3SposNow < 0):
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> "
                                           + 'M3 will be changed to provide '
                                             'beam to AMO (unless beam will be '
                                             'going down hard line)')
                self.mirror["softSwitch"], self.mirror["AMO"] = True, True

            if M3SposThen < 0 and (M3SposNow > 0):
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> "
                                           + 'M3 will be changed to provide '
                                             'beam to SXR (unless beam will be '
                                             'going down hard line)')
                self.mirror["softSwitch"], self.mirror["SXR"] = True, True

        except TypeError:
            # Channel archiver issues crop up from time to time
            print ('Could not determine M3 position at requested time (Archive '
                   'Appliance error).  Soft mirror will NOT be changed.')

            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> "
                                       + 'M3 movement disabled; problem '
                                         'retrieving position from archive '
                                         'appliance')
            self.mirror["softSwitch"] = False
            self.ui.m3_cb.setChecked(False)
            self.ui.m3_cb.setDisabled(True)

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

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + 'Stoppers inserted and feedbacks disabled')

    # Load scores for selected region(s). Use threading to speed things up
    # (calls ScoreThread function which is defined below)
    def LoadScores(self):
        self.ui.textBrowser.append('<i>' + str(datetime.now())[11:19]
                                   + "-</i> " + 'Loading Scores...')

        QApplication.processEvents()
        self.ui.textBrowser.repaint()

        self.thread_list = []
        regionlist = []

        if self.ui.injector_cb.isChecked():
            regionlist.append('"Gun to TD11-LEM"')

        if self.ui.score_cb.isChecked():
            regionlist.extend(('"Cu Linac-LEM"', '"Hard BSY thru LTUH-LEM"'))

        if self.ui.taper_cb.isChecked():
            regionlist.extend(('"Undulator Taper"', '"Undulator-LEM"'))

        # Put message in message log that scores are being loaded
        log("facility=pythonenergychange Loading SCORE from "
            + self.scoreInfo["dateChosen"] + " " + self.scoreInfo["timeChosen"]
            + " for regions " + ", ".join(regionlist))

        for region in regionlist:
            # Have a thread subclass to handle this (defined at bottom of this
            # file); normal threading class returns NONE
            t = ThreadWithReturnValue(target=self.ScoreThread,
                                      args=(region,))
            self.thread_list.append(t)

        for thread in self.thread_list:
            thread.start()

    def CheckScoreLoads(self):
        try:
            for thread in self.thread_list:
                # I want to wait for each thread to finish execution so the
                # score completion/failure messages come out together
                # TODO what does join return?
                status, region = thread.join()
                if status[-8:-1] == 'SUCCESS':
                    self.ui.textBrowser.append("<i>"
                                               + str(datetime.now())[11:19]
                                               + "-</i> "
                                               + 'Set/trimmed devices for '
                                               + region)
                else:
                    self.ui.textBrowser.append("<i>"
                                               + str(datetime.now())[11:19]
                                               + "-</i> " + 'Error loading '
                                               + region + ' region (see xterm)')
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
        # TODO I can change this to a method call, but I have no idea what the
        # status should be IT CAN BE WHATEVER I WANT
        command = ('/usr/local/lcls/tools/python/toolbox/echg/'
                   'score_load_oracle.py ' + region + ' '
                   + self.scoreInfo["dateChosen"] + ' '
                   + self.scoreInfo["timeChosen"] + ':00')

        runloadscript = Popen(command, shell=True, stdout=PIPE)
        status = runloadscript.communicate()[0]
        return status, region

    # Check that bend dump has finished trimming and then start standardize
    def StdzMags(self):
        # Set LTU region to be standardized
        caput('SIOC:SYS0:ML01:AO405', '1')

        # NO L3,L2,L1,L0 STDZ.  Also, don't include QMs to Design and don't
        # include UND to Matched Design
        regions = ['SIOC:SYS0:ML01:AO404', 'SIOC:SYS0:ML01:AO403',
                   'SIOC:SYS0:ML01:AO402', 'SIOC:SYS0:ML01:AO401',
                   'SIOC:SYS0:ML01:AO065',
                   'SIOC:SYS0:ML01:AO064']

        for region in regions:
            caput(region, '0')

        status = caget('BEND:DMP1:400:CTRL')
        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + 'Waiting for BEND:DMP1:400:CTRL to read '
                                     '"Ready"...')

        # Simple loop to wait for this supply to finish trimming (this supply
        # takes longest; how kalsi determines when to start stdz)
        while status != 0:
            status = caget('BEND:DMP1:400:CTRL')
            QApplication.processEvents()
            sleep(0.2)

        # Paranoid sleep, sometimes one of the BSY quads wasn't standardizing
        sleep(3)

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + 'Starting STDZ')

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

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + 'Setting 6x6 Parameters and LTU/UND '
                                     'feedback matrices')

        caput('FBCK:FB04:LG01:STATE', '0')
        caput('FBCK:FB04:LG01:S3DES', self.ValfromJson(self.BC1["current"]))
        caput('ACCL:LI22:1:ADES', self.ValfromJson(self.L2["amplitude"]))
        caput('ACCL:LI22:1:PDES', self.ValfromJson(self.L2["phase"]))
        caput('FBCK:FB04:LG01:S5DES', self.ValfromJson(self.L2["peakCurrent"]))
        caput('ACCL:LI25:1:ADES', self.ValfromJson(self.L3["energy"]))
        sleep(.2)
        caput('FBCK:FB04:LG01:STATE', '1')

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + 'Setting 6x6 complete')

    def SetAllTheSetpoints(self):
        if self.ui.matrices_cb.isChecked():
            command = ('/usr/local/lcls/tools/python/toolbox/echg/'
                       'matrices_load.py ' + self.scoreInfo["dateChosen"] + ' '
                       + self.scoreInfo["timeChosen"] + ':00')

            # Load matrices and stop/start feedbacks
            Popen(command, shell=True)
            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> "
                                       + 'Sent LTU/UND matrices to feedbacks '
                                         'and stopped/started')

        # Set BC2 chicane mover and phase (magnet strength is set in
        # LoadScores())
        if self.ui.BC2_cb.isChecked():
            self.SetBC2Mover()

        # Set feedback setpoints, laser heater, L3 phase, laser heater camera
        # waveplates, vernier etc.
        if self.ui.setpoints_cb.isChecked():
            self.SetSetpoints()

        if self.ui.pstack_cb.isChecked():
            caput('PSDL:LR20:117:TDES',
                  self.ValfromJson(self.laser["pulseStackerDelay"]))
            caput('WPLT:LR20:117:PSWP_ANGLE',
                  self.ValfromJson(self.laser["pulseStackerWP"]))
            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> "
                                       + 'Set pulse stacker delay and '
                                         'waveplate')

        if self.ui.l1x_cb.isChecked():
            caput('ACCL:LI21:180:L1X_ADES',
                  self.ValfromJson(self.L1X["amplitude"]))
            caput('ACCL:LI21:180:L1X_PDES', self.ValfromJson(self.L1X["phase"]))
            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> "
                                       + 'Set L1X phase and amplitude')

        if self.ui.bc1coll_cb.isChecked():
            caput('COLL:LI21:235:MOTR.VAL',
                  self.ValfromJson(self.BC1["leftJaw"]))
            caput('COLL:LI21:236:MOTR.VAL',
                  self.ValfromJson(self.BC1["rightJaw"]))
            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> " + 'Set BC1 collimators')

    # Set mirrors to desired positions
    def SetMirrors(self):
        QApplication.processEvents()

        # M1S switching to hard position, don't care about M3S
        if self.mirror["hard"] & self.ui.m1_cb.isChecked():
            caput('MIRR:FEE1:1560:LOCK', '1')
            sleep(.3)
            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> " + 'Setting M1 for Hard')
            caput('MIRR:FEE1:1561:MOVE', '1')

        # M1S switching to soft position, M3S switch not needed
        elif (self.mirror["soft"] & (not self.mirror["softSwitch"])
              & self.ui.m1_cb.isChecked()):

            caput('MIRR:FEE1:1560:LOCK', '1')
            sleep(.3)
            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> " + 'Setting M1 for Soft')
            caput('MIRR:FEE1:0561:MOVE', '1')

        # M1S switching to soft position, M3S switch needed
        elif (self.mirror["soft"] & self.mirror["softSwitch"]
              & (self.ui.m1_cb.isChecked() or self.ui.m3_cb.isChecked())):

            caput('MIRR:FEE1:1560:LOCK', '1')
            caput('MIRR:FEE1:1810:LOCK', '1')
            sleep(.3)

            if self.mirror["SXR"]:
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> "
                                           + 'Setting M1 for Soft and/or M3 '
                                             'for SXR (depending on your '
                                             'selection)')

                if self.ui.m1_cb.isChecked():
                    self.ui.textBrowser.append("<i>"
                                               + str(datetime.now())[11:19]
                                               + "-</i> "
                                               + 'Setting M1 for Soft')
                    caput('MIRR:FEE1:0561:MOVE', '1')

                if self.ui.m3_cb.isChecked():
                    self.ui.textBrowser.append("<i>"
                                               + str(datetime.now())[11:19]
                                               + "-</i> "
                                               + 'Setting M3 for SXR')
                    caput('MIRR:FEE1:2811:MOVE', '1')

            if self.mirror["AMO"]:
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> "
                                           + 'Setting M1 for Soft and/or M3 '
                                             'for AMO (depending on your '
                                             'selection)')

                if self.ui.m1_cb.isChecked():
                    self.ui.textBrowser.append("<i>"
                                               + str(datetime.now())[11:19]
                                               + "-</i> "
                                               + 'Setting M1 for Soft')
                    caput('MIRR:FEE1:0561:MOVE', '1')

                if self.ui.m3_cb.isChecked():
                    self.ui.textBrowser.append("<i>"
                                               + str(datetime.now())[11:19]
                                               + "-</i> "
                                               + 'Setting M3 for AMO')
                    caput('MIRR:FEE1:1811:MOVE', '1')

        # M1S mirror change not needed, M3S mirror was in different position,
        # going to an energy where we care about M3S position (i.e. beam is
        # going that way as we are staying with soft x-rays)
        elif ((not self.mirror["soft"]) & (not self.mirror["hard"]) &
              self.mirror["softSwitch"]
              & (self.photon["energyNow"] < 2050) & self.ui.m3_cb.isChecked()):
            caput('MIRR:FEE1:1810:LOCK', '1')
            sleep(.3)
            if self.mirror["SXR"]:
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> " + 'Setting M3 for SXR')

                caput('MIRR:FEE1:2811:MOVE', '1')

                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> "
                                           + 'Checking M3 Position for SXR...')
            if self.mirror["AMO"]:
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> " + 'Setting M3 for AMO')

                caput('MIRR:FEE1:1811:MOVE', '1')

                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> "
                                           + 'Checking M3 Position for AMO...')

    # Check that mirrors reach their desired positions
    def CheckMirrors(self):
        QApplication.processEvents()
        waiting = True
        # M1S switching to hard position, don't care about M3S
        if self.mirror["hard"] & self.ui.m1_cb.isChecked():
            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> "
                                       + 'Checking M1 Mirror Position for '
                                         'Hard...')

            while waiting:
                QApplication.processEvents()
                sleep(1)
                position = caget('MIRR:FEE1:1561:POSITION')

                if position == 1:
                    self.ui.textBrowser.append("<i>"
                                               + str(datetime.now())[11:19]
                                               + "-</i> "
                                               + 'Detected M1 Mirror in Hard '
                                                 'Position')
                    waiting = False

            caput('MIRR:FEE1:1560:LOCK', '0')

        # M1S switching to soft position, M3S switch not needed
        elif self.mirror["soft"] & (
                not self.mirror["softSwitch"]) & self.ui.m1_cb.isChecked():

            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> "
                                       + 'Checking M1 Mirror Position for '
                                         'Soft...')
            while waiting:
                QApplication.processEvents()
                sleep(1)
                position = caget('MIRR:FEE1:0561:POSITION')

                if position == 1:
                    self.ui.textBrowser.append("<i>"
                                               + str(datetime.now())[11:19]
                                               + "-</i> "
                                               + 'Detected M1 Mirror in Soft '
                                                 'Position')
                    waiting = False

            caput('MIRR:FEE1:1560:LOCK', '0')

        # M1S switching to soft position, M3S switch needed
        elif (self.mirror["soft"] & self.mirror["softSwitch"]
              & (self.ui.m1_cb.isChecked() or self.ui.m3_cb.isChecked())):

            if self.mirror["SXR"]:
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> "
                                           + 'Waiting for mirror(s)...')
                while waiting:
                    QApplication.processEvents()
                    sleep(1)
                    M1Sposition = caget('MIRR:FEE1:0561:POSITION')
                    M3Sposition = caget('MIRR:FEE1:2811:POSITION')

                    if ((M1Sposition == 1) & (M3Sposition == 1)
                            & self.ui.m1_cb.isChecked()
                            & self.ui.m3_cb.isChecked()):
                        self.ui.textBrowser.append("<i>"
                                                   + str(datetime.now())[11:19]
                                                   + "-</i> "
                                                   + 'Detected M1 Mirror in '
                                                     'Soft Position, M3 in SXR '
                                                     'position')
                        waiting = False

                    elif ((M1Sposition == 1) & self.ui.m1_cb.isChecked()
                          & (not self.ui.m3_cb.isChecked())):
                        self.ui.textBrowser.append("<i>"
                                                   + str(datetime.now())[11:19]
                                                   + "-</i> "
                                                   + 'Detected M1 Mirror in '
                                                     'Soft Position')
                        waiting = False

                    elif ((M3Sposition == 1) & self.ui.m3_cb.isChecked()
                          & (not self.ui.m1_cb.isChecked())):
                        self.ui.textBrowser.append("<i>"
                                                   + str(datetime.now())[11:19]
                                                   + "-</i> "
                                                   + 'Detected M3 Mirror in '
                                                     'SXR Position')
                        waiting = False

            if self.mirror["AMO"]:
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> "
                                           + 'Waiting for mirror(s)...')
                while waiting:
                    QApplication.processEvents()
                    sleep(1)
                    M1Sposition = caget('MIRR:FEE1:0561:POSITION')
                    M3Sposition = caget('MIRR:FEE1:1811:POSITION')

                    if (M1Sposition == 1) & (M3Sposition == 1):
                        self.ui.textBrowser.append("<i>"
                                                   + str(datetime.now())[11:19]
                                                   + "-</i> "
                                                   + 'Detected M1 Mirror in '
                                                     'Soft Position, M3 in '
                                                     'AMO position')
                        waiting = False

                    elif ((M1Sposition == 1) & self.ui.m1_cb.isChecked()
                          & (not self.ui.m3_cb.isChecked())):
                        self.ui.textBrowser.append("<i>"
                                                   + str(datetime.now())[11:19]
                                                   + "-</i> "
                                                   + 'Detected M1 Mirror in '
                                                     'Soft Position')
                        waiting = False

                    elif ((M3Sposition == 1) & self.ui.m3_cb.isChecked()
                          & (not self.ui.m1_cb.isChecked())):
                        self.ui.textBrowser.append("<i>"
                                                   + str(datetime.now())[11:19]
                                                   + "-</i> "
                                                   + 'Detected M3 Mirror in '
                                                     'AMO Position')
                        waiting = False

            caput('MIRR:FEE1:1560:LOCK', '0')
            caput('MIRR:FEE1:1810:LOCK', '0')

        # M1S mirror change not needed, M3S mirror was in different position,
        # going to an energy where we care about M3S position (i.e. beam is
        # going that way as we are staying with soft x-rays)
        elif ((not self.mirror["soft"]) & (not self.mirror["hard"]) &
              self.mirror["softSwitch"]
              & (self.photon["energyNow"] < 2050) & self.ui.m3_cb.isChecked()):

            if self.mirror["SXR"]:
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> "
                                           + 'Checking M3 Position for SXR...')
                while waiting:
                    QApplication.processEvents()
                    sleep(1)
                    M3Sposition = caget('MIRR:FEE1:2811:POSITION')
                    if M3Sposition == 1:
                        self.ui.textBrowser.append("<i>"
                                                   + str(datetime.now())[11:19]
                                                   + "-</i> "
                                                   + 'Detected M3 in SXR '
                                                     'position')
                        waiting = False

            if self.mirror["AMO"]:
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> "
                                           + 'Checking M3 Position for AMO...')
                while waiting:
                    QApplication.processEvents()
                    sleep(1)
                    M3Sposition = caget('MIRR:FEE1:1811:POSITION')
                    if M3Sposition == 1:
                        self.ui.textBrowser.append("<i>"
                                                   + str(datetime.now())[11:19]
                                                   + "-</i> "
                                                   + 'Detected M3S in AMO '
                                                     'position')
                        waiting = False

            caput('MIRR:FEE1:1810:LOCK', '0')

    # Score loading should set Magnet to proper value, this will set chicane
    # mover and chicane phase which makes sure R56 is right.
    def SetBC2Mover(self):
        BC2MoverNow = caget('BMLN:LI24:805:MOTR.VAL')
        BC2PhaseNow = caget('SIOC:SYS0:ML00:AO063')

        if (BC2MoverNow == self.ValfromJson(self.BC2["mover"])
                and BC2PhaseNow == self.ValfromJson(self.BC2["phase"])):
            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> "
                                       + 'BC2 Mover/Phase look the same, '
                                         'not sending values')

            # No need to load them since they are the same
            return

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + 'Setting BC2 Mover and Phase')

        caput('BMLN:LI24:805:MOTR.VAL', self.ValfromJson(self.BC2["mover"]))
        caput('SIOC:SYS0:ML00:AO063', self.ValfromJson(self.BC2["phase"]))

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + 'Set BC2 Mover and Phase')

    # Set random setpoints (xcav, und launch, lhwp etc.)
    def SetSetpoints(self):
        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + 'Setting Xcav, LHWP, Und Launch, L3P and '
                                     'vernier')

        caput('FBCK:FB01:TR03:S1DES', self.ValfromJson(self.xcav["x"]))
        caput('FBCK:FB01:TR03:S2DES', self.ValfromJson(self.xcav["y"]))

        try:
            caput('WPLT:LR20:220:LHWP_ANGLE',
                  self.ValfromJson(self.laser["LHWP1"]))
            caput('WPLT:LR20:230:LHWP_ANGLE',
                  self.ValfromJson(self.laser["LHWP2"]))

        except:
            print 'Unable to set heater waveplate(s)'
            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> "
                                       + 'Unable to set heater power'
                                         ' waveplates')

        caput('WPLT:IN20:467:VHC_ANGLE', self.ValfromJson(self.laser["VHCWP"]))
        caput('WPLT:IN20:459:CH1_ANGLE',
              self.ValfromJson(self.laser["CH1WP"]))
        caput('FBCK:FB03:TR04:S1DES', self.ValfromJson(self.undLaunch["xPos"]))
        caput('FBCK:FB03:TR04:S2DES', self.ValfromJson(self.undLaunch["xAng"]))
        caput('FBCK:FB03:TR04:S3DES', self.ValfromJson(self.undLaunch["yPos"]))
        caput('FBCK:FB03:TR04:S4DES', self.ValfromJson(self.undLaunch["yAng"]))
        caput('FBCK:FB04:LG01:DL2VERNIER', self.ValfromJson(self.vernier))
        caput('ACCL:LI25:1:PDES', self.ValfromJson(self.L3["phase"]))

        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19] + "-</i> "
                                   + 'Set Xcav, LHWP, Und Launch, L3 Phase and '
                                     'Vernier')

    ############################################################################
    # HHHHHHHHHIIIIIIIIIIIIIIIIIIIIII
    # ZIIIIIMMMMMMMMMMMMMMMMMMMMMMMEEEEEEEEERRRRRRRRRRRRRRRRRRRRRRRR
    ############################################################################

    # Set gas detector recipe/pressure and pmt voltages
    def SetGdet(self):
        def caputGdetData(pv, key):
            caput(pv, self.ValfromJson(self.gdetData[key]))

        if self.ui.pmt_cb.isChecked():
            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> "
                                       + 'Setting PMT voltages/Calibration/'
                                         'Offset')
            QApplication.processEvents()

            for PMT in ["241", "242", "361", "362"]:
                caputGdetData('HVCH:FEE1:' + PMT + ':VoltageSet',
                              "voltagePMT" + PMT)

                caputGdetData('GDET:FEE1:' + PMT + ':CALI',
                              "calibrationPMT" + PMT)

                caputGdetData('GDET:FEE1:' + PMT + ':OFFS', "offsetPMT" + PMT)

            self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                       + "-</i> "
                                       + 'Set PMT voltages/Calibration/Offset')

        self.setPressuresForHardMirrorChange()
        self.setPressuresForSoftMirrorChange()

        # No recipe change needed, not switching between hard/soft xrays
        if not self.mirror["change"]:
            if self.ui.pressure_cb.isChecked():
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> " + 'Setting pressures')
                QApplication.processEvents()
                caputGdetData('VFC:FEE1:GD01:PLO_DES', "GD1PressureLo")
                caputGdetData('VFC:FEE1:GD02:PLO_DES', "GD2PressureLo")
                caputGdetData('VFC:FEE1:GD01:PHI_DES', "GD1PressureHi")
                caputGdetData('VFC:FEE1:GD02:PHI_DES', "GD2PressureHi")

    def setPressuresForSoftMirrorChange(self):
        # Mirror change to soft setting
        if self.mirror["change"] and self.mirror["soft"]:
            if self.ui.recipe_cb.isChecked():
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> "
                                           + 'Changing recipe from high to low')
                QApplication.processEvents()
                caput('VFC:FEE1:GD01:PHI_DES', '0')
                caput('VFC:FEE1:GD02:PHI_DES', '0')
                sleep(14)
                caput('VFC:FEE1:GD01:RECIPE_DES', '4')
                caput('VFC:FEE1:GD02:RECIPE_DES', '4')
                sleep(1.5)

            if self.ui.pressure_cb.isChecked():
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> " + 'Setting pressures')
                QApplication.processEvents()
                caput('VFC:FEE1:GD01:PLO_DES',
                      self.ValfromJson(self.gdetData["GD1PressureLo"]))
                caput('VFC:FEE1:GD02:PLO_DES',
                      self.ValfromJson(self.gdetData["GD2PressureLo"]))

    def setPressuresForHardMirrorChange(self):
        # Mirror change required, and changing to hard xray setting; or somehow
        # are running hard xrays with low recipe (has happened and then OPS
        # thinks there is no FEL)
        if ((self.mirror["change"] and self.mirror["hard"])
                or ((self.photon["energy"] > 2050)
                    and (caget('VFC:FEE1:GD01:RECIPE_DES') == 4))):

            if self.ui.recipe_cb.isChecked():
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> "
                                           + 'Changing recipe from low to high')
                QApplication.processEvents()
                caput('VFC:FEE1:GD01:RECIPE_DES', '3')
                caput('VFC:FEE1:GD02:RECIPE_DES', '3')
                sleep(1.5)

            if self.ui.pressure_cb.isChecked():
                self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                           + "-</i> " + 'Setting pressures')
                QApplication.processEvents()
                caput('VFC:FEE1:GD01:PLO_DES', 0.0)
                caput('VFC:FEE1:GD02:PLO_DES', 0.0)
                caput('VFC:FEE1:GD01:PHI_DES',
                      self.ValfromJson(self.gdetData["GD1PressureHi"]))
                caput('VFC:FEE1:GD02:PHI_DES',
                      self.ValfromJson(self.gdetData["GD2PressureHi"]))

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
