from threading import Thread, RLock
import logging
from octoprint.events import Events  # pylint: disable=import-error

_logger = logging.getLogger('octoprint.plugins.celestrius')

class ZOffset():

  def __init__(self, plugin):
    self.plugin = plugin

    self._mutex = RLock()
    self.prusa_zoffset_following = False
    self.z_offset = None
    self.prusa_firmware = False

  def on_event(self, event, payload):
      if event == 'Connected':
          self.plugin._printer.commands(['M851'])
      elif event == Events.FIRMWARE_DATA:
          _logger.debug('Get firmware data: %s - %s',
                              payload.get('name'), payload.get('data'))
          firmware_name = payload.get('name')
          if firmware_name:
              self.prusa_firmware = 'prusa' in firmware_name.lower()

  def received_gcode(self, comm, line, *args, **kwargs):
      if not line:
          return line
      line_lower = line.lower().strip()

      if self.prusa_zoffset_following:
          self.prusa_zoffset_following = False
          _logger.debug('Z offset value (prusa): %s', line_lower)
          self.set_z_offset_from_printer_response(line_lower)
          return line
      if len(line_lower) < 3:
          return line
      elif 'zprobe_zoffset' in line_lower:
          _logger.debug('CR3D M851 echo: %s', line_lower)
          self.set_z_offset_from_printer_response(line_lower.split('=')[-1])
      elif 'probe z offset:' in line_lower:
          _logger.debug('Marlin 1.x M851 echo: %s', line_lower)
          self.set_z_offset_from_printer_response(line_lower.split(':')[-1])
      elif line_lower.endswith('z offset') and self.prusa_firmware:
          _logger.debug('Prusa M851 echo: z offset may follow')
          self.prusa_zoffset_following = True
      elif 'z offset' in line_lower:
          _logger.debug(
              'CR3D variant echo to M851Z[VALUE]: %s', line_lower)
          self.set_z_offset_from_printer_response(line_lower.split(' ')[-1])
      elif 'm851' in line_lower or 'probe offset ' in line_lower:
          _logger.debug('Marlin 2.x M851 echo: %s', line_lower)
          self.set_z_offset_from_gcode(line_lower.replace('probe offset', ''))
      elif '?z out of range' in line_lower:
          _logger.error('Setting z offset: %s', line_lower)
          self._printer.commands(['M851'])
      return line

  def set_z_offset_from_printer_response(self, offset):
      offset = offset.strip().replace(' ', '').replace('"', '')
      if not offset:
          _logger.warning('Offset part is empty !')
          return
      if not offset.replace('-', '', 1).replace('.', '', 1).isdigit():
          _logger.warning('Unable to extract Z offset from "%s"', offset)
          return
      _logger.info('Z probe offset is now %s', offset)
      self.z_offset = float(offset)

  def set_z_offset_from_gcode(self, line):
      offset_map = line.lower().replace('m851', '').split()
      z_part = list(filter(lambda v: v.startswith('z'), offset_map))
      if not z_part:
          _logger.warning('Bad M851 response: %s', line)
          return
      self.set_z_offset_from_printer_response(z_part[0][1:])
