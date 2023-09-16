"""Netgear API Client."""
import json
import logging
import time

import aiohttp
from aiohttp import hdrs
from aiohttp.client_reqrep import ClientResponse
from typing import List, Optional

from custom_components.netgear_wax.client import NetgearClient, DeviceState, Ssid, Stat
from custom_components.netgear_wax.const import STATE_REQUEST_DATA
from custom_components.netgear_wax.utils import parse_human_string, safe_cast

_LOGGER: logging.Logger = logging.getLogger(__package__)


class NetgearWaxClient(NetgearClient):
    """ NetgearWaxClient is the client for accessing Netgear WAX access points """

    def __init__(self, username: str, password: str, address: str, port: int, session: aiohttp.ClientSession) -> None:
        super().__init__()
        self._username = username
        self._password = password
        self._address = address
        self._session = session
        self._base_url = "https://{0}:{1}".format(address, port)
        self._lhttpdsid = ""
        self._security_token = ""
        self._internet_connectivity_check: Optional[float] = None

        _LOGGER.debug("Creating client with username %s", username)

    async def async_login(self):
        """ async_login sets the lhttpdsid and security token which are needed to issues requests """
        _LOGGER.debug("Logging in with username %s", self._username)

        # Login step 1 - Get lhttpdsid cookie
        response: ClientResponse = await self._session.get(self._base_url)
        cookies: dict = self.get_cookies(response)
        lhttpdsid = cookies.get("lhttpdsid")
        if lhttpdsid is None:
            text = await response.text()
            raise Exception("Could not get lhttpdsid cookie: " + text)
        response.raise_for_status()

        # Login step 2 - Get security token
        data = json.dumps({"system": {"basicSettings": {"adminName": self._username, "adminPasswd": self._password}}})
        response = await self._session.post(url=self._base_url + "/socketCommunication", data=data,
                                            cookies={"lhttpdsid": lhttpdsid})
        response.raise_for_status()
        _LOGGER.debug("login security token response=%s", await response.text())

        # Older firmwares use a response header
        security_token = response.headers.get("security")

        # Newer firmewares return a security token in the response
        text = ""
        if security_token is None:
            text = await response.text()
            result = json.loads(text)
            if "system" in result and "security_token" in result["system"]:
                security_token = result["system"]["security_token"]

        if security_token is None:
            raise Exception("Could not get security token: " + text)

        # TODO: is python thread safe? I have no idea. If not, we should guard when settings these two values
        self._lhttpdsid = lhttpdsid
        self._security_token = security_token

    async def async_logout(self):
        """ async_logout issues a log out action for the currently auth session"""
        _LOGGER.debug("Logging out with username %s", self._username)
        data = json.dumps({self._username: self._username})
        response = await self._session.post(url=self._base_url + "/logout", data=data,
                                            cookies=self.get_auth_cookie(), headers=self.get_auth_header())
        response.raise_for_status()

    async def async_get_state(self, check_firmware: Optional[bool] = False) -> DeviceState:
        """ async_get_state gets the current state from the access point (mac address, name, firmware, etc) """
        data = STATE_REQUEST_DATA.copy()

        if (self._internet_connectivity_check is None or time.time() - self._internet_connectivity_check) > 3600:
            system_data = data["system"]
            monitor_data = system_data["monitor"]
            monitor_data["internetConnectivityStatus"] = ""

            self._internet_connectivity_check = time.time()

        if check_firmware:
            system_data = data["system"]
            system_data["FwUpdate"] = {
                    "ImageAvailable": "",
                    "ImageVersion": ""
            }

            self._firmware_update_check = time.time()

        request_data = json.dumps(data)

        result = await self.async_post(request_data)
        system = result["system"]
        monitor = system["monitor"]

        state = DeviceState()
        state.firmware_version = monitor["sysVersion"]
        state.device_name = result["system"]["basicSettings"]["apName"]
        state.model = monitor["productId"]
        state.mac_address = monitor["ethernetMacAddress"]
        state.serial_number = monitor["sysSerialNumber"]
        state.total_number_of_devices = monitor["totalNumberOfDevices"]
        state.firmware_update_available = "FwUpdate" in system and "ImageAvailable" in system["FwUpdate"] and int(
            system["FwUpdate"]["ImageAvailable"]) > 0
        state.stats = {}

        if "stats" in monitor:
            stats = monitor["stats"]
            for lan in ["lan", "wlan0", "wlan1"]:
                if lan in stats:
                    state.stats[lan] = Stat(
                        safe_cast(stats[lan]["channelUtil"], int, 0) if "channelUtil" in stats[lan] else 0,
                        parse_human_string(stats[lan]["traffic"]))

        return state

    # {"system":{"wlanSettings":{"wlanSettingTable":{"ssidSetDetails":
    # {"SSID3":{"wlan0":{"vap1":{"vapProfileStatus":"1", "ssid":"AT&T"}},
    #           "wlan1":{"vap1":{"vapProfileStatus":"1", "ssid":"AT&T"}}}}}}}}
    async def async_get_ssids(self) -> List[Ssid]:
        """ async_get_ssids gets the SSIDs from the access point. Returns a list of ssid"""
        data = json.dumps({"system": {"wlanSettings": {"wlanSettingTable": {"ssidGetDetails": ""}}}})
        result = await self.async_post(data)
        details = result["system"]["wlanSettings"]["wlanSettingTable"]["ssidGetDetails"]

        ssids = []
        for ssid_index, ssid_value in details.items():
            for i in range(4):
                wlan_id = "wlan" + str(i)
                if wlan_id in ssid_value:
                    ssids.extend(self.load_wlan(ssid_index, wlan_id, ssid_value[wlan_id]))

        return ssids

    async def async_enable_ssid(self, ssids: List[Ssid], enable: bool):
        """ async_enable_ssid will turn an ssid on or off. All supplied ssids but be the same ssid, but there
        can be more than one, for example 2.5 GHz and 5.0 GHz"""
        if len(ssids) == 0:
            _LOGGER.warning("No ssids supplied")
            return

        ssid_id = ssids[0].ssid_id
        status = "1" if enable else "0"
        details = {}

        for ssid in ssids:
            details[ssid.wlan_id] = {ssid.vap: {"vapProfileStatus": status, "ssid": ssid.ssid}}

        data = json.dumps({"system": {"wlanSettings": {"wlanSettingTable": {"ssidSetDetails": {ssid_id: details}}}}})

        _LOGGER.debug("Setting SSID '%s' enabled state to %s", ssids[0].ssid, enable)
        result = await self.async_post(data)
        _LOGGER.debug("result=%s", result)

    async def check_for_firmware_updates(self):
        """ check_for_firmware_updates tells the device to check for firmware updates"""
        _LOGGER.debug("Checking for firmware updates")
        data = json.dumps({"method": 5, "upgradeCheck": 0})
        response = await self._session.post(url=self._base_url + "/LogFile", data=data,
                                            cookies=self.get_auth_cookie(), headers=self.get_auth_header())
        response.raise_for_status()

    @staticmethod
    def load_wlan(ssid_index: str, wlan_id: str, vaps) -> List[Ssid]:
        """
        Returns a dictionary of ssid unique IDs to the Ssid

        ssid_index: example: SSID1, SSID2, etc
        wlan_id: example: wlan0, wlan1 where wlan0=2.5 GHz, wlan1=5.0 GHz
        vaps: "vap1": { "vapProfileStatus": 0, "ssid": "My_Network_Name", "hideNetworkName": 0, ...
        """
        ssids = []
        for vid, vap in vaps.items():
            ssid = Ssid()

            ssid.ssid_id = ssid_index
            ssid.ssid = vap["ssid"]
            ssid.vap = vid
            ssid.wlan_id = wlan_id
            ssid.enabled = "vapProfileStatus" in vap and vap["vapProfileStatus"] == 1
            ssid.ssid_index = ssid_index
            ssid.unique_id = f"{ssid_index}_{wlan_id}_{vid}_{ssid.ssid}"
            if ssid is not None:
                ssids.append(ssid)

        return ssids

    async def async_post(self, data: {}):
        async def call():
            return await self._session.post(url=self._base_url + "/socketCommunication", data=data,
                                            cookies=self.get_auth_cookie(), headers=self.get_auth_header())

        response = await call()
        text = await response.text()
        result = json.loads(text)

        if response.status == 401 or ("status" in result and result["status"] == 100):
            await self.async_login()
            response = await call()
            response.raise_for_status()
            text = await response.text()
            result = json.loads(text)

        if result["status"] != 0:
            _LOGGER.warning("Invalid response fetching state: %s", text)

        return result

    def get_auth_cookie(self) -> dict:
        return {"lhttpdsid": self._lhttpdsid}

    def get_auth_header(self) -> dict:
        return {"security": self._security_token}

    @staticmethod
    def get_cookies(response: ClientResponse) -> dict:
        """
        get_cookies
        returns
        a
        dictionary
        with the key as the cookie name and the value as the cookie value
        for all cookies found in the response cookie header.This does not handle duplicate cookie names.
        """
        cookies = {}
        for cookie_headers in response.headers.getall(hdrs.SET_COOKIE, ()):
            # hdr looks like this:
            # lhttpdsid=some_value; Path=/; HttpOnly; SameSite;
            key_value_pairs = cookie_headers.split(";")
            for kv_line in key_value_pairs:
                kv_pair = kv_line.split("=", maxsplit=1)
                cookies[kv_pair[0].strip()] = "" if len(kv_pair) <= 1 else kv_pair[1].strip()
        return cookies
