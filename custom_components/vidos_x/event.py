"""Event platform for Vidos X (stateless doorbell presses)."""

from __future__ import annotations

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, EVENT_DOORBELL_RUNG
from .entity import VidosEntity

EVENT_TYPE_RING = "ring"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the doorbell event entity."""
    async_add_entities([VidosDoorbellEvent(entry.runtime_data.coordinator, entry)])


class VidosDoorbellEvent(VidosEntity, EventEntity):
    """Fires a ``ring`` event whenever the coordinator reports a new ring.

    Listens to the ``vidos_x.doorbell_rung`` event fired by the coordinator,
    so this entity stays in lock-step with the binary sensor.
    """

    _attr_name = "Doorbell"
    _attr_device_class = EventDeviceClass.DOORBELL
    _attr_event_types = [EVENT_TYPE_RING]

    async def async_added_to_hass(self) -> None:
        """Subscribe to the integration's ring event."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.hass.bus.async_listen(
                f"{DOMAIN}.{EVENT_DOORBELL_RUNG}", self._handle_rung_event
            )
        )

    @callback
    def _handle_rung_event(self, event: Event) -> None:
        """Trigger the HA event entity for this device's ring."""
        if event.data.get("entry_id") != self._entry.entry_id:
            return
        self._trigger_event(EVENT_TYPE_RING, {"when": event.data.get("when")})
        self.async_write_ha_state()
