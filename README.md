# Vidos X for Home Assistant

Home Assistant custom integration for **Vidos X** intercoms / door stations
(Vidos sp. z o.o., white-labeled Qualvision/Quvii "TDK cloud" platform).

> **Status: Phase 0 verified (V1.0) + live video snapshots (v0.3.0) + per-channel
> ring detection (v0.4.0).** The status
> poll and door-open commands were validated on real hardware (IDS9483AW):
> header `adminapp2` + `sha256(password)` + `passwordencode=1`, unlock content
> `door`+`locknumber`+`password=sha256(...)`. **Video:** no RTSP/ONVIF — but the
> proprietary `quii://` media port 34567 is reverse-engineered and ported
> (snapshot camera, see *Video* below). **Rings:** the device's picture-record
> log reports *which* doorbell rang (channel 1/2). Cloud discovery lives in
> `cloud.py` (backend kept, removed from the setup UI).

## Features

| Feature | Entity | Status |
|---|---|---|
| Open door (`set.device.opendoor`) | `button.open_door` + `vidos_x.open_door` service | **verified on hardware** (sha256 unlock password) |
| Device online status | `binary_sensor.status` | **verified on hardware** (local poll) |
| Lock state | `sensor.lock_state` | verified field (`devicestatus.lockstatus`), model-dependent |
| Doorbell / ring event | `binary_sensor.*_doorbell` + `event.*_doorbell` | **per-channel via the ring picture log** (v0.4.0, hardware-verified) + LAN broadcast fallback (Azeno scan/reply, ~6 s after ring) |
| Alarm arm/disarm | `switch.alarm_disarmed` (opt-in) | experimental |
| Live video | `camera.*` snapshot (built-in `quii://` port) | **verified on hardware** (no RTSP/ONVIF; on-demand snapshot via port 34567) |
| Associated cameras | camera entities from other integrations attached to the device page | options: pick entities (multiple) |
| Device discovery | cloud login | **removed from the UI** (`cloud.py` kept for later) |

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
  This is the only setup path; cloud discovery was removed from the UI
  (the backend in `cloud.py` is kept for later).

Options (per device): poll interval, TLS verification, LAN ring detection
(on by default), ring-picture-log detection (on by default; interval 3–30 s,
display names for channel 1/2), snapshot camera (on by default), door
password, open-button
output (`default_door` / `default_lock`, default `1`/`1` = the verified DOOR1
output), associated camera entities (multiple, from other integrations),
experimental alarm switch.

Service `vidos_x.open_door` targets one or more devices by `device_id`. The
`door`/`lock` fields map to the device's lock table (`get.device.attachInfo`);
when omitted they fall back to the configured defaults:

| Output | `door` (channel) | `lock` |
|---|---|---|
| DOOR1 (CAM1) | 1 | 1 |
| DOOR2 (CAM2) | 2 | 1 |
| **Automatic gate** | 0 | 2 |

**DOOR1 (`door: 1`, `lock: 1`) is physically verified** — it is now the default
for the button and the service. `DOOR2` and the gate are accepted (`error=0`)
but not yet heard to actuate — see `docs/VIDOS_X_PROTOCOL.md` §3.1.

## Doorbell notifications

**Primary: the ring picture log (v0.4.0, per-channel).** Every press makes
the station store a tiny picture record; a two-phase
`get.record.session` / `get.record.message` query (every 3 s by default)
picks up new records and their `<channel>` — so the event says **which**
doorbell rang (channel 1 = camera doorbell, channel 2 = dummy button on the
reference install; names configurable in the options). The poller keeps one
session open, primes a two-cycle baseline (the device may answer with a
truncated listing) and collapses records/Azeno into a single event inside a
10 s window. Protocol details and the firmware traps (never send
`filetype=all` — it crashes the CGI service) are in
[`docs/VIDOS_X_PROTOCOL.md`](docs/VIDOS_X_PROTOCOL.md) §4.6.

**Fallback: LAN broadcast (verified 2026-10-02, channel-less).**
`get.device.status` does *not* change when the bell is pressed — polling
alone cannot see a ring. The integration therefore also listens on the LAN
for the Azeno discovery chain: the
Vidos app on a phone (woken by the push notification, app closed) broadcasts
`ASZENO.SEARCH.V4.1` to UDP 5000, and the door station answers on UDP 5001 —
observed ~6 s after every ring, silence otherwise. Both sources fire the
`vidos_x.doorbell_rung` event, pulse the binary sensor for 15 s and trigger
the `event.*_doorbell` entity:

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
          message: >-
            {{ trigger.event.data.channel_name or trigger.event.data.device }}
            rang at {{ trigger.event.data.when }}
```

Notes:

* *Ring picture log detection* (on by default) needs nothing but the device
  on the LAN; *LAN ring detection* additionally requires a phone with the
  Vidos X app **on the same LAN** (the burst comes from the phone; HA and
  the phone just need to share a broadcast domain). Turn it off in the
  options if you don't want UDP 5000/5001 bound.
* HA must receive **broadcasts** for the fallback path: bare-metal/VM on the
  LAN is fine; Docker bridge networks usually are not (use
  `network_mode: host`).
* Known caveat: opening the Vidos app manually runs the same discovery scan
  and can produce a false ring event (now deduplicated against a log ring
  within 10 s).
* Event payload: `device`, `entry_id`, `when`, `source`
  (`records` / `lan-scan` / `lan-reply` / `cgi`), `channel` (1/2 or `null`
  for channel-less sources), `channel_name` ("Channel 1"/"Channel 2" by
  default, configurable).
* `event.*_doorbell` (device class `doorbell`, event type `ring`) is the
  stateless alternative — its state changes to a timestamp on every press:

  ```yaml
  trigger:
    - platform: state
      entity_id: event.your_intercom_doorbell
  ```
* `binary_sensor.*_doorbell` (plain state, `mdi:doorbell` icon) is ON for 15 s
  after each ring; attributes `last_rung`, `channel`, `channel_name`.
* Debug the LAN chain standalone with `python tools/lanwatch.py`.

## Video

**The station exposes no standard video protocol on the LAN** (probed
2026-10-02): port scan shows only `443` (CGI), `34567` (proprietary media) and
`8765` (unknown binary protocol); `554`, ONVIF ports and HTTP are closed;
`get.network.base`/`get.network.config`/`get.onvif.pwd` all answer `error=-10`
(firmware does not implement them).

**But port 34567 speaks a fully reverse-engineered protocol** (the official
app's `quii://` URL), and the integration ports it: the `camera` entity grabs
a **still snapshot on demand** — it opens a short media session, pulls the
first H.264 keyframe (~2.2 s) and decodes it to JPEG locally:

* Needs the **ffmpeg binary** (installed with Home Assistant / add-on; the
  manifest declares the `ffmpeg` integration as a dependency).
* Snapshots are cached for 5 s and the entity backs off 15 s after failures —
  there is **no continuous streaming** and essentially no background traffic.
* Turn it off in the options (*Snapshot camera*); the camera then isn't loaded
  at all.
* Per-channel caveat: `idc=1` is CAM1 (door view, 352×280); CAM2 streams the
  blank default while its lens is disconnected.

Still useful: cameras from other integrations (IP cam / NVR pointed at the
door) can be **associated** in the options — they appear on the intercom's
device page (association only, no restream).

Wire-level details: [`docs/VIDOS_X_PROTOCOL.md`](docs/VIDOS_X_PROTOCOL.md) §4.

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
3. ✅ Video probe: no RTSP/ONVIF on this firmware — `554`/ONVIF ports closed,
   `get.network.base`, `get.network.config`, `get.onvif.pwd` → `error=-10`;
   media only via proprietary port 34567 (`quii://`, native `live_player`).
4. ✅ `quii://` port 34567 reverse-engineered and ported (v0.3.0): handshake,
   AES-256-CBC framing and keyframe extraction verified on hardware; snapshot
   camera produces JPEG via local ffmpeg (see §4 of the protocol doc).
5. ✅ Ring picture log queried on hardware (v0.4.0): two-phase
   `get.record.session`/`get.record.message`, records carry the ringing
   channel (camera-press → `<channel>1</channel>` confirmed); `filetype=all`
   crash trap documented (§4.6).
6. Cloud discovery UI removed; `cloud.py` backend kept for a later release.

## Security notes

* Credentials are stored in the config entry (Home Assistant encrypted storage) and
  redacted from diagnostics/logs.
* The official app sends the device password in the CGI XML header
  (`security=username`); treat the device VLAN accordingly.
* This integration is not affiliated with Vidos sp. z o.o.

## License

MIT (repository scaffolding) - see repository `LICENSE` once published.
