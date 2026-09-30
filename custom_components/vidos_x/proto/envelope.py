"""XML Envelope build/parse for the TDK CGI dialect.

App parity: mirrors `com.quvii.qvweb.device.DeviceRequestHelp` envelope
handling + the `Envelope{header, body}` / `Header{security, username, password,
passwordencode, nc}` beans (docs/APP_PARITY.md §3).

Wire-verified facts (legacy Phase 0 hardware capture, IDS9483AW):

* envelope order: ``<body>`` before ``<header>`` (SimpleXML bean order);
* header field order: password, passwordencode?, security, username;
* header password = sha256hex(device password) with ``passwordencode=1``;
* ``DeviceUnlockContent`` wire tags ``door``/``locknumber`` are SimpleXML
  ``@Element`` renames of the Java fields ``channelNum``/``lockNum``;
* responses tolerate root/casing variation: ``<error>`` + ``<content>``.

``<security>`` value: app ``initHeader`` const is ``httpauthen`` (default here);
the Phase-0 probe verified this firmware also accepts ``username`` (legacy
value) — both recorded in APP_PARITY §3/§11.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

CGI_PATH = "/tdkcgi"
DEFAULT_CGI_PORT = 443
DEFAULT_SCHEME = "https"
DEFAULT_TIMEOUT = 10.0

#: App parity: DeviceRequestHelp.initHeader (APP_PARITY §3).
DEFAULT_SECURITY = "httpauthen"
#: App parity: initHeader literal; Phase-0 probe variant "lan-hash" username.
DEFAULT_USERNAME = "adminapp2"
#: Legacy probe-verified fallback (APP_PARITY §3 / §11).
SECURITY_USERNAME_LEGACY = "username"

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


def build_header(
    username: str,
    password: str,
    security: str = DEFAULT_SECURITY,
    passwordencode: bool = False,
    nc: str | None = None,
) -> str:
    """Build the ``<header>`` element (Header bean, APP_PARITY §3)."""
    encode = "<passwordencode>1</passwordencode>" if passwordencode else ""
    nc_xml = f"<nc>{_esc(nc)}</nc>" if nc else ""
    return (
        "<header>"
        f"<password>{_esc(password)}</password>"
        f"{encode}"
        f"<security>{_esc(security)}</security>"
        f"<username>{_esc(username)}</username>"
        f"{nc_xml}"
        "</header>"
    )


def build_body(command: str, content: str | None = None) -> str:
    """Build the ``<body>`` element for a device CGI request."""
    return f"<body><command>{_esc(command)}</command>{content or ''}</body>"


def build_envelope(
    command: str,
    *,
    username: str,
    password: str,
    content: str | None = None,
    security: str = DEFAULT_SECURITY,
    passwordencode: bool = False,
    nc: str | None = None,
) -> str:
    """Build a complete device CGI request envelope (body before header)."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Envelope>"
        f"{build_body(command, content)}"
        f"{build_header(username, password, security, passwordencode, nc)}"
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
