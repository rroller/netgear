"""Sensor platform for netgear_wax."""
import logging
from typing import List

from homeassistant.const import PERCENTAGE, UnitOfInformation
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from custom_components.netgear_wax import NetgearDataUpdateCoordinator

from .const import (
    DOMAIN,
    DEVICES_ICON,
    UPDATE_ICON,
    CHART_DONUT_ICON,
    ROUTER_NETWORK_ICON,
    LAN_ICON,
)
from .entity import NetgearBaseEntity

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_devices):
    """Setup sensor platform."""
    coordinator: NetgearDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    sensors: List[SensorEntity] = [
        NetgearUpdateSensor(coordinator, entry, "Update"),
        NetgearTotalDevicesSensor(coordinator, entry, "Connected Clients"),
        NetgearAddressSensor(coordinator, entry, "IP"),
        NetgearMacSensor(coordinator, entry, "MAC"),
    ]

    stats = coordinator.get_stats()
    if stats is not None:
        for lan in ["wlan0", "wlan1"]:
            if lan in stats:
                sensors.append(
                    NetgearWlanUtilizationSensor(coordinator, entry, f"{lan} util", lan)
                )
        for lan in ["lan", "wlan0", "wlan1"]:
            if lan in stats:
                sensors.append(
                    NetgearInterfaceTrafficSensor(
                        coordinator, entry, f"{lan} traffic", lan
                    )
                )

    async_add_devices(sensors)


class NetgearSensor(NetgearBaseEntity, SensorEntity):
    """netgear_wax sensor"""

    def __init__(
        self, coordinator: NetgearDataUpdateCoordinator, config_entry, sensor_type: str
    ):
        NetgearBaseEntity.__init__(self, coordinator, config_entry)
        SensorEntity.__init__(self)
        self._coordinator = coordinator
        # self._device_class = SAFETY_DEVICE_CLASS
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


class NetgearUpdateSensor(NetgearSensor):
    """Sensor to report when there's a firmware update available"""

    def __init__(
        self, coordinator: NetgearDataUpdateCoordinator, config_entry, sensor_type: str
    ):
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
    """Sensor to report how many devices are connected"""

    def __init__(
        self, coordinator: NetgearDataUpdateCoordinator, config_entry, sensor_type: str
    ):
        NetgearSensor.__init__(self, coordinator, config_entry, sensor_type)
        self._coordinator = coordinator

    @property
    def state(self):
        return self._coordinator.total_number_of_devices()

    @property
    def icon(self) -> str:
        return DEVICES_ICON

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT


class NetgearWlanUtilizationSensor(NetgearSensor):
    """Sensor to report WiFi Channel Utilization"""

    def __init__(
        self,
        coordinator: NetgearDataUpdateCoordinator,
        config_entry,
        sensor_type: str,
        lan: str,
    ):
        NetgearSensor.__init__(self, coordinator, config_entry, sensor_type)
        self._coordinator = coordinator
        self._lan = lan

    @property
    def state(self):
        stats = self._coordinator.get_stats()
        if self._lan in stats:
            return self._coordinator.get_stats().get(self._lan).utilization
        return 0

    @property
    def icon(self) -> str:
        return CHART_DONUT_ICON

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return native unit of measurement of sensor."""
        return PERCENTAGE


class NetgearInterfaceTrafficSensor(NetgearSensor):
    """Sensor to report how many devices are connected"""

    def __init__(
        self,
        coordinator: NetgearDataUpdateCoordinator,
        config_entry,
        sensor_type: str,
        lan: str,
    ):
        NetgearSensor.__init__(self, coordinator, config_entry, sensor_type)
        self._coordinator = coordinator
        self._lan = lan

    @property
    def state(self):
        stats = self._coordinator.get_stats()
        if self._lan in stats:
            return self._coordinator.get_stats().get(self._lan).bytes_transferred
        return 0

    @property
    def icon(self) -> str:
        return ROUTER_NETWORK_ICON

    @property
    def device_class(self):
        """Return the class of this sensor"""
        return SensorDeviceClass.DATA_SIZE

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return native unit of measurement of sensor."""
        return UnitOfInformation.BYTES

    @property
    def state_class(self):
        return SensorStateClass.TOTAL_INCREASING


class NetgearAddressSensor(NetgearSensor):
    """Sensor to show the IP address of the device"""

    def __init__(
        self, coordinator: NetgearDataUpdateCoordinator, config_entry, sensor_type: str
    ):
        NetgearSensor.__init__(self, coordinator, config_entry, sensor_type)

    @property
    def state(self):
        return self._coordinator.get_ip_address()

    @property
    def icon(self) -> str:
        return LAN_ICON


class NetgearMacSensor(NetgearSensor):
    """Sensor to show the IP address of the device"""

    def __init__(
        self, coordinator: NetgearDataUpdateCoordinator, config_entry, sensor_type: str
    ):
        NetgearSensor.__init__(self, coordinator, config_entry, sensor_type)

    @property
    def state(self):
        return self._coordinator.get_mac()

    @property
    def icon(self) -> str:
        return LAN_ICON
