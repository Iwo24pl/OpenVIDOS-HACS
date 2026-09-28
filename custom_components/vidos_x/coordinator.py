"""Coordinator for Vidos X device polling."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .cgi import VidosCgiClient, VidosCgiConnectionError, VidosCgiError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .models import VidosStatus, ring_started

_LOGGER = logging.getLogger(__name__)

EVENT_DOORBELL_RUNG = "doorbell_rung"


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

    @callback
    def _handle_ring(self, status: VidosStatus) -> None:
        """Fire ``<domain>.doorbell_rung`` once per rising edge of the ring flag."""
        prev = self.data.fields if self.data else None
        if not ring_started(prev, status.fields):
            return
        self.last_rung = datetime.now()
        self.hass.bus.async_fire(
            f"{DOMAIN}.{EVENT_DOORBELL_RUNG}",
            {
                "device": self.config_entry.title,
                "entry_id": self.config_entry.entry_id,
                "when": self.last_rung.isoformat(timespec="seconds"),
            },
        )
        _LOGGER.info("Doorbell rang: %s", self.config_entry.title)

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
