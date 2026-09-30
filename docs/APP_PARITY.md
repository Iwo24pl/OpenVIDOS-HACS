# Vidos X App — Local Protocol Parity Specification (`APP_PARITY.md`)

Phase-1 deliverable of the vidos-x rewrite. Source of truth: **the official app**
(`com.vidos.vidosx` V1.7, versionCode 12, Vidos sp. z o.o. / white-label Quvii,
`OEM_ID="G0108"`) extracted to `../com.vidos.vidosx/` (`classes.dex` … `classes4.dex`,
no native libs).

**Rule for the rewrite:** implement what the app implements, nothing more.
Behavior that is not derived from the app requires an explicit, recorded
justification (see §9). Cloud/duplex features are out of scope for milestone 1
(user decision).

Extraction provenance (reproducible):

- Scripts: `%TEMP%/opencode/phase1_extract.py`, `phase1_extra.py`,
  `phase1_targeted.py`, `phase1_final.py`, `phase1_header.py`, `phase1_auth.py`,
  `phase1_intercept.py` (androguard 4.1.4; `DEX(bytes)`; `loguru.remove()` needed).
- Raw dumps: `%TEMP%/opencode/phase1/` — `commands.txt` (196 XML-dialect commands),
  `commands_extra.txt` (597 hits incl. camelCase), `callsites.txt`,
  `callsites_extra.txt`, `keywords.txt` (14,979 lines), `beans.txt`,
  `targeted.txt`, `final.txt`, `header.txt`.
- Old (pre-wipe) implementation restorable at git tag `legacy-v0.4.0`.

---

## 1. App architecture — three protocol layers

| Layer | Classes | Dialect | Role |
|---|---|---|---|
| A. XML CGI | `com.quvii.qvweb.device.DeviceRequestHelp` (128 methods, `COMMAND_*` fields), `HttpDeviceManager` (facade, 538 methods) | XML `Envelope` over `POST /tdkcgi` | Core device I/O: status, unlock, record log, streamkey, attach, live status |
| B. JSON CGI | `HttpDeviceJsonManager` (obfuscated single-letter methods → command strings), `DeviceJsonRequestHelp`, `DeviceCustomJsonRequestHelp` | JSON bodies, same `/tdkcgi` | Settings: auto-unlock, call time, lock status, custom ring, fingerprints/RFID/SIP (cloud-era) |
| C. Video/CGI control | `com.quvii.core.QvDeviceCgiCtrlCore`, `QvPlayerCore` (228 methods), `QvNetDeviceCoreHelper` | `quii://` URL + binary QUII, `/tdkcgi/pwdencryp*` | Live view, talk, playback, PTZ |

HTTP layer: OkHttp with `com.quvii.qvweb.publico.intercept.DeviceAuthHeaderInterceptor`
(see §3). `requset` (sic) is the **bean package** `com.quvii.qvweb.device.bean.requset.*`,
not a command path.

## 2. Transport

- `POST /tdkcgi` on the device (HTTPS default port 443; `createCgiCtrl` builds
  `http://` or `https://` from scheme + host + port).
- Two content types on layer A: `CONTENT_TYPE_XML` (normal) and
  `CONTENT_TYPE_JSON` (`nc` field present); layer B is JSON.
- CGI control-plane helper endpoints (layer C):
  - `/tdkcgi/passwordencryption` — `QvNetDeviceCoreHelper.getDevCgiUrl` builds
    `https://<user>:<pass>@<host>:<port>/tdkcgi/passwordencryption`;
  - `/tdkcgi/pwdencryp` — alternate path in `QvDeviceCgiCtrlCore.createCgiCtrl`;
  - file plane (cloud-era, out of scope): `/tdkfile/video/`, `/tdkfile/audio/`,
    `/tdkfile/file/` multipart uploads.

## 3. Authentication (app behavior)

**HTTP Digest (OkHttp interceptor), `DeviceAuthHeaderInterceptor`:**

- `intercept` parses the `WWW-Authenticate` response header (splits on `,`,
  `=`, `"`) → `Digest realm`, `nonce`, `opaque`, `qop`.
- `digestAuthForUsername` builds (MD5):
  `Digest username="%s",realm="%s",nonce="%s",uri="%s",algorithm=%s,response="%s",opaque="%s",qop=%s,nc=%s,cnonce="%s"`
  with literals: username **`adminapp`**, uri **`/tdkcgi`**, method **`POST`**,
  `algorithm=MD5`, nc counter (`nc00001` const — exact runtime format to verify,
  §11), cnonce from `suiji` (“random”); sets `Authorization`.

**XML application header (layer A envelope), `DeviceRequestHelp.initHeader`:**

```xml
<Header>
  <security>httpauthen</security>
  <username>adminapp2</username>
  <password>…</password>          <!-- initHeader literals: '1','adminapp2','httpauthen','' -->
  <passwordencode>1</passwordencode>
  <nc>…</nc>
</Header>
```

Bean: `Header{security, username, password, passwordencode, nc}` inside
`Envelope{header, body}`. Layer B header (`DeviceJsonRequestHelp.initHeader`,
`initHeaderAlarm`): `httpauthen`, `adminapp2`, `''` — same scheme, JSON flavor.
Variants: `initHsHeader` (`usernametoken`, `username`, `httpauthen` — WS-Security
style, cloud/HS), `initUnbindHeader` (`usernametoken`).

`getIpDeviceHeader` → command **`get.header.content`** (app fetches the device’s
expected header content; response shape unverified, §11).

**Reconciled facts (forensics):**

- `lan-hash` is **not** an HTTP header — it was the legacy probe's *variant name*
  for the XML header combo `adminapp2 + sha256(password) + passwordencode=1`,
  hardware-verified in Phase 0. No conflict with the app.
- Bean **field names ≠ wire tags**: `DeviceUnlockContent{channelNum, lockNum}`
  serializes as `<door>`/`<locknumber>` (SimpleXML `@Element` renames; both
  strings present in dex; hardware-verified shape `door`+`locknumber`+`password`
  from the real app path `DeviceRequestHelp.deviceUnlock:152`).
- `<security>` value: legacy probe verified `username` on this firmware; app
  `initHeader` const is `httpauthen`. Device appears not to validate it —
  default `httpauthen` (parity), `username` kept as verified fallback (§9 D4).
- `lan-hash`/`Basic` strings absent from APK; digest (§3) is the app's HTTP-level
  mechanism, triggered by a `401` challenge (contingency path — see §11.1).

## 4. Milestone-1 command matrix

Layer A (XML envelope; request bean → app method; response beans verified from
dex field dumps):

| Command | App method(s) | Request content | Response bean |
|---|---|---|---|
| `get.device.status` | `getDeviceAllInfo` (facade `HttpDeviceManager.getDeviceAllInfo`) | — | `DeviceAllInfoResp` (§6) |
| `get.device.streamkey` | `getSecret` | `GetDeviceSecretContent{authcode}` | `GetDeviceSecretResp{Content{key, synctime, tdc}}` |
| `get.header.content` | `getIpDeviceHeader` | — | unverified (§11) |
| `set.device.opendoor` | `deviceUnlock` / `openLock` | `DeviceUnlockContent{channelNum, lockNum, password}` / `OpenLockContent{lockNum, password}` | envelope error only |
| `set.opendoor.checkpassword` | `CheckUnlockPassword` | `CheckUnlockPasswordContent{password}` | — |
| `set.opendoor.password` | `SetUnlockPassword` | `SetUnlockPasswordContent{newPasswrod (sic), oldPassword}` | — |
| `get.record.session` | `getRecordSession` | `GetRecordSessionContent{record}` | `RecordSessionRes{body{error, content{record{id}}}}` |
| `get.record.message` | `getRecordMessage` | `GetRecordMessageContent{record}` | respond bean not located (§11; legacy capture is fallback) |
| `get.record.search` | `getRecordSearch` | `GetRecordSearchContent` | — |
| `get.record.alarmrecord` | `getRecordAlarm` | `GetRecordAlarmContent{Record{alarmId, alarmType}}` | — |
| `get.device.attachInfo` | `getAttachmentInfo` | — | JSON-in-XML (legacy §2 knowledge: `Channel_1→Lock_1_1`, `Gate_1`) |
| `get.live.status` | `getIpAddDeviceOnLineState` | — | — |
| `get.device.info` / `get.system.ability` / `get.time.zone` / `get.soundandlight.state` / `get.channelmanagement.config` / `get.system.automaintenance` | `getDeviceInfo`, `getSystemAbilityInfo`, `getTimeZone`, `getSoundLightConfig`, `getChannelManagement`, `getAutoRebootConfig` | — | settings beans |

`Record{channels, endTime, fileType, id, occurType, startTime, stream}` —
shared by all record request beans.

Layer B (JSON; route ids from `DeviceJsonRequestHelp`/`HttpDeviceJsonManager`):

| Command | Route id | Request bean / shape |
|---|---|---|
| `get.auto.unlock` / `set.auto.unlock` | `$27` | `GetDeviceAutoUnlockContentReq{channel, lock}` / `SetDeviceAutoUnlockContentReq{apply:[{channel,lock}], channel, lock, schedule:[{mode (0=MOMENTARY,1=HOLD), time:[{TIME1..6, enabled, start, end, section}], week}]}` → `GetDeviceAutoUnlockContentResp{channels:[{number, locks:[{number, schedule}]}]}` |
| `get.call.time` / `set.call.time` | `$26` | `GetDeviceCallTimeContentReq{channel}` / `SetDeviceCallTimeContentReq{channel, time}` |
| `get.lock.status` | `$20` | — |
| `set.lock.status` | `r0` | — |
| `get.custom.ring` / `set.custom.ring` | `$38` / `o` | ring file mgmt (`set.custom.ringset`, `set.custom.ringdel`; file plane `/tdkfile/file/`) |
| `set.hold.unlock` | `$29` | hold-open unlock (also reachable via `QvPlayerCore.holdOpenUnlock`) |
| `set.smart.relay` | in inventory | smart relay |

Full 196-command inventory: Appendix A. Commands beyond milestone 1 (SIP, facepic,
RFID/fingerprint, wifi/network, PTZ, upgrades, voice messages, smart switches) are
**out of scope** — recorded, not implemented.

## 5. Record log flow (app → HA entity source)

1. `get.record.session` with `{record{channels, startTime, endTime, fileType, occurType}}`
   → returns `record{id}` (session id).
2. `get.record.message` with same `{record}` **plus session id** → data items
   (legacy device capture: `<channel>`, `<starttime>` `2026-09-30t14:38:07z`,
   `<filename>`, …).
3. `get.record.search` / `get.record.alarmrecord` for history/alarm listings.

The app itself receives ring/push events via **cloud push** (see §8); the local
record-log path is its history viewer. HA reuses it as the local ring source
(divergence D1, §9).

## 6. `get.device.status` response (layer A status core)

`DeviceAllInfoResp{body{error, content{…}}}` — `Content` fields: `channel`,
`crydetection`, `devability`, `fps`, `fpsMode`, `humandetection`, `humantrace`,
`info{mac, model, releaseDate, version}`, `infraredLight{mode}`, `key`,
`latestReleaseTime`, `latestVersion`, `ledstatus`, `mirror`, `moveDetection`,
`netWork{address, dhcp, gateWay, httpPort, httpsPort, subMask}`, `rotate`,
**`status: DeviceStatus`**, `summertime`, `tfCard{dataList[{diskId, exist, free,
status, total}], formatting, freeSum, totalSum}`, `time{datetime, dstset, timeZone}`,
`upgradeStatus`, `vionoff`, `wifiInfo{mode, rssi, ssid}`.

`DeviceStatus`: `automaintenance{rebootday, reboothour}`, `babySitter`,
**`calling`**, `detetionInfo`, `enhancePtzRange`, `hdr`, `humandete`,
**`lockstatus`**, `needAesPwd`, `ns_mirror`, `ns_vionoff`, `smdPeds`, `smdVehc`,
`summertimeconfig`, `tfCard`, `volume`.

Per-channel: `Channel{id, motionDetection{alarmLightEnable, enabled, range,
sensitivity, whistleEnable}, recordconfig{prerecord, recordcontrol,
recordstream, redundancy, schedule{monday…sunday → VideoTime{start,end,type} ×
time…time6}}}`. Recording schedule lives inside `get.device.status`.

## 7. Live view flow (layer C)

- URL builders emitting `quii://` — call sites: `QvDeviceCore.getStreamUrl`,
  `QvDeviceCtrlCore.getUrl` / `getUrlIpAddQv`, `QvPlayerCore.buildTalkConnection`
  / `startPlay`, `QvMediaFile.resetConnectInfo`.
- `QvPlayerCore.playFormLan` / `playFormOnline` / `playFormIpConnect` /
  `dealPlayFormParsedIp` / `IpAddOpenDevice`; `asyncGetDevCgiPort` /
  `asyncGetDevStreamPort` (`mCgiPort`, `mStreamPort`, `mCgiPortRunnable`,
  `mStreamPortRunnable` — ports discovered at runtime);
  `CONNECT_TYPE_DIRECT|FORWARD|P2P`; `STREAM_MAIN|SUB|THIRD`;
  fields `mAuthCode`, `mPassword`, `mDataEncodeKey`, `mIsEncryptData`,
  `supportTls`, `mChannelNo`, `mCid`.
- Config/start sequence mirrors legacy hardware-verified QUII flow (Setup `0xA9`,
  Play `0x01`, media `0xA0..0xA3`, IV `'0'×16`, CAM1 `idc=1,ids=1`,
  352×288-class preview @25fps, snapshot ~2.2 s) — parity decision D3, §9.
- Streamkey comes from §4 `get.device.streamkey` (`GetDeviceSecretContent{authcode}` —
  authcode = device password; legacy sent empty content and it worked, keep parity
  with the app: send the bean).

## 8. Ring detection — findings & open question

- **`ASZENO` does not appear anywhere in the APK's dex/asset files** (raw byte
  search over all extracted files), and no `quvii`/`vidos` class references
  `DatagramSocket` / `MulticastSocket` or ports 5000/5001 (const scan).
  **Resolution:** the extraction directory contains **no `lib/` folder** —
  native libraries were not extracted. `QvPlayerCore` is a JNI facade over
  `liblive_player.so` (per the MIT quii-lan-client RE), which is the likely
  home of both the QUII binary protocol and the ASZENO broadcast strings.
  Legacy observed the *app* broadcasting `ASZENO.SEARCH.V4.1` (src port 5003)
  ~6 s after a bell press with the app closed (silent push wake), with the
  device replying on UDP 5001 — consistent with native app code.
- App-side ring/event delivery: cloud push (dex contains push SDKs);
  `DeviceStatus.calling` exists in `get.device.status` but legacy verified it
  does not flip on ring.
- **Conclusion:** the app has no discoverable *local* ring path in this build.
  HA therefore keeps the record-log watcher (D1) and treats ASZENO broadcast
  listening as an optional device-side helper (D2).

## 9. Parity decisions (recorded)

| # | Decision | Rationale |
|---|---|---|
| D1 | Ring events via **record-log polling** (`get.record.session` → `get.record.message`), adapter pattern from legacy | App relies on cloud push; local-only HA needs a local source; session/protocol shape is app-derived |
| D2 | **Optional** ASZENO broadcast listener (device-side UDP5000/5001) behind an option, default off | Not app code; hardware-observed device behavior; kept only as helper |
| D3 | **Reuse legacy QUII player/stream implementation** (`git show legacy-v0.4.0:…`) for live view | Hardware-verified 352×288@25fps; re-implementing `QvPlayerCore` (exoplayer + native) is out of scope; wire it to app-derived streamkey/header beans |
| D4 | Auth = **Digest interceptor (username `adminapp`) + XML/JSON header (`httpauthen`/`adminapp2`/`passwordencode=1`)** exactly as app; `lan-hash` support kept as fallback **flag** (default off) | App parity is primary; lan-hash is device-accepted (legacy-verified) but app-absent — flag gives a hardware-bring-up escape hatch |
| D5 | Cloud-only commands (SIP, facepic, RFID/FP, wifi/network, upgrades, `/tdkfile` uploads, HS `usernametoken`) **not implemented** | Milestone-1 scope (user decision) |
| D6 | No record-log dedup/watcher “extras” beyond what is needed for D1 parity | “No behavior not in the app” rule |
| D7 | Auto-unlock / call-time / lock-status **implemented in `proto/device_json_api.py`**; HA options UI gated on a live wire capture (§11.7) before entities are exposed | App parity for device settings the app offers; wire form unverified |

## 10. Phase-2 `proto/` module mapping

| New module | Mirrors app class(es) | Notes |
|---|---|---|
| `proto/auth.py` | `DeviceAuthHeaderInterceptor` | Digest challenge/response (aiohttp, manual 401 retry), `nc`/`cnonce` per §3 |
| `proto/envelope.py` | `Envelope`, `Header` beans + `initHeader`/`initEnvelope`/`initSimpleEnvelope` | XML build/parse |
| `proto/request_help.py` | `DeviceRequestHelp` | Milestone-1 commands only (§4 table), `COMMAND_*` constants verbatim |
| `proto/device_api.py` | `HttpDeviceManager` (transport slice) | `POST /tdkcgi`, content-type, errors `-10028/-10029/-10/-1`, `filetype=all` hazard |
| `proto/device_json_api.py` | `HttpDeviceJsonManager`, `DeviceJsonRequestHelp` | Layer-B JSON commands (§4) |
| `proto/beans/` (`unlock.py`, `record.py`, `secret.py`, `auto_unlock.py`, `call_time.py`, `status.py`, `attach.py`) | `bean/requset/*`, `bean/respond/*` | Field names verbatim incl. typos (`newPasswrod`) |
| `proto/live_player.py` | `QvPlayerCore` + legacy QUII impl (D3) | `quii://` URL handling, cgi/stream port discovery |
| `proto/azeno.py` | — (device-side, D2) | optional, default off |
| `custom_components/vidos_x/` (Phase 3) | app UI/features slice | config flow, coordinator, entities, options (auto-unlock, call time, channel names, record ring toggle) |

HA-free fixture tests for every module; fixtures = legacy captures + app bean shapes.

## 11. Open questions (resolve during Phase 2/4 hardware pass)

1. Does the device issue `401 WWW-Authenticate: Digest …` challenges on this
   firmware, or does it accept header-only auth? (Determines whether D4’s digest
   path is exercised; fall back to lan-hash flag if no challenge.) → capture with
   the real app or raw socket test.
2. Exact runtime `nc` value format (const `nc00001` vs `00000001`) and whether
   `passwordencryption` is required before first CGI call.
3. `get.header.content` request/response shape.
4. `get.record.message` respond bean (dex didn’t surface a dedicated resp class;
   validate against legacy capture).
5. Local ring path — confirmed absent in app build; re-check if ring behavior
   differs on newer firmware.
6. **Parity test (deferred click bug):** does the official app’s live view also
   click/relay every ~5 s? (If yes → device behavior, not integration bug.)
7. Layer-B route ids `$20/$26/$27/$29/$38` — confirm the wire form (body wrapper)
   from a live capture before exposing settings entities.

## 12. Phase-4 hardware verification checklist (from legacy, still open)

- `door=0,lock=2` gate silent-failure; DOOR2 (`door=2,lock=1`) unlock unverified;
  Gate unlock unverified; channel-2 record-log unverified.
- Port 8765 meaning; `get.live.status` semantics; record time-filter ignoring.
- Credentials stay out of repo (`DEVICE_IP`, `DEVICE_AUTH_CODE`, `DEVICE_STREAM_KEY`
  env vars).

---

## Appendix A — full XML-dialect command inventory (196)

Source: `%TEMP%/opencode/phase1/commands.txt` (`command<TAB>dex file`).
Milestone-1 commands are marked ★ in §4; the remainder are recorded for parity
reference only (D5).

```
delete.prox.card  delete.temp.pwd  get.alarm.ability.pack  get.alarm.alarmin
get.alarm.alarmin.schedule  get.alarm.alarmout  get.alarm.crydetection
get.alarm.motiondetection  get.alarm.motiondetection.schedule  get.alarm.status
get.alarm.videolost  get.alarm.videolost.schedule  get.alarm.videoshelter
get.alarm.videoshelter.schedule  get.audio.outvolume  get.audio.session
get.auto.unlock  get.call.time  get.channelmanagement.config  get.city.coordinate
get.custom.ring  get.device.qrcode  get.device.status  get.device.streamkey
get.dtmf.info  get.encode.audio  get.encode.bitratelist  get.encode.channelname
get.encode.fps  get.encode.resolution  get.enhance.ptz.range  get.facepic.delete
get.facepic.info  get.fisheye.setting  get.floodlight.schedule  get.floodlight.switch
get.fp.create  get.fp.info  get.fps.mode  get.hdd.base  get.hdr.config
get.header.content  get.humantrace.info  get.light.info  get.live.status
get.lock.status  get.motiondetection.info  get.movedetection.info  get.network.base
get.network.cloud  get.network.config  get.network.workmode  get.np.filter
get.onvif.pwd  get.private.pwd  get.product.info  get.product.time  get.prox.card
get.ptz.position  get.ptz.preset  get.qrcode.delete  get.qrcode.info
get.record.alarmrecord  get.record.config  get.record.message  get.record.search
get.record.session  get.reset.code  get.rfid.create  get.rfid.info
get.rrpc.commandlist  get.shape.mirror  get.sip.list  get.smart.lightinfo
get.smartswitch.info  get.soundandlight.state  get.system.ability
get.system.automaintenance  get.system.general  get.system.info  get.system.status
get.system.upgradeprocess  get.system.upgradestatus  get.system.upgradeversion
get.temp.pwd  get.tfcard.info  get.thirdpartypush.info  get.tip.sound
get.video.timetitle  get.videoswitch.vionoff  get.voice.message  get.whistle.list
get.wifi.list  set.alarm.alarmin  set.alarm.alarmin.schedule
set.alarm.alarmout.switch  set.alarm.crydetection  set.alarm.humandetection
set.alarm.mode  set.alarm.motiondetection  set.alarm.motiondetection.schedule
set.alarm.status  set.alarm.videolost  set.alarm.videolost.schedule
set.alarm.videoshelter  set.alarm.videoshelter.schedule  set.audio.outvolume
set.audio.session  set.auto.unlock  set.call.time  set.channel.device
set.channelmanagement.config  set.city.coordinate  set.custom.ring
set.custom.ringdel  set.custom.ringset  set.debug.synctime
set.device.f1function.enable  set.device.opendoor  set.dtmf.info
set.elevator.summonl  set.encode.audio  set.encode.channelname  set.encode.fps
set.enhance.ptz.range  set.facepic.create  set.facepic.info  set.fisheye.setting
set.floodlight.schedule  set.floodlight.switch  set.fp.create  set.fp.delete
set.fps.mode  set.hdd.base.format  set.hdr.config  set.hold.unlock
set.humantrace.info  set.light.mode  set.light.name  set.light.roomname
set.lock.status  set.motiondetection.info  set.movedetection.info  set.network.base
set.network.config  set.network.workmode  set.np.info  set.onvif.pwd
set.opendoor.checkpassword  set.opendoor.password  set.private.pwd
set.product.time  set.prox.card  set.ptz.position  set.ptz.preset
set.ptz.preset.clear  set.ptz.tour.start  set.ptz.tour.stop  set.qrcode.create
set.qrcode.name  set.record.config  set.rfid.create  set.rfid.delete
set.rfid.update  set.seurity.verifycode  set.shape.mirror  set.sip.create
set.sip.delete  set.sip.modify  set.sip.use  set.sip.usemaster  set.smart.lightinfo
set.smart.lightmode  set.smart.relay  set.smartswitch.rename  set.smartswitch.roommode
set.smartswitch.switch  set.smartswitch.switchadd  set.smartswitch.switchdel
set.soundandlight.state  set.subdevice.name  set.system.automaintenance
set.system.general  set.system.summertime  set.system.upgrade  set.system.whistle
set.temp.pwd  set.tfcard.format  set.thirdpartypush.info  set.tip.sound
set.videoswitch.vionoff  set.voice.message  set.voice.message.clear
set.voice.message.name  set.whistle.list  set.wifi.info
```

Additional JSON-dialect-only strings (layer B, not in the 196): `set.private.pwd`,
`set.np.info`, `set.sip.*`, `set.tip.sound`, `set.babysitter`, `set.fps.mode`,
`set.hdr.config`, `set.enhance.ptz.range`, `set.floodlight.switch`,
`set.audio.outvolume`, `update.temp.pwd`, `delete.temp.pwd`, `set.onvif.pwd`,
`set.thirdpartypush.info`, `set.dtmf.info`, `set.rfid.update`, `set.fp.delete`,
`set.facepic.*`, `set.voice.message.*`, `set.custom.ringset/del`,
`set.channel.device`, `set.system.automaintenance`, `set.alarm.detailInfo`,
`set.alarm.iDetailInfo`, `close.zone.alarm.triggered`, `set.subdevice.name`,
`get.light.status` values `on|off|auto`.

## Appendix B — key class inventory (extraction index)

- `DeviceRequestHelp` (classes4.dex): 128 methods; `COMMAND_*` fields
  (e.g. `COMMAND_GET_DEVICE_ALL_INFO`, `COMMAND_GET_DEVICE_SECRET`,
  `COMMAND_OPEN_LOCK`, `COMMAND_GET_RECORD_SESSION/MESSAGE/SEARCH`,
  `COMMAND_GET_ATTACHMENT_INFO`, `COMMAND_GET_LIVE_STATUS`,
  `COMMAND_SET_UNLOCK_PASSWORD`, `COMMAND_CHECK_UNLOCK_PASSWORD`,
  `COMMAND_GET_HEADER_CONTENT`); `initHeader`, `initEnvelope`,
  `initSimpleEnvelope`, `initHsHeader`, `initUnbindHeader`.
- `HttpDeviceManager` (classes4.dex): facade, 538 methods (obfuscated names
  `A…z6` + named `deal*Resp` parsers).
- `DeviceAuthHeaderInterceptor` (classes4.dex): `intercept`,
  `digestAuthForUsername` (§3).
- `HttpDeviceJsonManager` / `DeviceJsonRequestHelp` / `DeviceCustomJsonRequestHelp`
  (classes4.dex): layer B (§4).
- `QvPlayerCore` (classes2.dex): 228 methods (§7).
- `QvDeviceCgiCtrlCore` (classes2.dex): `createCgiCtrl` (§2);
  `QvNetDeviceCoreHelper.getDevCgiUrl`.
- Beans (classes4.dex): `bean/requset/*` (request contents §4),
  `bean/respond/*` (`DeviceAllInfoResp*`, `RecordSessionRes*`, `GetRecordConfigResp`,
  `GetRecordAlarmResp`, `GetDeviceSecretResp`, `GetDeviceAutoUnlockContentResp`).
