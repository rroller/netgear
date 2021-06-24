# Home Assistant Netgear Integration

The `Netgear` [Home Assistant](https://www.home-assistant.io) integration allows you to integrate your Netgear access
points into Home Assistant. Today this integration supports the WAX device models but is coded to make it easy to add
other devices, simply implement the NetgearClient interface.

Supports turning on WI-FI SSIDs. This is particular useful if you want to automate turning on your guest WI-FI network.

## Installation

### HACS install

To install with [HACS](https://hacs.xyz/):

TODO: Waiting for this integration to be published in HACS.

### Manual install

To manually install:

```bash
# Download a copy of this repository
$ wget https://github.com/rroller/netgear/archive/netgear-main.zip

# Unzip the archive
$ unzip netgear-main.zip

# Move the netgear directory into your custom_components directory in your Home Assistant install
$ mv netgear-main/custom_components/netgear <home-assistant-install-directory>/config/custom_components/
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

Please let me know if you've tested with additional devices

# Entities

## Switches

Switch |  Description |
:------------ | :------------ |
SSID | Enables or disables a WI-FI ssid

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
    custom_components.netgear: debug
```
