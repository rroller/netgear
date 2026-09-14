"""
Custom integration to integrate Netgear WAX access points with Home Assistant.
"""
import asyncio
import time
from typing import Any, List, Dict
import logging

from datetime import timedelta

from homeassistant.core_config import Config
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.const import EVENT_HOMEASSISTANT_STOP

from .client import NetgearClient, Stat, WirelessClient
from .client_names import normalize_mac, useful_name
from .client_wax import NetgearWaxClient, DeviceState, Ssid

from .const import (
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    CONF_ADDRESS,
    DOMAIN,
    DATA_LOGBOOK_READY,
    EVENT_CLIENT_ACTIVITY,
    EVENT_LOGBOOK_READY,
    PLATFORMS,
    STARTUP_MESSAGE, CONF_MAC,
)

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
        hass, address, port, username, password, mac, entry.entry_id
    )
    await coordinator.async_config_entry_first_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # https://developers.home-assistant.io/docs/config_entries_index/
    for platform in PLATFORMS:
        if entry.options.get(platform, True):
            coordinator.platforms.append(platform)
            await hass.config_entries.async_forward_entry_setups(entry, [platform])

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
        entry_id: str,
    ) -> None:
        """Initialize"""
        # TODO: Support multiple clients here
        self.client: NetgearClient = NetgearWaxClient(username, password, address, port,
                                                      async_get_clientsession(hass, verify_ssl=False))
        self.platforms = []
        self._initialized = False
        self._mac = mac
        self._entry_id = entry_id
        self._state: DeviceState
        self._ssids: List[Ssid]
        self._wireless_clients: List[WirelessClient] = []
        self._device_id: str | None = None
        self._initial_client_activity_logged = False
        self._unsub_logbook_ready = hass.bus.async_listen(
            EVENT_LOGBOOK_READY, self._async_handle_logbook_ready
        )
        self._firmware_last_checked: int = 0
        self._address = address

        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL_SECONDS)

    async def async_stop(self, event: Any):
        """ Stop anything we need to stop """
        self._unsub_logbook_ready()
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
            radios = ["wlan0", "wlan1"]
            if "wlan2" in self._state.stats:
                radios.append("wlan2")
            wireless_clients = await self.client.async_get_wireless_clients(radios)
            if self._initialized:
                self._async_log_client_activity(
                    self._wireless_clients, wireless_clients
                )
            self._wireless_clients = wireless_clients
            self._initialized = True
        except Exception as exception:
            _LOGGER.debug("Failed to read current state", exc_info=exception)
            raise UpdateFailed() from exception

        return self._state

    def _async_log_client_activity(
        self,
        previous_clients: List[WirelessClient],
        current_clients: List[WirelessClient],
    ) -> None:
        """Add client connect and disconnect events to this AP's activity feed."""
        previous_by_mac = {
            client.mac_address.lower(): client
            for client in previous_clients
            if client.mac_address
        }
        current_by_mac = {
            client.mac_address.lower(): client
            for client in current_clients
            if client.mac_address
        }

        if self._device_id is None:
            return

        for mac_address in current_by_mac.keys() - previous_by_mac.keys():
            self._async_log_client_event(current_by_mac[mac_address], "connected")
        for mac_address in previous_by_mac.keys() - current_by_mac.keys():
            self._async_log_client_event(previous_by_mac[mac_address], "disconnected")

    def register_device_activity(self) -> None:
        """Associate client activity with this access point's device."""
        device_registry = dr.async_get(self.hass)
        if hasattr(device_registry, "async_get_device_by_identifier"):
            device = device_registry.async_get_device_by_identifier(
                (DOMAIN, self.get_mac()), self._entry_id
            )
        else:
            # Support Home Assistant versions before device identifiers became
            # scoped to a config entry.
            device = device_registry.async_get_device(
                identifiers={(DOMAIN, self.get_mac())}
            )
        if device is None:
            _LOGGER.warning("Unable to find device for connected-client activity")
            return
        self._device_id = device.id

        if self.hass.data[DOMAIN].get(DATA_LOGBOOK_READY):
            self._async_log_initial_client_activity()

    @callback
    def _async_handle_logbook_ready(self, event: Any) -> None:
        """Log current clients once the custom logbook event is registered."""
        self._async_log_initial_client_activity()

    def _async_log_initial_client_activity(self) -> None:
        """Record the clients found during the first coordinator refresh."""
        if self._initial_client_activity_logged or self._device_id is None:
            return
        self._initial_client_activity_logged = True

        # The first coordinator refresh runs before entities are created. Record
        # the clients it found now that the logbook event is ready to render.
        for client in self._wireless_clients:
            if client.mac_address:
                self._async_log_client_event(client, "was detected as connected")

    def _async_log_client_event(self, client: WirelessClient, activity: str) -> None:
        """Write a client event associated with this access point."""
        if self._device_id is None:
            return

        label = self._client_activity_name(client)
        if label != client.mac_address:
            label = f"{label} ({client.mac_address})"

        network = ""
        if client.ssid:
            network = f" on {client.ssid}"
        if client.radio:
            network += f" ({client.radio})"

        self.hass.bus.async_fire(
            EVENT_CLIENT_ACTIVITY,
            {
                "device_id": self._device_id,
                "name": self.get_device_name(),
                "message": f"{label} {activity}{network}",
            },
        )

    def _client_activity_name(self, client: WirelessClient) -> str:
        """Prefer the AP hostname, then a locally registered device name."""
        if hostname := useful_name(client.hostname, client.mac_address):
            return hostname

        registry = dr.async_get(self.hass)
        connections = {(dr.CONNECTION_NETWORK_MAC, normalize_mac(client.mac_address))}
        if hasattr(registry, "async_get_devices"):
            devices = registry.async_get_devices(connections=connections)
        else:
            # Compatibility with Home Assistant before the multi-device API.
            device = registry.async_get_device(connections=connections)
            devices = [device] if device else []

        # User-assigned names take precedence across matching integrations.
        for attribute in ("name_by_user", "name"):
            for device in sorted(devices, key=lambda item: item.id):
                if name := useful_name(getattr(device, attribute), client.mac_address):
                    return name

        return useful_name(client.username, client.mac_address) or client.mac_address

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

    def get_wireless_clients(self) -> List[WirelessClient]:
        """Return the wireless clients associated with this access point."""
        return self._wireless_clients

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
