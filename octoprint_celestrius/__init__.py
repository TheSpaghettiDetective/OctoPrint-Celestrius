# coding=utf-8
from __future__ import absolute_import
from threading import Thread, RLock
from datetime import datetime
import os
import subprocess
import logging
import requests
import time
import re
import psutil
import shutil
from google.cloud import storage


### (Don't forget to remove me)
# This is a basic skeleton for your plugin's __init__.py. You probably want to adjust the class name of your plugin
# as well as the plugin mixins it's subclassing from. This is really just a basic skeleton to get you started,
# defining your plugin as a template plugin, settings and asset plugin. Feel free to add or remove mixins
# as necessary.
#
# Take a look at the documentation on what other plugin mixins are available.

import octoprint.plugin

_logger = logging.getLogger('octoprint.plugins.celestrius')

class CelestriusPlugin(octoprint.plugin.SettingsPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.WizardPlugin
):

    def __init__(self):
        self._mutex = RLock()
        self.current_flow_rate = 1.0
        self.current_z_offset = None


    ##~~ SettingsPlugin mixin

    def get_settings_defaults(self):
        return {
            'snapshot_url': 'http://localhost:8080/?action=snapshot',
            'enabled': False,
            'pilot_email': None,
        }

    ##~~ AssetPlugin mixin

    def get_assets(self):
        # Define your plugin's asset files to automatically include in the
        # core UI here.
        return {
            "js": ["js/celestrius.js"],
            "css": ["css/celestrius.css"],
            "less": ["less/celestrius.less"]
        }

	##~~ TemplatePlugin mixin

    # def get_template_configs(self):
    #     return [
    #         dict(type="navbar"),
    #         dict(type="settings", custom_bindings=True)
    #     ]

    ##########
    ### Wizard
    ##########

    def is_wizard_required(self):
        return True

    def get_wizard_version(self):
        return 1

    ##~~ Softwareupdate hook

    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://docs.octoprint.org/en/master/bundledplugins/softwareupdate.html
        # for details.
        return {
            "celestrius": {
                "displayName": "Celestrius Data Collector",
                "displayVersion": self._plugin_version,

                # version check: github repository
                "type": "github_release",
                "user": "TheSpaghettiDetective",
                "repo": "OctoPrint-Celestrius",
                "current": self._plugin_version,

                # update method: pip
                "pip": "https://github.com/TheSpaghettiDetective/OctoPrint-Celestrius/archive/{target_version}.zip",
            }
        }


    def on_after_startup(self):
        main_thread = Thread(target=self.main_loop)
        main_thread.daemon = True
        main_thread.start()

    # Private methods

    def main_loop(self):
        last_collect = 0.0
        data_dirname = None
        while True:
            if self._printer.get_state_id() in ['PRINTING', 'PAUSING', 'RESUMING', ]:
                if not self._settings.get(["enabled"]):
                    continue

                if data_dirname == None:
                    filename = self._printer.get_current_job().get('file', {}).get('name')
                    if not filename:
                        continue

                    print_id = str(int(datetime.now().timestamp()))
                    data_dirname = os.path.join(self._data_folder, f'{filename}.{print_id}')
                    os.makedirs(data_dirname, exist_ok=True)

                ts = datetime.now().timestamp()
                if ts - last_collect >= 0.4:
                    last_collect = ts
                    jpg = self.capture_jpeg()
                    with open(f'{data_dirname}/{ts}.jpg', 'wb') as f:
                        f.write(jpg)
                    with open(f'{data_dirname}/{ts}.labels', 'w') as f:
                        with self._mutex:
                            f.write(f'flow_rate:{self.current_flow_rate}')

            elif self._printer.get_state_id() in ['PAUSED']:
                pass
            else:
                if data_dirname is not None:
                    data_dirname_to_compress = data_dirname
                    compress_thread = Thread(target=self.compress_and_upload, args=(data_dirname_to_compress,))
                    compress_thread.daemon = True
                    compress_thread.start()
                data_dirname = None

            time.sleep(0.02)

    def capture_jpeg(self):
        snapshot_url = self._settings.get(["snapshot_url"])
        if snapshot_url:
            r = requests.get(snapshot_url, stream=True, timeout=5, verify=False )
            r.raise_for_status()
            jpg = r.content
            return jpg

    def sent_gcode(self, comm_instance, phase, cmd, cmd_type, gcode, subcode=None, tags=None, *args, **kwargs):
        if gcode == 'M221':
            match = re.search(r's(\d+)', cmd, re.IGNORECASE)

            if match:
                with self._mutex:
                    self.current_flow_rate = float(match.group(1)) / 100.0

    def compress_and_upload(self, data_dirname):
        parent_dir_name = os.path.dirname((data_dirname))
        basename = os.path.basename((data_dirname))
        tarball_filename = data_dirname + '.tgz'
        _logger.info('Compressing ' + basename)
        proc = psutil.Popen(['tar', '-C', parent_dir_name, '-zcf', tarball_filename, basename], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.nice(10)
        returncode = proc.wait()
        (stdoutdata, stderrdata) = proc.communicate()
        msg = 'RETURN:\n{}\nSTDOUT:\n{}\nSTDERR:\n{}\n'.format(returncode, stdoutdata, stderrdata)
        _logger.debug(msg)
        shutil.rmtree(data_dirname, ignore_errors=True)
        _logger.info('Deleting ' + basename)
        _logger.info('Uploading ' + tarball_filename)
        self.upload_to_data_bucket(tarball_filename)
        _logger.info('Done')

    def upload_to_data_bucket(self, filename):
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'celestrius-data-collector.json')

        client = storage.Client()
        bucket = client.bucket('celestrius-data-collection')
        basename = os.path.basename((filename))
        with open(filename, 'rb') as f:
            blob = bucket.blob(f'{self._settings.get(["pilot_email"])}/{basename}')
            blob.upload_from_file(f)


# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "Celestrius Data Collector"


# Set the Python version your plugin is compatible with below. Recommended is Python 3 only for all new plugins.
# OctoPrint 1.4.0 - 1.7.x run under both Python 3 and the end-of-life Python 2.
# OctoPrint 1.8.0 onwards only supports Python 3.
__plugin_pythoncompat__ = ">=3,<4"  # Only Python 3

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = CelestriusPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
        "octoprint.comm.protocol.gcode.sent": __plugin_implementation__.sent_gcode
    }