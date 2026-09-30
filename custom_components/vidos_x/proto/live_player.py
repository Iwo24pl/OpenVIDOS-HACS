"""QUII media protocol client (TCP 34567) - snapshot source for the camera.

Parity note (APP_PARITY §7/§9 D3): the app plays video via the native
`liblive_player.so` behind `QvPlayerCore` (exoplayer facade); this module is
the hardware-verified Python port of that wire protocol (kept from
legacy v0.4.0 rather than re-reversing the native library).

Wire format and crypto verified on IDS9483AW hardware 2026-10-02
(`docs/VIDOS_X_PROTOCOL.md` ┬ž4.3/┬ž4.4): Setup 0xA9 -> Play 0x01 (AES-256-CBC,
IV = ASCII '0' x 16, SHA-256 trailer) -> media 0xA0..0xA3 carrying a 20-byte
QV frame header + annex-B H.264.

Framing and crypto adapted from the MIT-licensed `quii-lan-client` project
(github.com/fariborz0015/quii-lan-client), itself an offline RE of
`liblive_player.so` (`CQUIIStreamBase::EncryptData` / `SetIvec`).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import struct
import time
from typing import Final

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)

MSG_HDR: Final = 32
AES_BLOCK: Final = 16
IV_ZEROS: Final = b"0" * AES_BLOCK
DEFAULT_MEDIA_PORT: Final = 34567

# Annex-B start codes that mark a decodable keyframe (SPS 0x67/0x27,
# IDR 0x65/0x25) - same marker set the reference client accepts.
_KEYFRAME_MARKERS: Final = (
    b"\x00\x00\x00\x01\x67",
    b"\x00\x00\x00\x01\x27",
    b"\x00\x00\x01\x67",
    b"\x00\x00\x01\x27",
    b"\x00\x00\x00\x01\x65",
    b"\x00\x00\x00\x01\x25",
    b"\x00\x00\x01\x65",
    b"\x00\x00\x01\x25",
)
_SPS_MARKERS: Final = _KEYFRAME_MARKERS[:4]
_IDR_MARKERS: Final = _KEYFRAME_MARKERS[4:]

QV_HDR_LEN: Final = 20  # 00 00 01 | E0+type | u32le len | ... | payload @ 0x14


class QuiiError(Exception):
    """Base error for the QUII media client."""


class QuiiConnectionError(QuiiError):
    """Handshake or connection to the media port failed."""


class QuiiNoMediaError(QuiiError):
    """Session opened but no keyframe arrived in time."""


def _key_bytes(key_material: str | bytes, enc_mode: int) -> bytes:
    """AES key bytes: raw prefix of the SetKey C-string (no hex decoding)."""
    raw = key_material.encode("ascii") if isinstance(key_material, str) else key_material
    length = {1: 16, 2: 32}.get(enc_mode, 16)
    if len(raw) < length:
        raise ValueError(f"key material shorter than {length} bytes")
    return raw[:length]


def _aes(data: bytes, key_material: str | bytes, enc_mode: int, *, decrypt: bool) -> bytes:
    if enc_mode == 0:
        return data
    if len(data) % AES_BLOCK:
        raise ValueError(f"data length {len(data)} not block aligned")
    key = _key_bytes(key_material, enc_mode)
    cipher = Cipher(algorithms.AES(key), modes.CBC(IV_ZEROS))
    op = cipher.decryptor() if decrypt else cipher.encryptor()
    return op.update(data) + op.finalize()


def decrypt_header(wire32: bytes, key_material: str | bytes, enc_mode: int) -> bytes:
    """Decrypt one 32-byte message header (independent CBC chunk)."""
    if enc_mode == 0:
        return wire32[:MSG_HDR]
    if len(wire32) < MSG_HDR:
        raise ValueError("header shorter than 32 bytes")
    return _aes(wire32[:MSG_HDR], key_material, enc_mode, decrypt=True)


def encrypt_packet(clear: bytes, key_material: str | bytes, enc_mode: int) -> bytes:
    """Wire transform for send (Play/KeepAlive): AES(hdr) || AES(rest)."""
    if enc_mode == 0:
        return clear
    if len(clear) < MSG_HDR:
        raise ValueError("packet shorter than msgheader")
    rest = clear[MSG_HDR:]
    if len(rest) % AES_BLOCK:
        raise ValueError("payload after header not block aligned")
    return _aes(clear[:MSG_HDR], key_material, enc_mode, decrypt=False) + _aes(
        rest, key_material, enc_mode, decrypt=False
    )


def build_setup(*, talk: bool = False) -> bytes:
    """Live Setup packet: 0xA9 + zeros (talk sets hdr[9] = 2)."""
    buf = bytearray(MSG_HDR)
    buf[0] = 0xA9
    if talk:
        buf[9] = 2
    return bytes(buf)


def build_play(
    username: str,
    password: str,
    key_material: str | bytes,
    *,
    enc_mode: int = 2,
    sha_mode: int = 1,
    idc: int = 1,
    ids: int = 1,
    play_arg: int = 1,
) -> bytes:
    """Full Play packet (opcode 0x01) with SHA-256 trailer, encrypted.

    ``password`` is the wire password (sha256 hex of the device auth code),
    ``ids`` is the wire value after the client's URL ``ids-1`` adjustment.
    """
    body = username.encode() + b"&&" + password.encode() + b"\x00\x00"
    body_len = len(body)
    sha_len = 32 if sha_mode == 1 else 0
    total = body_len + sha_len
    padded = ((total + AES_BLOCK - 1) // AES_BLOCK) * AES_BLOCK if enc_mode else total

    buf = bytearray(MSG_HDR + padded)
    buf[0] = 0x01
    struct.pack_into("<Q", buf, 1, int(time.time()) & 0xFFFFFFFFFFFFFFFF)
    struct.pack_into("<H", buf, 9, padded if enc_mode else 0)
    struct.pack_into("<H", buf, 0x0B, body_len)
    struct.pack_into("<H", buf, 0x0D, idc & 0xFFFF)
    buf[0x0F] = play_arg & 0xFF
    buf[0x10] = ids & 0xFF
    buf[0x11] = 0  # inner
    buf[MSG_HDR : MSG_HDR + body_len] = body
    if sha_len:
        digest = hashlib.sha256(bytes(buf[: MSG_HDR + body_len])).digest()
        buf[MSG_HDR + body_len : MSG_HDR + body_len + sha_len] = digest
    return encrypt_packet(bytes(buf), key_material, enc_mode)


def build_keepalive(
    key_material: str | bytes, *, enc_mode: int = 2, sha_mode: int = 1
) -> bytes:
    """KeepAlive packet (opcode 0x00, empty body + optional SHA pad)."""
    sha_len = 32 if sha_mode == 1 else 0
    total = sha_len
    padded = ((total + AES_BLOCK - 1) // AES_BLOCK) * AES_BLOCK if enc_mode else total
    buf = bytearray(MSG_HDR + padded)
    buf[0] = 0x00
    struct.pack_into("<Q", buf, 1, int(time.time()) & 0xFFFFFFFFFFFFFFFF)
    struct.pack_into("<H", buf, 9, padded if enc_mode else 0)
    struct.pack_into("<H", buf, 0x0B, 0)
    if sha_len:
        digest = hashlib.sha256(bytes(buf[:MSG_HDR])).digest()
        buf[MSG_HDR : MSG_HDR + sha_len] = digest
    return encrypt_packet(bytes(buf), key_material, enc_mode)


def media_body_len(hdr: bytes) -> int:
    """Media body length: u32 at +0x0B (with u16/command fallbacks)."""
    if len(hdr) < 0x0F:
        return 0
    u32 = struct.unpack_from("<I", hdr, 0x0B)[0]
    u16 = struct.unpack_from("<H", hdr, 0x0B)[0]
    if 0 < u32 <= 2_000_000:
        return u32
    if 0 < u16 <= 0xFFFF:
        return u16
    return struct.unpack_from("<H", hdr, 9)[0]


def unpack_media_payload(
    clear_hdr: bytes, body_cipher: bytes, key_material: str | bytes, enc_mode: int
) -> bytes:
    """Decrypt/unstrip one media message body to its payload (QV hdr + data).

    Observed on hardware: param_len@+9 == 32, hdr[0x0F] == 0 - only the first
    ``param_len`` body bytes are AES, the remainder (annex-B) is plaintext.
    """
    param9 = struct.unpack_from("<H", clear_hdr, 9)[0]
    off10 = struct.unpack_from("<H", clear_hdr, 0x10)[0]
    media_flag = clear_hdr[0x0F]

    body = body_cipher
    if param9 >= 1 and enc_mode and len(body) >= param9 and param9 % 16 == 0:
        body = _aes(body[:param9], key_material, enc_mode, decrypt=True) + body[param9:]

    if media_flag != 0 and enc_mode:
        start = min(off10, len(body))
        media_ct = body[start:]
        aligned = len(media_ct) - (len(media_ct) % AES_BLOCK)
        if aligned > 0:
            pt = _aes(media_ct[:aligned], key_material, enc_mode, decrypt=True)
            body = body[:start] + pt + media_ct[aligned:]

    if off10 and off10 < len(body):
        return body[off10:]
    return body


def strip_to_annexb(payload: bytes) -> bytes | None:
    """Return payload from its first SPS/IDR start code, else None."""
    hits = [
        idx
        for needle in _KEYFRAME_MARKERS
        if (idx := payload.find(needle)) >= 0
    ]
    if hits:
        return payload[min(hits):]
    for startcode in (b"\x00\x00\x00\x01", b"\x00\x00\x01"):
        idx = payload.find(startcode)
        if idx < 0:
            continue
        if idx + len(startcode) < len(payload):
            nal_type = payload[idx + len(startcode)] & 0x1F
            if nal_type in (1, 5, 6, 7, 8, 9):
                return payload[idx:]
    return None


def is_keyframe(payload: bytes) -> bool:
    """True when a QV payload carries SPS + IDR markers (standalone-decodable)."""
    has_sps = any(m in payload for m in _SPS_MARKERS)
    has_idr = any(m in payload for m in _IDR_MARKERS)
    return has_sps and has_idr


def qv_frame_type(payload: bytes) -> int | None:
    """QV frame type (0=P, 1=IDR, 3=audio) from the 20-byte frame header."""
    if len(payload) > QV_HDR_LEN and payload[:3] == b"\x00\x00\x01":
        return payload[3] - 0xE0
    return None


class QuiiStream:
    """One async QUII live session (Setup -> Play -> read until keyframe)."""

    def __init__(
        self,
        host: str,
        *,
        username: str,
        password: str,
        stream_key: str,
        port: int = DEFAULT_MEDIA_PORT,
        idc: int = 1,
        ids: int = 1,
        timeout: float = 10.0,
        keepalive: float = 5.0,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password  # wire password (sha256 hex)
        self._key = stream_key
        self._idc = idc
        self._ids = ids
        self._timeout = timeout
        self._keepalive = keepalive
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._enc_mode = 2
        self._sha_mode = 1
        self._buf = bytearray()

    async def async_open(self) -> None:
        """Connect, run the Setup/Play handshake; raise QuiiConnectionError."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port), self._timeout
            )
        except (OSError, TimeoutError) as err:
            raise QuiiConnectionError(
                f"cannot reach media port {self._host}:{self._port}: {err}"
            ) from err

        try:
            assert self._writer is not None and self._reader is not None
            self._writer.write(build_setup())
            await self._writer.drain()
            reply = await asyncio.wait_for(
                self._reader.readexactly(MSG_HDR), self._timeout
            )
            if reply[0] != 0xA9 or reply[9] != 0:
                raise QuiiConnectionError(f"setup rejected: {reply[:12].hex()}")
            self._enc_mode = reply[0x0A]
            self._sha_mode = reply[0x0B]
            _LOGGER.debug(
                "QUII setup %s:%s enc_mode=%s sha_mode=%s",
                self._host, self._port, self._enc_mode, self._sha_mode,
            )
            self._writer.write(
                build_play(
                    self._username,
                    self._password,
                    self._key,
                    enc_mode=self._enc_mode,
                    sha_mode=self._sha_mode,
                    idc=self._idc,
                    ids=self._ids,
                )
            )
            await self._writer.drain()
        except (OSError, TimeoutError, asyncio.IncompleteReadError) as err:
            await self.async_close()
            raise QuiiConnectionError(f"handshake failed: {err}") from err

    async def async_read_keyframe(self, *, timeout: float | None = None) -> bytes:
        """Read until a standalone-decodable H.264 keyframe arrives.

        Sends encrypted keepalives while waiting. Raises QuiiNoMediaError on
        timeout, QuiiConnectionError on stream/parse failure.
        """
        if self._reader is None:
            raise QuiiConnectionError("stream not open")
        deadline = time.monotonic() + (timeout or self._timeout)
        next_keepalive = time.monotonic() + self._keepalive
        fallback = bytearray()  # video payloads since last candidate

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise QuiiNoMediaError(
                    f"no keyframe from {self._host} within {timeout or self._timeout}s"
                )
            if time.monotonic() >= next_keepalive:
                await self._async_send_keepalive()
                next_keepalive = time.monotonic() + self._keepalive
            try:
                chunk = await asyncio.wait_for(
                    self._reader.read(65536), min(remaining, self._keepalive)
                )
            except TimeoutError:
                continue
            except OSError as err:
                raise QuiiConnectionError(f"media read failed: {err}") from err
            if not chunk:
                raise QuiiConnectionError("media connection closed by device")
            self._buf.extend(chunk)

            keyframe = self._parse_buffer(fallback)
            if keyframe is not None:
                return keyframe

    def _parse_buffer(self, fallback: bytearray) -> bytes | None:
        """Consume complete messages from the buffer; return a keyframe if seen."""
        buf = self._buf
        pos = 0
        result: bytes | None = None
        while len(buf) - pos >= MSG_HDR:
            try:
                hdr = decrypt_header(bytes(buf[pos : pos + MSG_HDR]), self._key, self._enc_mode)
            except ValueError as err:
                raise QuiiConnectionError(f"header decrypt failed: {err}") from err
            cmd = hdr[0]
            if 0xA0 <= cmd <= 0xA3:
                total = MSG_HDR + media_body_len(hdr)
                if len(buf) - pos < total:
                    break
                payload = unpack_media_payload(
                    hdr, bytes(buf[pos + MSG_HDR : pos + total]), self._key, self._enc_mode
                )
                frame_type = qv_frame_type(payload)
                annexb = strip_to_annexb(payload)
                if annexb is not None and frame_type in (0, 1, None):
                    if result is None and is_keyframe(payload):
                        result = annexb
                    else:
                        fallback.extend(annexb)
            else:
                param_len = struct.unpack_from("<H", hdr, 9)[0]
                total = MSG_HDR + param_len
                if len(buf) - pos < total:
                    break
            pos += total
        if pos:
            del buf[:pos]
        if result is None and fallback and is_keyframe(bytes(fallback)):
            idx = max(bytes(fallback).rfind(m) for m in _SPS_MARKERS)
            result = bytes(fallback)[idx:] if idx >= 0 else bytes(fallback)
        return result

    async def _async_send_keepalive(self) -> None:
        if self._writer is None:
            return
        try:
            self._writer.write(
                build_keepalive(
                    self._key, enc_mode=self._enc_mode, sha_mode=self._sha_mode
                )
            )
            await self._writer.drain()
        except OSError as err:
            _LOGGER.debug("QUII keepalive failed: %s", err)

    async def async_close(self) -> None:
        """Close the session (best effort)."""
        writer, self._writer, self._reader = self._writer, None, None
        if writer is None:
            return
        try:
            writer.close()
            await writer.wait_closed()
        except OSError:  # noqa: BLE001 - device may drop first
            pass

    async def __aenter__(self) -> QuiiStream:
        await self.async_open()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.async_close()
