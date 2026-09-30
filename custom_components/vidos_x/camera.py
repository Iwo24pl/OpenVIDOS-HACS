"""Snapshot camera for Vidos X - one keyframe per image via the QUII protocol.

On demand: fetch streamkey (CGI) -> short TCP 34567 session -> first H.264
keyframe -> local ffmpeg -> JPEG. No continuous traffic; see
``docs/VIDOS_X_PROTOCOL.md`` ┬ž4.5 for the design rationale.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time

from homeassistant.components.camera import Camera
from homeassistant.components.ffmpeg import async_get_image
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DEVICE_IP,
    CONF_DEVICE_USERNAME,
    SNAPSHOT_COOLDOWN_SECONDS,
    SNAPSHOT_TIMEOUT_SECONDS,
    SNAPSHOT_TTL_SECONDS,
    STREAM_KEY_CACHE_SECONDS,
)
from .entity import VidosEntity
from .proto.envelope import VidosCgiError
from .proto.live_player import (
    DEFAULT_MEDIA_PORT,
    QuiiConnectionError,
    QuiiError,
    QuiiStream,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the snapshot camera for a config entry."""
    async_add_entities([VidosXCamera(entry)])


class VidosXCamera(VidosEntity, Camera):
    """Snapshot-only camera backed by the device's QUII media port."""

    _attr_name = "Camera"
    _attr_icon = "mdi:cctv"

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry.runtime_data.coordinator, entry)
        Camera.__init__(self)
        self._jpeg: bytes | None = None
        self._jpeg_at: float = 0.0
        self._cooldown_until: float = 0.0
        self._stream_key: str | None = None
        self._stream_key_at: float = 0.0
        self._lock = asyncio.Lock()

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a JPEG snapshot (cached, with failure cooldown)."""
        async with self._lock:
            now = time.monotonic()
            if self._jpeg is not None and now - self._jpeg_at < SNAPSHOT_TTL_SECONDS:
                return self._jpeg
            if now < self._cooldown_until:
                return self._jpeg
            try:
                jpeg = await self._async_snapshot()
            except (QuiiError, VidosCgiError) as err:
                _LOGGER.warning("Vidos X snapshot failed: %s", err)
                self._cooldown_until = time.monotonic() + SNAPSHOT_COOLDOWN_SECONDS
                return self._jpeg
            except Exception:  # noqa: BLE001 - a camera must never raise 500s
                _LOGGER.exception("Vidos X snapshot failed unexpectedly")
                self._cooldown_until = time.monotonic() + SNAPSHOT_COOLDOWN_SECONDS
                return self._jpeg
            if jpeg is None:
                self._cooldown_until = time.monotonic() + SNAPSHOT_COOLDOWN_SECONDS
                return self._jpeg
            self._jpeg = jpeg
            self._jpeg_at = time.monotonic()
            return jpeg

    async def _async_snapshot(self) -> bytes | None:
        """Grab one keyframe and decode it to JPEG with the HA ffmpeg binary."""
        runtime = self._entry.runtime_data
        host = self._entry.data[CONF_DEVICE_IP]
        key = await self._async_get_stream_key()

        stream = QuiiStream(
            host,
            username=self._entry.data.get(CONF_DEVICE_USERNAME, "adminapp2"),
            password=runtime.client.header_password,
            stream_key=key,
            port=DEFAULT_MEDIA_PORT,
        )
        try:
            await stream.async_open()
            annexb = await stream.async_read_keyframe(
                timeout=SNAPSHOT_TIMEOUT_SECONDS
            )
        finally:
            await stream.async_close()
        return await self._async_decode(annexb)

    async def _async_get_stream_key(self) -> str:
        """Fetch (and briefly cache) the ``get.device.streamkey`` token."""
        now = time.monotonic()
        if (
            self._stream_key is not None
            and now - self._stream_key_at < STREAM_KEY_CACHE_SECONDS
        ):
            return self._stream_key
        runtime = self._entry.runtime_data
        resp = await runtime.client.async_command(
            "get.device.streamkey", require_ok=False
        )
        key = str(resp.fields.get("key") or "")
        if not key:
            raise QuiiConnectionError("device returned no streamkey")
        self._stream_key = key
        self._stream_key_at = now
        return key

    async def _async_decode(self, annexb: bytes) -> bytes | None:
        """Decode raw annex-B H.264 to JPEG using Home Assistant's ffmpeg.

        Uses a plain ``tempfile`` file: Config's temp-dir attribute was
        removed from current HA cores and raised AttributeError -> HTTP 500.
        """
        uid = (self._attr_unique_id or "vidos_x").replace("-", "_")
        fd, path = tempfile.mkstemp(prefix=f"vidos_x_{uid}_", suffix=".h264")
        os.close(fd)
        try:
            with open(path, "wb") as handle:
                handle.write(annexb)
            image = await async_get_image(self.hass, path)
        except (KeyError, ValueError, OSError) as err:
            _LOGGER.warning(
                "Vidos X cannot decode snapshot (ffmpeg not available): %s", err
            )
            return None
        finally:
            try:
                os.remove(path)
            except OSError:  # noqa: BLE001 - temp file may already be gone
                pass
        if not image:
            _LOGGER.warning("Vidos X ffmpeg produced no image")
            self._stream_key = None  # key may be stale; refetch next attempt
            return None
        return image
