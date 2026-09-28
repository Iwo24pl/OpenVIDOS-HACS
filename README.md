# Vidos X for Home Assistant

Home Assistant custom integration for **Vidos X** intercoms / door stations
(Vidos sp. z o.o., white-labeled Qualvision/Quvii "TDK cloud" platform).

> **Status: Phase 0 verified (V1.0).** The status poll and door-open commands were
> validated on real hardware (IDS9483AW): header `adminapp2` + `sha256(password)` +
> `passwordencode=1`, unlock content `door`+`locknumber`+`password=sha256(...)`.
> Video (RTSP/ONVIF) and cloud discovery remain unverified (V2.0).

## Features

| Feature | Entity | Status |
|---|---|---|
| Open door (`set.device.opendoor`) | `button.open_door` + `vidos_x.open_door` service | **verified on hardware** (sha256 unlock password) |
| Device online status | `binary_sensor.status` | **verified on hardware** (local poll) |
| Lock state | `sensor.lock_state` | verified field (`devicestatus.lockstatus`), model-dependent |
| Doorbell / ring event | `binary_sensor.doorbell` | field identified (`devicestatus.calling`), not yet live-tested |
| Alarm arm/disarm | `switch.alarm_disarmed` (opt-in) | experimental |
| Live video | `camera` via RTSP URL (opt-in) | requires RTSP/ONVIF on the device (unverified) |
| Device discovery | cloud login (opt-in) | unverified (`vidos.qvcloud.net`) |

Everything except discovery runs **locally**: the integration talks
`https://<device-ip>:443/tdkcgi` directly. No cloud account is required if you add
the device manually (IP + credentials).

## Installation

1. [HACS](https://hacs.xyz) → Integrations → ⋮ → *Custom repositories* →
   category **Integration** → `https://github.com/Iwo24pl/OpenVIDOS-HACS`.
2. Install **Vidos X** and restart Home Assistant.

Manual install: copy `custom_components/vidos_x` into your HA `config/custom_components/`
directory and restart.

## Configuration

* **Manual** – device IP, CGI port (443/80), device username (default `adminapp2`,
  verified) and first-contact password (sent as `sha256` + `passwordencode=1`).
  Scheme `https`/`http`, TLS verification toggle (off for self-signed certs).
* **Cloud account** – Vidos X app credentials used only to *discover* devices
  (IP / port / dynamic password). Unverified.

Options (per device): poll interval, TLS verification, door password,
RTSP stream URL (enables the camera entity), experimental alarm switch.

Service `vidos_x.open_door` targets one or more devices by `device_id`.

## Doorbell notifications

The integration polls `get.device.status` every **10 s** by default (option
*Poll interval*, min 5 s). When `devicestatus.calling` flips to `true` the
binary sensor turns on **and** a `vidos_x.doorbell_rung` event fires — use that
event for notifications:

```yaml
automation:
  - alias: Doorbell rang
    trigger:
      - platform: event
        event_type: vidos_x.doorbell_rung
    action:
      - service: notify.mobile_app_phone
        data:
          message: "Somebody rang the doorbell!"
      - service: persistent_notification.create
        data:
          title: Doorbell
          message: "{{ trigger.event.data.device }} rang at {{ trigger.event.data.when }}"
```

Notes:

* For minimal latency set the poll interval option to **5 s** (a ring must be
  long enough to be caught by a poll; typical intercom calls are 20 s+).
* `binary_sensor.*_doorbell` (plain state, `mdi:doorbell` icon) works too if you prefer
  state-based triggers; attribute `last_rung` holds the last ring timestamp.

## Development

```bash
pip install -r requirements_test.txt
ruff check custom_components tests
python -m compileall -q custom_components
python -m unittest discover -s tests -v      # protocol unit tests, no HA needed
```

Protocol notes live in [`docs/VIDOS_X_PROTOCOL.md`](docs/VIDOS_X_PROTOCOL.md), the
implementation plan in [`docs/HACS_INTEGRATION_PLAN.md`](docs/HACS_INTEGRATION_PLAN.md).

## Verification checklist (Phase 0)

1. ✅ Envelope XML + auth mode confirmed on hardware: `security=username`,
   `adminapp2` + `sha256(password)` + `passwordencode=1`.
2. ✅ `set.device.opendoor` reply `<error>0</error>` (content: `door`, `locknumber`,
   `password=sha256(unlock password)`).
3. Scan the device for RTSP/ONVIF (`554`, ONVIF ports) and set the RTSP URL option *(V2.0)*.
4. Validate cloud discovery responses (`get-device-list`) if you use cloud mode *(V2.0)*.

## Security notes

* Credentials are stored in the config entry (Home Assistant encrypted storage) and
  redacted from diagnostics/logs.
* The official app sends the device password in the CGI XML header
  (`security=username`); treat the device VLAN accordingly.
* This integration is not affiliated with Vidos sp. z o.o.

## License

MIT (repository scaffolding) - see repository `LICENSE` once published.
