# Vidos X for Home Assistant

Home Assistant custom integration for **Vidos X** intercoms / door stations
(Vidos sp. z o.o., white-labeled Qualvision/Quvii "TDK cloud" platform).

> **Status: 1.0.0 — rebuilt as a 1:1 replication of the official app's local
> protocol.** The v0.x line was hard-deleted; the full history lives at git tag
> `legacy-v0.4.0`. The protocol layer (`custom_components/vidos_x/proto/`) is
> derived from an exhaustive reverse-engineering of the official app
> (`com.vidos.vidosx` V1.7) — command inventory, request/response beans, auth
> and call graphs are documented in **[`docs/APP_PARITY.md`](docs/APP_PARITY.md)**;
> hardware-verified facts (unlock shapes, record log, QUII video) are in
> **[`docs/VIDOS_X_PROTOCOL.md`](docs/VIDOS_X_PROTOCOL.md)**.

## Features

| Feature | Entity | Status |
|---|---|---|
| Open door (`set.device.opendoor`) | `button.open_door` + `vidos_x.open_door` service | **verified on hardware** (`door`+`locknumber`+`password=sha256(...)`) |
| Device online status | `binary_sensor.status` | **verified on hardware** (local poll) |
| Lock state | `sensor.lock_state` | verified field (`devicestatus.lockstatus`), model-dependent |
| Doorbell / ring event | `binary_sensor.*_doorbell` + `event.*_doorbell` | **per-channel via the ring picture log** (hardware-verified) |
| LAN ring detection (Azeno) | same event, source-tagged | **optional, off by default** (device/app UDP 5000/5001 chain) |
| Alarm arm/disarm | `switch.alarm_disarmed` (opt-in) | experimental |
| Live video | `camera.*` snapshot (built-in `quii://` port) | **verified on hardware** (no RTSP/ONVIF; on-demand snapshot via port 34567) |
| Associated cameras | camera entities from other integrations attached to the device page | options: pick entities (multiple) |

Everything runs **locally**: the integration talks
`https://<device-ip>:443/tdkcgi` directly. No cloud account is required.

### Protocol parity (what "1:1" means here)

* **Commands & beans** — the milestone-1 command set, request/response bean
  fields (including SimpleXML wire renames such as `channelNum`→`door`) are
  taken from the app's dex, verbatim (`proto/request_help.py`, `proto/beans/`).
* **Auth** — XML header `security=httpauthen` / `username=adminapp2` /
  `passwordencode=1` (`DeviceRequestHelp.initHeader`), plus the app's HTTP
  Digest handshake (`DeviceAuthHeaderInterceptor`, username `adminapp`) handled
  automatically when the device answers `401`.
* **Live view** — the app plays video through native `liblive_player.so`; the
  hardware-verified Python port of that wire protocol is kept
  (`proto/live_player.py`, decision D3).
* **Ring detection** — the app receives rings via cloud push; for local-only
  HA the integration polls the device's ring picture log
  (`get.record.session`/`get.record.message`, decision D1). The ASZENO
  broadcast listener is kept as an *optional* source (default off, D2).
* Settings commands the app exposes over its JSON dialect
  (`get/set.auto.unlock`, `get/set.call.time`, …) are implemented in
  `proto/device_json_api.py` and will be surfaced after a live wire capture
  (APP_PARITY §11).

## Installation

1. [HACS](https://hacs.xyz) → Integrations → ⋮ → *Custom repositories* →
   category **Integration** → `https://github.com/Iwo24pl/OpenVIDOS-HACS`.
2. Install **Vidos X** and restart Home Assistant.

Manual install: copy `custom_components/vidos_x` into your HA `config/custom_components/`
directory and restart.

## Configuration

* **Manual** – device IP, CGI port (443/80), device username (default `adminapp2`),
  first-contact password (sent as `sha256` + `passwordencode=1`; also used for
  the Digest handshake), scheme `https`/`http`, TLS verification toggle
  (off for self-signed certs).

Options (per device): poll interval, TLS verification, ring-picture-log
detection (on by default; interval 3–30 s, display names for channel 1/2),
LAN ring detection (off by default), snapshot camera (on by default), door
password, open-button output (`default_door` / `default_lock`, default `1`/`1`
= the verified DOOR1 output), associated camera entities (multiple),
experimental alarm switch.

Service `vidos_x.open_door` targets one or more devices by `device_id`. The
`door`/`lock` fields map to the device's lock table (`get.device.attachInfo`);
when omitted they fall back to the configured defaults:

| Output | `door` (channel) | `lock` |
|---|---|---|
| DOOR1 (CAM1) | 1 | 1 |
| DOOR2 (CAM2) | 2 | 1 |
| **Automatic gate** | 0 | 2 |

**DOOR1 (`door: 1`, `lock: 1`) is physically verified** — it is the default for
the button and the service. `DOOR2` and the gate are accepted (`error=0`) but
not yet heard to actuate — see `docs/VIDOS_X_PROTOCOL.md` §3.1.

## Doorbell notifications

**Primary: the ring picture log.** Every press makes the station store a tiny
picture record; a two-phase `get.record.session` / `get.record.message` query
(every 3 s by default) picks up new records and their `<channel>` — so the
event says **which** doorbell rang (channel 1 = camera doorbell, channel 2 =
dummy button on the reference install; names configurable in the options).
The poller keeps one session open, primes a two-cycle baseline (the device may
answer with a truncated listing), and detects new records by filename set +
timestamp cutoff.

Each accepted ring fires:

* a `vidos_x.doorbell_rung` **event bus event** with `channel`, `channel_name`,
  `source` (`records` / `lan-scan` / `lan-reply` / `cgi`), `when`, `entry_id`;
* the doorbell **binary sensors** for 15 s;
* the `event.*_doorbell` entity with its channel attribute.

Sources observed within 10 s collapse into one press (record log first, the
phone-woken Azeno burst ~6 s later).

**Optional: LAN broadcast (Azeno).** The app/door-station discovery chain
(`ASZENO.SEARCH.V4.1` on UDP 5000 → reply on 5001) is observable seconds after
a ring when a phone on the same Wi-Fi wakes the app. Enable it in the options
if you want a second, faster source; it is off by default.

## Video (snapshots)

There is no RTSP/ONVIF. The integration speaks the device's proprietary
`quii://` media protocol on TCP **34567** directly: `get.device.streamkey` →
Setup `0xA9` → Play `0x01` (AES-256-CBC, IV `'0'×16`, SHA-256 trailer) →
media frames carrying annex-B H.264; the first keyframe is fed to `ffmpeg` for
an on-demand JPEG snapshot (TTL 5 s). Framing/crypto adapted from the MIT
[quii-lan-client](https://github.com/fariborz0015/quii-lan-client).

## Development

* Protocol spec & parity matrix: `docs/APP_PARITY.md` (Phase-1 app RE),
  `docs/VIDOS_X_PROTOCOL.md` (hardware captures).
* Lint: `ruff check custom_components tests`
* Tests (HA-free; `homeassistant`-dependent tests auto-skip when absent):
  `python -m unittest discover -s tests`
* Credentials never enter the repository (`DEVICE_IP` / `DEVICE_AUTH_CODE` /
  `DEVICE_STREAM_KEY` env vars for manual probing).

## Credits

* Protocol RE baselines: [quii-lan-client](https://github.com/fariborz0015/quii-lan-client)
  (MIT), [fdaneluzzi/homeassistant-allo-wt7](https://github.com/fdaneluzzi/homeassistant-allo-wt7),
  [totoantibes/golmar-quvii-ha](https://github.com/totoantibes/golmar-quvii-ha),
  [jdntortosa/fermax-wayfi-ha](https://github.com/jdntortosa/fermax-wayfi-ha).
* Official app `com.vidos.vidosx` V1.7 — source of the parity specification.
