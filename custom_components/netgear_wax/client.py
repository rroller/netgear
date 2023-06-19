"""Netgear API Client."""
import abc
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(unsafe_hash=True)
class Ssid:
    ssid_id = ""
    ssid: str = ""
    vap: str = ""
    wlan_id: str = ""
    enabled: bool = False
    ssid_index: int = 0


@dataclass(unsafe_hash=True)
class Stat:
    utilization: int
    bytes_transferred: int


@dataclass(unsafe_hash=True)
class DeviceState:
    ssid: str = ""
    serial_number: str = ""
    mac_address: str = ""
    firmware_version: str = ""
    firmware_update_available: bool = False
    device_name: str = ""
    model: str = ""
    total_number_of_devices: int = 0
    # Key is: wlan0, wlan1, etc
    stats: Dict[str, Stat] = None


class NetgearClient(abc.ABC):
    """NetgearWaxClient is the client for accessing Netgear WAX access points"""

    def __init__(self) -> None:
        pass

    @abc.abstractmethod
    async def async_login(self):
        pass

    @abc.abstractmethod
    async def async_logout(self):
        pass

    @abc.abstractmethod
    async def async_get_state(
        self, check_firmware: Optional[bool] = False
    ) -> DeviceState:
        pass

    @abc.abstractmethod
    async def async_get_ssids(self) -> List[Ssid]:
        pass

    @abc.abstractmethod
    async def async_enable_ssid(self, ssids: List[Ssid], enable: bool):
        """async_enable_ssid will turn an ssid on or off"""
        pass

    @abc.abstractmethod
    async def check_for_firmware_updates(self):
        """check_for_firmware_updates tells the device to check for firmware updates"""
        pass
