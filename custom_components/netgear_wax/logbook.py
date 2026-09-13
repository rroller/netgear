"""Logbook support for Netgear WAX client activity."""

from typing import Any

from homeassistant.components.logbook import LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.core import callback

from .const import DOMAIN, EVENT_CLIENT_ACTIVITY


async def async_describe_events(_hass: Any, async_describe_event: Any) -> None:
    """Describe Netgear client activity for Home Assistant's logbook."""
    async_describe_event(DOMAIN, EVENT_CLIENT_ACTIVITY, _describe_client_activity)


@callback
def _describe_client_activity(event: Any) -> dict[str, str]:
    """Return the display text for a client activity event."""
    return {
        LOGBOOK_ENTRY_NAME: event.data["name"],
        LOGBOOK_ENTRY_MESSAGE: event.data["message"],
    }
