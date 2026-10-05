"""Firmware regression tests using real HA classes and mocked device responses."""

from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from multidict import CIMultiDict
import pytest
import pytest_asyncio

from custom_components.netgear_wax import NetgearDataUpdateCoordinator
from custom_components.netgear_wax.client import DeviceState
from custom_components.netgear_wax.client_wax import NetgearWaxClient
from custom_components.netgear_wax.const import STATE_REQUEST_DATA
from custom_components.netgear_wax.sensor import NetgearUpdateSensor

pytestmark = pytest.mark.asyncio


def response(payload=None, *, status=200, body=None, headers=None):
    """Build a response with realistic HTTP error behavior."""
    result = Mock(spec=aiohttp.ClientResponse)
    result.status = status
    result.headers = CIMultiDict(headers or {})
    result.text = AsyncMock(return_value=json.dumps(payload) if body is None else body)
    if status >= 400:
        result.raise_for_status.side_effect = aiohttp.ClientResponseError(
            Mock(real_url="https://ap.example/LogFile"), (), status=status
        )
    return result


def state_response(firmware=None, version="10.4.1.5"):
    """Return a minimal successful AP state response."""
    system = {
        "monitor": {
            "sysVersion": version,
            "productId": "WAX610",
            "ethernetMacAddress": "00:11:22:33:44:55",
            "sysSerialNumber": "test-serial",
            "totalNumberOfDevices": 2,
        },
        "basicSettings": {"apName": "Test AP"},
    }
    if firmware is not None:
        system["FwUpdate"] = firmware
    return {"status": 0, "system": system}


@pytest.fixture
def client():
    """Create a client with an existing authenticated session."""
    session = Mock(spec=aiohttp.ClientSession)
    session.post = AsyncMock()
    session.get = AsyncMock()
    api = NetgearWaxClient("admin", "test-password", "ap.example", 443, session)
    api._lhttpdsid = "old-cookie"
    api._security_token = "old-token"
    return api


@pytest_asyncio.fixture
async def coordinator(tmp_path, client):
    """Use the real Home Assistant coordinator without starting HA."""
    hass = HomeAssistant(str(tmp_path))
    with patch("custom_components.netgear_wax.async_get_clientsession"):
        result = NetgearDataUpdateCoordinator(
            hass, "ap.example", 443, "admin", "test-password", "test-mac", "test-entry"
        )
    result.client = client
    client.async_get_ssids = AsyncMock(return_value=[])
    client.async_get_wireless_clients = AsyncMock(return_value=[])
    yield result
    result._unsub_logbook_ready()


@pytest.mark.parametrize("status", [0, "0"])
async def test_check_uses_documented_endpoint_and_validates_success(client, status):
    """The firmware check must use method 5, never the install command 7."""
    client._session.post.return_value = response({"status": status})
    await client.check_for_firmware_updates()
    request = client._session.post.call_args.kwargs
    assert request["url"] == "https://ap.example:443/LogFile"
    assert json.loads(request["data"]) == {"method": 5, "upgradeCheck": 0}
    assert request["cookies"] == {"lhttpdsid": "old-cookie"}
    assert request["headers"] == {"security": "old-token"}


async def test_first_check_authenticates_before_sending_command(client):
    """Startup checks must not send empty session credentials."""
    client._lhttpdsid = client._security_token = ""
    client._session.get.return_value = response(
        {}, headers={"Set-Cookie": "lhttpdsid=new-cookie; Path=/; HttpOnly"}
    )
    client._session.post.side_effect = [
        response({"system": {"security_token": "new-token"}}),
        response({"status": 0}),
    ]
    await client.check_for_firmware_updates()
    login, check = client._session.post.call_args_list
    assert login.kwargs["url"].endswith("/socketCommunication")
    assert check.kwargs["url"].endswith("/LogFile")
    assert check.kwargs["cookies"] == {"lhttpdsid": "new-cookie"}
    assert check.kwargs["headers"] == {"security": "new-token"}


@pytest.mark.parametrize("expired", [100, "100", "http401"])
async def test_check_refreshes_expired_authentication_once(client, expired):
    """Both device status 100 and a non-JSON HTTP 401 require a fresh login."""
    initial = (
        response(status=401, body="Unauthorized")
        if expired == "http401"
        else response({"status": expired})
    )
    client._session.post.side_effect = [initial, response({"status": "0"})]

    async def login():
        client._lhttpdsid = "new-cookie"
        client._security_token = "new-token"

    client.async_login = AsyncMock(side_effect=login)
    await client.check_for_firmware_updates()
    client.async_login.assert_awaited_once()
    assert client._session.post.await_count == 2
    assert client._session.post.call_args.kwargs["headers"] == {"security": "new-token"}


@pytest.mark.parametrize("status", [1, "1", 2, "2", 100, "100", None])
async def test_device_error_is_not_a_successful_check(client, status):
    """An HTTP 200 must not hide offline, server, or authentication errors."""
    client._session.post.return_value = response({"status": status})
    client.async_login = AsyncMock()
    with pytest.raises(ValueError, match="failed with status"):
        await client.check_for_firmware_updates()
    assert client._session.post.await_count <= 2


@pytest.mark.parametrize("status", [401, 500])
async def test_http_errors_propagate_without_parsing_html(client, status):
    """HTTP failures are reported even when the device responds with HTML."""
    client._session.post.return_value = response(
        status=status, body="<html>Error</html>"
    )
    client.async_login = AsyncMock()
    with pytest.raises(aiohttp.ClientResponseError):
        await client.check_for_firmware_updates()
    assert client._session.post.await_count <= 2


@pytest.mark.parametrize("body", ["", "<html>Login</html>", "{}", "[]"])
async def test_invalid_response_is_not_a_successful_check(client, body):
    """Malformed or incomplete success responses must be retried later."""
    client._session.post.return_value = response(body=body)
    with pytest.raises(ValueError):
        await client.check_for_firmware_updates()


async def test_requests_are_isolated_and_connectivity_is_throttled(client):
    """Optional request fields must not leak to other polls or APs."""
    original = deepcopy(STATE_REQUEST_DATA)
    client._session.post.return_value = response(
        state_response({"ImageAvailable": "1"})
    )
    with patch(
        "custom_components.netgear_wax.client_wax.time.monotonic", return_value=100
    ):
        await client.async_get_state(check_firmware=True)
        await client.async_get_state()
    first, second = (
        json.loads(c.kwargs["data"])["system"]
        for c in client._session.post.call_args_list
    )
    assert "FwUpdate" in first
    assert "FwUpdate" not in second
    assert "internetConnectivityStatus" in first["monitor"]
    assert "internetConnectivityStatus" not in second["monitor"]
    assert original == STATE_REQUEST_DATA
    other = NetgearWaxClient("admin", "pw", "other.example", 443, Mock())
    other.async_post = AsyncMock(return_value=state_response())
    state = await other.async_get_state()
    assert state.firmware_update_available is None
    assert "FwUpdate" not in json.loads(other.async_post.call_args.args[0])["system"]
    with patch(
        "custom_components.netgear_wax.client_wax.time.monotonic", return_value=3700
    ):
        await client.async_get_state()
    assert (
        "internetConnectivityStatus"
        in json.loads(client._session.post.call_args.kwargs["data"])["system"][
            "monitor"
        ]
    )


@pytest.mark.parametrize(
    "available,expected", [(0, False), ("0", False), (1, True), ("1", True)]
)
async def test_firmware_availability_and_installed_version(client, available, expected):
    """Numeric and string flags from the AP have the same meaning."""
    client._session.post.return_value = response(
        state_response({"ImageAvailable": available})
    )
    state = await client.async_get_state(True)
    assert state.firmware_update_available is expected
    assert state.firmware_version == "10.4.1.5"


@pytest.mark.parametrize(
    "firmware",
    [
        None,
        {},
        {"ImageAvailable": ""},
        {"ImageAvailable": None},
        {"ImageAvailable": "bad"},
        {"ImageAvailable": 2},
    ],
)
async def test_missing_or_invalid_firmware_preserves_last_result(client, firmware):
    """Missing results are unknown initially and cannot clear a known update."""
    client._session.post.return_value = response(state_response(firmware))
    assert (await client.async_get_state(True)).firmware_update_available is None
    client._session.post.return_value = response(
        state_response({"ImageAvailable": "1"})
    )
    assert (await client.async_get_state(True)).firmware_update_available is True
    client._session.post.return_value = response(state_response(firmware))
    assert (await client.async_get_state(True)).firmware_update_available is True
    client._session.post.return_value = response(
        state_response({"ImageAvailable": "0"}, "10.6.1.1")
    )
    updated = await client.async_get_state(True)
    assert updated.firmware_update_available is False
    assert updated.firmware_version == "10.6.1.1"


async def test_check_schedule_and_late_result_reach_sensor(coordinator, client):
    """Check every six hours, but read and display results on every refresh."""
    client.check_for_firmware_updates = AsyncMock()
    client._session.post.side_effect = [
        response(state_response({"ImageAvailable": flag}))
        for flag in ["0", "1", "1", "0"]
    ]
    coordinator._state = DeviceState(device_name="Test AP")
    sensor = NetgearUpdateSensor(coordinator, SimpleNamespace(), "Update")
    with patch("custom_components.netgear_wax.time.monotonic") as now:
        for instant, expected, count in [
            (100, 0, 1),
            (160, 1, 1),
            (21699, 1, 1),
            (21700, 0, 2),
        ]:
            now.return_value = instant
            await coordinator._async_update_data()
            assert sensor.state == expected
            assert client.check_for_firmware_updates.await_count == count
    for call in client._session.post.call_args_list:
        assert "FwUpdate" in json.loads(call.kwargs["data"])["system"]


@pytest.mark.parametrize(
    "failure",
    [ValueError("server unreachable"), TimeoutError(), aiohttp.ClientConnectionError()],
)
async def test_failed_check_retries_next_poll_without_disabling_state(
    coordinator, client, failure
):
    """Failed checks must not postpone retries for six hours or break sensors."""
    client.check_for_firmware_updates = AsyncMock(side_effect=[failure, None])
    client._session.post.return_value = response(
        state_response({"ImageAvailable": "1"})
    )
    assert (await coordinator._async_update_data()).firmware_update_available is True
    assert coordinator._firmware_last_checked is None
    await coordinator._async_update_data()
    assert client.check_for_firmware_updates.await_count == 2
    assert coordinator._firmware_last_checked is not None


async def test_state_error_does_not_mask_check_success(coordinator, client):
    """A failed state read reports UpdateFailed; the successful check is retained."""
    client.check_for_firmware_updates = AsyncMock()
    client._session.post.side_effect = aiohttp.ClientConnectionError()
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator._firmware_last_checked is not None
    client._session.post.side_effect = None
    client._session.post.return_value = response(
        state_response({"ImageAvailable": "1"})
    )
    assert (await coordinator._async_update_data()).firmware_update_available is True
    client.check_for_firmware_updates.assert_awaited_once()


async def test_initial_sensor_unknown_until_valid_result(coordinator):
    """Unknown firmware availability must not be advertised as up to date."""
    coordinator._state = DeviceState()
    sensor = NetgearUpdateSensor(coordinator, SimpleNamespace(), "Update")
    assert sensor.state is None
