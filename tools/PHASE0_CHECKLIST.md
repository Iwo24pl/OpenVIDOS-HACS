# Phase 0 checklist — V1.0 (status + door-open)

Goal: confirm 4 unknowns before trusting the integration code.

- [x] A. Device IP, port, scheme (443/https confirmed working via probe)
- [x] B. Auth mode: **`lan-hash`** = `adminapp2` + `sha256(first-contact)` + `passwordencode=1`
- [x] C. Response shape of `get.device.status` (fixture: `tests/fixtures/device_status_sample.xml`)
- [x] D. `set.device.opendoor`: `door=0`, `locknumber=0`, `password=sha256(first-contact)`

## Inputs — two secrets, not one

| Secret | Where it comes from | How the app sends it |
|---|---|---|
| **QR passcode** (`--qr`) | 3rd token of the intercom QR label (`apName uid authCode model`); modifiable via `set.seurity.verifycode` | LAN shortcut: `username=adminapp2`, `password=sha256(qr)`, `passwordencode=1` (`DeviceRequestHelp.initHeader` LAN branch) |
| **First-contact password** (`--password`) | The "initial password" the app makes you set right after adding the device (`DeviceAddConfigPresenter` -> `showConfigPassword` -> `modifyAuthCode`); stored as `device.password` / `getDeviceConfigPassword()` | Normal requests: `username=adminapp`, password raw **or** `passwordencode=1` hashed (`initHsHeader` / `DeviceJsonRequestHelp.initHeader`) |

Not to be confused with:

- account/register PIN — cloud login only, never sent to the device
- door **unlock** password — `set.opendoor.password`, passed in the `<content>` of the opendoor command

Probe header variants (in order): `hs-plain` (adminapp+raw), `hash-encode`
(adminapp+sha256+flag), `raw-encode` (adminapp+raw+flag), `lan-hash`
(adminapp2+sha256+flag), `lan-plain` (adminapp2+raw). Each provided secret is
tried against all 5, then fallback credentials (empty / `123456` / `admin`).

## Steps

### 1. Port scan

```powershell
python tools\probe.py --host <IP> --scan-only
```

Expect: `open: [443]` or `[80]` (554 = RTSP, noted for V2.0, not used now).

- [x] Ports recorded (443 open, https works)

### 2+3. Status probe (both secrets x header variants)

```powershell
python tools\probe.py --host <IP> --password "<first-contact password>" --qr "<QR passcode>" --save tests\fixtures\device_status_sample.xml
```

Either secret may be omitted; supply both when available.

- [x] `SUCCESS with variant [lan-hash] secret [first-contact]` (B done, response C captured)
- [x] Fixture saved

### 4. Door-open test (after step 2 succeeds)

```powershell
python tools\probe.py --host <IP> --password "<first-contact password>" --qr "<QR passcode>" --open-door
```

The probe walks a matrix — no separate unlock password needed on your side:

- content shape: `DeviceUnlockContent` = `door` + `locknumber` + `password`
  (the app's real path, `DeviceRequestHelp.deviceUnlock:152`) and the legacy
  `door`+`password` shape as fallback
- content password candidates: `sha256(first-contact)` (ability-24 path,
  `QvDeviceApi.deviceUnlock:753`), raw, `sha256(qr)`, raw qr, empty — because
  at first contact the app sets **unlockPassword = authCode = first-contact
  password** (`DeviceVerifyCodeModifyPresenter.g:40-41`)
- locks: `--lock` (default 0), then 0 and 1
- device error codes: `-10028` = incorrect password, `-10029` = busy

- [x] `RESULT: door-open accepted [shape=full, lock=0, pwd=first-contact-hash]`
- [ ] Relay/door physically confirmed by user
- [x] Recorded: shape=`full` (`door`+`locknumber`+`password`), lock=0, pwd=`sha256(first-contact)`
- [n/a] fallback capture not needed

### 5. Feed results back

- [x] Patch `cgi.py` / integration with confirmed scheme, port, header variant, field names
- [x] Add captured fixture as a unit test (`tests/test_cgi.py::FixtureTests`)
- [x] Mark verified items in `VIDOS_X_PROTOCOL.md`
- [x] Update `HACS_INTEGRATION_PLAN.md`: V1.0 verified, video stays V2.0

## Fallback — only if all variants fail

The device may require the `usernametoken` hash (`initHsHeader` with
`cgiType==1`: random `nc`, native `QvJniFunc.getEncryptPassword`). Capture one
app session first:

1. Same-LAN packet capture while operating the app (status + open door):
   - `tcpdump -i any -s 0 -w vidos.pcap host <IP>` on a Pi / router / gateway box, or
   - mitmproxy on a rooted phone with JustTrustMe (app may use custom CA = pinning risk).
2. Extract one request body + response body (if TLS blocks payload, use port 80 /
   `http://` route — check whether 80 is open).
3. If payload is opaque, reverse `QvJniFunc.getEncryptPassword` in
   `liblive_player.so` (32-bit) — that is the only missing primitive.

## Exit criteria (V1.0)

- [x] `get.device.status` returns `<error>0</error>` with saved XML fixture
- [x] `set.device.opendoor` returns `<error>0</error>` (relay click pending user confirmation)
- [x] Both request/response pairs stored under `tests/fixtures/`
