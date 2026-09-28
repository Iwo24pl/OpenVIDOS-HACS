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
| `set.device.opendoor` | `<error>0</error>` + relay click with content `door=0`, `locknumber=0`, `password=sha256hex(first-contact password)` (`DeviceUnlockContent` shape) ✅ |
| Error codes | `-10028` incorrect password, `-10029` busy (from `SDKStatus.java`) |
| RTSP/ONVIF, cloud discovery | **not yet probed** (V2.0) |

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
* `set.device.opendoor` — open door. Content (`OpenLockContent`/`DeviceUnlockContent`):
  `channelNum`, `lockNum`, `password`. This is **the** command behind `openLock()`.
* `set.opendoor.password` (set unlock password), `set.opendoor.checkpassword`
* `get.lock.status` / `set.lock.status`, `get.auto.unlock` / `set.auto.unlock`
* `set.temp.pwd` / `delete.temp.pwd` / `get.temp.pwd` (temporary door codes)
* `set.qrcode.create` / `get.qrcode.info` (unlock QR codes), `set.smart.relay`

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

---

## 4. Live video / snapshot

* App live view and snapshots go through the **P2P SDK** (`libqv-p2p-v2.so`) + player
  (`QvPlayerCore.snapShot()` JNI) — proprietary, not directly usable from Home Assistant.
* `device_list`/binding models expose `ip`, `cgiPort`, `mac`, `status`, `port` — so the LAN
  address needed for direct streaming is available from the cloud device list.
* **ONVIF/RTSP is the practical HA route**: devices support ONVIF password management over CGI
  and report `onvifSupport`. Expect `rtsp://<ip>:554/...` and ONVIF on 80/8899 — **VERIFY on
  hardware** (nmap + ONVIF discovery, try credentials from `get.onvif.pwd`).
* Native `liblive_player.so` contains a full RTSP server/client + ONVIF config parser
  (`<port>`, device CGI XML, `addPresetByCgi`, `snapShot`) — same codebase is used device-side.

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
        │  http(s)://<ip>:<cgiPort>/tdkcgi   ← XML/JSON CGI, door open,   │
        │       status, ONVIF pwd, config (this is what the app uses)     │
        │  RTSP :554 / ONVIF            ← for video (VERIFY)             │
        │  P2P (native lib)             ← app's live view, not for HA    │
        └─────────────────────────────────────────────────────────────────┘
```

Practical consequences:
1. **Door opening in HA = direct HTTP(S) POST to the device's `/tdkcgi`** (LAN or reachable
   network). The cloud is *not* used as a relay for control commands — `openLock()` builds a
   Retrofit client on `ip:cgiPort`.
2. Cloud access is needed to: discover devices (ip/cgiPort/dynamic password), learn online
   status, and read alarm/ring records.
3. Video: ONVIF/RTSP if enabled; otherwise P2P-only (would need an add-on with the native lib —
   not realistic, 32-bit ARM lib only).

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
2. Confirm ONVIF/RTSP ports and stream URLs; test credentials from `get.onvif.pwd`.
3. Confirm which cloud region host `vidos.qvcloud.net` resolves to for EU users and whether
   service type 0/1 addresses are subdomains of it.
4. Confirm ring/alarm delivery: FCM only, or also a server-pushed down-channel event?
   (`client-query-recordlist` polling is the fallback.)
5. Determine the login mode (account vs no-login) used by the user's actual account.
