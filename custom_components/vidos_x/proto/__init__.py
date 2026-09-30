"""HA-free protocol library for Vidos X / Quvii (TDK) intercoms.

Module map follows docs/APP_PARITY.md §10 (app class → module). Importing
this package must never require Home Assistant.
"""

from __future__ import annotations

from .auth import DigestState, build_digest_authorization, parse_www_authenticate
from .device_api import VidosCgiClient
from .envelope import (
    CgiResponse,
    VidosCgiCommandError,
    VidosCgiConnectionError,
    VidosCgiError,
    VidosCgiResponseError,
    build_envelope,
    parse_response,
    sha256_hex,
)
from .records import RecordRingWatcher

__all__ = [
    "CgiResponse",
    "DigestState",
    "RecordRingWatcher",
    "VidosCgiClient",
    "VidosCgiCommandError",
    "VidosCgiConnectionError",
    "VidosCgiError",
    "VidosCgiResponseError",
    "build_digest_authorization",
    "build_envelope",
    "parse_response",
    "parse_www_authenticate",
    "sha256_hex",
]
