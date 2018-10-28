# Written by Tony, refactored by Ben and Lisa

import os
import datetime
import cx_Oracle
import re
from energyChangeUtils import Struct


class PyScore(object):
    def __init__(self):
        os.environ["TWO_TASK"] = "MCCO"
        os.environ["TNS_ADMIN"] = "/usr/local/lcls/tools/oracle/wallets/score"
        self.con = cx_Oracle.connect("/@MCCO")
        self.cur = self.con.cursor()

    ############################################################################
    #                            Main Pyscore Methods                          #
    ############################################################################

    # Returns a dictionary of setpoint and readback PVs and their associated
    # values for one config. (see example.py for details)
    # Dictionary looks like this: {'actpvs':[pv list],
    #                              'actvals':[list of values],
    #                              'despvs':[pv list],
    #                              'desvals':[list of values]}
    def read_pvs(self, region=None, date=None, time=None, pvs=None):
        con = cx_Oracle.connect("/@MCCO")
        cur = con.cursor()

        if not date or not time:
            print 'Must specify a date & time!'
            self.closeConnection(con, cur)
            raise NameError('Must specify a date & time!')

        statement = ("select set_pt_sgnl_id,set_pt_sgnl_val,rb_sgnl_id,"
                     "rb_sgnl_val from score_snapshot_sgnl "
                     "where program_id = 1")

        startTime, stopTime = self.time_adjust(date, time)
        stateDict = {"startTime": startTime, "stopTime": stopTime}

        statement += " and (mod_dte >= :startTime) and (mod_dte <= :stopTime)"

        if region:
            stateDict['region'] = region
            statement += " and equip_cat_id = :region"

        data = []
        try:
            if not pvs:
                # No PVs specified so get everything using the base statement
                cur.execute(statement, stateDict)
                new_data = cur.fetchall()
                data += new_data[:]
            else:
                # One or more PVs specified so the query is trickier
                statement += (" and (set_pt_sgnl_id like :pvs or rb_sgnl_id "
                              "like :pvs)")
                for pv in pvs:
                    stateDict['pvs'] = pv
                    cur.execute(statement, stateDict)
                    new_data = cur.fetchall()
                    data += new_data[:]
        except:
            print ('pyScore error in read_pvs - attempted executing: "'
                   + statement + '" ' + stateDict)
            self.closeConnection(con, cur)
            raise

        if not data:
            print 'No data obtained from SCORE database.'

        else:
            # We successfully retrieved data so pack it into a dict and
            # return it to the user.
            data_dict = {"desPVs": [], "desVals": [], "actPVs": [],
                         "actVals": []}

            for element in data:
                data_dict["desPVs"].append(element[0])
                data_dict["desVals"].append(self.sanitize_val(element[1]))
                data_dict["actPVs"].append(element[2])
                data_dict["actVals"].append(self.sanitize_val(element[3]))

            if not data_dict:
                print 'No data output. Check PV keyword for typos'

            self.closeConnection(con, cur)
            return data_dict

    @staticmethod
    def closeConnection(con, cur):
        cur.close()
        con.close()

    # Returns a valid list of config dates based on the the user's energy
    # specification and time range specification. (see example.py for details)
    def read_dates(self, region='Gun to TD11-LEM', energy=None, est_energy=None,
                   edelta=None, emin=None, emax=None, beg_date=None,
                   end_date=None, sample_snaps=None, columns=[]):

        if region == 'EVGUI':
            raise ValueError('region EVGUI is not implemented')

        columns = set(columns)
        columns = columns.union(["mod_dte", "config_title"])

        stateDict = {"region": region}
        clauses = ""

        if beg_date and end_date:
            dstartTime, dstopTime = self.time_range_adjust(beg_date, end_date)
            stateDict['startTime'] = dstartTime
            stateDict['stopTime'] = dstopTime
            clauses = "and (mod_dte >= :startTime) and (mod_dte <= :stopTime) "

        statement = ("select {cols} from score_snapshot_grp "
                     "where program_id = 1 "
                     "and equip_cat_id = :region {extra_filters}"
                     "order by mod_dte desc"
                     .format(cols=", ".join(columns),
                             extra_filters=clauses))
        try:
            self.cur.execute(statement, stateDict)

        except:
            print 'pyScore error in read_dates'
            raise

        return self.Etime_array(sample_snaps, energy, emin, emax, est_energy,
                                edelta)

    # Searches the database for the given PVs (entered as a list).
    # It returns a dictionary of the form {'PV1':'region1',...} if the PV
    # exists.
    # If the PV does not exist in SCORE, then something is printed to the
    # terminal and the offending PV is skipped.
    # If the date is <= 2016 some of the SCORE regions are different.
    def pvs_in_score(self, pvs, date=None):
        regionDict = {}

        try:
            for pv in pvs:
                data_ar = []
                pv_dict = {'pvs': pv}
                statement = ("select equip_cat_id from score_snapshot_sgnl "
                             "where program_id = 1 and (set_pt_sgnl_id = :pvs "
                             "or rb_sgnl_id = :pvs) order by mod_dte desc")
                self.cur.execute(statement, pv_dict)
                data = self.cur.fetchone()

                if data:
                    data_ar.append(data[0])

                    for _ in xrange(9):
                        data = self.cur.fetchone()
                        data_ar.append(data[0])

                    regionDict['%s' % pv] = self.region_parse(data_ar,
                                                              date=date)

                else:
                    print ('%s is not in SCORE. Maybe the PV is spelled wrong?'
                           % pv)
                    regionDict['%s' % pv] = None

        except:
            print 'pyScore error in pvs_in_score'
            raise

        return regionDict

    def get_assoc_configs(self, region=None, date=None, time=None):
        """Find all other configs that were saved at the same time as
        the user-specified config and return them as a dict whose keys
        are region names indexing grp_ids, i.e. config numbers.
        """

    ############################################################################
    #                         Helper Methods                                   #
    ############################################################################

    # Part of the read_dates method above. Returns a list of times for
    # instances where the user wants to search
    # a config for a specific energy or where the user simply wants the first
    # sample number of configs
    # @param {float} Emin, Emax, est_energy, Edelta, energy
    # returns a list of score structs with fields title, time, and comment
    def Etime_array(self, samples=None, energy=None, Emin=None, Emax=None,
                    est_energy=None, Edelta=None):
        # Parse the input arguments
        # Error checking is kind of light here, if a user enters a est_energy
        # in GeV, and Edelta in photon eV, they are gonna have a bad time.
        if not samples:
            samples = 50

        columns = [col[0] for col in self.cur.description]
        titleIdx = columns.index("CONFIG_TITLE")
        results = []

        # for column in columns:
        #     results[column] = []

        if not Emin and not Emax and est_energy:
            if Edelta:
                Emin = est_energy - Edelta
                Emax = est_energy + Edelta
            else:
                Emin = est_energy * 0.9
                Emax = est_energy * 1.1

        parse_pattern = re.compile("(EDES=[0-9]+\.[0-9]+ GeV BDES=)"
                                   "?(?P<electronenergy>[0-9]{1,2}\.[0-9]+) GeV"
                                   " \+ (?P<vernier>-?[0-9]+\.[0-9]+) MeV, "
                                   "(?P<peakcurrent>[0-9]+) A, "
                                   "(?P<pulseenergy>[0-9]+\.[0-9]+) mJ, "
                                   "(?P<photonenergy>[0-9]+) eV, "
                                   "(?P<injectorcharge>[0-9]+)->"
                                   "(?P<dumpcharge>[0-9]+) pC")
        num_rows = 0

        for row in self.cur:
            if not row[titleIdx]:
                continue

            match = parse_pattern.match(row[titleIdx])

            if not match:
                continue

            if energy:
                if not (float(match.group('electronenergy')) == energy
                        or float(match.group('photonenergy')) == energy):
                    continue

            elif Emin and Emax:
                if not ((Emin <= float(match.group('electronenergy')) <= Emax)
                        or (Emin <= float(match.group('photonenergy'))
                            <= Emax)):
                    continue

            results.append(Struct(time=row[0], title=row[1], comment=row[2]))

            num_rows += 1

            if num_rows >= samples:
                break

        return results

    # For read_pvs method. This adds and subtracts some number of minutes
    # (default = 3) from the config time the user specifies to generate a time
    # range.
    # This time range is used in a SQL command to find the correct config.
    # This was more of an empirical find than anything else, but if I had to
    # guess, it's probably due to the different way python interprets time and
    # oracle interprets time and the difference in time from
    # different regions when the 'save the world' action is taken on SCORE GUI.
    @staticmethod
    def time_adjust(date, time, delta=3):
        dtformat = datetime.datetime(int(date[0:4]), int(date[5:7]),
                                     int(date[8:]), int(time[0:2]),
                                     int(time[3:5]), int(time[6:]))
        startTime = dtformat - datetime.timedelta(minutes=delta)
        stopTime = dtformat + datetime.timedelta(minutes=delta)
        return startTime, stopTime

    # For read_dates method. Returns a format that the SQL code requires to
    # find configs between two dates.
    # Also uses the end string 'now' as a flag for the current date and time
    # if the user specifies 'now' instead of a specific date and time.
    @staticmethod
    def time_range_adjust(beg, end):

        if end == 'now':
            end = str(datetime.datetime.now())
            decloc = end.find('.')
            end = end[:decloc]

        idtformat = datetime.datetime(int(beg[0:4]), int(beg[5:7]),
                                      int(beg[8:10]), int(beg[11:13]),
                                      int(beg[14:16]), int(beg[17:]))

        fdtformat = datetime.datetime(int(end[0:4]), int(end[5:7]),
                                      int(end[8:10]), int(end[11:13]),
                                      int(end[14:16]), int(end[17:]))
        return idtformat, fdtformat

    @staticmethod
    def sanitize_val(value):
        """Sanitize a value fetched from the Oracle DB."""
        try:
            val = str(float(value))
            if 'nan' in val:
                san_val = 'NAN'
            else:
                san_val = float(value)

        # When a None type is encountered
        except TypeError:
            san_val = 'NAN'

        # When a string type is encountered (stuff like ONE_HERTZ, etc.)
        except ValueError:
            san_val = str(value)
        return san_val

    # For pvs_in_score method above. Returns a region without "LEM Undo".
    # It also factors in the change in score regions after 2017 and the random
    # occurences of old score regions being saved after 2017.
    @staticmethod
    def region_parse(array, date=None):
        new_array = [x for x in array if not x == 'LEM Undo']
        if not date:
            # replaces new score names with old if date <= 2016
            if int(str(date)[:4]) <= 2016:
                new_array = [w.replace('Cu Linac-LEM', 'TD11 to BSY-LEM')
                                 .replace('Hard BSY thru LTUH-LEM', 'LTU-LEM')
                             for w in new_array]

            # replaces old score names with new if date >= 2017
            elif int(str(date)[:4]) >= 2017:
                new_array = [w.replace('TD11 to BSY-LEM', 'Cu Linac-LEM')
                                 .replace('LTU-LEM', 'Hard BSY thru LTUH-LEM')
                             for w in new_array]

        return list(set(new_array))[0]

    # Closes the connection to the SCORE Oracle database. Done after each main
    # method above.
    def exit_score(self):
        self.closeConnection(self.con, self.cur)
        return
