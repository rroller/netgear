# Tests

Use Python 3.13 with the Home Assistant version in `requirements.txt`:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements_test.txt
.venv/bin/python -m pytest -q tests
```

The firmware tests use real Home Assistant coordinator/entity classes and the
integration's API client with mocked device HTTP responses. They cover
authentication, firmware-server errors, six-hour scheduling, failure retries,
request isolation, retained update state, late results, and installed-version
changes. They do not flash hardware.

Protocol reference: the web UI in NETGEAR's WAX610/610Y V10.4.1.5 firmware
(`home/www/dist/js/app.bundle.js`). The UI posts
`{"method": 5, "upgradeCheck": 0}` to `/LogFile`, accepts status `0`, handles
status `100` as an expired session, and reports statuses `1` and `2` as Internet
or firmware-server failures. It reads `system.FwUpdate.ImageAvailable` and
`ImageVersion` through `/socketCommunication`. Actual firmware installation is
a separate method `7` command and is not implemented by this integration.
