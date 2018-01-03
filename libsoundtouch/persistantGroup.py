from libsoundtouch import discover_devices
from requests.exceptions import ConnectionError
import time

global merged_zones
merged_zones = False

#Stue - F45EAB309C61
#KjÃ¸kken - A81B6A1DEC47
#Bad - A81B6A1E0104
#Soverom - 68C90BB8AFE0
zoneMembers = ["F45EAB309C61","A81B6A1DEC47","A81B6A1E0104"]

class deviceExt():
    def __init__(self,device):
        self.device = device
        self._wasOn = self.isOn()
        device.add_status_listener(self.status_listener)
        device.start_notification()
        print("Online: " + device.config.name)
        self.was_responding = self.is_responding()

    def update_responding(self):
        responding = self.is_responding()
        if (responding and not self.was_responding):
            self.device.start_notification()
            print(self.device.config.name + " is online")
        elif ((not responding) and self.was_responding):
            self.device.stop_notification()
            print(self.device.config.name + " is offline")
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
        print("Offline: "+ self.device.config.name)

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
        slaves = []
        global merged_zones
        if(ison and not merged_zones):
            merged_zones = True
            for dev in devices:
                if dev is not self and dev.device.config.device_id in zoneMembers:
                    slaves.append(dev.device)

            self.device.create_zone(slaves)
        elif(not ison and merged_zones):
            merged_zones = False
            for dev in devices:
                zone_status = dev.device.zone_status()
                if zone_status:
                    if zone_status.is_master:
                        dev.device.power_off()



devices = discover_devices(timeout=10)
devs = []
for dev in devices:
    devs.append(deviceExt(dev))
devices = devs

notResponding = []
while True:
    for dev in devices:
        dev.update_responding()
    time.sleep(10)
#     print("Searching")
#     new_devices = discover_devices(timeout=10)
#     #print("End search")
#
#     for dExisting in devices[:]:
#         exists = False
#         for dev in new_devices:
#             if dExisting.isEqualDevice(dev):
#                 exists = True
#         if not exists:
#             dExisting.close()
#             devices.remove(dExisting)
#
#
#
#     for dev in new_devices:
#         exists = False
#         for dExisting in devices:
#             if dExisting.isEqualDevice(dev):
#                 exists = True
#         if not exists:
#             devices.append(deviceExt(dev))
#
#     time.sleep(60)  # Wait for events

# devices = []
# while True:
#     print("Searching")
#     new_devices = discover_devices(timeout=10)
#     #print("End search")
#
#     for dExisting in devices[:]:
#         exists = False
#         for dev in new_devices:
#             if dExisting.isEqualDevice(dev):
#                 exists = True
#         if not exists:
#             dExisting.close()
#             devices.remove(dExisting)
#
#
#
#     for dev in new_devices:
#         exists = False
#         for dExisting in devices:
#             if dExisting.isEqualDevice(dev):
#                 exists = True
#         if not exists:
#             devices.append(deviceExt(dev))
#
#     time.sleep(60)  # Wait for events
