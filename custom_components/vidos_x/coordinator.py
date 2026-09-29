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

from .cgi import VidosCgiClient, VidosCgiConnectionError, VidosCgiError
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    DOORBELL_ON_SECONDS,
    EVENT_DOORBELL_RUNG,
)
from .models import VidosStatus, ring_started

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
        self._rung_off_cancel: Callable[[], None] | None = None

    @callback
    def note_rung(self, source: str = "cgi") -> None:
        """Fire ``<domain>.doorbell_rung`` and pulse the doorbell sensor.

        Sources: ``cgi`` (status flag), ``lan-scan`` / ``lan-reply`` (Azeno
        broadcast chain - the only LAN signal verified on hardware).
        """
        self.last_rung = datetime.now()
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
            },
        )
        _LOGGER.info("Doorbell rang (%s): %s", source, self.config_entry.title)
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
