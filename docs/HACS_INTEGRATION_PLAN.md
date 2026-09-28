# Work plan — Vidos X integration for Home Assistant (HACS)

Goal: a HACS-distributable integration that lets Home Assistant control Vidos X intercoms
(Vidos / Quvii TDK-cloud devices) and show their state/video.

> Terminology: **HACS stores repositories, not "add-ons"**. Two possible deliverables:
> * **Custom integration** (`type: integration` in HACS) — the normal path, pure Python,
>   installed through HACS. *This is the recommended target.*
> * **Home Assistant OS add-on** (Docker container in the add-on store) — only needed if we
>   require the proprietary 32-bit ARM P2P native library for video, or a bridge daemon.
>   Optional Phase 4, not required for door opening + status.

Deliverable chosen below: HACS custom integration `vidos_x`, with an optional later add-on.

---

## Architecture options (decision)

| Option | What it gives | Effort | Risk |
|---|---|---|---|
| **A. LAN CGI control** (recommended core) | `POST http(s)://<ip>:<cgiPort>/tdkcgi` with XML envelope → open door, status, arm/disarm, ONVIF password | Low–medium | Needs device IP + credentials (from cloud binding) |
| **B. Cloud account (XML duplex)** | Device discovery (`get-device-list`: ip, cgiPort, dynamic password, online status), alarm history (`/UserAlarm`) | Medium | Protocol reverse-engineered but not yet validated; region/service discovery done by native lib — we must pin `vidos.qvcloud.net` |
| **C. ONVIF/RTSP video** | Camera entities via HA's `onvif`/`generic` camera building blocks | Low if hardware supports it | **Unverified** (device exposes `get.onvif.pwd`, reports `onvifSupport`) |
| **D. P2P video (native lib)** | App-equivalent live view | Very high | 32-bit-only `.so`, no source — defer to optional add-on, likely never |

Plan: **A + B for control/state, C for video**, D explicitly out of scope for v1.

---

## Phase 0 — Ground truth on hardware (1–2 days, blocks everything)

1. Get the device IP + `cgiPort` (from the app's device detail, or cloud `get-device-list`).
2. Capture one app↔device session with `mitmproxy` (app trusts system CAs? if not, use a
   rooted device / `adb` + `tcpdump` on LAN) to record:
   - exact XML envelope for `set.device.opendoor` (header fields `security/username/password/nc`),
   - whether plaintext (`security=username`) or hashed (`usernametoken`) is used,
   - whether HTTPS or HTTP, and the device certificate.
3. Port-scan the device: `nmap -sV -p- <ip>` — look for 554 (RTSP), ONVIF (80/8899/2020),
   80/443 (CGI). Probe ONVIF with `onvif-discover` + credentials from `get.onvif.pwd`.
4. Decide final v1 scope from results (e.g. if ONVIF missing → camera entity degrades to
   "unavailable" or uses a snapshot CGI if one exists).

Exit criteria: a working `curl` that opens the door (or a documented failure), and a known
RTSP URL or a clear "no video" decision.

> ✅ **V1.0 verified (2026-09-28, IDS9483AW):** `tools/probe.py` achieved
> `error=0` on `get.device.status` and `set.device.opendoor` (door opened).
> Confirmed protocol: `POST https://<ip>:443/tdkcgi`, header
> `username=adminapp2` + `password=sha256hex(first-contact password)` +
> `passwordencode=1` + `security=username`; unlock content
> `door=0` + `locknumber=0` + `password=sha256hex(unlock password)`
> (= first-contact password). Captured fixture in `vidos-x/tests/fixtures/`,
> integration patched (`vidos-x/custom_components/vidos_x/cgi.py`).
> Remaining for later phases: RTSP/ONVIF scan, cloud discovery (V2.0), packet
> capture only needed for `usernametoken` fallback (not required by this device).

---

## Phase 1 — Python protocol library (2–4 days)

Separate, testable package used by the integration (repo: same repo, `vidos_x/` package,
or standalone `vidosx-protocol`):

- `cloud/client.py` — OAuth password grant against `https://vidos.qvcloud.net/qvoauthv2/token`
  (params: `grant_type, client_id, client_type, oemid=..., appid=..., usr, pwd, region_id,
  client_flag`), token caching/refresh (JWT `exp`).
- `cloud/userapi.py` — XML envelope up-channel `POST /auth/user;jus_duplex=up` (+ nologin
  variant), commands `login`, `get-device-list`, `get-device-token`.
- `cloud/alarmapi.py` — `POST /UserAlarm` with `client-login` / `client-query-recordlist`
  for ring/alarm events (poll fallback until push is understood).
- `device/cgi.py` — `POST /{scheme}://{ip}:{cgiPort}/tdkcgi` XML envelope builder/parser;
  helpers `open_door(channel, lock, password)`, `get_status()`, `get/set(onvif_pwd)`,
  `arm/disarm`, `get_lock_status`.
- `device/auth.py` — implement `security=username` first; add `usernametoken` once the hash is
  identified from Phase 0 captures (reimplement in pure Python, test against capture).
- Unit tests: fixture XML requests/responses recorded in Phase 0 (no hardware needed in CI).

Exit criteria: `pytest` green with recorded fixtures; a CLI (`python -m vidos_x.cli open-door <uid>`).

---

## Phase 2 — Home Assistant custom integration (3–5 days)

Repo layout (this is what HACS consumes):

```
vidos-x/                          # GitHub repo, hacs.json {"name":"Vidos X","render_readme":true}
├── hacs.json
├── README.md
├── info.md
├── custom_components/vidos_x/
│   ├── manifest.json             # domain vidos_x, "iot", config_flow, no deps beyond HA core
│   ├── __init__.py               # setup entry, coordinator lifecycle, services
│   ├── config_flow.py            # two-step: cloud login OR "LAN only (IP + password)"
│   ├── coordinator.py            # DataUpdateCoordinator: device list + CGI status polling
│   ├── entity.py                 # base entity with device info
│   ├── binary_sensor.py          # doorbell/ring, motion, armed, online
│   ├── sensor.py                 # lock status, SD/TF state, last ring time, signal
│   ├── lock.py                   # unlock (button-like, maps to set.device.opendoor)
│   ├── button.py                 # "Open door" momentary button (safest default)
│   ├── camera.py                 # ONVIF/Generic camera (stream URL from ONVIF probe)
│   ├── switch.py                 # arm/disarm (g.alm.disarm / s.alm.disarm)
│   ├── diagnostics.py            # redacted dump: ids, versions, reachable endpoints
│   ├── services.yaml             # open_door service with channel/lock/password fields
│   └── strings.json / translations/en.json, pl.json
└── tests/                        # pytest + HA test harness for config flow & entities
```

Behaviour:
- **Config flow**: (1) cloud credentials → fetch device list → show devices to import;
  (2) fallback "manual" mode: IP + `cgiPort` + device password (no cloud at all).
  Store only what's needed; passwords in HA config entry (encrypted store), never logged.
- **Coordinator** polls (default 30 s): `get.device.status` / `get.lock.status` per device;
  cloud mode additionally polls alarm records for ring events (fast interval, e.g. 5 s,
  only when a doorbell event source is configured).
- **Entities**: one `button.open_door` + optional `lock` (off by default), `binary_sensor.ring`,
  `binary_sensor.online`, `sensor.lock_status`, `switch.alarm_armed`, `camera`.
- **Options flow**: poll intervals, TLS verify on/off (device certs), default channel/lock number.
- Quality gates: `ruff`, `mypy`, `pytest`, HA brand guidelines (naming, entity categories,
  `has_entity_name`, device registry info with manufacturer "Vidos").

Exit criteria: integration works on a dev HA instance with hardware; `hassfest` and
`hacs-action` validation pass locally.

---

## Phase 3 — HACS publication (1 day)

1. Public GitHub repo `vidos-x` (README with screenshots, supported models, **security notes**).
2. Register in HACS default store: open PR to
   `hacs/integration` with the repo URL and `category: integration`
   (repo must have `hacs.json`, releases with `vX.Y.Z` tags, valid `manifest.json`).
3. Add `hassfest` + `hacs` GitHub Actions + `pytest` workflow so PRs are validated.
4. Publish release `v0.1.0` (downloadable via HACS), document manual install as fallback.
5. Optional: submit to HA core (long term, requires upstreamable code + brand assets).

---

## Phase 4 — Optional add-on (only if video without ONVIF is required)

- Docker image (armhf/aarch64) running a small bridge that loads `libqv-p2p-v2.so` +
  `liblive_player.so` via `qemu-arm`/chroot — exports a local RTSP/HTTP-flv stream HA can consume.
- Realistic assessment: high effort, licensing/ToS risk, brittle ABI; only pursue if Phase 0
  proves no ONVIF/RTSP and users demand live video.
- If pursued: separate `addon` repo, same GitHub org, referenced from the integration README.

---

## Risks / dependencies

| Risk | Mitigation |
|---|---|
| Device protocol (`usernametoken`) not yet captured | Phase 0 capture first; start with `security=username` |
| Cloud region discovery is native-lib-bound | Pin `vidos.qvcloud.net`, verify service paths in Phase 0 |
| Cloud ToS may forbid third-party API use | Default to LAN-only mode; cloud optional; document clearly |
| No ONVIF/RTSP on some models | Camera entity optional; degrade gracefully |
| 32-bit-only native libs | Excluded from Python integration by design |
| Credentials handling | HA config entries only, redacted diagnostics, no logging of envelopes |

## Rough effort

* Phase 0: 1–2 days (hardware + capture)
* Phase 1: 2–4 days
* Phase 2: 3–5 days
* Phase 3: 1 day
* **Total to a HACS-releaseable v0.1.0: ~1.5–2.5 weeks** part-time, hardware capture on day 1.

## First concrete next steps

1. Run Phase 0 on the user's device (needs: device IP, app capture method, ideally ONVIF probe).
2. Scaffold repo (`hacs.json`, `custom_components/vidos_x/manifest.json`, config flow stub).
3. Implement `device/cgi.py` + `open_door` end-to-end (smallest useful slice: one button).
