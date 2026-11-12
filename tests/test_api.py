"""Firmware regression tests using real HA classes and mocked device responses."""

import asyncio
from copy import deepcopy
import inspect
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed
from multidict import CIMultiDict
import pytest
import pytest_asyncio

from custom_components.netgear_wax import (
    NetgearDataUpdateCoordinator,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.netgear_wax.client import DeviceState
from custom_components.netgear_wax.client_wax import NetgearWaxClient
from custom_components.netgear_wax.const import DOMAIN, PLATFORMS, STATE_REQUEST_DATA
from custom_components.netgear_wax.entity import NetgearBaseEntity
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
    from homeassistant.helpers import frame
    if hasattr(frame, "async_setup"):
        frame.async_setup(hass)
    with patch("custom_components.netgear_wax.async_get_clientsession"):
        result = NetgearDataUpdateCoordinator(
            hass, "ap.example", 443, "admin", "test-password", "test-mac", "test-entry"
        )
    result.client = client
    client.async_get_ssids = AsyncMock(return_value=[])
    client.async_get_wireless_clients = AsyncMock(return_value=[])
    yield result
    result._unsub_logbook_ready()


async def test_entities_use_coordinator_updates_without_individual_polling(coordinator):
    """Coordinator entities must not schedule a second per-entity refresh."""
    entity = NetgearBaseEntity(coordinator, SimpleNamespace())

    assert entity.should_poll is False


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


@pytest.mark.parametrize("failure", [None, "http500", "connection", "timeout"])
@pytest.mark.parametrize("platforms_unloaded", [True, False])
async def test_logout_does_not_block_unload(
    coordinator, client, failure, platforms_unloaded, caplog
):
    """Device logout failures must not skip platform cleanup or alter its result."""
    if failure == "http500":
        client._session.post.return_value = response(status=500)
    elif failure == "connection":
        client._session.post.side_effect = aiohttp.ClientConnectionError("offline")
    elif failure == "timeout":
        client._session.post.side_effect = TimeoutError()
    else:
        client._session.post.return_value = response({})

    hass = coordinator.hass
    entry = SimpleNamespace(entry_id="test-entry")
    hass.data[DOMAIN] = {entry.entry_id: coordinator}
    coordinator.platforms = list(PLATFORMS)
    unsubscribe = Mock(wraps=coordinator._unsub_logbook_ready)
    coordinator._unsub_logbook_ready = unsubscribe
    unload = AsyncMock(return_value=platforms_unloaded)
    with (
        caplog.at_level("DEBUG", logger="custom_components.netgear_wax"),
        patch.object(
            hass,
            "config_entries",
            SimpleNamespace(async_forward_entry_unload=unload),
        ),
    ):
        assert await async_unload_entry(hass, entry) is platforms_unloaded

    unsubscribe.assert_called_once_with()
    client._session.post.assert_awaited_once()
    assert client._session.post.call_args.kwargs["url"].endswith("/logout")
    assert unload.await_count == len(PLATFORMS)
    assert {call.args[1] for call in unload.await_args_list} == set(PLATFORMS)
    assert (entry.entry_id not in hass.data[DOMAIN]) is platforms_unloaded
    if failure:
        record = next(r for r in caplog.records if r.message == "Failed to log out")
        assert record.exc_info is not None


async def test_stop_preserves_cancellation(coordinator, client):
    """Best-effort logout must still allow task cancellation to propagate."""
    client._session.post.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await coordinator.async_stop({})


@pytest.mark.parametrize("token_location", ["header", "body", "missing_cookie", "missing_token"])
async def test_login_diagnostics_do_not_expose_response_secrets(client, caplog, token_location):
    """Login diagnostics must not include raw HTML, cookies, or security tokens."""
    cookie = "private-session-cookie"
    token = "private-security-token"
    body_secret = "private-response-content"
    client._session.get.return_value = response(
        body=body_secret,
        headers={} if token_location == "missing_cookie" else {
            "Set-Cookie": f"lhttpdsid={cookie}; Path=/; HttpOnly"
        },
    )
    client._session.post.return_value = response(
        {"system": {"security_token": token}} if token_location == "body" else {
            "message": body_secret
        },
        headers={"security": token} if token_location == "header" else {},
    )
    with caplog.at_level("DEBUG", logger="custom_components.netgear_wax"):
        if token_location.startswith("missing"):
            with pytest.raises(ValueError) as error:
                await client.async_login()
            assert body_secret not in str(error.value)
        else:
            await client.async_login()
            assert client._security_token == token
    for secret in (cookie, token, body_secret):
        assert secret not in caplog.text


class FakeCoordinator:
    """Coordinator whose first refresh is released by the test."""

    instances = []

    def __init__(self, *args, **kwargs):
        """Record the instance so tests can reach it."""
        self.release = asyncio.Event()
        self.last_update_success = True
        self.platforms = []
        self.async_stop = AsyncMock()
        type(self).instances.append(self)

    async def async_refresh(self):
        """Wait until the test lets the refresh finish."""
        await self.release.wait()


@pytest_asyncio.fixture
async def setup_env(tmp_path):
    """Provide a bare hass and config entry for async_setup_entry."""
    FakeCoordinator.instances = []
    hass = HomeAssistant(str(tmp_path))
    hass.data[DOMAIN] = {}
    hass.config_entries = SimpleNamespace(
        async_forward_entry_setups=AsyncMock(),
        async_forward_entry_unload=AsyncMock(return_value=True),
    )
    entry = SimpleNamespace(
        entry_id="test-entry",
        data={
            "username": "admin",
            "password": "test-password",
            "address": "ap.example",
            "port": 443,
            "mac": "test-mac",
        },
        options={},
        add_update_listener=Mock(),
        async_on_unload=Mock(),
    )
    with patch("custom_components.netgear_wax.NetgearDataUpdateCoordinator", FakeCoordinator), patch(
        "custom_components.netgear_wax.FIRST_REFRESH_TIMEOUT", 0.05
    ):
        yield hass, entry


async def test_slow_first_refresh_is_retried_without_a_second_login(setup_env):
    """A slow AP must not block setup, and the retry must reuse the same refresh."""
    hass, entry = setup_env

    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)
    assert len(FakeCoordinator.instances) == 1

    FakeCoordinator.instances[0].release.set()
    assert await async_setup_entry(hass, entry) is True

    assert len(FakeCoordinator.instances) == 1
    assert hass.data[DOMAIN][entry.entry_id] is FakeCoordinator.instances[0]
    assert entry.entry_id not in hass.data[DOMAIN]["pending_setup"]


async def test_failed_first_refresh_logs_out_and_clears_pending(setup_env):
    """A refresh that finishes with an error must release the login and retry cleanly."""
    hass, entry = setup_env

    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)
    coordinator = FakeCoordinator.instances[0]
    coordinator.last_update_success = False
    coordinator.release.set()

    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)

    coordinator.async_stop.assert_awaited_once()
    assert entry.entry_id not in hass.data[DOMAIN]["pending_setup"]


async def test_unload_while_first_refresh_is_pending_cancels_it(setup_env):
    """Removing an entry that never finished setup must cancel the refresh and log out."""
    hass, entry = setup_env

    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)
    task = hass.data[DOMAIN]["pending_setup"][entry.entry_id][1]

    assert await async_unload_entry(hass, entry) is True
    await asyncio.sleep(0)

    assert task.cancelled()
    FakeCoordinator.instances[0].async_stop.assert_awaited_once()
    assert entry.entry_id not in hass.data[DOMAIN]["pending_setup"]


async def test_reconfigured_entry_does_not_reuse_a_stale_pending_refresh(setup_env):
    """New credentials must replace a pending refresh started with the old ones."""
    hass, entry = setup_env

    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)
    first = FakeCoordinator.instances[0]
    entry.data = {**entry.data, "password": "changed"}

    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)

    assert len(FakeCoordinator.instances) == 2
    first.async_stop.assert_awaited_once()


@pytest.mark.parametrize("change", ["removed", "disabled", "shutdown"])
async def test_pending_setup_cleanup_without_integration_unload(setup_env, change):
    """Retry-state entries must clean up even when HA skips integration unload."""
    from types import MappingProxyType
    from homeassistant.config_entries import (
        ConfigEntry, ConfigEntryState, ConfigEntryChange,
        ConfigEntryDisabler, SIGNAL_CONFIG_ENTRY_CHANGED,
    )
    from homeassistant.const import EVENT_HOMEASSISTANT_STOP
    from homeassistant.helpers.dispatcher import async_dispatcher_send

    hass, fake_entry = setup_env
    entry_kwargs = (
        {"subentries_data": []}
        if "subentries_data" in inspect.signature(ConfigEntry).parameters else {}
    )
    entry = ConfigEntry(
        data=fake_entry.data, discovery_keys=MappingProxyType({}), domain=DOMAIN,
        entry_id=fake_entry.entry_id, minor_version=1, options={}, source="user",
        title="AP", unique_id="test", version=1, state=ConfigEntryState.SETUP_RETRY,
        **entry_kwargs,
    )
    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)
    task = hass.data[DOMAIN]["pending_setup"][entry.entry_id][1]
    component = SimpleNamespace(async_unload_entry=AsyncMock())
    integration = SimpleNamespace(
        domain=DOMAIN, async_get_component=AsyncMock(return_value=component)
    )
    async with entry.setup_lock:
        assert await entry.async_unload(hass, integration=integration)
    component.async_unload_entry.assert_not_called()

    if change == "shutdown":
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    else:
        if change == "disabled":
            object.__setattr__(entry, "disabled_by", ConfigEntryDisabler.USER)
        async_dispatcher_send(
            hass, SIGNAL_CONFIG_ENTRY_CHANGED,
            ConfigEntryChange.REMOVED if change == "removed" else ConfigEntryChange.UPDATED,
            entry,
        )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert task.cancelled()
    assert entry.entry_id not in hass.data[DOMAIN]["pending_setup"]
    FakeCoordinator.instances[0].async_stop.assert_awaited_once()


async def test_failed_refresh_cleanup_has_a_deadline(setup_env):
    """A stalled logout cannot keep a failed setup attempt waiting indefinitely."""
    hass, entry = setup_env
    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)
    coordinator = FakeCoordinator.instances[0]
    coordinator.last_update_success = False
    coordinator.release.set()
    cancelled = asyncio.Event()

    async def stop(event):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    coordinator.async_stop = AsyncMock(side_effect=stop)
    with patch("custom_components.netgear_wax.CLEANUP_TIMEOUT", 0.01):
        with pytest.raises(ConfigEntryNotReady):
            await asyncio.wait_for(async_setup_entry(hass, entry), timeout=0.2)
    assert cancelled.is_set()
    assert entry.entry_id not in hass.data[DOMAIN]["pending_setup"]


async def test_logout_timeout_releases_logbook_listener(coordinator, client):
    """Bounded logout still removes the coordinator's event listener."""
    unsubscribe = Mock(wraps=coordinator._unsub_logbook_ready)
    coordinator._unsub_logbook_ready = unsubscribe
    cancelled = asyncio.Event()

    async def logout():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    client.async_logout = AsyncMock(side_effect=logout)
    with patch("custom_components.netgear_wax.CLEANUP_TIMEOUT", 0.01):
        await asyncio.wait_for(coordinator.async_stop({}), timeout=0.2)
    unsubscribe.assert_called_once_with()
    assert cancelled.is_set()


async def test_pending_listeners_are_removed_after_success(setup_env):
    """Signals after successful setup must not dispose of the loaded coordinator."""
    from homeassistant.config_entries import ConfigEntryChange, SIGNAL_CONFIG_ENTRY_CHANGED
    from homeassistant.helpers.dispatcher import async_dispatcher_send

    hass, entry = setup_env
    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)
    coordinator = FakeCoordinator.instances[0]
    coordinator.release.set()
    assert await async_setup_entry(hass, entry)
    async_dispatcher_send(hass, SIGNAL_CONFIG_ENTRY_CHANGED, ConfigEntryChange.REMOVED, entry)
    await hass.async_block_till_done(wait_background_tasks=True)
    coordinator.async_stop.assert_not_awaited()
    assert hass.data[DOMAIN][entry.entry_id] is coordinator


async def test_force_update_fetches_data_with_automatic_polling_disabled(coordinator):
    """The update_entity service must refresh even with should_poll disabled."""
    from homeassistant.helpers.entity_component import DATA_INSTANCES, async_update_entity

    coordinator.config_entry = SimpleNamespace(pref_disable_polling=True)
    coordinator._async_update_data = AsyncMock(return_value=DeviceState())
    entity = NetgearBaseEntity(coordinator, coordinator.config_entry)
    entity.hass = coordinator.hass
    entity.entity_id = "sensor.manual_refresh"
    entity._async_write_ha_state = Mock()
    coordinator.hass.data[DATA_INSTANCES] = {
        "sensor": SimpleNamespace(get_entity=Mock(return_value=entity))
    }
    unsubscribe = coordinator.async_add_listener(Mock())
    try:
        assert entity.should_poll is False
        await async_update_entity(coordinator.hass, entity.entity_id)
        coordinator._async_update_data.assert_awaited_once()
        entity._async_write_ha_state.assert_called_once()
        assert coordinator._unsub_refresh is None
    finally:
        unsubscribe()
        await coordinator.async_shutdown()
