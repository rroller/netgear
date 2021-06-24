"""Binary sensor platform for netgear."""
import logging
import re

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from custom_components.netgear import NetgearDataUpdateCoordinator, Ssid

from .const import (
    DOMAIN, CONNECTIVITY_DEVICE_CLASS,
)
from .entity import NetgearBaseEntity

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_devices):
    """Setup binary_sensor platform."""
    coordinator: NetgearDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    pass


class NetgearEventSensor(NetgearBaseEntity, BinarySensorEntity):
    """
    netgear binary_sensor class to record events. Many of these events are configured in the camera UI by going to:
    """

    def __init__(self, coordinator: NetgearDataUpdateCoordinator, config_entry, ssid: Ssid):
        NetgearBaseEntity.__init__(self, coordinator, config_entry)
        BinarySensorEntity.__init__(self)

        # event_name is the event name, example: VideoMotion, CrossLineDetection, SmartMotionHuman, etc
        self._coordinator = coordinator
        self._device_name = coordinator.get_device_name()
        self._device_class = CONNECTIVITY_DEVICE_CLASS
        self._name = ssid.ssid

        # Build the unique ID. This will convert the name to lower underscores. For example, "Smart Motion Vehicle" will
        # become "smart_motion_vehicle" and will be added as a suffix to the device serial number
        self._unique_id = coordinator.get_mac() + "_" + self._name.lower().replace(" ", "_")

    @property
    def unique_id(self):
        """Return the entity unique ID."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of the binary_sensor. Example: Cam14 Motion Alarm"""
        return f"{self._device_name} {self._name}"

    @property
    def device_class(self):
        """Return the class of this binary_sensor, Example: motion"""
        return self._device_class

    @property
    def is_on(self):
        """
        Return true if the event is activated.

        This is the magic part of this sensor along with the async_added_to_hass method below.
        The async_added_to_hass method adds a listener to the coordinator so when the event is started or stopped
        it calls the async_write_ha_state function. async_write_ha_state gets the current value from this is_on method.
        """
        return False
        # return self._coordinator.get_event_timestamp(self._event_name) > 0

    async def async_added_to_hass(self):
        """Connect to dispatcher listening for entity data notifications."""
        # self._coordinator.add_netgear_event_listener(self._event_name, self.async_write_ha_state)

    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state.  False if entity pushes its state to HA"""
        return True
