"""Async transport client for ``POST /tdkcgi`` (app parity: HttpDeviceManager
transport slice + DeviceAuthHeaderInterceptor digest handshake).

Flow per request (APP_PARITY §2/§3):

1. build the XML envelope (`envelope.build_envelope`, header password SHA-256);
2. POST with the app's header credentials;
3. on ``401`` with a Digest ``WWW-Authenticate`` challenge — retry once with
   an ``Authorization: Digest`` header (username ``adminapp``), remember the
   challenge for later requests;
4. parse the XML response; raise on non-zero error when ``require_ok``.

The aiohttp import lives inside `_async_post` so the digest/retry/parsing logic
unit-tests with a fake transport and no aiohttp installed.
"""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from .auth import DIGEST_METHOD, DIGEST_URI, DigestState
from .envelope import (
    CGI_PATH,
    DEFAULT_CGI_PORT,
    DEFAULT_SCHEME,
    DEFAULT_SECURITY,
    DEFAULT_TIMEOUT,
    DEFAULT_USERNAME,
    REQUEST_HEADERS,
    CgiResponse,
    VidosCgiCommandError,
    VidosCgiConnectionError,
    VidosCgiResponseError,
    build_envelope,
    parse_response,
    sha256_hex,
)

_LOGGER = logging.getLogger(__name__)

COMMAND_OPEN_DOOR = "set.device.opendoor"
COMMAND_GET_DEVICE_STATUS = "get.device.status"
COMMAND_GET_LOCK_STATUS = "get.lock.status"

#: App literal: DeviceAuthHeaderInterceptor digest username (≠ header username).
DIGEST_USER = "adminapp"


class VidosCgiClient:
    """Async client for the device's ``/tdkcgi`` endpoint."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_CGI_PORT,
        *,
        username: str = DEFAULT_USERNAME,
        password: str,
        session: Any,
        scheme: str = DEFAULT_SCHEME,
        verify_ssl: bool = False,
        timeout: float = DEFAULT_TIMEOUT,
        hash_password: bool = True,
        security: str = DEFAULT_SECURITY,
        digest_auth: bool = True,
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
        self._security = security
        self._digest_enabled = digest_auth
        self._digest: DigestState | None = None

    @property
    def header_password(self) -> str:
        """Password as placed into the XML header (SHA-256 hex by default)."""
        return sha256_hex(self._password) if self._hash_password else self._password

    @property
    def base_url(self) -> str:
        return f"{self._scheme}://{self._host}:{self._port}{CGI_PATH}"

    @property
    def configuration_url(self) -> str:
        return f"{self._scheme}://{self._host}:{self._port}/"

    @property
    def digest_ready(self) -> bool:
        """True once a 401 challenge has been answered successfully."""
        return self._digest is not None

    def _build_envelope(self, command: str, content: str | None) -> str:
        return build_envelope(
            command,
            username=self._username,
            password=self.header_password,
            content=content,
            security=self._security,
            passwordencode=self._hash_password,
        )

    def _request_headers(self) -> dict[str, str]:
        headers = dict(REQUEST_HEADERS)
        if self._digest is not None:
            headers["Authorization"] = self._digest.authorization(
                uri=DIGEST_URI, method=DIGEST_METHOD
            )
        return headers

    async def _async_post(
        self, data: bytes, headers: Mapping[str, str]
    ) -> tuple[int, Mapping[str, str], str]:
        """POST the envelope; overridden in tests (aiohttp lives only here)."""
        import aiohttp  # local import: keeps pure helpers unit-testable

        timeout = aiohttp.ClientTimeout(total=self._timeout)
        try:
            async with self._session.post(
                self.base_url,
                data=data,
                headers=dict(headers),
                timeout=timeout,
                ssl=self._verify_ssl,
            ) as resp:
                return resp.status, dict(resp.headers), await resp.text()
        except (TimeoutError, OSError, aiohttp.ClientError) as err:
            raise VidosCgiConnectionError(
                f"cannot reach device at {self.base_url}: {err}"
            ) from err

    async def async_command(
        self, command: str, content: str | None = None, *, require_ok: bool = True
    ) -> CgiResponse:
        """POST an envelope to ``/tdkcgi``; handle a 401 digest challenge once."""
        envelope = self._build_envelope(command, content)
        data = envelope.encode("utf-8")

        status, resp_headers, text = await self._async_post(data, self._request_headers())
        if status == 401 and self._digest_enabled:
            challenge = _header_value(resp_headers, "WWW-Authenticate")
            if challenge and challenge.strip().lower().startswith("digest"):
                _LOGGER.debug("CGI %s: digest challenge received", command)
                try:
                    self._digest = DigestState.from_header(
                        challenge, password=self._password
                    )
                except ValueError as err:
                    raise VidosCgiResponseError(f"bad digest challenge: {err}") from err
                status, _resp_headers, text = await self._async_post(
                    data, self._request_headers()
                )
        if status != 200:
            raise VidosCgiResponseError(f"HTTP {status} from device")

        response = parse_response(text)
        if require_ok and not response.ok:
            raise VidosCgiCommandError(command, response.error, response.content)
        _LOGGER.debug("CGI %s -> error=%s", command, response.error)
        return response

    async def async_open_door(
        self, door: int = 0, password: str = "", lock: int = 0
    ) -> CgiResponse:
        """Open a door lock (``set.device.opendoor``).

        Content = app ``DeviceUnlockContent`` wire shape (``door`` +
        ``locknumber`` + ``password``; Phase-0 hardware verified). ``password``
        is the unlock password (defaults to the device password), SHA-256-hex
        hashed on the ability-24 path.
        """
        unlock = password or self._password
        from .request_help import unlock_content

        return await self.async_command(
            COMMAND_OPEN_DOOR,
            unlock_content(door, lock, sha256_hex(unlock) if self._hash_password else unlock),
        )

    async def async_get_status(self) -> CgiResponse:
        """Fetch device status (``get.device.status``)."""
        return await self.async_command(COMMAND_GET_DEVICE_STATUS, require_ok=False)

    async def async_get_lock_status(self) -> CgiResponse:
        """Fetch lock state (``get.lock.status``)."""
        return await self.async_command(COMMAND_GET_LOCK_STATUS, require_ok=False)


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    """Case-insensitive header lookup (fake transports vary in casing)."""
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None
