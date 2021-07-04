"""Switch platform for netgear."""
import logging
import time
from typing import List

from homeassistant.core import HomeAssistant
from homeassistant.components.switch import SwitchEntity
from custom_components.netgear import NetgearDataUpdateCoordinator, Ssid

from .const import DOMAIN, CONNECTIVITY_DEVICE_CLASS, WIFI_ICON
from .entity import NetgearBaseEntity

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_devices):
    """Setup switch platform."""
    coordinator: NetgearDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    added = set()
    switches: List[NetgearSsidBinarySwitch] = []
    for ssid in coordinator.get_ssids():
        if ssid.ssid is not None and ssid.ssid not in added:
            added.add(ssid.ssid)
            switches.append(NetgearSsidBinarySwitch(coordinator, entry, ssid))

    if switches:
        async_add_devices(switches)


class NetgearSsidBinarySwitch(NetgearBaseEntity, SwitchEntity):
    """netgear SSID switch class. Used to enable or disable Wi-Fi SSIDs"""

    def __init__(self, coordinator: NetgearDataUpdateCoordinator, config_entry, ssid: Ssid):
        NetgearBaseEntity.__init__(self, coordinator, config_entry)
        SwitchEntity.__init__(self)

        self._coordinator = coordinator
        self._device_class = CONNECTIVITY_DEVICE_CLASS
        self._ssid_id = ssid.ssid_id
        self._name = f"{coordinator.get_device_name()} {ssid.ssid}"
        self._unique_id = f"{coordinator.get_mac()}_{ssid.ssid_index}"
        self._last_flipped_time: int = 0
        self._last_flipped_state: bool = False

    async def async_turn_on(self, **kwargs):  # pylint: disable=unused-argument
        """Turn on the ssid"""
        self._last_flipped_time = time.time()
        self._last_flipped_state = True
        self.hass.async_create_task(self.work_on(True))

    async def async_turn_off(self, **kwargs):  # pylint: disable=unused-argument
        """Turn off the ssid"""
        self._last_flipped_time = time.time()
        self._last_flipped_state = False
        self.hass.async_create_task(self.work_on(False))

    async def work_on(self, enabled: bool):
        ssids = self._coordinator.get_ssids_by_ssid_id(self._ssid_id)
        await self._coordinator.client.async_enable_ssid(ssids, enabled)
        await self._coordinator.async_refresh()


    @property
    def name(self):
        """Return the name of the switch"""
        return self._name

    @property
    def unique_id(self):
        """
        A unique identifier for this entity. Needs to be unique within a platform (ie light.hue). Should not be
        configurable by the user or be changeable see
        https://developers.home-assistant.io/docs/entity_registry_index/#unique-id-requirements
        """
        return self._unique_id

    @property
    def is_on(self):
        """ Return true if the ssid is enabled """
        ssids = self._coordinator.get_ssids_by_ssid_id(self._ssid_id)

        # The API to enable or disable an ssid is very slow. It can take 20 seconds to complete.
        # During that time the switch in the UI might jump back to the oposite state. So for for the
        # time below, we'll just assume the state we attempted to put it in to avoid a weird UI issue
        if time.time() - self._last_flipped_time <= 30:
            _LOGGER.debug("Returning assumed state %s", self._last_flipped_state)
            return self._last_flipped_state

        if len(ssids) > 0:
            return ssids[0].enabled
        return False

    @property
    def icon(self):
        """Return the icon of this switch."""
        return WIFI_ICON
