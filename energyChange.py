#!/usr/local/lcls/package/python/current/bin/python
# Author- Zimmer (Lil CZ), Editor - Lisa
# Loads scores; changes GDET Pressures, Recipes, PMT Voltages, Calibrations,
# Offsets; 6x6 stuff (including BC1 Peak Current); XCAV and Und Launch feedback
# setpoints; Laser Heater Waveplate; klystron complement; BC2 chicane mover;
# BC1 collimators BC2 phase PV (SIOC:SYS0:ML00:AO063) for different R56;
# moves mirrors; standardizes and sets vernier/L3 Phase along with UND/LTU
# feedback matrices and other things I haven't documented yet.

from sys import exit, argv
from PyQt4.QtCore import QTime, QDate
from PyQt4.QtGui import QApplication, QMainWindow
from epics import caget, caput
from PyQt4 import QtCore, QtGui
from time import sleep
from datetime import datetime, timedelta
from dateutil import parser
from subprocess import Popen
from pytz import utc, timezone
from message import log
from random import randint
from pyScore import PyScore
from copy import deepcopy
from numpy import array
import energyChangeUtils as Utils

from energyChange_UI import Ui_EnergyChange


# Where the magic happens, the main class that runs this baby!
# noinspection PyCompatibility,PyArgumentList,PyTypeChecker
class EnergyChange(QMainWindow):
    def __init__(self, parent=None):
        QMainWindow.__init__(self, parent)
        self.cssFile = "style.css"
        self.ui = Ui_EnergyChange()
        self.ui.setupUi(self)
        self.ui.scoretable.setSelectionMode(QtGui.QAbstractItemView
                                            .SingleSelection)
        self.setWindowTitle('Energy Change!')

        # Blank out 24-7 with 3 lines on klystron complement table (it doesn't
        # exist!)
        item = QtGui.QTableWidgetItem()
        item.setText('---')
        self.ui.tableWidget.setItem(6, 3, item)

        self.ui.textBrowser.append('Energy Change Initialized. Pick a time.')

        # Button for restoring klystron complement as found in archiver;
        # want disabled initially as nothing has been loaded yet
        self.ui.restoreButton.setDisabled(True)

        self.setupCalendar()

        # Instatiate python score class
        self.scoreObject = PyScore()

        self.ui.statusText.setText(Utils.greetings[randint(0,
                                                           len(Utils.greetings)
                                                           - 1)])
        self.loadStyleSheet()

        self.setpoints = {}
        Utils.populateSetpoints(self.setpoints)

        self.scoreInfo = {"comments": None, "titles": None, "times": None,
                          "dateChosen": None, "timeChosen": None}

        self.klystronComplement = {"desired": {}, "original": {}}

        self.mirrorStatus = {"needToChangeM1": False,
                             "hardPositionNeeded": False,
                             "softPositionNeeded": False,
                             "needToChangeM3": False,
                             "amoPositionNeeded": False,
                             "sxrPositionNeeded": False}

        self.timestamp = {"requested": None, "archiveStart": None,
                          "archiveStop": None, "changeStarted": None}

        # valsObtained is boolean representing whether user has obtained archive
        # data for selected time. Scoreproblem is a boolean representing if
        # there was a problem loading some BDES. progress keeps track of the
        # progress number (between 0 and 100)
        self.diagnostics = {"progress": 0, "valsObtained": False,
                            "scoreProblem": False, "threads": []}

        # Set progress bar to zero on GUI opening
        self.ui.progbar.setValue(0)

        # Get list of recent configs and populate GUI score table
        self.getScores()
        self.makeConnections()
        self.ui.startButton.setEnabled(False)

    def setupCalendar(self):
        timeGuiLaunched = datetime.now()
        timeGuiLaunchedStr = str(timeGuiLaunched)

        year = timeGuiLaunchedStr[0:4]
        month = timeGuiLaunchedStr[5:7]
        day = timeGuiLaunchedStr[8:10]

        dateLaunched = QDate(int(year), int(month), int(day))

        # Set current date for GUI calendar
        self.ui.calendarWidget.setSelectedDate(dateLaunched)
        timeGuiLaunched = timeGuiLaunchedStr[11:16]

        # Set current time for GUI time field
        self.ui.timeEdit.setTime(QTime(int(timeGuiLaunched[0:2]),
                                       int(timeGuiLaunched[3:5])))

    # Make gui SO PRETTY!
    def loadStyleSheet(self):
        try:
            with open(self.cssFile, "r") as f:
                self.setStyleSheet(f.read())

        # If my file disappears for some reason, load crappy black color scheme
        except IOError:
            self.printStatusMessage('No style sheet found!')
            palette = QtGui.QPalette()
            brush = QtGui.QBrush(QtGui.QColor(0, 0, 0))
            brush.setStyle(QtCore.Qt.SolidPattern)
            palette.setBrush(QtGui.QPalette.Active, QtGui.QPalette.Text, brush)
            brush = QtGui.QBrush(QtGui.QColor(0, 0, 0))
            brush.setStyle(QtCore.Qt.SolidPattern)
            palette.setBrush(QtGui.QPalette.Inactive, QtGui.QPalette.Text,
                             brush)
            self.ui.textBrowser.setPalette(palette)

    # Get recent score configs and display on gui score table
    def getScores(self):

        self.ui.scoretable.setDisabled(False)

        # Gets selected time from GUI and puts into usable format
        self.formatTime()

        # Clean slate!
        self.ui.scoretable.clearContents()

        fourWeeksBack = str(self.timestamp["requested"]
                            - timedelta(days=28)).split('.')[0]

        end = str(self.timestamp["requested"] + timedelta(minutes=1))
        columnLst = ["mod_dte", "config_title", "descr"]

        def filterFourWeeksBack(energy, photonColor, electronColor, delta):
            return self.filterScores(energy, photonColor, electronColor, delta,
                                     fourWeeksBack, end, columnLst)

        try:
            photonEnergyText = self.ui.PhotonEnergyEdit.text()
            electronEnergyText = self.ui.ElectronEnergyEdit.text()

            if photonEnergyText:
                photonEnergy = float(photonEnergyText)

                if photonEnergy < 350:
                    self.ui.PhotonEnergyEdit.setText('350')
                    photonEnergy = 350

                scoreData = filterFourWeeksBack(photonEnergy,
                                                "color: rgb(100,255,100)",
                                                "color: red", 300)

            elif electronEnergyText:
                scoreData = filterFourWeeksBack(float(electronEnergyText),
                                                "color: red",
                                                "color: rgb(100,255,100)", 0.5)

            else:
                scoreData = filterFourWeeksBack(None, "color: red",
                                                "color: red", None)

        except:
            self.printStatusMessage("Unable to filter SCORE's")
            self.ui.PhotonEnergyEdit.setText('')
            self.ui.ElectronEnergyEdit.setText('')
            scoreData = self.scoreObject.read_dates(beg_date=fourWeeksBack,
                                                    end_date=end,
                                                    sample_snaps=600,
                                                    columns=columnLst)

        self.scoreInfo["times"] = scoreData['MOD_DTE']
        self.scoreInfo["titles"] = scoreData['CONFIG_TITLE']
        self.scoreInfo["comments"] = scoreData['DESCR']

        self.populateScoreTable()

        # Make sure configs returned from SCORE don't get bungled; ensure number
        # of timestamps/comments/titles is consistent
        if (len(self.scoreInfo["times"]) != len(self.scoreInfo["comments"])
                or len(self.scoreInfo["times"]) != len(
                    self.scoreInfo["titles"])):
            self.scoreTableProblem()

    # Take date/time from GUI and put it into format suitable for passing to
    # archiver
    def formatTime(self):
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

        timeStop = self.timestamp["archiveStart"] + timedelta(minutes=1)
        # noinspection PyCallByClass
        self.timestamp["archiveStop"] = (str(datetime.isoformat(timeStop))
                                         + '.000Z')

        # self.timestamp["archiveStart"] and self.timestamp["archiveStop"] are
        # the times used to grab archive data
        self.timestamp["archiveStart"] = str(datetime.isoformat(
            self.timestamp["archiveStart"])) + '.000Z'

    # Connect GUI elements to functions
    def makeConnections(self):
        self.ui.startButton.clicked.connect(self.start)

        # Opens STDZ GUI
        self.ui.stdzButton.clicked.connect(Utils.stdz)

        # Opens SCORE GUI
        self.ui.scoreButton.clicked.connect(Utils.score)

        # Opens Model Manager GUI
        self.ui.modelButton.clicked.connect(Utils.modelMan)

        # Restores displayed complement to archived complement
        self.ui.restoreButton.clicked.connect(self.restoreComplement)

        # reinitButton grabs score configs from selected time -28days and
        # updates config list with configs that are found
        self.ui.reinitButton.clicked.connect(self.getScores)

        # If user selects new date, go back to initial mode in order to gather
        # new archive data for new date
        self.ui.calendarWidget.clicked.connect(self.userChange)

        # Same if user changes time
        self.ui.timeEdit.timeChanged.connect(self.userChange)

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

        self.ui.PhotonEnergyEdit.returnPressed.connect(self.getScores)
        self.ui.ElectronEnergyEdit.returnPressed.connect(self.getScores)

    # Fancy scrolling message when user changes time/date; this is pointless
    # but I like it and it makes me happy in an unhappy world
    def showRollingMessage(self):
        message = ''
        for letter in "Press 'Get Values' to get archived values":
            message += letter
            self.ui.statusText.setText(message)
            self.ui.statusText.repaint()
            sleep(0.01)

    # Function that is called when user presses main button (button could say
    # 'get values' or 'start the change' depending on what state GUI is in)
    # noinspection PyCallByClass
    def start(self):

        # valsObtained variable is used to tell if user has gotten archived
        # values from a certain time yet. This section simply grabs values and
        # doesn't change anything (runs when button says 'get values')
        if not self.diagnostics["valsObtained"]:
            return self.getValues()

        else:
            # Sanity check to make sure that a change isn't started accidentally
            txt = "<P><FONT COLOR='#FFF'>Are you sure?</FONT></P>"

            reallyWantToChange = QtGui.QMessageBox.question(self,
                                                            "Sanity Check", txt,
                                                            "No", "Yes")
            if reallyWantToChange:
                self.changeEnergy()

            else:
                self.printStatusMessage("Energy change aborted")

    def printStatusMessage(self, message, printToStatus=True):
        print message
        self.ui.textBrowser.append("<i>" + str(datetime.now())[11:19]
                                   + "-</i> " + message)
        if printToStatus:
            self.ui.statusText.setText(message)

        self.ui.statusText.repaint()
        QApplication.processEvents()

    def getValues(self):

        self.ui.restoreButton.setDisabled(True)
        self.formatTime()

        self.printStatusMessage("<b>Getting values...</b>")
        # self.updateProgress(5 - self.diagnostics["progress"])

        QApplication.processEvents()

        self.ui.statusText.repaint()

        # 80 is the number of klystrons
        incrementalProgress = 100.0/(len(self.setpoints) + 80
                                     + len(self.mirrorStatus))

        for key, pvStruct in self.setpoints.iteritems():
            self.getAndLogVal(key, pvStruct,
                              getHistorical=pvStruct.historical)
            self.updateProgress(incrementalProgress)

        self.getKlys(incrementalProgress)

        self.getMirrors()
        self.updateProgress(incrementalProgress * len(self.mirrorStatus))
        self.diagnostics["valsObtained"] = True

        energyDiff = (self.setpoints["electronEnergyCurrent"].val
                      - self.setpoints["electronEnergyDesired"].val)

        if energyDiff > 0.005 and self.ui.stdz_cb.isChecked():
            self.printStatusMessage("<b>I will standardize!!!</b>", False)

        self.ui.startButton.setText("Start the change!")

        message = ("Will switch to "
                   + str(round(self.setpoints["photonEnergyDesired"].val, 1))
                   + "eV ("
                   + str(round(self.setpoints["electronEnergyDesired"].val, 2))
                   + "GeV)")

        self.printStatusMessage(message, True)

        # We have values and are ready for the energy change
        self.diagnostics["valsObtained"] = True

        return

    def updateProgress(self, increment):
        self.diagnostics["progress"] += increment
        self.ui.progbar.setValue(self.diagnostics["progress"])

    def getAndLogVal(self, key, pvStruct, getHistorical, updateSetpoint=True):
        if getHistorical:
            val = Utils.get_hist(pvStruct.getPV, self.timestamp["archiveStart"],
                                 self.timestamp["archiveStop"], 'json')
            val = Utils.valFromJson(val)
        else:
            val = caget(pvStruct.getPV)

        if updateSetpoint:
            self.setpoints[key].val = val
            self.printStatusMessage(key + ": " + str(val))

        return val

    # Get klystron complement from time of interest
    def getKlys(self, incrementalProgress):

        QApplication.processEvents()
        self.klystronComplement["desired"] = {}

        # This PV returns a flattened truth table that starts at 20-1 and ends
        # at 31-2 (inclusive)
        complementDesired = Utils.get_hist("CUDKLYS:MCC0:ONBC1SUMY",
                                          self.timestamp["archiveStart"],
                                          self.timestamp["archiveStop"], 'json')

        # Remove sectors 20 and 31
        complementDesired = Utils.valFromJson(complementDesired)[8:88]

        # Reshape as a 2D array to make it easier to understand
        complementDesired = array(complementDesired).reshape(10, 8)

        for column, sector in enumerate(complementDesired):
            stations = {}
            for row, isOnBeam in enumerate(sector):
                stations[row + 1] = isOnBeam

                item = QtGui.QTableWidgetItem()

                if isOnBeam:
                    # If station on, make light green
                    brush = QtGui.QBrush(QtGui.QColor(100, 255, 100))
                else:
                    brush = QtGui.QBrush(QtGui.QColor(255, 0, 0))

                self.paintCell(row, column, item, brush)
                self.updateProgress(incrementalProgress)

            self.klystronComplement["desired"][column + 21] = stations

        # "Remove" 24-7 and 24-8
        self.klystronComplement["desired"][24][7] = None
        # self.klystronComplement["desired"][24][8] = None

        item = QtGui.QTableWidgetItem()
        # I can't figure out how to get the grey color and I don't care enough
        brush = QtGui.QBrush(QtGui.QColor.black)
        self.paintCell(6, 3, item, brush)

        # Copy list to have an 'original' list to revert to if user changes
        # complement and then wants to go back to original
        self.klystronComplement["original"] = \
            deepcopy(self.klystronComplement["desired"])

    # Get mirror positions from time of interest
    def getMirrors(self):

        goingFromHardToSoft = (self.setpoints["photonEnergyCurrent"].val
                               > Utils.ENERGY_BOUNDARY
                               > self.setpoints["photonEnergyDesired"].val)

        goingFromSoftToHard = (self.setpoints["photonEnergyDesired"].val
                               > Utils.ENERGY_BOUNDARY
                               > self.setpoints["photonEnergyCurrent"].val)

        self.mirrorStatus["needToChangeM1"] = (goingFromHardToSoft
                                               or goingFromSoftToHard)

        wantHardXrays = (self.setpoints["photonEnergyDesired"].val
                         > Utils.ENERGY_BOUNDARY)

        self.mirrorStatus["hardPositionNeeded"] = wantHardXrays
        self.mirrorStatus["softPositionNeeded"] = not wantHardXrays

        if self.mirrorStatus["needToChangeM1"]:
            self.printStatusMessage('Soft/Hard mirror change needed')
            self.printStatusMessage("Will change M1 mirror to "
                                    + ("Hard"
                                       if self.mirrorStatus["hardPositionNeeded"]
                                       else "Soft"))

        try:
            positionDesiredM3S = self.setpoints["positionDesiredM3S"].val

        except:
            # Channel archiver issues crop up from time to time
            self.printStatusMessage('Could not determine M3 position at '
                                    'requested time (Archive Appliance error). '
                                    'Soft mirror will NOT be changed.')

            self.mirrorStatus["needToChangeM3"] = False
            self.ui.m3_cb.setChecked(False)
            self.ui.m3_cb.setDisabled(True)
            return

        self.ui.m3_cb.setDisabled(False)
        positionNowM3S = self.setpoints["positionCurrentM3S"].val

        if self.mirrorStatus["softPositionNeeded"]:
            txt = ("<P><FONT COLOR='#FFF'>Select desired soft x-ray hutch"
                   "</FONT></P>")
            # noinspection PyCallByClass
            sxrPositionDesired = QtGui.QMessageBox.question(self,
                                                            "Hutch Selector",
                                                            txt, "AMO", "SXR")

            # The setpoints are 4501um for AMO and -4503um for SXR
            if sxrPositionDesired:
                self.mirrorStatus["amoPositionNeeded"] = False
                positionDesiredM3S = -4503

            else:
                self.mirrorStatus["amoPositionNeeded"] = True
                positionDesiredM3S = 4501

        else:
            self.mirrorStatus["amoPositionNeeded"] = positionDesiredM3S > 0


        self.mirrorStatus["sxrPositionNeeded"] = not self.mirrorStatus["amoPositionNeeded"]

        goingFromSXRToAMO = positionDesiredM3S > 0 > positionNowM3S
        goingFromAMOToSXR = positionDesiredM3S < 0 < positionNowM3S

        self.mirrorStatus["needToChangeM3"] = (goingFromSXRToAMO
                                               or goingFromAMOToSXR)

        if goingFromSXRToAMO:
            self.printStatusMessage('M3 will be changed to provide beam to '
                                    'AMO (unless beam will be going down '
                                    'hard line)')

        if goingFromAMOToSXR:
            self.printStatusMessage('M3 will be changed to provide beam to '
                                    'SXR (unless beam will be going down '
                                    'hard line)')

    ########################################################################
    # Where the magic happens (user has obtained values, time to do the
    # actual change).
    ########################################################################
    def changeEnergy(self):

        self.setupUiAndDiagnostics()
        self.implementSelectedChanges()

        # Set gas detector recipe/pressures/PMTs: conditional statements
        # are contained in function (e.g. user doesn't want PMTs set)
        self.setGdet()
        self.updateProgress(5)
        self.setAllTheSetpoints()
        self.updateProgress(10)

        # Get results of score load, make sure it worked
        self.checkScoreLoads()

        self.checkAndStandardize()

        if (self.mirrorStatus["needToChangeM1"]
                or self.mirrorStatus["needToChangeM3"]):
            # Check to make sure that mirror gets to where it should
            self.checkMirrors()

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
            energyDiff = (self.setpoints["electronEnergyCurrent"]
                          - self.setpoints["electronEnergyDesired"])

            if energyDiff > 0.005:
                if self.diagnostics["scoreProblem"]:
                    self.printStatusMessage("Skipping STDZ - problem loading "
                                            "scores")
                else:
                    self.stdzMags()

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
            self.printStatusMessage('problem with time logging or log writing',
                                    False)

    def implementSelectedChanges(self):

        if self.ui.stopper_cb.isChecked():
            # Insert stoppers and disable feedback
            self.disableFB()

        # Set mirrors immediately so they can start moving as they take
        # time (will check mirrors at end of calling function using
        # self.CheckMirrors)

        if (self.mirrorStatus["needToChangeM1"]
                or self.mirrorStatus["needToChangeM3"]):
            self.setMirrors()

        self.updateProgress(10)

        # Load scores if user wants

        if (self.ui.score_cb.isChecked() or self.ui.injector_cb.isChecked()
                or self.ui.taper_cb.isChecked()):
            self.loadScores()

        else:
            # TODO this doesn't seem to be done in LoadScores...
            # Add progress to progress bar; this is done in LoadScores but
            # needs to be done here if no scores are loaded
            self.updateProgress(35)

        if self.ui.klystron_cb.isChecked():
            # Set klystron complement
            self.setKlys()

        else:
            # Make up missing progress if klystrons are not set by this GUI
            self.updateProgress(25)

        if self.ui.fast6x6_cb.isChecked():
            # Set 6x6 parameters and feedback matrices
            self.set6x6()
            self.updateProgress(5)

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

        self.printStatusMessage("Working...", True)

        QApplication.processEvents()

        self.ui.statusText.repaint()
        self.updateProgress(5 - self.diagnostics["progress"])

    # If user clicks calendar or changes time, revert to initial state where
    # pressing button will only get archived values in preparation for energy
    # change
    def userChange(self):

        # Reinitialize variable so the GUI will grab new data
        self.diagnostics["valsObtained"] = False

        # Reinitialize main button
        self.ui.startButton.setText('Get Values')

        # Format user time so it is ready to pass to Archiver
        self.formatTime()

        self.updateProgress(-self.diagnostics["progress"])

        # Disable restore complement button
        self.ui.restoreButton.setDisabled(True)
        self.showRollingMessage()
        self.ui.statusText.setText("Press 'Get Values' to get archived values")

    # Handles user click of complement table in order to juggle stations
    def changeComp(self, row, column):
        station = row + 1
        sector = column + 21

        try:
            klysStatus = self.klystronComplement["desired"][sector][station]
            item = QtGui.QTableWidgetItem()

            brush = QtGui.QBrush(QtGui.QColor.black)

            if klysStatus == 1:
                self.klystronComplement["desired"][sector][station] = 0
                brush = QtGui.QBrush(QtGui.QColor(255, 0, 0))
            elif klysStatus == 0:
                self.klystronComplement["desired"][sector][station] = 1
                brush = QtGui.QBrush(QtGui.QColor(100, 255, 100))

            self.paintCell(row, column, item, brush)

            self.ui.restoreButton.setDisabled(False)

        # User hasn't gotten values yet, hence
        # self.klystronComplement["desired"] doesn't yet exist so just ignore
        # this error
        except AttributeError:
            self.printStatusMessage("Error changing " + str(sector) + "-"
                                    + str(station))
            pass

    # Restores original complement (the displayed complement to load will be
    # reverted to what it was from the archive)
    def restoreComplement(self):

        # Set master klystron list to be a copy of the original klystron
        # complement (this variable created in GetKlys function when archived
        # data is retrieved)
        self.klystronComplement["desired"] = \
            deepcopy(self.klystronComplement["original"])

        for sector in xrange(21, 31):
            for station in xrange(1, 9):
                klysStatus = self.klystronComplement["desired"][sector][station]
                item = QtGui.QTableWidgetItem()

                brush = QtGui.QBrush(QtGui.QColor.black)

                if klysStatus == 0:
                    brush = QtGui.QBrush(QtGui.QColor(255, 0, 0))
                elif klysStatus == 1:
                    brush = QtGui.QBrush(QtGui.QColor(100, 255, 100))

                self.paintCell(station - 1, sector - 21, item, brush)

        self.ui.restoreButton.setDisabled(True)

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

    def addScoreTableItem(self, txt, row, column):
        item = QtGui.QTableWidgetItem()
        item.setText(txt)
        self.ui.scoretable.setItem(row, column, item)

    def populateScoreTable(self):

        for idx, time in enumerate(self.scoreInfo["times"]):
            try:
                self.addScoreTableItem(str(time), idx, 0)
                self.addScoreTableItem(self.scoreInfo["comments"][idx], idx, 1)
                self.addScoreTableItem(self.scoreInfo["titles"][idx], idx, 2)

            # A safety if there is some mismatch among titles/comments/times
            # returned from score API and processed by this GUI (e.g. not the
            # same total number of each)
            except:
                self.scoreTableProblem()

    # Notify user that reading database had problem; set time/date manually
    def scoreTableProblem(self):
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
            self.ui.startButton.setEnabled(True)

        # User clicked a blank cell, stop here
        except IndexError:
            self.ui.statusText.setText("Error reading selected SCORE")

    def paintCell(self, row, column, item, brush):
        brush.setStyle(QtCore.Qt.SolidPattern)
        item.setBackground(brush)
        self.ui.tableWidget.setItem(row, column, item)

    # Disable BC2 longitudinal, DL2 energy, transverse feedbacks downstream of
    # XCAV
    def disableFB(self):
        QApplication.processEvents()

        self.printStatusMessage('Inserting stoppers, disabling feedbacks')

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
    def loadScores(self):
        self.printStatusMessage('Loading Scores...')

        QApplication.processEvents()
        self.ui.textBrowser.repaint()

        self.diagnostics["threads"] = []
        regionList = []

        if self.ui.injector_cb.isChecked():
            regionList.append("Gun to TD11-LEM")

        if self.ui.score_cb.isChecked():
            regionList.extend(("Cu Linac-LEM", "Hard BSY thru LTUH-LEM"))

        if self.ui.taper_cb.isChecked():
            regionList.extend(("Undulator Taper", "Undulator-LEM"))

        # Put message in message log that scores are being loaded
        for region in regionList:
            message = ("Loading SCORE from " + self.scoreInfo["dateChosen"]
                       + " " + self.scoreInfo["timeChosen"] + " for "
                       + region)

            self.printStatusMessage(message)
            log("facility=pythonenergychange " + message)

            # Have a thread subclass to handle this (defined at bottom of this
            # file); normal threading class returns NONE
            t = Utils.ThreadWithReturnValue(target=self.scoreThread,
                                            args=(region,))
            self.diagnostics["threads"].append(t)

        for thread in self.diagnostics["threads"]:
            thread.start()

    def checkScoreLoads(self):
        self.printStatusMessage("Waiting for SCORE regions to load...")

        try:
            for thread in self.diagnostics["threads"]:
                # I want to wait for each thread to finish execution so the
                # score completion/failure messages come out together
                status, region = thread.join()
                if status == 0:
                    self.printStatusMessage('Set/trimmed devices for ' + region)
                else:
                    self.printStatusMessage('Error loading ' + region
                                            + ' region (see xterm)')

                    # This flags the program to inform the user at end of change
                    #  that there was a problem
                    self.diagnostics["scoreProblem"] = True

                QApplication.processEvents()
                self.updateProgress(35)

        # User doesn't want scores loaded
        except AttributeError:
            self.updateProgress(35)

    # Thread function for loading each individual score region
    def scoreThread(self, region):
        try:
            data = self.scoreObject.read_pvs(region,
                                             self.scoreInfo["dateChosen"],
                                             self.scoreInfo["timeChosen"]
                                             + ':00')
        except:
            print "Error in scoreThread getting data for " + region
            return 1, region

        try:
            # return 0, region
            errors = Utils.setDevices(region, data)
            return (len(errors) if errors is not None else 1), region
        except:
            print "Error in scoreThread setting data for " + region
            return 1, region

    # Check that bend dump has finished trimming and then start standardize
    def stdzMags(self):
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
    def setKlys(self):
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
    def set6x6(self):

        self.printStatusMessage('Setting 6x6 Parameters and LTU/UND '
                                'feedback matrices')

        caput('FBCK:FB04:LG01:STATE', '0')

        self.caputSetpoint('FBCK:FB04:LG01:S3DES', "BC1PeakCurrent")
        self.caputSetpoint('ACCL:LI22:1:ADES', "amplitudeL2")
        self.caputSetpoint('ACCL:LI22:1:PDES', "phaseL2")
        self.caputSetpoint('FBCK:FB04:LG01:S5DES', "peakCurrentL2")
        self.caputSetpoint('ACCL:LI25:1:ADES', "amplitudeL3")

        sleep(.2)

        caput('FBCK:FB04:LG01:STATE', '1')

        self.printStatusMessage('Setting 6x6 complete')

    def setAllTheSetpoints(self):
        QApplication.processEvents()
        if self.ui.matrices_cb.isChecked():
            self.printStatusMessage('Sending LTU/UND matrices to feedbacks')
            data = self.scoreObject.read_pvs("Feedback-All",
                                             self.scoreInfo["dateChosen"],
                                             self.scoreInfo["timeChosen"]
                                             + ':00')
            Utils.setMatricesAndRestartFeedbacks(data)
            self.printStatusMessage('Sent LTU/UND matrices to feedbacks and '
                                    'stopped/started')

        # Set BC2 chicane mover and phase (magnet strength is set in
        # LoadScores())
        if self.ui.BC2_cb.isChecked():
            self.setBC2Mover()

        # Set feedback setpoints, laser heater, L3 phase, laser heater camera
        # waveplates, vernier etc.
        if self.ui.setpoints_cb.isChecked():
            self.setSetpoints()

        if self.ui.pstack_cb.isChecked():
            self.caputSetpoint('PSDL:LR20:117:TDES', "pulseStackerDelay")
            self.caputSetpoint('WPLT:LR20:117:PSWP_ANGLE',
                               "pulseStackerWaveplate")

            self.printStatusMessage('Set pulse stacker delay and waveplate')

        if self.ui.l1x_cb.isChecked():
            self.caputSetpoint('ACCL:LI21:180:L1X_ADES', "amplitudeL1X")
            self.caputSetpoint('ACCL:LI21:180:L1X_PDES', "phaseL1X")
            self.printStatusMessage('Set L1X phase and amplitude')

        if self.ui.bc1coll_cb.isChecked():
            self.caputSetpoint('COLL:LI21:235:MOTR.VAL', "BC1LeftJaw")
            self.caputSetpoint('COLL:LI21:236:MOTR.VAL', "BC1RightJaw")
            self.printStatusMessage('Set BC1 collimators')

    # Set mirrors to desired positions
    def setMirrors(self):
        QApplication.processEvents()

        caput('MIRR:FEE1:1560:LOCK', '1')
        sleep(.3)

        if self.mirrorStatus["hardPositionNeeded"]:
            if self.ui.m1_cb.isChecked():
                self.printStatusMessage('Setting M1 for Hard')
                caput('MIRR:FEE1:1561:MOVE', '1')

        elif self.mirrorStatus["softPositionNeeded"]:
            if self.ui.m1_cb.isChecked():
                self.printStatusMessage('Setting M1 for Soft')
                caput('MIRR:FEE1:0561:MOVE', '1')

            if self.ui.m3_cb.isChecked():
                caput('MIRR:FEE1:1810:LOCK', '1')
                sleep(.3)

                if self.mirrorStatus["sxrPositionNeeded"]:
                    self.printStatusMessage('Setting M3 for SXR')
                    caput('MIRR:FEE1:2811:MOVE', '1')

                elif self.mirrorStatus["amoPositionNeeded"]:
                    self.printStatusMessage('Setting M3 for AMO')
                    caput('MIRR:FEE1:1811:MOVE', '1')

    def waitForMirror(self, statusPV, lockPV, mirror, desiredPosition):
        self.printStatusMessage('Checking ' + mirror + ' Mirror Position for '
                                + desiredPosition + '...')

        while not caget(statusPV):
            QApplication.processEvents()
            sleep(1)
        self.printStatusMessage('Detected ' + mirror + ' Mirror in '
                                + desiredPosition + ' Position')
        caput(lockPV, '0')

    # Check that mirrors reach their desired positions
    def checkMirrors(self):
        QApplication.processEvents()

        if self.mirrorStatus["hardPositionNeeded"]:
            if self.ui.m1_cb.isChecked():
                self.waitForMirror('MIRR:FEE1:1561:POSITION',
                                   'MIRR:FEE1:1560:LOCK', "M1", "Hard")

        elif self.mirrorStatus["softPositionNeeded"]:
            if self.ui.m1_cb.isChecked():
                self.waitForMirror('MIRR:FEE1:0561:POSITION',
                                   'MIRR:FEE1:1560:LOCK', "M1", "Soft")

            if self.ui.m3_cb.isChecked():
                if self.mirrorStatus["sxrPositionNeeded"]:
                    self.waitForMirror('MIRR:FEE1:2811:POSITION',
                                       'MIRR:FEE1:1810:LOCK', "M3", "SXR")

                elif self.mirrorStatus["amoPositionNeeded"]:
                    self.waitForMirror('MIRR:FEE1:1811:POSITION',
                                       'MIRR:FEE1:1810:LOCK', "M3", "AMO")

    # Score loading should set Magnet to proper value, this will set chicane
    # mover and chicane phase which makes sure R56 is right.
    def setBC2Mover(self):
        BC2MoverNow = caget('BMLN:LI24:805:MOTR.VAL')
        BC2PhaseNow = caget('SIOC:SYS0:ML00:AO063')

        if (BC2MoverNow == self.setpoints["BC2Mover"]
                and BC2PhaseNow == self.setpoints["BC2Phase"]):
            self.printStatusMessage('BC2 Mover/Phase look the same, '
                                    'not sending values')
            return

        self.printStatusMessage('Setting BC2 Mover and Phase')

        self.caputSetpoint('BMLN:LI24:805:MOTR.VAL', "BC2Mover")
        self.caputSetpoint('SIOC:SYS0:ML00:AO063', "BC2Phase")

        self.printStatusMessage('Set BC2 Mover and Phase')

    # Set random setpoints (xcav, und launch, lhwp etc.)
    def setSetpoints(self):
        self.printStatusMessage('Setting Xcav, LHWP, Und Launch, L3P and '
                                'vernier')

        self.caputSetpoint('FBCK:FB01:TR03:S1DES', "xcavLaunchX")
        self.caputSetpoint('FBCK:FB01:TR03:S2DES', "xcavLaunchY")

        try:
            self.caputSetpoint('WPLT:LR20:220:LHWP_ANGLE', "heaterWaveplate1")
            self.caputSetpoint('WPLT:LR20:230:LHWP_ANGLE', "heaterWaveplate2")

        except:
            self.printStatusMessage('Unable to set heater power waveplates')

        self.caputSetpoint('WPLT:IN20:467:VHC_ANGLE', "waveplateVHC")
        self.caputSetpoint('WPLT:IN20:459:CH1_ANGLE', "waveplateCH1")

        self.caputSetpoint('FBCK:FB03:TR04:S1DES', "undLaunchPosX")
        self.caputSetpoint('FBCK:FB03:TR04:S2DES', "undLaunchAngX")
        self.caputSetpoint('FBCK:FB03:TR04:S3DES', "undLaunchPosY")
        self.caputSetpoint('FBCK:FB03:TR04:S4DES', "undLaunchAngY")

        self.caputSetpoint('FBCK:FB04:LG01:DL2VERNIER', "vernier")
        self.caputSetpoint('ACCL:LI25:1:PDES', "phaseL3")

        self.printStatusMessage('Set Xcav, LHWP, Und Launch, L3 Phase and '
                                'Vernier')

    ############################################################################
    # HHHHHHHHHIIIIIIIIIIIIIIIIIIIIII
    # ZIIIIIMMMMMMMMMMMMMMMMMMMMMMMEEEEEEEEERRRRRRRRRRRRRRRRRRRRRRRR
    ############################################################################

    def caputSetpoint(self, pv, key):
        self.printStatusMessage("Setting " + key + " to: "
                                + str(self.setpoints[key]))
        caput(pv, self.setpoints[key])

    # Set gas detector recipe/pressure and pmt voltages
    def setGdet(self):
        QApplication.processEvents()
        if self.ui.pmt_cb.isChecked():
            self.printStatusMessage('Setting PMT voltages/Calibration/Offset')
            QApplication.processEvents()

            for PMT in ["241", "242", "361", "362"]:
                self.caputSetpoint('HVCH:FEE1:' + PMT + ':VoltageSet',
                                   "voltagePMT" + PMT)

                self.caputSetpoint('GDET:FEE1:' + PMT + ':CALI',
                                   "calibrationPMT" + PMT)

                self.caputSetpoint('GDET:FEE1:' + PMT + ':OFFS',
                                   "offsetPMT" + PMT)

            self.printStatusMessage('Set PMT voltages/Calibration/Offset')

        self.setPressuresForHardMirrorChange()
        self.setPressuresForSoftMirrorChange()

        # No recipe change needed, not switching between hard/soft xrays
        if not self.mirrorStatus["needToChangeM1"]:
            if self.ui.pressure_cb.isChecked():
                self.printStatusMessage('Setting pressures')
                QApplication.processEvents()

                self.caputSetpoint('VFC:FEE1:GD01:PLO_DES', "GD1PressureLo")
                self.caputSetpoint('VFC:FEE1:GD02:PLO_DES', "GD2PressureLo")
                self.caputSetpoint('VFC:FEE1:GD01:PHI_DES', "GD1PressureHi")
                self.caputSetpoint('VFC:FEE1:GD02:PHI_DES', "GD2PressureHi")

    def setPressuresForSoftMirrorChange(self):
        # Mirror change to soft setting
        if (self.mirrorStatus["needToChangeM1"]
                and self.mirrorStatus["softPositionNeeded"]):

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

                self.caputSetpoint('VFC:FEE1:GD01:PLO_DES', "GD1PressureLo")
                self.caputSetpoint('VFC:FEE1:GD02:PLO_DES', "GD2PressureLo")

    def setPressuresForHardMirrorChange(self):
        # Mirror change required, and changing to hard xray setting; or somehow
        # are running hard xrays with low recipe (has happened and then OPS
        # thinks there is no FEL)
        if self.mirrorStatus["hardPositionNeeded"]:
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

                self.caputSetpoint('VFC:FEE1:GD01:PHI_DES', "GD1PressureHi")
                self.caputSetpoint('VFC:FEE1:GD02:PHI_DES', "GD2PressureHi")


def main():
    app = QApplication(argv)
    window = EnergyChange()

    # Close the SCORE connection
    app.aboutToQuit.connect(window.scoreObject.exit_score)

    window.show()
    exit(app.exec_())


if __name__ == "__main__":
    main()
