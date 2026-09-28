"""Local HTTP CGI client for Vidos X / Quvii (TDK) intercoms.

**Phase 0 verified** against an IDS9483AW door station (V1.0).

Devices expose ``http(s)://<ip>:<cgi_port>/tdkcgi`` and accept an XML envelope::

    <Envelope>
      <body>
        <command>set.device.opendoor</command>
        <content>
          <door>0</door><locknumber>0</locknumber>
          <password>sha256hex(unlock_password)</password>
        </content>
      </body>
      <header>
        <password>sha256hex(device_password)</password>
        <passwordencode>1</passwordencode>
        <security>username</security>
        <username>adminapp2</username>
      </header>
    </Envelope>

Response (tolerantly parsed)::

    <envelope><body><error>0</error><content>...</content></body></envelope>

Verified details (tools/PHASE0_CHECKLIST.md + tests/fixtures/):

* header: ``username=adminapp2``, ``password=sha256hex(first-contact device
  password)``, ``passwordencode=1`` (app LAN branch, DeviceRequestHelp.initHeader)
* door open: ``DeviceUnlockContent`` = ``door`` (channel) + ``locknumber`` +
  ``password=sha256hex(unlockPassword)``; at first contact the app sets
  unlockPassword = authCode = device password
* common device error codes: ``-10028`` incorrect password, ``-10029`` busy
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
from typing import Any
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

_LOGGER = logging.getLogger(__name__)

CGI_PATH = "/tdkcgi"
DEFAULT_CGI_PORT = 443
DEFAULT_TIMEOUT = 10.0
DEFAULT_USERNAME = "adminapp2"

SECURITY_USERNAME = "username"

COMMAND_OPEN_DOOR = "set.device.opendoor"
COMMAND_GET_LOCK_STATUS = "get.lock.status"
COMMAND_GET_DEVICE_STATUS = "get.device.status"
COMMAND_GET_ONVIF_PWD = "get.onvif.pwd"
COMMAND_GET_ALARM_DISARM = "g.alm.disarm"
COMMAND_SET_ALARM_DISARM = "s.alm.disarm"

REQUEST_HEADERS = {"Content-Type": "application/xml;charset=utf-8"}


class VidosCgiError(Exception):
    """Base error for the device CGI client."""


class VidosCgiConnectionError(VidosCgiError):
    """Device could not be reached (network / TLS / HTTP error)."""


class VidosCgiResponseError(VidosCgiError):
    """Device answered with an unparsable or failed response."""


class VidosCgiCommandError(VidosCgiError):
    """Device answered with a non-zero CGI error code."""

    def __init__(self, command: str, error: int, content: str = "") -> None:
        super().__init__(f"{command} failed: error={error} {content}".strip())
        self.command = command
        self.error = error
        self.content = content


@dataclass(frozen=True)
class CgiResponse:
    """Parsed device CGI response."""

    error: int
    content: str = ""
    raw: str = ""

    @property
    def ok(self) -> bool:
        return self.error == 0

    @property
    def fields(self) -> dict[str, str]:
        """Flatten the ``content`` XML into a ``{tag: text}`` mapping."""
        return flatten_fields(self.content)


def _esc(value: Any) -> str:
    return escape(str(value))


def sha256_hex(value: str) -> str:
    """QvEncrypt.EncodeDevicePassword: lowercase SHA-256 hex ("" for empty)."""
    if not value:
        return ""
    if len(value) >= 64:
        return value
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def content_from_mapping(data: dict[str, Any]) -> str:
    """Build a ``<content>`` element from an ordered mapping."""
    inner = "".join(f"<{_esc(k)}>{_esc(v)}</{_esc(k)}>" for k, v in data.items())
    return f"<content>{inner}</content>"


def build_envelope(
    command: str,
    *,
    username: str,
    password: str,
    content: str | None = None,
    security: str = SECURITY_USERNAME,
    passwordencode: bool = False,
) -> str:
    """Build a complete device CGI request envelope.

    Field order mirrors the app's SimpleXML beans: ``body`` before ``header``;
    header fields in order ``password, passwordencode?, security, username``.
    """
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Envelope>"
        f"{build_body(command, content)}"
        f"{build_header(username, password, security, passwordencode)}"
        "</Envelope>"
    )


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _find(root: ET.Element, name: str) -> ET.Element | None:
    wanted = name.lower()
    for el in root.iter():
        if _localname(el.tag) == wanted:
            return el
    return None


def parse_response(text: str) -> CgiResponse:
    """Parse a device CGI response, tolerating root/casing variations."""
    try:
        root = ET.fromstring(text.strip())
    except ET.ParseError as err:
        raise VidosCgiResponseError(f"invalid XML response: {err}") from err

    error = 0
    error_el = _find(root, "error")
    if error_el is not None and (error_el.text or "").strip():
        try:
            error = int(error_el.text.strip())
        except ValueError as err:
            raise VidosCgiResponseError(f"non-numeric error: {error_el.text!r}") from err

    content_el = _find(root, "content")
    content = (content_el.text or "") if content_el is not None else ""
    if content_el is not None and len(content_el) and not content.strip():
        content = ET.tostring(content_el, encoding="unicode")
    return CgiResponse(error=error, content=content, raw=text)


def flatten_fields(xml_text: str) -> dict[str, str]:
    """Flatten simple XML content into ``{localname: text}`` (first occurrence wins)."""
    if not xml_text or not xml_text.strip():
        return {}
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError:
        return {}
    fields: dict[str, str] = {}
    for el in root.iter():
        if el is root:
            continue
        name = _localname(el.tag)
        if name in fields:
            continue
        if len(el):
            continue
        text = (el.text or "").strip()
        if text:
            fields[name] = text
    return fields


class VidosCgiClient:
    """Async client for the device's ``/tdkcgi`` endpoint."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        username: str,
        password: str,
        session: Any,
        scheme: str = "https",
        verify_ssl: bool = False,
        timeout: float = DEFAULT_TIMEOUT,
        hash_password: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._session = session
        self._scheme = scheme
        self._verify_ssl = verify_ssl
        self._timeout = timeout
        self._hash_password = hash_password

    @property
    def header_password(self) -> str:
        """Password as placed into the request header (SHA-256 hex by default)."""
        return sha256_hex(self._password) if self._hash_password else self._password

    @property
    def base_url(self) -> str:
        return f"{self._scheme}://{self._host}:{self._port}{CGI_PATH}"

    @property
    def configuration_url(self) -> str:
        return f"{self._scheme}://{self._host}:{self._port}/"

    async def async_command(
        self, command: str, content: str | None = None, *, require_ok: bool = True
    ) -> CgiResponse:
        """POST an envelope to ``/tdkcgi`` and return the parsed response."""
        import aiohttp  # local import: keeps pure helpers unit-testable

        envelope = build_envelope(
            command,
            username=self._username,
            password=self.header_password,
            content=content,
            passwordencode=self._hash_password,
        )
        timeout = aiohttp.ClientTimeout(total=self._timeout)
        try:
            async with self._session.post(
                self.base_url,
                data=envelope.encode("utf-8"),
                headers=REQUEST_HEADERS,
                timeout=timeout,
                ssl=self._verify_ssl,
            ) as resp:
                if resp.status != 200:
                    raise VidosCgiResponseError(f"HTTP {resp.status} from device")
                text = await resp.text()
        except (TimeoutError, OSError, aiohttp.ClientError) as err:
            raise VidosCgiConnectionError(
                f"cannot reach device at {self.base_url}: {err}"
            ) from err

        response = parse_response(text)
        if require_ok and not response.ok:
            raise VidosCgiCommandError(command, response.error, response.content)
        _LOGGER.debug("CGI %s -> error=%s", command, response.error)
        return response

    async def async_open_door(
        self, door: int = 0, password: str = "", lock: int = 0
    ) -> CgiResponse:
        """Open a door lock (``set.device.opendoor``).

        ``password`` is the unlock password (defaults to the device password);
        the device expects it SHA-256-hashed (ability-24 path). Content shape
        verified in Phase 0: ``door`` + ``locknumber`` + ``password``.
        """
        unlock = password or self._password
        content = content_from_mapping(
            {
                "door": door,
                "locknumber": lock,
                "password": sha256_hex(unlock) if self._hash_password else unlock,
            }
        )
        return await self.async_command(COMMAND_OPEN_DOOR, content)

    async def async_get_status(self) -> CgiResponse:
        """Fetch device status (``get.device.status``)."""
        return await self.async_command(COMMAND_GET_DEVICE_STATUS, require_ok=False)

    async def async_get_lock_status(self) -> CgiResponse:
        """Fetch lock state (``get.lock.status``)."""
        return await self.async_command(COMMAND_GET_LOCK_STATUS, require_ok=False)

    async def async_set_alarm_disarm(self, disarmed: bool) -> CgiResponse:
        """Set the alarm disarm flag (``s.alm.disarm``) - unverified command."""
        content = content_from_mapping({"disarm": "1" if disarmed else "0"})
        return await self.async_command(COMMAND_SET_ALARM_DISARM, content)


def build_header(
    username: str,
    password: str,
    security: str = SECURITY_USERNAME,
    passwordencode: bool = False,
) -> str:
    """Build the ``<header>`` element for a device CGI request."""
    encode = "<passwordencode>1</passwordencode>" if passwordencode else ""
    return (
        "<header>"
        f"<password>{_esc(password)}</password>"
        f"{encode}"
        f"<security>{_esc(security)}</security>"
        f"<username>{_esc(username)}</username>"
        "</header>"
    )


def build_body(command: str, content: str | None = None) -> str:
    """Build the ``<body>`` element for a device CGI request."""
    return f"<body><command>{_esc(command)}</command>{content or ''}</body>"
