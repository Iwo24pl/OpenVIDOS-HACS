#!/usr/bin/env python3
"""Phase 0 probe for Vidos X door stations (stdlib only).

The device has two distinct secrets:

  * ``--qr``        QR passcode = auth/verification code (3rd QR token).
                    Used by the app's LAN shortcut:
                    username=adminapp2, password=sha256(qr), passwordencode=1
                    (DeviceRequestHelp.initHeader LAN branch).
  * ``--password``  first-contact device password - the "initial password"
                    the app makes you set right after adding the device
                    (DeviceAddConfigPresenter -> showConfigPassword ->
                    modifyAuthCode, stored as device.password /
                    getDeviceConfigPassword()). This is what normal
                    requests authenticate with (adminapp + raw or hashed,
                    see DeviceRequestHelp.initHsHeader / DeviceJsonRequestHelp).

Matrix probed: {each provided secret} x header variants (5), then credential
fallbacks, then optional --open-door.

Examples:
  python tools/probe.py --host 192.168.1.50 --password "12345678" --qr "654321"
  python tools/probe.py --host 192.168.1.50 --password "12345678" --save fixture.xml
  python tools/probe.py --host 192.168.1.50 --password "12345678" \
      --open-door --door 0 --unlock-password "9999"
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import socket
import ssl
import sys
import urllib.error
import urllib.request
from xml.etree import ElementTree

SCAN_PORTS = (80, 443, 554, 8000, 8080, 8899)
CGI_PATH = "/tdkcgi"
XML_PROLOG = '<?xml version="1.0" encoding="UTF-8"?>'
PASSWORD_VARIANTS_EXTRAS = ("", "123456", "admin")

# (name, username, password-mode, passwordencode)
#   mode "plain"  -> send the secret as-is, no passwordencode
#   mode "hash"   -> send sha256(secret), passwordencode=1
#   mode "raw"    -> send the secret as-is but with passwordencode=1
# (JSON path always sets passwordencode=1; HS/XML path sends raw, no flag.)
HEADER_VARIANTS = (
    ("hs-plain", "adminapp", "plain", False),
    ("hash-encode", "adminapp", "hash", True),
    ("raw-encode", "adminapp", "raw", True),
    ("lan-hash", "adminapp2", "hash", True),
    ("lan-plain", "adminapp2", "plain", False),
)

SECRET_LABELS = {"qr": "qr-passcode", "password": "first-contact", "extra": "fallback"}


def encode_device_password(value: str) -> str:
    """QvEncrypt.EncodeDevicePassword: sha256 hex unless already 64+ chars."""
    if not value:
        return ""
    if len(value) >= 64:
        return value
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def scan_ports(host: str, timeout: float) -> list[int]:
    open_ports: list[int] = []
    for port in SCAN_PORTS:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                open_ports.append(port)
        except OSError:
            continue
    return open_ports


def candidate_urls(host: str, open_ports: list[int]) -> list[str]:
    urls: list[str] = []
    for port in open_ports:
        if port == 554:
            continue  # RTSP, not CGI (V2.0)
        schemes = ("https",) if port == 443 else ("http", "https")
        for scheme in schemes:
            urls.append(f"{scheme}://{host}:{port}{CGI_PATH}")
    return urls


def transform_password(secret: str, mode: str) -> str:
    if mode == "hash":
        return encode_device_password(secret)
    return secret


def build_header_xml(username: str, password: str, passwordencode: bool) -> str:
    encode_element = "<passwordencode>1</passwordencode>" if passwordencode else ""
    return (
        f"<header>"
        f"<password>{escape_xml(password)}</password>"
        f"{encode_element}"
        f"<security>username</security>"
        f"<username>{escape_xml(username)}</username>"
        f"</header>"
    )


def build_status_request(
    username: str, password: str, passwordencode: bool = False
) -> bytes:
    return (
        f"{XML_PROLOG}<Envelope>"
        f"<body><command>get.device.status</command></body>"
        f"{build_header_xml(username, password, passwordencode)}"
        f"</Envelope>"
    ).encode()


def build_opendoor_request(
    username: str,
    password: str,
    passwordencode: bool,
    channel: int,
    lock: int,
    content_password: str,
    shape: str = "full",
) -> bytes:
    """set.device.opendoor.

    shape "full"   -> DeviceUnlockContent: door(channel) + locknumber + password
                      (DeviceRequestHelp.deviceUnlock:152 - the app's main path)
    shape "legacy" -> OpenLockContent: door(lockNum) + password only
    """
    if shape == "full":
        content = (
            f"<content><door>{channel}</door><locknumber>{lock}</locknumber>"
            f"<password>{escape_xml(content_password)}</password></content>"
        )
    else:
        content = (
            f"<content><door>{lock}</door>"
            f"<password>{escape_xml(content_password)}</password></content>"
        )
    return (
        f"{XML_PROLOG}<Envelope>"
        f"<body>"
        f"<command>set.device.opendoor</command>"
        f"{content}"
        f"</body>"
        f"{build_header_xml(username, password, passwordencode)}"
        f"</Envelope>"
    ).encode()


def escape_xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def post(url: str, payload: bytes, timeout: float, verify: bool) -> tuple[int, str]:
    """POST payload, return (http_status, body_text). Raises on network errors."""
    context = ssl._create_unverified_context() if url.startswith("https") else None
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/xml;charset=utf-8"}
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 - local device probe
            request, timeout=timeout, context=context
        ) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body


def extract_error(body: str) -> int | None:
    match = re.search(r"<error>\s*(-?\d+)\s*</error>", body, re.IGNORECASE)
    return int(match.group(1)) if match else None


def flatten_xml(body: str) -> dict[str, str]:
    """Flatten simple element paths, e.g. {'body.status.lockstate': '1'}."""
    flat: dict[str, str] = {}
    try:
        body = re.sub(r"<\?xml[^>]*\?>", "", body, count=1).strip()
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return flat

    def walk(node: ElementTree.Element, prefix: str) -> None:
        for child in node:
            path = f"{prefix}>{child.tag}".lower()
            if len(child):
                walk(child, path)
            else:
                flat[path] = (child.text or "").strip()

    walk(root, root.tag.lower())
    return flat


def build_combos(args: argparse.Namespace) -> list[tuple[str, str, tuple]]:
    """Ordered (secret_label, secret_value, variant) attempts."""
    secrets: list[tuple[str, str]] = []
    if args.password:
        secrets.append(("first-contact", args.password))
    if args.qr:
        secrets.append(("qr-passcode", args.qr))
    if not secrets:
        secrets.append(("none", ""))

    combos: list[tuple[str, str, tuple]] = [
        (label, secret, variant)
        for label, secret in secrets
        for variant in HEADER_VARIANTS
    ]
    if any(secret for _label, secret in secrets):
        combos.extend(
            ("fallback", extra, variant)
            for extra in PASSWORD_VARIANTS_EXTRAS
            for variant in HEADER_VARIANTS
        )
    return combos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vidos X Phase 0 probe")
    parser.add_argument("--host", default="", help="device IP")
    parser.add_argument(
        "--password",
        default="",
        help="first-contact device password (the 'initial password' you set in "
        "the app after adding the device)",
    )
    parser.add_argument(
        "--qr",
        default="",
        help="QR passcode (3rd token of the intercom QR label / auth code)",
    )
    parser.add_argument(
        "--timeout", type=float, default=5.0, help="per-request timeout"
    )
    parser.add_argument(
        "--save", metavar="FILE", help="save first successful status XML here"
    )
    parser.add_argument(
        "--scan-only", action="store_true", help="stop after the port scan"
    )
    parser.add_argument(
        "--open-door",
        action="store_true",
        help="send set.device.opendoor after a successful status probe",
    )
    parser.add_argument(
        "--door", type=int, default=0, help="door/channel number (content door)"
    )
    parser.add_argument(
        "--lock", type=int, default=0, help="lock number (content locknumber)"
    )
    parser.add_argument(
        "--unlock-password",
        default="",
        help="explicit unlock password; if omitted the probe derives candidates "
        "from --password/--qr (raw + sha256, app ability-24 path)",
    )
    parser.add_argument(
        "--url",
        help="explicit CGI URL (e.g. https://192.168.1.50/tdkcgi) instead of scanning",
    )
    args = parser.parse_args(argv)

    if args.url:
        urls = [args.url]
        print(f"[1/4] using explicit URL {args.url}")
    elif args.host:
        print(f"[1/4] port scan {args.host}")
        open_ports = scan_ports(args.host, args.timeout)
        if not open_ports:
            print("  no open ports found - wrong IP / device offline / different subnet")
            return 2
        print(f"  open: {open_ports}")
        urls = candidate_urls(args.host, open_ports)
    else:
        parser.error("either --host or --url is required")

    combos = build_combos(args)
    print(f"[2/4] status probe: {len(urls)} url(s) x {len(combos)} attempt(s)")

    working: tuple[str, str, bool, tuple] | None = None  # url, pwd, enc, variant

    for pass_index in (1, 2):
        if pass_index == 2:
            if not any(c[1] for c in combos):
                break
            print("[3/4] fallback credential variants")
        for url in urls:
            for label, secret, variant in combos:
                name, username, mode, passwordencode = variant
                if pass_index == 1 and label == "fallback":
                    continue
                if pass_index == 2 and label != "fallback":
                    continue
                password = transform_password(secret, mode)
                shown = password if len(password) <= 16 else password[:16] + "..."
                print(f"  -> {url}  [{name}|{label}] user={username} pwd={shown}")
                try:
                    status, body = post(
                        url,
                        build_status_request(username, password, passwordencode),
                        args.timeout,
                        verify=False,
                    )
                except (urllib.error.URLError, TimeoutError, OSError, ssl.SSLError) as exc:
                    print(f"    transport failure: {exc}")
                    break
                error_code = extract_error(body)
                print(f"     http={status} error={error_code}")
                if error_code == 0:
                    working = (url, password, passwordencode, variant)
                    print(f"  SUCCESS with variant [{name}] secret [{label}]")
                    _dump(body, args.save)
                    break
                if body and error_code is not None:
                    print(f"     response: {body[:400]}")
            if working:
                break
        if working:
            break

    if working is None:
        print(
            "\nRESULT: all variants failed.\n"
            "Next: capture one app session (see PHASE0_CHECKLIST.md, fallback section)"
        )
        return 1

    url, password, passwordencode, variant = working
    name, username, mode, _enc = variant
    if not args.open_door:
        print(f"\nRESULT: working CGI URL = {url}")
        print(f"RESULT: working variant = [{name}] (password mode={mode})")
        print("Re-run with --open-door to test the relay (listen for the click).")
        return 0

    print(f"[4/4] set.device.opendoor (matrix, channel={args.door})")
    attempts = build_door_attempts(args)
    last_error: int | None = None
    for label, content_password, lock, shape in attempts:
        print(
            f"  -> shape={shape} door={args.door} lock={lock} "
            f"pwd[{label}]={content_password[:16] or '(empty)'}"
        )
        payload = build_opendoor_request(
            username, password, passwordencode, args.door, lock, content_password, shape
        )
        try:
            http_status, body = post(url, payload, args.timeout, verify=False)
        except (urllib.error.URLError, TimeoutError, OSError, ssl.SSLError) as exc:
            print(f"    transport failure: {exc}")
            return 2
        error_code = extract_error(body)
        last_error = error_code
        print(
            f"     http={http_status} error={error_code} "
            f"{describe_error(error_code)}"
        )
        if error_code == 0:
            print(
                f"RESULT: door-open accepted [shape={shape}, lock={lock}, "
                f"pwd={label}] - confirm relay/door"
            )
            return 0
    print(
        f"\nRESULT: all {len(attempts)} door attempts failed "
        f"(last error={last_error} {describe_error(last_error)}). "
        "If every attempt returns -10028, the content password is wrong; "
        "see PHASE0_CHECKLIST.md (capture one app session)."
    )
    return 1


def describe_error(code: int | None) -> str:
    return {
        0: "(ok)",
        -10028: "(incorrect password)",
        -10029: "(device busy)",
    }.get(code, "") if code is not None else ""


def build_door_attempts(args: argparse.Namespace) -> list[tuple[str, str, int, str]]:
    """Ordered (label, content_password, lock, shape) attempts."""
    candidates: list[tuple[str, str]] = []
    if args.unlock_password:
        candidates.append(("given-raw", args.unlock_password))
        candidates.append(("given-hash", encode_device_password(args.unlock_password)))
    else:
        # App path: unlockPassword == first-contact password, sha256 when the
        # device has ability 24 (QvDeviceApi.deviceUnlock:753).
        for label, secret in (("first-contact", args.password), ("qr", args.qr)):
            if secret:
                candidates.append((f"{label}-hash", encode_device_password(secret)))
                candidates.append((f"{label}-raw", secret))
        candidates.append(("empty", ""))

    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for label, value in candidates:
        if value not in seen:
            seen.add(value)
            unique.append((label, value))

    locks = list(dict.fromkeys([args.lock, 0, 1]))
    return [
        (label, value, lock, shape)
        for label, value in unique
        for shape in ("full", "legacy")
        for lock in locks
    ]


def _dump(body: str, save_path: str | None) -> None:
    if save_path:
        try:
            path = Path(save_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
            print(f"  saved fixture -> {save_path}")
        except OSError:
            print(f"  WARNING: could not save fixture to {save_path}")
    flat = flatten_xml(body)
    if flat:
        print("  flattened fields:")
        for key, value in sorted(flat.items()):
            print(f"    {key} = {value}")


if __name__ == "__main__":
    sys.exit(main())
