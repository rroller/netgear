"""Regression coverage for setup diagnostics and best-effort logout."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import pytest

from custom_components.netgear_wax.config_flow import NetgearFlowHandler

pytestmark = pytest.mark.asyncio


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
