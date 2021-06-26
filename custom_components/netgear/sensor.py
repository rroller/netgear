"""Sensor platform for netgear."""
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from custom_components.netgear import NetgearDataUpdateCoordinator

from .const import (
    DOMAIN, SAFETY_DEVICE_CLASS,
)
from .entity import NetgearBaseEntity

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_devices):
    """Setup sensor platform."""
    coordinator: NetgearDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    sensors: list[SensorEntity] = [
        NetgearUpdateSensor(coordinator, entry, "Update Sensor"),
    ]
    async_add_devices(sensors)


class NetgearSensor(NetgearBaseEntity, SensorEntity):
    """ netgear sensor """

    def __init__(self, coordinator: NetgearDataUpdateCoordinator, config_entry, sensor_type: str):
        NetgearBaseEntity.__init__(self, coordinator, config_entry)
        SensorEntity.__init__(self)
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
        """Return the name of the sensor. Example: Cam14 Motion Alarm"""
        return self._name

    @property
    def device_class(self):
        """Return the class of this sensor"""
        return self._device_class


class NetgearUpdateSensor(NetgearSensor):
    """ Sensor to report when there's a firmware update available """

    def __init__(self, coordinator: NetgearDataUpdateCoordinator, config_entry, sensor_type: str):
        NetgearSensor.__init__(self, coordinator, config_entry, sensor_type)

    @property
    def state(self):
        if self._coordinator.is_firmware_update_available():
            self._attr_unit_of_measurement = "pending update"
            return 1
        self._attr_unit_of_measurement = "pending updates"
        return 0
