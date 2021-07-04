"""Sensor platform for netgear."""
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from custom_components.netgear import NetgearDataUpdateCoordinator

from .const import (
    DOMAIN, SAFETY_DEVICE_CLASS, DEVICES_ICON, UPDATE_ICON, CHART_DONUT_ICON,
)
from .entity import NetgearBaseEntity
from .utils import human_bytes

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_devices):
    """Setup sensor platform."""
    coordinator: NetgearDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    sensors: list[SensorEntity] = [
        NetgearUpdateSensor(coordinator, entry, "Update"),
        NetgearTotalDevicesSensor(coordinator, entry, "Connected Clients"),
    ]

    stats = coordinator.get_stats()
    if stats is not None:
        for lan in ["wlan0", "wlan1"]:
            if lan in stats:
                sensors.append(NetgearWlanUtilizationSensor(coordinator, entry, f"{lan} util", lan))
        for lan in ["lan", "wlan0", "wlan1"]:
            if lan in stats:
                sensors.append(NetgearInterfaceTrafficSensor(coordinator, entry, f"{lan} traffic", lan))

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

    @property
    def icon(self) -> str:
        return UPDATE_ICON


class NetgearTotalDevicesSensor(NetgearSensor):
    """ Sensor to report how many devices are connected """

    def __init__(self, coordinator: NetgearDataUpdateCoordinator, config_entry, sensor_type: str):
        NetgearSensor.__init__(self, coordinator, config_entry, sensor_type)
        self._coordinator = coordinator

    @property
    def state(self):
        return self._coordinator.total_number_of_devices()

    @property
    def icon(self) -> str:
        return DEVICES_ICON


class NetgearWlanUtilizationSensor(NetgearSensor):
    """ Sensor to report how many devices are connected """

    def __init__(self, coordinator: NetgearDataUpdateCoordinator, config_entry, sensor_type: str, lan: str):
        NetgearSensor.__init__(self, coordinator, config_entry, sensor_type)
        self._coordinator = coordinator
        self._lan = lan
        self._attr_unit_of_measurement = "%"

    @property
    def state(self):
        stats = self._coordinator.get_stats()
        if self._lan in stats:
            return self._coordinator.get_stats().get(self._lan).utilization
        return 0

    @property
    def icon(self) -> str:
        return CHART_DONUT_ICON


class NetgearInterfaceTrafficSensor(NetgearSensor):
    """ Sensor to report how many devices are connected """

    def __init__(self, coordinator: NetgearDataUpdateCoordinator, config_entry, sensor_type: str, lan:str):
        NetgearSensor.__init__(self, coordinator, config_entry, sensor_type)
        self._coordinator = coordinator
        self._lan = lan
        self._attr_unit_of_measurement = "B"

    @property
    def state(self):
        stats = self._coordinator.get_stats()
        if self._lan in stats:
            return self._coordinator.get_stats().get(self._lan).bytes_transferred
        return 0
