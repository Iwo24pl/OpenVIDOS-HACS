"""Vidos X cloud (TDK) client - account login and device discovery.

Everything here is reverse-engineered from the Vidos X app and is **not yet
validated against the live cloud** (Phase 0 of the work plan):

* token endpoint: ``GET https://vidos.qvcloud.net/qvoauthv2/token``
* device list: XML up-channel ``POST /auth/user;jus_duplex=up`` with command
  ``get-device-list`` (envelope: ``<envelope><content/><header/></envelope>``,
  header flag ``tdkcloud``)

The cloud is only used for *discovery*: control always talks to the device
directly over its local CGI endpoint (see :mod:`cgi`).
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any
import uuid
from xml.sax.saxutils import escape

from .cgi import DEFAULT_CGI_PORT, DEFAULT_USERNAME, flatten_fields
from .models import VidosDevice

_LOGGER = logging.getLogger(__name__)

DEFAULT_CLOUD_BASE_URL = "https://vidos.qvcloud.net"
OAUTH_TOKEN_PATH = "/qvoauthv2/token"
USER_UP_PATH = "/auth/user;jus_duplex=up"

OEM_ID = "G0108"
APP_ID = "4108"
FLAG = "tdkcloud"
COMMAND_GET_DEVICE_LIST = "get-device-list"
CLIENT_FLAG_ACCOUNT = "1"
CLIENT_FLAG_NO_LOGIN = "2"

XML_HEADERS = {"Content-Type": "application/xml;charset=utf-8"}


class VidosCloudError(Exception):
    """Base error for the cloud client."""


class VidosCloudAuthError(VidosCloudError):
    """Login was rejected by the cloud."""


class VidosCloudConnectionError(VidosCloudError):
    """Cloud could not be reached."""


@dataclass(frozen=True)
class CloudToken:
    """OAuth token response."""

    access_token: str
    refresh_token: str = ""


def make_client_id(client_type: int = 0) -> str:
    """Build an ``ALARM_CLIENT_ID``: ``00<clientType>-<appId>-<unique>``."""
    return f"00{client_type}-{APP_ID}-{uuid.uuid4().hex[:16]}"


def _esc(value: Any) -> str:
    return escape(str(value))


def build_cloud_envelope(
    command: str,
    content: str,
    *,
    client_id: str,
    client_type: int = 0,
    session: str = "",
    version: str = "1",
    seq: int = 1,
) -> str:
    """Build a cloud up-channel envelope.

    Order mirrors the app's beans: ``<content>`` before ``<header>``; header
    children: ``Client, command, flag, seq, session, version``.
    """
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<envelope>"
        f"<content>{content}</content>"
        "<header>"
        "<Client>"
        f"<app>{_esc(APP_ID)}</app>"
        f"<id>{_esc(client_id)}</id>"
        f"<oem>{_esc(OEM_ID)}</oem>"
        f"<type>{_esc(client_type)}</type>"
        "</Client>"
        f"<command>{_esc(command)}</command>"
        f"<flag>{_esc(FLAG)}</flag>"
        f"<seq>{_esc(seq)}</seq>"
        f"<session>{_esc(session)}</session>"
        f"<version>{_esc(version)}</version>"
        "</header>"
        "</envelope>"
    )


async def async_login(
    session: Any,
    username: str,
    password: str,
    *,
    base_url: str = DEFAULT_CLOUD_BASE_URL,
    client_id: str | None = None,
    client_type: int = 0,
    region_id: int = 0,
    client_flag: str = CLIENT_FLAG_ACCOUNT,
) -> CloudToken:
    """Password-grant login (``GET /qvoauthv2/token``)."""
    import aiohttp

    client_id = client_id or make_client_id(client_type)
    params = {
        "grant_type": "password",
        "client_id": client_id,
        "client_type": str(client_type),
        "oemid": OEM_ID,
        "appid": APP_ID,
        "usr": username,
        "pwd": password,
        "region_id": str(region_id),
        "client_flag": client_flag,
    }
    url = f"{base_url}{OAUTH_TOKEN_PATH}"
    try:
        async with session.get(url, params=params) as resp:
            body = await resp.json(content_type=None)
            if resp.status >= 400:
                raise VidosCloudAuthError(
                    f"login rejected: HTTP {resp.status} {body.get('error', '')}"
                )
    except (TimeoutError, OSError, aiohttp.ClientError) as err:
        raise VidosCloudConnectionError(f"cannot reach {url}: {err}") from err
    except ValueError as err:  # non-JSON body
        raise VidosCloudConnectionError(f"unexpected response from {url}: {err}") from err

    token = body.get("access_token")
    if not token:
        if body.get("error"):
            raise VidosCloudAuthError(f"login rejected: {body.get('error')}")
        raise VidosCloudConnectionError("no access_token in token response")
    return CloudToken(access_token=token, refresh_token=body.get("refresh_token", ""))


def parse_devices(xml_text: str) -> list[VidosDevice]:
    """Best-effort parser for ``get-device-list`` responses (unverified schema)."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError:
        _LOGGER.debug("device list response is not XML: %s", xml_text[:200])
        return []

    devices: list[VidosDevice] = []
    seen: set[str] = set()
    for el in root.iter():
        children = list(el)
        if not children:
            continue
        fields = flatten_fields(ET.tostring(el, encoding="unicode"))
        if "ip" not in fields and "ipaddress" not in fields:
            continue
        uid = next(
            (fields[k] for k in ("uid", "id", "devid", "deviceid") if k in fields), None
        )
        ip = fields.get("ip") or fields.get("ipaddress")
        if not uid or not ip or uid in seen:
            continue
        seen.add(uid)
        port_raw = next(
            (fields[k] for k in ("cgiport", "cgi_port", "port", "httpport") if k in fields),
            str(DEFAULT_CGI_PORT),
        )
        try:
            port = int(port_raw)
        except ValueError:
            port = DEFAULT_CGI_PORT
        devices.append(
            VidosDevice(
                uid=uid,
                name=fields.get("name") or fields.get("devicename") or uid,
                ip=ip,
                cgi_port=port,
                username=fields.get("username") or DEFAULT_USERNAME,
                password=fields.get("password") or fields.get("dynamicpassword") or "",
                model=fields.get("model") or fields.get("devicemodel"),
            )
        )
    return devices


async def async_get_device_list(
    session: Any,
    token: CloudToken,
    *,
    base_url: str = DEFAULT_CLOUD_BASE_URL,
    client_id: str | None = None,
    client_type: int = 0,
    version: str = "1",
) -> list[VidosDevice]:
    """POST ``get-device-list`` to the cloud up-channel (UNVERIFIED)."""
    import aiohttp

    client_id = client_id or make_client_id(client_type)
    envelope = build_cloud_envelope(
        COMMAND_GET_DEVICE_LIST,
        "<devlist></devlist>",
        client_id=client_id,
        client_type=client_type,
        session=token.access_token,
        version=version,
    )
    url = f"{base_url}{USER_UP_PATH}"
    headers = {
        **XML_HEADERS,
        "Authorization": f"Bearer {token.access_token}",
    }
    try:
        async with session.post(url, data=envelope.encode("utf-8"), headers=headers) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise VidosCloudConnectionError(f"device list failed: HTTP {resp.status}")
    except (TimeoutError, OSError, aiohttp.ClientError) as err:
        raise VidosCloudConnectionError(f"cannot reach {url}: {err}") from err

    devices = parse_devices(text)
    _LOGGER.debug("cloud returned %d device(s)", len(devices))
    return devices
