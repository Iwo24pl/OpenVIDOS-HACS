# Vidos X (`com.vidos.vidosx`) — protocol & connection dossier

Source: static analysis of the unpacked XAPK (base APK decompiled with jadx 1.5.2, plus
`assets/`, `resources.arsc`, native `.so` strings). Anything marked **VERIFY** must be
confirmed against real hardware/network traffic.

## Phase 0 verification status (V1.0) — hardware-confirmed

Tested against an **IDS9483AW** door station (fw `V100.R001.A311.00.G0108.B018`),
2026-09-28, via `tools/probe.py` (fixture: `vidos-x/tests/fixtures/device_status_sample.xml`):

| Item | Result |
|---|---|
| Endpoint | `POST https://<ip>:<cgiPort>/tdkcgi` (XML envelope) ✅ |
| Header variant | **`lan-hash`**: `username=adminapp2`, `password=sha256hex(first-contact password)`, `passwordencode=1`, `security=username` ✅ |
| Secrets | two distinct: QR passcode (`authCode`) vs first-contact "initial password" (`device.password`); unlockPassword = authCode = first-contact password at add time ✅ |
| `get.device.status` | `<error>0</error>`; content fields: `info.model`, `info.version`, `channel.id`, `devicestatus.calling` (ring), `devicestatus.lockstatus`, `devability`, `key`, `tdc` ✅ |
| `set.device.opendoor` | `<error>0</error>` + **physical relay actuation confirmed** with content `door=1`, `locknumber=1`, `password=sha256hex(first-contact password)` (`DeviceUnlockContent` shape) ✅ 2026-10-02. Note: the device returns `error=0` even for pairs with no configured output (e.g. `door=0, lock=0`) — `error=0` alone does not prove actuation. |
| Error codes | `-10028` incorrect password, `-10029` busy (from `SDKStatus.java`) |
| RTSP/ONVIF, cloud discovery | RTSP/ONVIF **probed absent** (§4, 2026-10-02); cloud discovery UI removed (`cloud.py` kept) |
| Live video | **`quii://` media protocol on TCP 34567 verified end-to-end** (handshake → AES-256 → H.264 352×280@25fps decoded frame) ✅ 2026-10-02, see §4 |

---

## 1. App identity / vendor

| Item | Value |
|---|---|
| Package | `com.vidos.vidosx`, "Vidos X", V1.7 (versionCode 12), minSdk 26 / targetSdk 36 |
| Vendor | Vidos sp. z o.o., Sokołowska 44, 05-806 Sokołów, Poland (biuro@vidos.pl) |
| SDK vendor | Qualvision / **Quvii (Shanghai)** — white-label SDK, package `com.quvii.*` |
| Cloud platform | **TDK cloud** (XML request header `FLAG = "tdkcloud"`), Firebase project `tdk-app` |
| OEM / app ids | `OEM_ID = "G0108"`, `APP_ID = 4108`, `CLIENT_TYPE` set from login mode, `AUTH_CODE = 2`, `S_VERSION = "S27647"` |
| Auth key | `serviceKey = Base64("G0108|4108|0")` |
| Bootstrap host | `AppConfig.SERVER_ADDRESS = "vidos.qvcloud.net"`, port **443** (`SERVER_PORT`) |
| Languages | `en,pl` (default `en`) |
| Cloud storage | disabled (`APP_CLOUD_STORAGE_ENABLE=false`) → recordings live on device SD/TF card |

Config constants: `com/quvii/qvfun/publico/common/AppConfig.java`, `com/quvii/qvfun/core/BuildConfig.java`,
init in `com/quvii/qvfun/publico/sdk/SdkManager.java` (`QvOpenSDK...setService(appServiceIp, 443).setKey(serviceKey)`).

---

## 2. Cloud (account) API

### 2.1 Server discovery
`QvLocationManager` does **not** use a hard-coded region list: it asks the **native P2P SDK**
(`libqv-p2p-v2.so` → `QvP2PV2Api.queryServiceAddress(typeMask, groupId)`) with the bootstrap
`vidos.qvcloud.net:443` + `serviceKey`. The native layer returns `QvServerInfo[]`
(`httpsAddress`, `httpsUrl`, `httpsPort`, `type`, `groupId`, `currentIpGroupId`, `urlVersion`)
and results are cached per service **type** in `SpUtil`.

Service types observed (int keys): `0,1` = auth/down-channel, `2` = device shadow, `3,7` = report/log,
`4` = OAuth, `5,6,8` = cloud storage / **openapi-tdk**, `9` = push-server register, `10` = open SDK.
`urlVersion==1` ⇒ address needs a custom CA (`getCurrentUrlNeedCA`).

### 2.2 OAuth login (`com.quvii.qvweb.oauth.QvOAuthManager`)
`GET /qvoauthv2/token` (Retrofit `OAuthApi`, JSON converter), query params:

```
grant_type=password | refresh_token
client_id  = SDKVariates.ALARM_CLIENT_ID      # "00" + CLIENT_TYPE + "-" + APP_ID + "-" + <uniqid>
client_type = SDKVariates.CLIENT_TYPE         # 0/1 login mode; see client_flag
oemid      = "G0108"
appid      = "4108"
usr        = <account>
pwd        = <password>
region_id  = QvLocationManager.getCurrentRegionId()
client_flag= "1" account mode, "2" no-login mode
refresh flow: grant_type=refresh_token&refresh_token=...
```

Response `GetTokenResp`: `access_token` / `refresh_token` are **JWTs** (client parses `exp` from
payload). Tokens cached per user in `QvOAuthSpUtil`, refreshed when < 5 min left.

**Login modes** (`AppVariates.getAuthMode()`, persisted): `DEFAULT_LOGIN_MODE = 1` →
`isNoLoginMode() == true` for Vidos X by default. In no-login mode there is still a cloud
connection (device-bind/register + down-channel), but the app can work without a user password
login; `client_flag = 2`. **VERIFY** which mode a typical Vidos X user account runs in.

### 2.3 Cloud user channel (XML over HTTP, "duplex")
Base URL = `DownChannelManager.getRequestUrl()` (the `httpsAddress` for the auth service).

* **Up channel** (request): `POST /auth/user;jus_duplex=up` with `Content-Type: application/xml`
  — variants: `/auth/nologin;jus_duplex=up` (free/no-login), `/auth/user/deli;jus_duplex=up` (deli).
* **Down channel** (response/push): long-lived HTTP connection to
  `.../auth/user;jus_duplex=down` (or the nologin/deli variants), read with `OkHttp` streaming.
* Envelope: `<?xml …?>` + `<Envelope><Header …/><Body><command>…</command><content>…</content></Body></Envelope>`
  Header carries `source="tdkcloud"`, version, `sessionId`, and a `Client{clientId, clientType, oemId, appId}`.
* Dispatcher: `QvUserAuthCore.handleDownChannelResponse()` — routes by command name
  (`login`, `get-device-list`, `device-bind`, `device-unbind`, `device-bind-check`,
  `get-device-token`, `dev-bind-register`, `auth-login`, …). Device list/online updates arrive here.

Cloud commands (`UserAuthRequestHelper` / `UserAuthConst`): `login`, `logout`, `account-register`,
`send-register-code`, `send-login-code`, `reset-password`, `apply-password-reset`,
`device-bind`, `device-bind-check`, `device-unbind`, `get-device-list`, `get-device-token`,
`add-device-share`, `edit-device-name`, `edit-channel-name`, `get-devices-shared`,
`generate-share-invitation`, `accept-share-invitation`, `get-share-link`, `get-share-group-list`, …
Header flag for every envelope: `"tdkcloud"`.

### 2.4 Alarm/ring channel
Separate service (service type 9 / `AlarmApi`), endpoints `POST /UserAlarm` and `/DeviceAlarm`,
same XML envelope, commands (`AlarmRequestHelper`): `client-login`, `client-logout`,
`client-query-recordlist` (alarm/ring history incl. `event`, `chno`, `devid`, `resUrl` snapshot URL,
`answered`, `time`), `client-update-config`, `client-query-config`, `client-update-token`,
`client-query-dev`, `client-update-dev`, `client-delete_record`, `dev-report-alarm-test`.
Push delivery to the phone is FCM (`fcm`/`getui` token registered via `/pushserver/api/v1/client/register`
and `openapi-tdk` `pushToken`, signed `HmacSHA1(clientId-timestamp, clientId)`).

### 2.5 Open API (third party, `openapi-tdk`)
`QvOpenApiTdkManager` → service type 8, OAuth bearer token, signature
`HmacSHA1(ALARM_CLIENT_ID + "-" + ts, ALARM_CLIENT_ID)`. Endpoints under `/openapi-tdk/...`
(`getAppNoticeList`, `getUserDevicesCloudStorageStatus`, `pushToken`, `logoutOpenApi`, …).
Not currently exposed to end users — possible future route for HA, **VERIFY** availability.

### 2.6 Other fixed URLs
* `https://license.eapil.com:7080/AccessCenter/sdk/licenseVerify` (player licence)
* `https://web.qvcloud.net/Help/help_nologin.html` (base64 in `ST_NO_LOGIN_HELP_URL`)
* Version check: `.../webs/version/app/version_check.jsp?os=android&appid=…`
* `tdkcgi/passwordencryption` on the **device** (see below)
* Google OAuth client (Firebase): `HH852288695552-uhk10qtaljgpdb0pap3qopkhoeeuk6vj.apps.googleusercontent.com`

---

## 3. Device local HTTP/CGI protocol (the important part for HA)

All control (door open, config, PTZ, status) is plain **HTTP(S) POST to the device itself**:

```
{scheme}://{ip}:{cgiPort}/tdkcgi            # HttpDeviceConst.CGI_ADDRESS = "/tdkcgi"
scheme = https (SDKConfig.CGI_PROTOCOL) or http for HS/VSU devices (SDKConst.CGI_SCHEME_*)
cgiPort default: 443 (DEVICE_DEFAULT_CGI_PORT) / 80 (DEVICE_DEFAULT_CGI_HTTP_PORT)
```

* Retrofit interface: `DeviceApi` (XML body, SimpleXML) and `DeviceJsonApi` (JSON body, Gson),
  both `POST /tdkcgi`.
* Two request formats:
  * **XML**: `<Envelope><Header><security/><username/><password/><passwordencode/><nc/></Header>
    <Body><command>…</command><content>…</content></Body></Envelope>`
  * **JSON**: `QvBaseJsonRequest<T>` with the same command strings (newer devices).
* Header auth (`DeviceRequestHelp.initHeader`):
  * `security = "username"` → plaintext password (`SDKConst.CGI_DEVICE_SECURITY`)
  * `security = "usernametoken"` → `password = native MD5-like hash(username, password, nc)`,
    `nc` = random 32-char nonce (`QvJniFunc.getEncryptPassword`) — **algorithm lives in
    `liblive_player.so`, must be reimplemented (VERIFY by traffic capture)**
  * `security = "httpauthen"` when `SDKConfig.IS_OPEN_AUTH` and device supports HTTP auth
    (interceptor adds HTTP auth headers instead of XML password).
  * default app username constant: `CGI_DEVICE_USERNAME = "adminapp"` (actual username comes
    from the binding, `qvDevice.getUsername()`).
* Device credentials come from the binding: `QvDevice.password` (dynamic password from cloud
  `get-device-token`), `dataEncodeKey`, `authCode`, `deviceConfigPassword`.
  URL with inline basic-auth is built for password encryption:
  `https://user:deviceConfigPassword@ip:cgiPort/tdkcgi/passwordencryption`.
* TLS: device uses a CA-signed/custom cert (`getDeviceCgiWithCustomCAInstance`, `isSupportTls`).
* Port/scheme selection: `HS` devices (`cloudType==2`) → http; `VSU` → http unless `cgiScheme!=0`;
  otherwise `https`. `getUseIp()` = `parsedIp` (domain→IP resolution) or `ip`.

### 3.1 Key CGI commands (verified constants)

Door / lock:
* `set.device.opendoor` — open door. Content (`DeviceUnlockContent`, the app's main path):
  `door` (= channel number), `locknumber` (= lock id), `password`. Legacy `OpenLockContent`
  shape: `door` (= lock id) + `password` only. This is **the** command behind `openLock()`.
* `set.opendoor.password` (set unlock password), `set.opendoor.checkpassword`
* `get.lock.status` / `set.lock.status`, `get.auto.unlock` / `set.auto.unlock`
* `set.temp.pwd` / `delete.temp.pwd` / `get.temp.pwd` (temporary door codes)
* `set.qrcode.create` / `get.qrcode.info` (unlock QR codes), `set.smart.relay`

**Lock enumeration via `get.device.attachInfo`** (hardware 2026-10-02; answered JSON in an XML
envelope). `profile.subs` reports `lock total=3 enable=1`; `sub-devlist` lists them —
`children` code-refs attach a lock to its channel, unreferenced locks are standalone:

| code | name | channel (`door`) | lock id (`locknumber`) | note |
|---|---|---|---|---|
| `Lock_1_1` | DOOR1 | 1 | 1 | child of `Channel_1` (CAM1) — **physically verified 2026-10-02** |
| `Lock_2_1` | DOOR2 | 2 | 1 | child of `Channel_2` (CAM2) |
| `Gate_1` | **Automatic gate** | 0 | **2** | standalone (`CHANNEL_LOCK=0`); app uses a distinct icon for `subLock.id==2` (`device_attachment_lock2`) |

App call chain: `DeviceAttachmentAdapter` → `onClick(subLock, 0, subChannel.getId())` →
`MainDeviceListPresenter.deviceUnlock(device, door=channelId, lock=subLock.getId())` →
`DeviceRequestHelp.deviceUnlock` → `set.device.opendoor`. Standalone locks pass
`CHANNEL_LOCK = 0` as the channel. *Physical verification: DOOR1 done (2026-10-02);
gate `(0,2)` accepted with `error=0` but not yet heard to actuate — re-test with
`tools/probe.py --open-door --exact --door 0 --lock 2` while standing at the gate.*

Status / info:
* `get.device.status` (all info), `get.product.info`, `get.system.info`, `get.system.ability`,
  `get.channelmanagement.config`, `get.encode` (video), `get.hdd.base`, `get.tfcard.info`,
  `get.network.config`, `get.wifi.list`, `get.live.status`, `get.device.qrcode`, `getHWInfo`

Alarms / detection:
* `get/set.alarm.motiondetection`, `get/set.alarm.alarmin`, `get/set.alarm.videolost`,
  `get/set.alarm.videoshelter`, `get.alarm.motiondetection.schedule`, `get.whistle.list`,
  `get/set.alarm.detailInfo`, `g.alm.disarm` / `s.alm.disarm` (arm/disarm)

ONVIF / streams:
* `get.onvif.pwd` / `set.onvif.pwd` (`DeviceJsonRequestHelp.COMMAND_GET_ONVIF_PWD`) — device
  stores an ONVIF password ⇒ **device is expected to expose an ONVIF/RTSP server on the LAN**.
* `GetVideoConfigResp.onvifSupport` element (device reports ONVIF capability)
* `set.encode` (main/sub/alarm/third stream), `get.device.streamkey` (stream key)

Door station extras: `set.sip.*` (SIP call server params), `set.rfid.*`, `set.fp.*` (fingerprint),
`set.prox.card`, `set.facepic.*`, `set.custom.ring*`, `set.voice.message*`, `set.elevator.summonl`,
`set.smartswitch.*`, `set.floodlight.switch`, PTZ `ctrl.ptz.preset.goto`, `set.ptz.position`, …

Full lists: `com/quvii/qvweb/device/DeviceRequestHelp.java` (XML) and
`DeviceJsonRequestHelp.java` (JSON); interfaces `device/api/DeviceApi.java`,
`DeviceJsonApi.java`.

### 3.2 JSON protocol (second dialect — hardware-confirmed 2026-09-28)

Same endpoint and same `header` credentials, but `Content-Type: application/json;charset=utf-8`
and a JSON envelope (`QvCommonJsonRequest` + `QvJsonHeader`):

```json
{"header": {"username": "adminapp2", "password": "<sha256-hex>", "passwordencode": 1, "security": "username"},
 "body": {"command": "get.lock.status", "content": {"...": "optional per-command content"}}}
```

* **JSON-only commands** (`get.lock.status`, `get.live.status`, `get.babysitter`,
  `get.audio.session`, …) answer `error=-10` in the XML dialect — this is the missing piece.
* **The response dialect is chosen per command, not per request**: `get.device.attachInfo`
  sent in an *XML* envelope came back as JSON
  (`{"body":{"error":0,"content":{"profile":{"chns":{"total":4,…` — 4 channels: cam 2, cctv 2).
* Error codes parse the same (`"error": -10`); see `probe.extract_error` / `flatten_json`.
* Probe support: `tools/probe.py --watch` sends `jlock`/`jaudio`/`jbabysitter` over JSON.

### 3.3 Azeno LAN discovery / ring signal (hardware-confirmed 2026-10-02)

UDP broadcast protocol spoken by the station and the vendor's apps (name from
the packet magic; NOT present in the app's Java code — implemented in the
device firmware and the native `libqv-p2p-v2.so`):

| Direction | Packet | Notes |
|---|---|---|
| Phone app → broadcast `:5000` | `ASZENO.SEARCH.V4.1` (18 B, src port 5003) | discovery probe, 4 packets @1 Hz |
| Station → broadcast `:5001` | `ASZENO.SEARCH.V4` + 616 B total | reply 15–85 ms after each probe |

Station reply layout: `ASZENO.SEARCH.V4` magic (16 B) + header
(`01000000 00000000 20000000 10020000 …` — 40 B) + **392-byte fixed blob**
(device identity, high entropy) + **224-byte varying tail** (differs per
packet; first divergence at byte 392).

**Ring chain (verified live):** bell press → device → cloud → FCM push →
phone app wakes (closed, ~6 s latency) → `ASZENO.SEARCH.V4.1` burst →
station replies. `get.device.status`/`get.record.alarmrecord` showed **no**
change during a ring (12-command watch, XML+JSON dialects), so this
broadcast burst is the only LAN-observable ring signal. Sources: Wireshark
capture (`capture.pcapng`), `tools/lanwatch.py`, integration `lan.py`.

Caveats: needs a phone with the vendor app on the same LAN; opening the app
manually runs the same scan (possible false positive). The station's normal
cloud traffic is unicast and invisible to a plain LAN capture (switched
network).

---

## 4. Live video — `quii://` media protocol (hardware-verified 2026-10-02)

**Result: live video works fully over the LAN.** The proprietary media
protocol on TCP **34567** was reverse-engineered and verified end-to-end on
the IDS9483AW: handshake → decrypt → H.264 keyframe → decoded picture.

**No standard video protocol exists on this firmware** (still true): port scan
(TCP, full range) shows only **`443` (CGI), `34567` (media), `8765` (unknown
binary)** — `554`, `8000`, `8899` and HTTP are closed/refusing.

* `get.network.base` / `get.network.config` (both dialects) → `error=-10`
  (firmware does not implement them — no `rtspport`/`rtspurl` to read).
* `get.onvif.pwd` (JSON) → `error=-10`; `get.system.ability` (XML) → `error=0`
  but **empty content** (no `<rtsp><preview>` / `ability_rtsp`).
* Raw probes: RTSP `OPTIONS`, HTTP, ONVIF `GetCapabilities` against 8765/34567
  → not those protocols. Port **8765 answered with an unknown binary frame**
  (`0a 00 01 00 00 00 ee 26 …`); port **34567** is the media port below.
* Prior (static-only) expectations for ONVIF/RTSP (`get.onvif.pwd` command,
  `onvifSupport` fields in `get.encode`) are **not realized by this firmware**.
* App snapshots are decoded client-side (`QvPlayerCore.snapShot()` JNI) — no
  HTTP snapshot/JPEG endpoint exists anywhere in the Java layer.

### 4.1 Prior art (open source — read this first)

The media protocol is already documented/implemented by the community
(license-compatible, credited in README):

| Project | What it covers |
|---|---|
| [`fariborz0015/quii-lan-client`](https://github.com/fariborz0015/quii-lan-client) (MIT) | Full QUII media client: Setup/Play/keepalive, AES crypto, H.264 + G.711 listen/talk — offline RE of `liblive_player.so` (`CQUIIStreamBase`, `EncryptData`, `SetIvec`) |
| [`fdaneluzzi/homeassistant-allo-wt7`](https://github.com/fdaneluzzi/homeassistant-allo-wt7) | Door control + ring polling (`get.record.session`) on sibling `IDS9478AW` |
| [`totoantibes/golmar-quvii-ha`](https://github.com/totoantibes/golmar-quvii-ha) | HACS door-open for Golmar/Quvii panels (cloud+local key), brand App ID/OEM ID table |
| [`jdntortosa/fermax-wayfi-ha`](https://github.com/jdntortosa/fermax-wayfi-ha) | UMEye/Quvii-family LAN door protocol (different port 5801, UMSP) |

Our findings below independently confirm the wire format on the IDS9483AW.

### 4.2 Credentials

1. **Stream key**: CGI `get.device.streamkey` (XML, works) → `<key>` (32 ASCII
   chars, AES key material) and `<tdc>` (large blob, unused so far).
2. **Wire auth**: user `adminapp2`, password = `sha256hex(auth code)` — the
   same value the CGI `lan-hash` header uses (device password works as the QR
   auth code `c` field equivalent).
3. App URL shape (`QvPlayerCore:3127-3147`):
   `quii://<user>[:<sha256pass>]@<ip>:<streamPort>/mode=real&idc=<ch>&ids=<stream>[&tls=1]`,
   `DEVICE_DEFAULT_STEAM_PORT = 34567`.

### 4.3 Wire flow (verified)

```
TCP connect <ip>:34567
C→S  Setup     0xA9 + 31×0x00                      (32 B, plaintext)
S→C  Setup-RX  hdr[9]=0, enc_mode=hdr[0x0A]=2 (AES-256), sha_mode=hdr[0x0B]=1 (SHA-256)
C→S  Play      opcode 0x01, body "user&&pass\0"[+ids]
               fields: param_len@+9, body_len@+0x0B, idc@+0x0D(u16),
               play_arg@+0x0F, ids@+0x10, inner@+0x11
               SHA-256(hdr||body) appended; AES-CBC (IV='0'×16) applied as three
               independent chunks: hdr32 | body[:padded prefix] | body tail clear
S→C  0x01 Play-ACK, 0xFE info messages (contain the channel tag, e.g. "CAM1"),
    then media 0xA0..0xA3
C→S  KeepAlive 0x00 (encrypted, empty body) — device echoes 0x00 back
```

Media message: encrypted 32-B header (`body_len` = u32@+0x0B), body = first
`param_len`(u16@+9) bytes AES + remainder plaintext. Decrypted payload starts
with a **20-byte QV frame header**: `00 00 01 | E0+type | u32le payload_len |
… | codec@0x0E | payload@0x14`, payload = annex-B H.264 (or G.711 A-law when
type=3).

Frame types (`hdr[3] - 0xE0`): `0` = P-frame, `1` = IDR keyframe, `3` = audio.

### 4.4 Measured behavior (IDS9483AW, 2026-10-02)

| Property | Value |
|---|---|
| CAM1 (`idc=1`, `ids=1`) | H.264 **352×280 @ 25 fps**, ~60 KB/s (night scene), IDR every ~2.1 s |
| CAM2 (`idc=2`, `ids=1`) | **640×280 @ 25 fps** stream exists but shows the blank/white default — lens disconnected (confirmed by owner) |
| `ids=2` | no media (only `0xFE` info) |
| Time to first frame | ~2.0–2.5 s after connect |
| Keepalive | echo confirmed (`0x00` ×5 in a 30 s session) |
| Reconnect | new session OK after **0.5 s** gap; one failure observed after an abrupt mid-burst close → use connect backoff |
| Session stability | ≥30 s verified repeatedly; 5-min endurance run (4572 media msgs, 46 keyframes, 29 keepalives echoed): see §7 |
| Snapshot path (HA) | live test: streamkey 0.07 s → keyframe 2.15 s → 5916 B H.264 → 16 KB JPEG |

Audio (`type=3`, G.711 A-law 8 kHz) is interleaved in the same media stream.

### 4.5 Implication for HA (implemented, v0.3.0)

Snapshots require a **local H.264→JPEG decode step (ffmpeg)** — the device
never serves JPEG. The integration therefore ships:

* **`quii.py`** — async client for the flow in §4.3 (Setup → Play → media
  parser → keyframe extraction). Framing/crypto adapted from the MIT-licensed
  [`quii-lan-client`](https://github.com/fariborz0015/quii-lan-client).
* **`camera.py`** — snapshot-only camera entity (no continuous streaming):
  on each image request it fetches a short-lived `get.device.streamkey`, opens
  a brief media session, grabs the first standalone keyframe (SPS+IDR, ~2.2 s
  after connect), decodes it to JPEG with Home Assistant's `ffmpeg`
  integration (`dependencies: ["ffmpeg"]` in the manifest) and caches the
  result (5 s TTL, 15 s failure cooldown). Disabled via the
  *Snapshot camera* option (`enable_camera`, on by default).

External camera entities can still be *associated* with the device
(options → "Associated cameras"). Port **8765** remains an unknown binary
protocol (not needed for video).

### 4.6 Ring-picture log — per-channel ring detection (hardware-verified 2026-09-30)

Every doorbell press stores a tiny **picture record** whose `channel` field
says *which* input rang. This is the only ring signal on this hardware that
carries the channel (Azeno broadcasts and `devicestatus.calling` do not).

**Two-phase query** (POST `/tdkcgi`, same `lan-hash` auth as §3.1):

1. `get.record.session` with EXACT content:

   ```xml
   <content><record>
     <filetype>picture</filetype>
     <occurtype>all</occurtype>
     <channels>1,2</channels>
     <starttime>2026-09-30T14:00:00</starttime>   <!-- ISO with capital T -->
     <endtime>2026-09-30T15:00:00</endtime>
     <stream>all</stream>
   </record></content>
   ```

   Response: `<record><id>N</id></record>` — the session id.

2. `get.record.message` with `<content><record><id>N</id></record></content>`
   → pages of records (oldest first):

   ```xml
   <data>
     <filetype>picture</filetype>
     <occurtype>unknown</occurtype>
     <channel>1</channel>
     <starttime>2026-09-30t14:38:07z</starttime>   <!-- lowercase t/z -->
     <endtime>2026-09-30t14:38:09z</endtime>
     <filename>/mnt/sd/record/...</filename>
     <filesize>20480</filesize>
     <describe>...</describe>   <!-- base64, ends in CAM1, same for all -->
   </data>
   ```

   Read pages until an empty `<datalist>` (cap ~20).

**Hard-won constraints (do not "improve" these):**

* **`filetype=all` (or other wrong params) crashes the device's CGI
  service**: connections get refused for ~60–90 s. Only
  `filetype=picture` with the field set above is safe.
* Time filters only accept the ISO `T` separator; the device ignores the
  window anyway (returns everything it has).
* `occurtype` is always `unknown` — records cannot be told apart by event
  type; `describe` is identical for all. **Channel is the only
  discriminating field.**
* The device may return a **truncated listing** (oldest-first prefix,
  missing the newest entries) on cold reads; it also throttles rapid
  connections. Detect new records by filename set + timestamp cutoff
  (never by "max starttime changed"), reuse the session id (reopening
  forces a full listing re-read), pace requests (~1 req / 3 s), and prime
  the baseline over **two** cycles (`records.py`).
* `get.record.session` answering **`-1`/`-10`** = command unknown on that
  firmware dialect (IDS9478AW family) → give up cleanly.

**Channel table** (`get.device.attachInfo`, JSON even for XML requests —
parser must tolerate both):

| key | type | id | name | children |
|---|---|---|---|---|
| `Channel_1` | cam | 1 | CAM1 | `Lock_1_1` → **DOOR1** (`door=1,lock=1`, verified) |
| `Channel_2` | cam | 2 | CAM2 | `Lock_2_1` → DOOR2 (`door=2,lock=1`, untested) |
| `Channel_3`/`Channel_4` | cctv | 3/4 | CCTV1/CCTV2 | — |
| `Gate_1` | lock | 2 | Automatic gate | — |

Wiring on the reference install (owner-confirmed): **channel 1 = camera
doorbell** (live-verified: its presses produce `<channel>1</channel>`
records), **channel 2 = dummy button**. One Wi-Fi station serves both.
`profile.chns.total = 4` (`cam 2`, `cctv 2`), `ability.switchdirectly:1`.

**HA implementation (v0.4.0):** `records.py` `RecordRingWatcher` polls the
log every `record_poll_interval` s (default 3, 3–30) while
`enable_record_rung` is on, fires `coordinator.note_rung("records",
channel)` for records newer than the primed cutoff; events carry
`channel` + `channel_name` (options `channel_1_name`/`channel_2_name`,
defaults "Channel 1"/"Channel 2"). `enable_lan_rung` Azeno remains as a
channel-less fallback; both sources land in one event within a 10 s dedup
window (`DOORBELL_RUNG_DEDUP_SECONDS`).

Known caveat: the channel-2 record path was never observed live (owner
declined the test); if the firmware skips picture saves for the dummy
button, those rings arrive channel-less via Azeno instead.

---

## 5. Connectivity summary (how the pieces fit)

```
                 ┌────────────  cloud: vidos.qvcloud.net:443 (TDK) ────────────┐
 Phone/HA ──────►│  GET /qvoauthv2/token            (OAuth password grant)     │
                 │  POST /auth/user;jus_duplex=up   (XML envelopes, commands)  │
                 │  long-poll /auth/user;jus_duplex=down (device list/status)  │
                 │  POST /UserAlarm  (alarm/ring history, client-login)        │
                 │  /pushserver, /openapi-tdk, /logserver, /tdkcgi/password…   │
                 └───────────────┬────────────────────────────────────────────┘
                                 │  (device maintains its own cloud link)
   LAN  ┌────────────────────────▼─────────────────────────────────────────┐
        │  Door station / camera                                          │
        │  http(s)://<ip>:<cgiPort>/tdkcgi   ← XML/JSON CGI, door open,       │
        │       status, config (this is what the app uses)                   │
         │  :34567 quii:// media + :8765 binary  ← video: quii:// RE'd & verified    │
         │       (§4); no RTSP/ONVIF; 8765 still unknown                            │
        │  P2P (native lib)             ← app's cloud fallback, not for HA   │
        └─────────────────────────────────────────────────────────────────────┘
```

Practical consequences:
1. **Door opening in HA = direct HTTP(S) POST to the device's `/tdkcgi`** (LAN or reachable
   network). The cloud is *not* used as a relay for control commands — `openLock()` builds a
   Retrofit client on `ip:cgiPort`.
2. Cloud access is needed to: discover devices (ip/cgiPort/dynamic password), learn online
   status, and read alarm/ring records — **UI removed for now, `cloud.py` kept**.
3. Video: **no RTSP/ONVIF** (probed) — live video works over the proprietary
   `quii://` media port 34567 (§4, verified), which the integration now uses for
   its camera entity; external camera entities can still be associated.

---

## 6. Security notes

* `assets/client.txt` contains a **bundled RSA private key** + `client.pem`/`device.pem`
  (mTLS certs, CA "QUALVISION TECHNOLOGY CO., LTD", 2017–2037) shared by all Quvii SDK apps.
* `usesCleartextTraffic=false`, no `network_security_config.xml`, `allowBackup=false`.
* Partial R8 obfuscation (~811 shortened `com.quvii.*` leaf names), but all protocol constants
  (`ServerAddress`, command strings, OAuth params) are intact and readable.
* Device CGI auth may be plaintext password in XML (`security=username`) — treat LAN as trusted.

---

## 7. Open questions to verify on hardware / traffic

1. Capture one app session (`mitmproxy` with the bundled CA, or device-side tcpdump) to confirm:
   the exact envelope XML, password hashing (`usernametoken`), and whether `IS_OPEN_AUTH` is on.
2. ~~Confirm ONVIF/RTSP ports~~ **done 2026-10-02: none exist** (see §4);
   ~~identify the `quii://` handshake on 34567~~ **done 2026-10-02: verified
   end-to-end** (§4.3); remaining: identify the binary protocol on port 8765,
   and explain the rare no-media-on-reconnect case (use backoff meanwhile).
3. Confirm which cloud region host `vidos.qvcloud.net` resolves to for EU users and whether
   service type 0/1 addresses are subdomains of it.
4. Confirm ring/alarm delivery: FCM only, or also a server-pushed down-channel event?
   (`client-query-recordlist` polling is the fallback.)
5. Determine the login mode (account vs no-login) used by the user's actual account.
