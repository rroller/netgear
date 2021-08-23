"""Binary sensor platform for netgear_wax."""
import logging
from typing import List

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant

from . import NetgearDataUpdateCoordinator
from .const import (
    DOMAIN, SAFETY_DEVICE_CLASS,
)
from .entity import NetgearBaseEntity

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_devices):
    """Setup binary_sensor platform."""
    coordinator: NetgearDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    sensors: List[BinarySensorEntity] = []

    # sensors.append(NetgearBinarySensor(coordinator, entry, "Example Sensor"))

    async_add_devices(sensors)


class NetgearBinarySensor(NetgearBaseEntity, BinarySensorEntity):
    """ netgear_wax binary_sensor """

    def __init__(self, coordinator: NetgearDataUpdateCoordinator, config_entry, sensor_type: str):
        NetgearBaseEntity.__init__(self, coordinator, config_entry)
        BinarySensorEntity.__init__(self)
        self._coordinator = coordinator
        self._device_class = SAFETY_DEVICE_CLASS
        self._name = f"{coordinator.get_device_name()} {sensor_type}"
        self._unique_id = f"{coordinator.get_mac()}_{sensor_type}"

    @property
    def unique_id(self):
        """Return the entity unique ID."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of the binary_sensor"""
        return self._name

    @property
    def device_class(self):
        """Return the class of this binary_sensor, Example: motion"""
        return self._device_class

    @property
    def is_on(self):
        return False
