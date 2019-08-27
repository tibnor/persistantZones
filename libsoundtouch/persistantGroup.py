from libsoundtouch import discover_devices, SoundTouchDevice
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
from typing import List, Optional

__main_path__ = os.path.dirname(os.path.realpath(sys.argv[0]))

with open(__main_path__ + "/../persistant.cfg", 'r') as f:
    config = json.load(f)

logging.basicConfig(level=logging.ERROR)
_LOGGER = logging.getLogger(__name__)
fh = logging.FileHandler(__main_path__ + "/../persistantGroup.log")
fh.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
_LOGGER.addHandler(fh)


class DeviceSet:
    devices: List['DeviceExtender'] = []

    @staticmethod
    def get_devices() -> List['DeviceExtender']:
        return DeviceSet.devices

    @staticmethod
    def add_device(device: 'DeviceExtender'):
        DeviceSet.devices.append(device)

    @staticmethod
    def remove_device(device: 'DeviceExtender'):
        DeviceSet.devices.remove(device)

    @staticmethod
    def get_master() -> Optional['DeviceExtender']:
        for d in DeviceSet.get_devices():
            zone_status = d.device.zone_status()
            if zone_status:
                if zone_status.is_master:
                    return d
        return None

    @staticmethod
    def set_volume(volume: float):
        master = DeviceSet.get_master()
        if master is None:
            return

        old_volume: float = master.device.volume().actual
        dv = volume - old_volume
        for d in DeviceSet.get_devices():
            if d.is_on():
                old_volume = d.device.volume().actual
                new_volume = max(min(old_volume + dv, 100), 0)
                _LOGGER.info('Changing volume of %s from %f to %f' % (d.device.config.name, old_volume, new_volume))
                d.device.set_volume(new_volume)

    @staticmethod
    def turn_off_all():
        _LOGGER.info("Turn off all devices")
        DeviceExtender.merged_zones = False
        d = DeviceSet.get_master()
        if d is not None:
            d.device.power_off()


class DeviceExtender:
    merged_zones = False

    def __init__(self, device: SoundTouchDevice) -> None:
        self.device = device
        self._wasOn = self.is_on()
        device.add_status_listener(self.status_listener)
        device.start_notification()
        if device.config.device_id in config:
            cfg = config[device.config.device_id]
            self.turnAllOn = cfg["turnAllOn"]
            self.remoteTurnOn = cfg["remoteTurnOn"]

        else:
            self.turnAllOn = True
            self.remoteTurnOn = True
        _LOGGER.info("Online: " + device.config.name + " (" + device.config.device_id + ", "+device.config.device_ip+")")
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
            if not on_pong_time:
                self.device.stop_notification()
                _LOGGER.warning(self.device.config.name + " is offline (lost ping)")
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
            self.is_on()
            return True
        except (ConnectionError, NewConnectionError):
            return False

    def is_equal_device(self, device):
        cfg0 = self.device.config
        cfg1 = device.config
        if cfg0.device_id != cfg1.device_id:
            return False
        if cfg0.device_ip != cfg1.device_ip:
            return False
        return True

    def close(self):
        self.device.stop_notification()
        _LOGGER.warning("Offline: " + self.device.config.name)

    def is_on(self, status=None):
        if status is None:
            status = self.device.status()
        return status.source != "STANDBY"

    def status_listener(self, status):
        _LOGGER.info("New status: %s" % status)
        is_on = self.is_on(status)
        if is_on != self._wasOn:
            self._wasOn = is_on
            if self._power_listener is not None:
                self._power_listener(is_on)

    def _power_listener(self, ison):
        mz = DeviceExtender.merged_zones
        if ison and not mz and self.turnAllOn:
            self._group()
        elif ison and mz and self.turnAllOn and not self.remoteTurnOn:
            self._add_to_group()
        elif not ison and mz and self.turnAllOn:
            DeviceSet.turn_off_all()

    def _group(self):
        _LOGGER.info("Merge all to a zone")
        DeviceExtender.merged_zones = True
        slaves = []
        for d in DeviceSet.get_devices():
            if d is not self and d.remoteTurnOn:
                slaves.append(d.device)
        if len(slaves) > 0:
            self.device.create_zone(slaves)

    def _add_to_group(self):
        _LOGGER.info("Add device to zone")
        for d in DeviceSet.get_devices():
            zone_status = d.device.zone_status()
            if zone_status:
                if zone_status.is_master:
                    d.device.add_zone_slave([self.device])


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
            _LOGGER.info("Turn off all devices")
            DeviceSet.turn_off_all()
        elif parsed_path.path == "/volume":
            qs = parse.parse_qs(parsed_path.query)
            try:
                volume = float(qs['volume'][0])
            except KeyError:
                pass
            else:
                DeviceSet.set_volume(volume)

        self.send_response(200)
        self.send_header('Content-Type',
                         'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(message.encode('utf-8'))


def start_server():
    host_name = ''
    port_number = 8003
    server_class = http.server.HTTPServer
    httpd = server_class((host_name, port_number), MyHandler)
    thread = threading.Thread(target=httpd.serve_forever)
    thread.start()


def run_device_checker_loop():
    while True:
        #    _LOGGER.info("Start searching for devices")
        new_devices = discover_devices(timeout=10)
        _LOGGER.info("Found %d devices" % len(new_devices))

        # Check if all devices are still found and not changed IP
        for old_dev in DeviceSet.get_devices()[:]:
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
                DeviceSet.remove_device(old_dev)

        # Check if any devices are new
        for dev in new_devices:
            is_found = False
            for old_dev in DeviceSet.get_devices():
                mac_new = dev.config.mac_address
                mac_old = old_dev.device.config.mac_address
                if mac_new == mac_old:
                    is_found = True
                    break

            if not is_found:
                _LOGGER.info("New device: %s" % dev.config.name)
                DeviceSet.add_device(DeviceExtender(dev))

        for dev in DeviceSet.get_devices():
            dev.update_responding()
            time.sleep(120)


if __name__ == "__main__":
    start_server()
    run_device_checker_loop()
