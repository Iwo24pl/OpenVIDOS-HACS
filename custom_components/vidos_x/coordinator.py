"""Coordinator for Vidos X device polling."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_CHANNEL_1_NAME,
    CONF_CHANNEL_2_NAME,
    DEFAULT_CHANNEL_1_NAME,
    DEFAULT_CHANNEL_2_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    DOORBELL_ON_SECONDS,
    DOORBELL_RUNG_DEDUP_SECONDS,
    EVENT_DOORBELL_RUNG,
)
from .proto.device_api import VidosCgiClient
from .proto.envelope import VidosCgiConnectionError, VidosCgiError
from .proto.models import VidosStatus, ring_started, rung_is_duplicate

_LOGGER = logging.getLogger(__name__)


class VidosXCoordinator(DataUpdateCoordinator[VidosStatus]):
    """Polls a single Vidos device over its local CGI endpoint."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        entry: ConfigEntry,
        client: VidosCgiClient,
    ) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{entry.title}",
            update_interval=timedelta(seconds=interval),
        )
        self.config_entry = entry
        self.client = client
        self.last_rung: datetime | None = None
        self.last_rung_channel: int | None = None
        self._rung_off_cancel: Callable[[], None] | None = None

    def channel_name(self, channel: int | None) -> str | None:
        """Configured display name for a ring-log channel."""
        if channel == 1:
            return self.config_entry.options.get(
                CONF_CHANNEL_1_NAME, DEFAULT_CHANNEL_1_NAME
            )
        if channel == 2:
            return self.config_entry.options.get(
                CONF_CHANNEL_2_NAME, DEFAULT_CHANNEL_2_NAME
            )
        return None

    @callback
    def note_rung(self, source: str = "cgi", channel: int | None = None) -> None:
        """Fire ``<domain>.doorbell_rung`` and pulse the doorbell sensor.

        Sources: ``records`` (device ring log - carries the channel),
        ``cgi`` (status flag), ``lan-scan`` / ``lan-reply`` (Azeno broadcast
        chain). One press observed by several sources inside the dedup
        window collapses into a single event.
        """
        now = datetime.now()
        if rung_is_duplicate(self.last_rung, now, DOORBELL_RUNG_DEDUP_SECONDS):
            _LOGGER.debug(
                "suppressed duplicate ring (%s, channel=%s)", source, channel
            )
            return
        self.last_rung = now
        self.last_rung_channel = channel
        if self._rung_off_cancel is not None:
            self._rung_off_cancel()
        self._rung_off_cancel = async_call_later(
            self.hass, DOORBELL_ON_SECONDS, self._rung_expired
        )
        self.hass.bus.async_fire(
            f"{DOMAIN}.{EVENT_DOORBELL_RUNG}",
            {
                "device": self.config_entry.title,
                "entry_id": self.config_entry.entry_id,
                "when": self.last_rung.isoformat(timespec="seconds"),
                "source": source,
                "channel": channel,
                "channel_name": self.channel_name(channel),
            },
        )
        _LOGGER.info(
            "Doorbell rang (%s, channel=%s): %s",
            source,
            channel,
            self.config_entry.title,
        )
        self.async_update_listeners()

    @callback
    def _rung_expired(self, _now: datetime) -> None:
        """Turn the doorbell binary sensor back OFF."""
        self._rung_off_cancel = None
        self.async_update_listeners()

    @callback
    def cancel_rung_pulse(self) -> None:
        """Cancel a pending sensor-off timer (config entry unload)."""
        if self._rung_off_cancel is not None:
            self._rung_off_cancel()
            self._rung_off_cancel = None

    @callback
    def _handle_ring(self, status: VidosStatus) -> None:
        """Fire once per rising edge of the CGI ring flag."""
        prev = self.data.fields if self.data else None
        if ring_started(prev, status.fields):
            self.note_rung("cgi")

    async def _async_update_data(self) -> VidosStatus:
        try:
            response = await self.client.async_get_status()
        except VidosCgiConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except VidosCgiError as err:
            raise UpdateFailed(str(err)) from err
        status = VidosStatus(
            fields=response.fields, error=response.error, content=response.content
        )
        self._handle_ring(status)
        return status
