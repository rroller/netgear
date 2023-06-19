"""
Custom integration to integrate Netgear WAX access points with Home Assistant.
"""
import asyncio
from datetime import timedelta
import logging
import time
from typing import Any, Dict, List

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Config, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import NetgearClient, Stat
from .client_wax import DeviceState, NetgearWaxClient, Ssid
from .const import CONF_ADDRESS, CONF_MAC, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, DOMAIN, PLATFORMS, STARTUP_MESSAGE

SCAN_INTERVAL_SECONDS = timedelta(seconds=60)

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup(hass: HomeAssistant, config: Config):
    """
    Set up this integration with the UI. YAML is not supported.
    https://developers.home-assistant.io/docs/asyncio_working_with_async/
    """
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up this integration using UI."""
    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})
        _LOGGER.info(STARTUP_MESSAGE)

    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)
    address = entry.data.get(CONF_ADDRESS)
    port = int(entry.data.get(CONF_PORT))
    mac = entry.data.get(CONF_MAC)

    coordinator = NetgearDataUpdateCoordinator(
        hass, address, port, username, password, mac
    )
    await coordinator.async_config_entry_first_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # https://developers.home-assistant.io/docs/config_entries_index/
    for platform in PLATFORMS:
        if entry.options.get(platform, True):
            hass.async_add_job(
                hass.config_entries.async_forward_entry_setup(entry, platform)
            )

    entry.add_update_listener(async_reload_entry)

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, coordinator.async_stop)
    )

    return True


class NetgearDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Netgear API."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        port: int,
        username: str,
        password: str,
        mac: str,
    ) -> None:
        """Initialize"""
        # TODO: Support multiple clients here
        self.client: NetgearClient = NetgearWaxClient(
            username,
            password,
            address,
            port,
            async_get_clientsession(hass, verify_ssl=False),
        )
        self.platforms = []
        self._initialized = False
        self._mac = mac
        self._state: DeviceState
        self._ssids: List[Ssid]
        self._firmware_last_checked: int = 0
        self._address = address

        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL_SECONDS
        )

    async def async_stop(self, event: Any):
        """Stop anything we need to stop"""
        # Log out is important, the device limits concurrent logins
        await self.client.async_logout()

    async def _async_update_data(self) -> DeviceState:
        """Reload information by fetching from the API"""
        # Only check for firmware updates every 6 hours
        check_firmware = False
        try:
            check_firmware = (time.time() - self._firmware_last_checked) > 21600

            if check_firmware:
                self._firmware_last_checked = time.time()
                await self.client.check_for_firmware_updates()
        except Exception as exception:
            # Not vital for this API to run so we'll pass on errors
            _LOGGER.info("Failed to check for firmware updates", exc_info=exception)
            pass

        try:
            self._state = await self.client.async_get_state(check_firmware)
            self._ssids = await self.client.async_get_ssids()
            self._initialized = True
        except Exception as exception:
            _LOGGER.debug("Failed to read current state", exc_info=exception)
            raise UpdateFailed() from exception

        return self._state

    def on_receive(self, data_bytes: bytes):
        data = data_bytes.decode("utf-8", errors="ignore")
        self.hass.bus.fire("netgear_event_received", data)

    def get_mac(self) -> str:
        return self._mac

    def get_ip_address(self) -> str:
        """
        Returns the IP address, example: 192.168.1.2
        """
        return self._address

    def get_device_name(self) -> str:
        return self._state.device_name

    def get_model(self) -> str:
        return self._state.model

    def get_firmware_version(self) -> str:
        return self._state.firmware_version

    def get_ssids(self) -> List[Ssid]:
        return self._ssids

    def get_ssids_by_ssid_id(self, ssid_id: str) -> List[Ssid]:
        ssids = []
        for ssid in self._ssids:
            if ssid_id == ssid.ssid_id:
                ssids.append(ssid)
        return ssids

    def is_firmware_update_available(self) -> bool:
        return self._state.firmware_update_available

    def total_number_of_devices(self) -> int:
        return self._state.total_number_of_devices

    def get_stats(self) -> Dict[str, Stat]:
        return self._state.stats


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_stop({})
    unloaded = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
                if platform in coordinator.platforms
            ]
        )
    )
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
