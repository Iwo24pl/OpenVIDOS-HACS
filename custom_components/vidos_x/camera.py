"""Camera platform for Vidos X (RTSP stream - URL must be configured).

Live video in the official app goes through the proprietary P2P stack. If the
device exposes RTSP/ONVIF (``get.onvif.pwd`` CGI suggests it does), set the
stream URL in the integration options and this entity exposes it to Home
Assistant's stream integration.
"""

from __future__ import annotations

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_RTSP_URL
from .entity import VidosEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the camera when an RTSP URL is configured."""
    if entry.options.get(CONF_RTSP_URL):
        async_add_entities([VidosStreamCamera(entry.runtime_data.coordinator, entry)])


class VidosStreamCamera(VidosEntity, Camera):
    """RTSP stream from the device."""

    _attr_name = "Camera"
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        Camera.__init__(self)
        VidosEntity.__init__(self, coordinator, entry)

    @property
    def stream_source(self) -> str | None:
        return self._entry.options.get(CONF_RTSP_URL) or None
