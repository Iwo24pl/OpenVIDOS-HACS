"""Binary sensors for Vidos X."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOORBELL_ON_SECONDS
from .entity import VidosEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    async_add_entities(
        [
            VidosOnlineBinarySensor(entry.runtime_data.coordinator, entry),
            VidosDoorbellBinarySensor(entry.runtime_data.coordinator, entry),
        ]
    )


class VidosOnlineBinarySensor(VidosEntity, BinarySensorEntity):
    """Device is reachable and answering polls."""

    _attr_name = "Status"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success


class VidosDoorbellBinarySensor(VidosEntity, BinarySensorEntity):
    """Doorbell ON while ringing (CGI flag) or within the LAN-ring pulse."""

    _attr_name = "Doorbell"
    # No device class: HA has no DOORBELL class, and OCCURRENCE was removed in
    # 2026.x - use plain state + icon so every HA version loads.
    _attr_device_class = None
    _attr_icon = "mdi:doorbell"

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data
        if data and data.ringing:
            return True
        last_rung = self.coordinator.last_rung
        return bool(
            last_rung
            and (datetime.now() - last_rung).total_seconds() < DOORBELL_ON_SECONDS
        )

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        last_rung = self.coordinator.last_rung
        channel = self.coordinator.last_rung_channel
        return {
            "last_rung": last_rung.isoformat(timespec="seconds") if last_rung else None,
            "channel": channel,
            "channel_name": self.coordinator.channel_name(channel),
        }
