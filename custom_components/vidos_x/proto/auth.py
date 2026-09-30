"""HTTP Digest auth — parity with `DeviceAuthHeaderInterceptor`.

App behavior (docs/APP_PARITY.md §3):

* `intercept` reads `WWW-Authenticate`, splits on `,`/`=`/`"` for
  `Digest realm`, `nonce`, `opaque`, `qop`;
* `digestAuthForUsername` builds (MD5, qop=auth):
  ``Digest username="…",realm="…",nonce="…",uri="/tdkcgi",algorithm=MD5,
  response="…",opaque="…",qop=…,nc=…,cnonce="…"`` with username literal
  ``adminapp``, uri ``/tdkcgi``, method ``POST``, nc counter (app const
  ``nc00001`` — runtime format unverified, §11.2) and a random cnonce
  (app: `suiji`).

Pure functions only — no I/O, unit-testable without aiohttp.
"""

from __future__ import annotations

import hashlib
import secrets

#: App literal: DeviceAuthHeaderInterceptor.digestAuthForUsername.
DIGEST_USERNAME = "adminapp"
DIGEST_URI = "/tdkcgi"
DIGEST_METHOD = "POST"
DEFAULT_NC = "00000001"
DEFAULT_ALGORITHM = "MD5"


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()


def parse_www_authenticate(value: str) -> dict[str, str] | None:
    """Parse a ``WWW-Authenticate`` header; None when not a Digest challenge.

    Returns ``{"scheme": "Digest", "realm": …, "nonce": …, …}`` with quotes
    stripped; unknown keys are kept as-is (app keeps everything it splits).
    """
    if not value:
        return None
    value = value.strip()
    if not value.lower().startswith("digest"):
        return None
    result: dict[str, str] = {"scheme": "Digest"}
    for part in _split_params(value[len("digest") :]):
        if "=" not in part:
            continue
        key, _, raw = part.partition("=")
        result[key.strip().lower()] = raw.strip().strip('"')
    return result


def _split_params(text: str) -> list[str]:
    """Split ``k="a,b", k=v`` on commas that are outside quotes."""
    parts: list[str] = []
    buf: list[str] = []
    in_quotes = False
    for char in text:
        if char == '"':
            in_quotes = not in_quotes
            buf.append(char)
        elif char == "," and not in_quotes:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(char)
    if buf:
        parts.append("".join(buf).strip())
    return [p for p in parts if p]


def build_digest_authorization(
    challenge: dict[str, str],
    *,
    password: str,
    uri: str = DIGEST_URI,
    method: str = DIGEST_METHOD,
    username: str = DIGEST_USERNAME,
    nc: str = DEFAULT_NC,
    cnonce: str | None = None,
) -> str:
    """Build the ``Authorization: Digest …`` value for a parsed challenge."""
    realm = challenge.get("realm", "")
    nonce = challenge["nonce"]
    algorithm = challenge.get("algorithm") or DEFAULT_ALGORITHM
    cnonce = cnonce or secrets.token_hex(8)
    qop = _pick_qop(challenge.get("qop", ""))

    ha1 = _md5(f"{username}:{realm}:{password}")
    if algorithm.upper().endswith("-SESS"):
        ha1 = _md5(f"{ha1}:{nonce}:{cnonce}")
    ha2 = _md5(f"{method}:{uri}")
    if qop:
        response = _md5(f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}")
    else:
        response = _md5(f"{ha1}:{nonce}:{ha2}")

    parts = [
        f'username="{username}"',
        f'realm="{realm}"',
        f'nonce="{nonce}"',
        f'uri="{uri}"',
        f"algorithm={algorithm}",
        f'response="{response}"',
    ]
    if "opaque" in challenge:
        parts.append(f"opaque={challenge['opaque']}")
    if qop:
        parts.append(f"qop={qop}")
        parts.append(f"nc={nc}")
        parts.append(f"cnonce={cnonce}")
    return "Digest " + ",".join(parts)


def _pick_qop(qop_raw: str) -> str:
    """Prefer ``auth`` (app uses qop=auth); empty when qop not offered."""
    options = [q.strip() for q in qop_raw.split(",") if q.strip()]
    if not options:
        return ""
    return "auth" if "auth" in options else options[0]


class DigestState:
    """Caches the challenge + builds per-request Authorization values."""

    def __init__(self, challenge: dict[str, str], *, password: str) -> None:
        if not challenge.get("nonce"):
            raise ValueError("digest challenge missing nonce")
        self._challenge = challenge
        self._password = password
        self._count = 0

    @classmethod
    def from_header(cls, header_value: str, *, password: str) -> DigestState:
        parsed = parse_www_authenticate(header_value)
        if parsed is None:
            raise ValueError("not a digest challenge")
        return cls(parsed, password=password)

    def authorization(self, *, uri: str = DIGEST_URI, method: str = DIGEST_METHOD) -> str:
        self._count += 1
        return build_digest_authorization(
            self._challenge,
            password=self._password,
            uri=uri,
            method=method,
            nc=f"{self._count:08x}",
        )
