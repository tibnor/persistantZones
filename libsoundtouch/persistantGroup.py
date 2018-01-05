from libsoundtouch import discover_devices
from requests.exceptions import ConnectionError
import time
import json
import os
import sys
import logging

__main_path__ = os.path.dirname(os.path.realpath(sys.argv[0]))


with open(__main_path__+"/../persistant.cfg", 'r') as f:
    config = json.load(f)

global merged_zones
merged_zones = False

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)
fh = logging.FileHandler(__main_path__+"/../persistantGroup.log")
fh.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
_LOGGER.addHandler(fh)

class deviceExt():
    def __init__(self,device):
        self.device = device
        self._wasOn = self.isOn()
        device.add_status_listener(self.status_listener)
        device.start_notification()
        if device.config.device_id in config:
            cfg = config[device.config.device_id]
            self.turnAllOn = cfg["turnAllOn"]
            self.remoteTurnOn = cfg["remoteTurnOn"]
        else:
            self.turnAllOn = True
            self.remoteTurnOn = True
        _LOGGER.info("Online: " + device.config.name + " (" + device.config.device_id + ")")
        self.was_responding = self.is_responding()

    def update_responding(self):
        if self.was_responding:
            on_pong_time = self.device.is_pong_on_time()
            if (not on_pong_time):
                self.device.stop_notification()
                _LOGGER.warn(self.device.config.name + " is offline (lost ping)")
                self.was_responding = False

        responding = self.is_responding()
        if (responding and not self.was_responding):
            self.device.start_notification()
            _LOGGER.warn(self.device.config.name + " is online")
        elif ((not responding) and self.was_responding):
            self.device.stop_notification()
            _LOGGER.warn(self.device.config.name + " is offline (lost get)")
        self.was_responding = responding

    def is_responding(self):
        try:
            self.isOn()
            return True
        except ConnectionError:
            return False

    def isEqualDevice(self,device):
        cfg0 = self.device.config
        cfg1 = device.config
        if cfg0.device_id != cfg1.device_id:
            return False
        if cfg0.device_ip != cfg1.device_ip:
            return False
        return True

    def close(self):
        self.device.stop_notification()
        _LOGGER.warn("Offline: "+ self.device.config.name)

    def isOn(self,status = None):
        if status == None:
            status=self.device.status()
        return status.source != "STANDBY"

    def status_listener(self,status):
        ison = self.isOn(status)
        if (ison != self._wasOn):
            self._wasOn = ison
            if (self._power_listener != None):
                self._power_listener(ison)


    def _power_listener(self,ison):
        global merged_zones
        if(ison and not merged_zones and self.turnAllOn):
            self._group()
        elif(ison and merged_zones and self.turnAllOn and not self.remoteTurnOn):
            self._add_to_group()
        elif(not ison and merged_zones and self.turnAllOn):
            self._turnOffAll()

    def _group(self):
        _LOGGER.info("Merge all to a zone")
        global merged_zones
        merged_zones = True
        slaves = []
        for dev in devices:
            if dev is not self and dev.remoteTurnOn:
                slaves.append(dev.device)
        self.device.create_zone(slaves)

    def _add_to_group(self):
        _LOGGER.info("Add device to zone")
        for dev in devices:
            zone_status = dev.device.zone_status()
            if zone_status:
                if zone_status.is_master:
                    dev.device.add_zone_slave([self.device])

    def _turnOffAll(self):
        _LOGGER.info("Turn off all devices")
        global merged_zones
        merged_zones = False
        for dev in devices:
            zone_status = dev.device.zone_status()
            if zone_status:
                if zone_status.is_master:
                    dev.device.power_off()



_LOGGER.info("Start searching for devices")
devices = discover_devices(timeout=10)
_LOGGER.info("End searching for devices, found %d devices" % len(devices))
devs = []
for dev in devices:
    devs.append(deviceExt(dev))
devices = devs

notResponding = []
while True:
    for dev in devices:
        dev.update_responding()
    time.sleep(10)
