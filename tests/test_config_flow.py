"""Regression coverage for setup diagnostics and best-effort logout."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest

from custom_components.netgear_wax.config_flow import NetgearFlowHandler

pytestmark = pytest.mark.asyncio


async def test_config_flow_does_not_use_deprecated_connection_class():
    """The manifest iot_class replaces ConfigFlow.CONNECTION_CLASS."""
    assert "CONNECTION_CLASS" not in NetgearFlowHandler.__dict__


@pytest.mark.parametrize("logout_error", [None, TimeoutError(), aiohttp.ClientConnectionError()])
async def test_successful_discovery_survives_logout_failure(logout_error):
    """Logout failures must not reject a successfully discovered access point."""
    client = Mock()
    client.async_login = AsyncMock()
    client.async_get_state = AsyncMock(
        return_value=SimpleNamespace(mac_address="00:11:22:33:44:55", device_name="AP")
    )
    client.async_logout = AsyncMock(side_effect=logout_error)
    flow = NetgearFlowHandler()
    with (
        patch("custom_components.netgear_wax.config_flow.async_create_clientsession"),
        patch("custom_components.netgear_wax.config_flow.NetgearWaxClient", return_value=client),
    ):
        assert await flow._test_credentials("admin", "secret", "ap.example", 443) == {
            "mac": "00:11:22:33:44:55", "name": "AP"
        }
    assert flow._errors == {}
    client.async_logout.assert_awaited_once()


@pytest.mark.parametrize(
    "stage,failure,expected",
    [
        ("login", aiohttp.ClientResponseError(Mock(), (), status=401), "auth"),
        ("login", aiohttp.ClientResponseError(Mock(), (), status=403), "auth"),
        ("login", aiohttp.ClientResponseError(Mock(), (), status=500), "cannot_connect"),
        ("login", TimeoutError(), "cannot_connect"),
        ("login", aiohttp.ClientConnectionError(), "cannot_connect"),
        ("login", ValueError("Missing login cookie"), "invalid_response"),
        ("reading device state", KeyError("system"), "invalid_response"),
        ("reading device state", aiohttp.ClientResponseError(Mock(), (), status=401), "cannot_connect"),
    ],
)
async def test_setup_reports_failure_stage_and_preserves_original_error(stage, failure, expected, caplog):
    """Network and protocol failures must not all be described as bad credentials."""
    client = Mock()
    client.async_login = AsyncMock(side_effect=failure if stage == "login" else None)
    client.async_get_state = AsyncMock(side_effect=failure)
    client.async_logout = AsyncMock(side_effect=TimeoutError())
    flow = NetgearFlowHandler()
    with (
        caplog.at_level("DEBUG", logger="custom_components.netgear_wax"),
        patch("custom_components.netgear_wax.config_flow.async_create_clientsession"),
        patch("custom_components.netgear_wax.config_flow.NetgearWaxClient", return_value=client),
    ):
        assert await flow._test_credentials("admin", "secret", "ap.example", 443) is None
    assert flow._errors == {"base": expected}
    record = next(r for r in caplog.records if r.message == f"Setup failed during {stage}")
    assert record.exc_info[1] is failure
    client.async_logout.assert_awaited_once()


@pytest.mark.parametrize("existing", [{}, {"sensor": False, "switch": True, "custom": "preserve"}])
async def test_options_flow_opens_and_saves_without_assigning_config_entry(tmp_path, existing):
    """Open the form after HA attaches the entry, preserving defaults and options."""
    from homeassistant.core import HomeAssistant
    from custom_components.netgear_wax.const import PLATFORMS

    entry = SimpleNamespace(entry_id="options-entry", options=existing.copy(), data={"username": "admin"})
    # Construction must succeed before hass/handler are assigned, including on
    # HA versions where OptionsFlow.config_entry has no setter.
    flow = NetgearFlowHandler.async_get_options_flow(entry)
    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = SimpleNamespace(async_get_known_entry=Mock(return_value=entry))
    flow.hass = hass
    flow.handler = entry.entry_id

    result = await flow.async_step_init()
    assert result["type"] == "form"
    assert result["step_id"] == "user"
    defaults = result["data_schema"]({})
    assert defaults == {platform: existing.get(platform, True) for platform in PLATFORMS}

    submitted = {"sensor": True, "switch": False, "binary_sensor": False}
    saved = await flow.async_step_user(submitted)
    assert saved["type"] == "create_entry"
    assert saved["data"] == {**existing, **submitted}
    assert entry.options == existing
