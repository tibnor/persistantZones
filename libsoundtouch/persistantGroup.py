from libsoundtouch import discover_devices
from requests.exceptions import ConnectionError
from urllib3.exceptions import NewConnectionError
import time
import json
import os
import sys
import logging
import http.server
from urllib import parse
import threading
from typing import List

__main_path__ = os.path.dirname(os.path.realpath(sys.argv[0]))

with open(__main_path__ + "/../persistant.cfg", 'r') as f:
    config = json.load(f)

global merged_zones
merged_zones = False

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.INFO)
fh = logging.FileHandler(__main_path__ + "/../persistantGroup.log")
fh.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
_LOGGER.addHandler(fh)


class deviceExt():
    def __init__(self, device):
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

    def __del__(self):
        self.stop()

    def __str__(self):
        return "Device, device name: %s" % self.device.config.name

    def stop(self):
        self.device.stop_notification()

    def update_responding(self):
        if self.was_responding:
            on_pong_time = self.device.is_pong_on_time()
            if (not on_pong_time):
                self.device.stop_notification()
                _LOGGER.warn(self.device.config.name + " is offline (lost ping)")
                self.was_responding = False

        responding = self.is_responding()
        if responding and not self.was_responding:
            self.device.start_notification()
            _LOGGER.warning(self.device.config.name + " is online")
        elif (not responding) and self.was_responding:
            self.device.stop_notification()
            _LOGGER.warning(self.device.config.name + " is offline (lost get)")
        self.was_responding = responding

    def is_responding(self):
        try:
            self.isOn()
            return True
        except (ConnectionError, NewConnectionError):
            return False

    def isEqualDevice(self, device):
        cfg0 = self.device.config
        cfg1 = device.config
        if cfg0.device_id != cfg1.device_id:
            return False
        if cfg0.device_ip != cfg1.device_ip:
            return False
        return True

    def close(self):
        self.device.stop_notification()
        _LOGGER.warn("Offline: " + self.device.config.name)

    def isOn(self, status=None):
        if status is None:
            status = self.device.status()
        return status.source != "STANDBY"

    def status_listener(self, status):
        ison = self.isOn(status)
        if ison != self._wasOn:
            self._wasOn = ison
            if self._power_listener is not None:
                self._power_listener(ison)

    def _power_listener(self, ison):
        global merged_zones
        if ison and not merged_zones and self.turnAllOn:
            self._group()
        elif ison and merged_zones and self.turnAllOn and not self.remoteTurnOn:
            self._add_to_group()
        elif not ison and merged_zones and self.turnAllOn:
            self._turnOffAll()

    def _group(self):
        _LOGGER.info("Merge all to a zone")
        global merged_zones
        merged_zones = True
        slaves = []
        for dev in devices:
            if dev is not self and dev.remoteTurnOn:
                slaves.append(dev.device)
        if len(slaves) > 0:
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


devices = []


class MyHandler(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

    def do_GET(self):
        """Respond to a GET request."""
        parsed_path = parse.urlparse(self.path)
        message = '\r\n' + parsed_path.path

        if parsed_path.path == "/off":
            print("checking devices off")
            for d in devices:
                if d.isOn():
                    d._turnOffAll()
                    print("Turn off")
                    break
        self.send_response(200)
        self.send_header('Content-Type',
                         'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(message.encode('utf-8'))


HOST_NAME = 'localhost'
PORT_NUMBER = 8003
server_class = http.server.HTTPServer
httpd = server_class((HOST_NAME, PORT_NUMBER), MyHandler)
thread = threading.Thread(target=httpd.serve_forever)
thread.start()

while True:
    #    _LOGGER.info("Start searching for devices")
    new_devices = discover_devices(timeout=10)
    _LOGGER.info("Found %d devices" % len(new_devices))

    # Check if all devices are still found and not changed IP
    for old_dev in devices[:]:
        is_found = False
        for dev in new_devices:
            mac_new = dev.config.mac_address
            mac_old = old_dev.device.config.mac_address
            if mac_new == mac_old:
                ip_new = dev.config.device_ip
                ip_old = old_dev.device.config.device_ip
                is_found = ip_new == ip_old
                break

        if not is_found:
            _LOGGER.info("Did not find %s" % old_dev.device.config.name)
            old_dev.stop()
            devices.remove(old_dev)

    # Check if any devices are new
    for dev in new_devices:
        is_found = False
        for old_dev in devices:
            mac_new = dev.config.mac_address
            mac_old = old_dev.device.config.mac_address
            if mac_new == mac_old:
                is_found = True
                break

        if not is_found:
            _LOGGER.info("New device: %s" % dev.config.name)
            devices.append(deviceExt(dev))

    for dev in devices:
        dev.update_responding()
    time.sleep(120)
