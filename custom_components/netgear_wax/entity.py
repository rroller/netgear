"""NetgearBaseEntity class"""
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.netgear_wax import NetgearDataUpdateCoordinator

from .const import DOMAIN


class NetgearBaseEntity(CoordinatorEntity):
    """
    NetgearBaseEntity is the base entity for all Netgear entities
    """

    def __init__(self, coordinator: NetgearDataUpdateCoordinator, config_entry):
        super().__init__(coordinator)
        self.config_entry = config_entry
        self._coordinator = coordinator

    # https://developers.home-assistant.io/docs/entity_registry_index
    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return self._coordinator.get_mac()

    # https://developers.home-assistant.io/docs/device_registry_index
    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._coordinator.get_mac())},
            "name": self._coordinator.get_device_name(),
            "model": self._coordinator.get_model(),
            "manufacturer": "Netgear",
            "configuration_url": "https://" + self._coordinator.get_ip_address(),
            "sw_version": self._coordinator.get_firmware_version(),
        }

    # See extra_state_attributes  for extra data

    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state.  False if entity pushes its state to HA"""
        return True
