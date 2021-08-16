# Home Assistant Netgear Integration

The `Netgear` [Home Assistant](https://www.home-assistant.io) integration is a completely local (no cloud) integration that allows you to integrate your Netgear WAX access points into Home Assistant. Today this integration supports the WAX device models but is coded to make it easy to add other devices in the future.

Supports turning on WI-FI SSIDs. This is particular useful if you want to automate turning on your guest WI-FI network.

## Installation

### HACS install

To install with [HACS](https://hacs.xyz/):
1. Click on HACS in the Home Assistant menu
1. Click on Integrations
1. Click the EXPLORE & ADD REPOSITORIES button
1. Search for `Netgear`
1. Click the INSTALL THIS REPOSITORY IN HACS button
1. Restart Home Assistant
Configure the access point by going to Configurations -> Integrations -> ADD INTERATIONS button, search for Netgear and configure the device.

### Manual install

To manually install:

```bash
# Download a copy of this repository
$ wget https://github.com/rroller/netgear/archive/netgear-main.zip

# Unzip the archive
$ unzip netgear_wax-main.zip

# Move the netgear_wax directory into your custom_components directory in your Home Assistant install
$ mv netgear_wax-main/custom_components/netgear_wax <home-assistant-install-directory>/config/custom_components/
```

> :warning: **After executing one of the above installation methods, restart Home Assistant. Also clear your browser cache before proceeding to the next step, as the integration may not be visible otherwise.**

### Setup

1. Now the integration is added to HACS and available in the normal HA integration installation, so...
2. In the HA left menu, click `Configuration`
3. Click `Integrations`
4. Click `ADD INTEGRATION`
5. Type `Netgear` and select it
6. Enter the details:
    1. **Username**: Your device username, typically `admin`
    2. **Password**: Your device password
    3. **Address**: Your device IP address
    4. **Port**: Your device port, typical `443`

# Known supported devices

* WAX-610
* WAX-620
* Probably the other WA* devices but I haven't tested them

Please let me know if you've tested with additional devices

# Known issues
* Toggling wifi on/off taks about 25 seconds. During that time the switch in the UI may toggle to the original setting until the underlying call completes on the API. There's no harm but just a jaring user experience that needs to be worked out.

# Preview

![netgear](https://user-images.githubusercontent.com/445655/124390453-935a9f80-dca0-11eb-9c75-fe989dd97b44.png)

# Entities

## Switches

Switch |  Description |
:------------ | :------------ |
SSID | Enables or disables a WI-FI ssid

## Sensors

Sensor |  Description |
:------------ | :------------ |
Update Sensor | Shows when the device has a firmware update. Checked every few hours
WLAN Channel Util | Shows how saturated the channel is
Traffic Sensor | Shows a count of bytes sent over the wlan or lan interface
Connected Clients Sensor | Shows a count of the total number of connected clients
IP Address Sensor | Shows the device IP address
MAC Sensor | Shows the device MAC

# Local development

If you wish to work on this component, the easiest way is to
follow [HACS Dev Container README](https://github.com/custom-components/integration_blueprint/blob/master/.devcontainer/README.md)
. In short:

* Install Docker
* Install Visual Studio Code
* Install the devcontainer Visual Code plugin
* Clone this repo and open it in Visual Studio Code
* View -> Command Palette. Type `Tasks: Run Task` and select it, then click `Run Home Assistant on port 9123`
* Open Home Assistant at http://localhost:9123

# Debugging

Add to your configuration.yaml:

```yaml
logger:
  default: info
  logs:
    custom_components.netgear_wax: debug
```
