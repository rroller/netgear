"""Constants for Netgear."""
# Base component constants
NAME = "Netgear WAX"
DOMAIN = "netgear_wax"
ATTRIBUTION = "Data provided by local device"
ISSUE_URL = "https://github.com/rroller/netgear/issues"

# Icons - https://materialdesignicons.com/
WIFI_ICON = "mdi:wifi"
DEVICES_ICON = "mdi:devices"
UPDATE_ICON = "mdi:update"
CHART_DONUT_ICON = "mdi:chart-donut"
ROUTER_NETWORK_ICON = "mdi:router-network"
LAN_ICON = "mdi:lan"

# Device classes - https://www.home-assistant.io/integrations/binary_sensor/#device-class
CONNECTIVITY_DEVICE_CLASS = "connectivity"
SAFETY_DEVICE_CLASS = "safety"

# Platforms
BINARY_SENSOR = "binary_sensor"
SENSOR = "sensor"
SWITCH = "switch"
PLATFORMS = [BINARY_SENSOR, SENSOR, SWITCH]

# Configuration and options
CONF_ENABLED = "enabled"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_ADDRESS = "address"
CONF_PORT = "port"
CONF_MAC = "mac"

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
This is a custom integration for Netgear WAX access points!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""

STATE_REQUEST_DATA = {
    "system": {
        "monitor": {
            "productId": "",
            "totalNumberOfDevices": "",
            "sysSerialNumber": "",
            "ethernetMacAddress": "",
            "sysVersion": "",
            "FiveGhzSupport": {},
            "stats": {
                "lan": {
                    "traffic": "",
                },
                "wlan0": {
                    "traffic": "",
                    "channelUtil": "",
                },
                "wlan1": {
                    "traffic": "",
                    "channelUtil": "",
                },
            },
        },
        "basicSettings": {
            "apName": "",
        },
    }
}
