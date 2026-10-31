"""Adds config flow (UI flow) for Netgear WAX access points"""
import logging

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .client_wax import NetgearWaxClient
from .const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_ADDRESS,
    CONF_PORT,
    DOMAIN,
    PLATFORMS,
    CONF_MAC,
)

# https://developers.home-assistant.io/docs/data_entry_flow_index

_LOGGER: logging.Logger = logging.getLogger(__package__)


class NetgearFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Netgear API."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize."""
        self._errors = {}

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        self._errors = {}

        # Uncomment the next 2 lines if only a single instance of the integration is allowed:
        # if self._async_current_entries():
        #     return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            data = await self._test_credentials(
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                user_input[CONF_ADDRESS],
                user_input[CONF_PORT],
            )
            if data is not None:
                user_input[CONF_MAC] = data.get("mac")
                title = data.get("name")
                return self.async_create_entry(title=title, data=user_input)

            return await self._show_config_form(user_input)

        return await self._show_config_form(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return NetgearOptionsFlowHandler(config_entry)

    async def _show_config_form(self, user_input):  # pylint: disable=unused-argument
        """Show the configuration form to edit location data."""
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default="admin"): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(CONF_ADDRESS): str,
                    vol.Required(CONF_PORT, default="443"): str,
                }
            ),
            errors=self._errors,
        )

    async def _test_credentials(self, username, password, address, port):
        """Return true if credentials is valid."""
        session = async_create_clientsession(self.hass, verify_ssl=False)
        client = NetgearWaxClient(username, password, address, port, session)
        stage = "login"
        try:
            await client.async_login()
            stage = "reading device state"
            state = await client.async_get_state()
            if state is None or not state.mac_address:
                raise ValueError("Device state did not include a MAC address")
            return {"mac": state.mac_address, "name": state.device_name}
        except aiohttp.ClientResponseError as exception:
            self._errors["base"] = (
                "auth" if stage == "login" and exception.status in (401, 403)
                else "cannot_connect"
            )
            _LOGGER.debug("Setup failed during %s", stage, exc_info=True)
        except (aiohttp.ClientError, TimeoutError):
            self._errors["base"] = "cannot_connect"
            _LOGGER.debug("Setup failed during %s", stage, exc_info=True)
        except Exception as exception:  # pylint: disable=broad-except
            self._errors["base"] = "invalid_response"
            _LOGGER.debug("Setup failed during %s", stage, exc_info=exception)
        finally:
            # Release device sessions even if reading state failed after login.
            # Logout must not hide the setup result or its original error.
            try:
                await client.async_logout()
            except Exception:
                _LOGGER.debug("Failed to log out after setup", exc_info=True)


class NetgearOptionsFlowHandler(config_entries.OptionsFlow):
    """Netgear config flow options handler."""

    def __init__(self, config_entry):
        """Initialize HACS options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):  # pylint: disable=unused-argument
        """Manage the options."""
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        if user_input is not None:
            self.options.update(user_input)
            return await self._update_options()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(x, default=self.options.get(x, True)): bool
                    for x in sorted(PLATFORMS)
                }
            ),
        )

    async def _update_options(self):
        """Update config entry options."""
        return self.async_create_entry(
            title=self.config_entry.data.get(CONF_USERNAME), data=self.options
        )
