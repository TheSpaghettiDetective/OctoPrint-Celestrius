from __future__ import absolute_import
import logging
import logging.handlers
import octoprint.plugin
import octoprint.filemanager
import octoprint.filemanager.util
import octoprint.printer
import octoprint.util
import re, os, sys, json
import flask
import time
from flask_login import current_user
from octoprint.events import Events
from octoprint.filemanager import FileDestinations
from threading import Thread, RLock
import logging

_logger = logging.getLogger('octoprint.plugins.celestrius')

class GCodeObject():

    def __init__(self, plugin):
        self.plugin = plugin

        self.object_list = []
        self.skipping = False
        self.startskip = False
        self.endskip = False
        self.objects_known = False
        self.active_object = None
        self.object_regex = []
        self.reptag = None
        self.ignored = []
        self.beforegcode = []
        self.aftergcode = []
        self.allowed = []
        self.trackE = False
        self.lastE = 0
        self.prevE = 0
        self.skipstarttime = 0.0
        self.parser = Gcode_parser()


    def on_event(self, event, payload):

        if event in (Events.FILE_SELECTED, Events.PRINT_STARTED):
            self.object_list = []
            self.lastE = 0
            selectedFile = payload.get("file", "")
            if not selectedFile:
                path = payload.get("path", "")
                if payload.get("origin") == "local":
                    # Get full path to local file
                    path = self.plugin._file_manager.path_on_disk(FileDestinations.LOCAL, path)
                selectedFile = path
            with open(selectedFile, "r") as f:
                i = 0
                for line in f:
                    try:
                        obj = self.process_line(line)
                        if obj:
                            obj["id"] = i
                            self.object_list.append(obj)
                            i = i + 1
                    except (ValueError, RuntimeError):
                        print("Error")
            # Send objects to server
            self._updateobjects(payload.get('name', None))

        elif event in (Events.PRINT_DONE, Events.PRINT_FAILED, Events.PRINT_CANCELLED, Events.FILE_DESELECTED):
            if self.skipping:
                self.skipping = False
                self.plugin._printer.set_temperature('bed', 0)
                self.plugin._printer.set_temperature('tool0', 0)
            self.object_list = []
            self.objects_known = False
            self.trackE = False
            self.lastE = 0
            self.active_object = 'None'


    def _updateobjects(self, filename):
        if len(self.object_list) > 0:
            if filename:
                self.plugin.update_object_list(self.object_list, filename)

            for each in self.object_list:
                if each["object"] in self.ignored:
                    each["ignore"] = True

    def initialize(self):
        self._settings = self.get_settings_defaults()

        self.object_regex = self._settings.get("object_regex")
        self.reptag = self._settings.get("reptag")
        self.reptagregex = re.compile("@{0} ([^\t\n\r\f\v]*)".format(self.reptag), re.IGNORECASE)
        self.objectinforegex = re.compile("@{0}info ([^\t\n\r\f\v]*) X([-]*\d+\.*\d*) Y([-]*\d+\.*\d*)".format(self.reptag), re.IGNORECASE)
        self.stopobjectregex = re.compile("@{0}stop ([^\t\n\r\f\v]*)".format(self.reptag), re.IGNORECASE)
        self.allowedregex = []
        self.trackregex = [re.compile("G1 .* E(\d*\.\d+)")]

        try:
            self.beforegcode = self._settings.get("beforegcode").split(",")
            # Remove any whitespace entries to avoid sending empty lines
            self.beforegcode = list(filter(None, self.beforegcode))
        except:
            _logger.info("No beforegcode defined")
        try:
            self.aftergcode = self._settings.get("aftergcode").split(",")
            # Remove any whitespace entries to avoid sending empty lines
            self.aftergcode = list(filter(None, self.aftergcode))
        except:
            _logger.info("No aftergcode defined")
        try:
            self.ignored = self._settings.get("ignored").split(",")
            # Remove any whitespace entries to avoid sending empty lines
            self.ignored = list(filter(None, self.ignored))
        except:
            _logger.info("No ignored objects defined")
        try:
            self.allowed = self._settings.get("allowed").split(",")
            # Remove any whitespace entries
            self.allowed = list(filter(None, self.allowed))
            for allow in self.allowed:
                regex = re.compile(allow)
                self.allowedregex.append(regex)
        except:
            _logger.info("No allowed GCODE defined")

    def get_settings_defaults(self):
        return dict(
            #S3D, Cura, Slic3r/Prusa/SuperSlicer, ideaMaker
            object_regex=[{"objreg": '; process (.*)'},\
                          {"objreg": ';MESH:(.*)'},\
                          {"objreg": '; printing object (.*)'},\
                          {"objreg": ';PRINTING: (.*)'}],
            reptag="Object",
            ignored="ENDGCODE,STARTGCODE",
            beforegcode=None,
            aftergcode=None,
            allowed="",
            shownav=True,
            stoptags=False,
            markers=True,
            )

    def modify_file(self, path, file_object, blinks=None, printer_profile=None, allow_overwrite=True, *args, **kwargs):
        if not octoprint.filemanager.valid_file_type(path, type="gcode"):
            return file_object
        import os
        name, _ = os.path.splitext(file_object.filename)
        modfile = octoprint.filemanager.util.StreamWrapper(file_object.filename,
                                                           ModifyComments(file_object.stream(), self.object_regex,
                                                                          self.reptag))

        return modfile

    def process_line(self, line):
        if line.startswith("@{0}info".format(self.reptag)):
            info = self.objectinforegex.match(line)
            if info:
                entry = self._get_entry(info.group(1))
                if entry:
                    return None
                else:
                    # Making the perhaps poor assumption that all objects are known
                    self.objects_known = True
                    return dict({"object": info.group(1),
                                 "id": None,
                                 "active": False,
                                 "cancelled": False,
                                 "ignore": False,
                                 "max_x": float(info.group(2)),
                                 "min_x": float(info.group(2)),
                                 "max_y": float(info.group(3)),
                                 "min_y": float(info.group(3))
                    })

        if line.startswith("@{0}".format(self.reptag)):
            obj = self._check_object(line)
            if obj:
                entry = self._get_entry(obj)
                if entry:
                    return None
                else:
                    return dict({"object": obj,
                                 "id": None,
                                 "active": False,
                                 "cancelled": False,
                                 "ignore": False,
                                 "max_x": 0,
                                 "min_x": 10000,
                                 "max_y": 0,
                                 "min_y": 10000})
        return None

    def _check_object(self, line):
        matched = self.reptagregex.match(line)
        if matched:
            obj = matched.group(1)
            return obj
        return None

    def _get_entry(self, name):
        for o in self.object_list:
            if o["object"] == name:
                return o
        return None

    def _get_entry_byid(self, objid):
        for o in self.object_list:
            if o["id"] == int(objid):
                return o
        return None

    def _cancel_object(self, cancelled):
        obj = self._get_entry_byid(cancelled)
        obj["cancelled"] = True
        _logger.info("Object {0} cancelled".format(obj["object"]))
        if obj["object"] == self.active_object:
            self.skipping = True

    def _skip_allow(self, cmd):
        for allow in self.allowedregex:
            try:
                match = allow.match(cmd)
                if match:
                    _logger.info("Allowing command: {0}".format(cmd))
                    return cmd
            except:
                print
                "Skip regex error"

        return None,

    def check_atcommand(self, comm, phase, command, parameters, tags=None, *args, **kwargs):

        if command != self.reptag:
            self.plugin.next_object()

        if command == "{0}stop".format(self.reptag) and self._settings.get('stoptags') and self.skipping:
            self.skipping = False
            return

        if command != self.reptag:
            return

        entry = self._get_entry(parameters)
        if not entry:
            _logger.info("Could not get entry {0}".format(parameters))
            return
        if entry["cancelled"]:
            _logger.info("Hit a cancelled object, {0}".format(parameters))
            self.skipstarttime = time.time()
            self.skipping = True
            self.startskip = True
        else:
            if self.skipping:
                self.skipping = False
                self.endskip = True
            self.active_object = entry["object"]

    def check_queue(self, comm_instance, phase, cmd, cmd_type, gcode, tags, *args, **kwargs):
        # Need this or @ commands get caught in skipping block
        #if self._check_object(cmd):
        #    return cmd
        if not self.plugin._printer.is_printing():
            return cmd

        if cmd.startswith("@"):
            return cmd

        e_move = None
        e_move = self.parser.is_extrusion_move(cmd)

        if cmd == "M82":
            self.trackE = True
            _logger.info("Tracking Extrusion")

        if cmd == "M83":
            self.trackE = False
            _logger.info("Not Tracking Extrusion")

        if self.startskip and len(self.beforegcode) > 0:
            cmd = self._skip_allow(cmd)
            if cmd:
                cmd = [cmd]
                cmd.extend(self.beforegcode)
            self.startskip = False
            return cmd

        if self.endskip:
            _logger.info("Took {0} to skip block".format(time.time() - self.skipstarttime))
            cmd = [cmd]
            if len(self.aftergcode) > 0:
                cmd.extend(self.aftergcode)
            if self.trackE:
                # _logger.info("Update extrusion: {0}".format(self.lastE))
                cmd.insert(0,"G92 E{0}".format(self.lastE))
            self.endskip = False
            # _logger.info(cmd)
            return cmd

        if self.skipping:
            if self.trackE:
                eaction = None
                eaction = self.parser.parse_move_args(cmd)
                if eaction and eaction[3]:
                    self.lastE = eaction[3]
                    # _logger.info("Last extrusion: {0}".format(self.lastE))
                # We also need to catch any distance resets
                if cmd == "G92 E0":
                    self.lastE = 0.0
                # _logger.info("Reset extrusion")
            if len(self.allowed) > 0:
                cmd = self._skip_allow(cmd)
            else:
                cmd = None,

        if cmd and e_move and not self.skipping and not self.objects_known:
            self.update_objects_position(e_move)

        if e_move:
            self.prevE = e_move[3]

        return cmd

    def update_objects_position(self, e_move):
        try:
            # _logger.info("E{0}".format(e_move[3]))
            # Absolute extrusion
            if self.trackE and e_move[3] > self.prevE:
                obj = self._get_entry(self.active_object)
                if obj:
                    # min max X, Y position
                    if e_move[0] > obj["max_x"]:
                        obj["max_x"] = e_move[0]
                    if e_move[1] > obj["max_y"]:
                        obj["max_y"] = e_move[1]
                    if e_move[0] < obj["min_x"]:
                        obj["min_x"] = e_move[0]
                    if e_move[1] < obj["min_y"]:
                        obj["min_y"] = e_move[1]

            # Relative extrusiom
            elif e_move[3] > 0.0 and not self.trackE:
                # _logger.info("Extrusion was: {0}".format(e_move[3]))
                obj = self._get_entry(self.active_object)
                if obj:
                    # min max X, Y position
                    if e_move[0] is not None and e_move[0] > obj["max_x"]:
                        obj["max_x"] = e_move[0]
                    if e_move[1] is not None and e_move[1] > obj["max_y"]:
                        obj["max_y"] = e_move[1]
                    if e_move[0] is not None and e_move[0] < obj["min_x"]:
                        obj["min_x"] = e_move[0]
                    if e_move[1] is not None and e_move[1] < obj["min_y"]:
                        obj["min_y"] = e_move[1]
        except Exception as err:
            _logger.error("Error updating object position: " + str(err))


# stolen directly from filaswitch, https://github.com/spegelius/filaswitch
class Gcode_parser:
    MOVE_RE = re.compile("^G0\s+|^G1\s+")
    X_COORD_RE = re.compile(".*\s+X([-]*\d*\.*\d*)")
    Y_COORD_RE = re.compile(".*\s+Y([-]*\d*\.*\d*)")
    E_COORD_RE = re.compile(".*\s+E([-]*\d*\.*\d*)")
    Z_COORD_RE = re.compile(".*\s+Z([-]*\d*\.*\d*)")
    SPEED_VAL_RE = re.compile(".*\s+F(\d*\.*\d*)")

    def __init__(self):
        self.last_match = None

    def is_extrusion_move(self, line):
        """
        Match given line against extrusion move regex
        :param line: g-code line
        :return: None or tuple with X, Y and E positions
        """
        self.last_match = None
        m = self.parse_move_args(line)
        if m and (m[0] is not None or m[1] is not None) and m[3] is not None and m[3] != 0:
            self.last_match = m
        return self.last_match

    def parse_move_args(self, line):

        self.last_match = None
        m = self.MOVE_RE.match(line)
        if m:
            x = None
            y = None
            z = None
            e = None
            speed = None

            m = self.X_COORD_RE.match(line)
            if m:
                x = float(m.groups()[0])

            m = self.Y_COORD_RE.match(line)
            if m:
                y = float(m.groups()[0])

            m = self.Z_COORD_RE.match(line)
            if m:
                z = float(m.groups()[0])

            m = self.E_COORD_RE.match(line)
            if m:
                e = float(m.groups()[0])

            m = self.SPEED_VAL_RE.match(line)
            if m:
                speed = float(m.groups()[0])

            return x, y, z, e, speed

class ModifyComments(octoprint.filemanager.util.LineProcessorStream):

    def __init__(self, fileBufferedReader, object_regex, reptag):
        super(ModifyComments, self).__init__(fileBufferedReader)
        self.patterns = []
        for each in object_regex:
            if each["objreg"]:
                regex = re.compile(each["objreg"])
                self.patterns.append(regex)
        self._reptag = "@{0}".format(reptag)
        self.infomatch = re.compile("; object:.*")
        self.stopmatch = re.compile("; stop printing object ([^\t\n\r\f\v]*)")

    def process_line(self, line):
        try:
            # if line is of type bytes then convert to string
            line = line.decode("utf-8", "strict")
        except (UnicodeDecodeError, AttributeError):
            pass

        if line.startswith(";"):
            line = self._matchComment(line)
        if not len(line):
            return None
        return line.encode('ascii','xmlcharrefreplace')

    def _matchComment(self, line):
        for pattern in self.patterns:
            matched = pattern.match(line)
            if matched:
                obj = matched.group(1).encode('ascii','xmlcharrefreplace')
                line = "{0} {1}\n".format(self._reptag, obj.decode('utf-8'))
        #Match SuperSlicer Object information
        info = self.infomatch.match(line)
        if info:
            objinfo = json.loads(info.group(0)[9:])
            objname = objinfo['id'].encode('ascii','xmlcharrefreplace')
            line = "{0}info {1} X{2} Y{3}\n".format(self._reptag, objname.decode('utf-8'), objinfo['object_center'][0], objinfo['object_center'][1])

        #Match PrusaSlicer/SuperSlicer stop printing comments
        stop = self.stopmatch.match(line)
        if stop:
            stopobj = stop.group(1).encode('ascii','xmlcharrefreplace')
            line = "{0}stop {1}\n".format(self._reptag, stopobj.decode('utf-8'))
        return line
