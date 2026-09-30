"""Sensors for Vidos X."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import VidosEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    async_add_entities(
        [
            VidosLockStateSensor(entry.runtime_data.coordinator, entry),
            VidosLastErrorSensor(entry.runtime_data.coordinator, entry),
        ]
    )


class VidosLockStateSensor(VidosEntity, SensorEntity):
    """Raw lock state as reported by ``get.lock.status`` / ``get.device.status``."""

    _attr_name = "Lock state"
    _attr_icon = "mdi:lock-smart"

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        if data is None:
            return None
        return data.lock_state or "unknown"


class VidosLastErrorSensor(VidosEntity, SensorEntity):
    """Last CGI error code returned by the device (0 = OK)."""

    _attr_name = "Last device error"
    _attr_icon = "mdi:alert-circle-outline"

    @property
    def native_value(self) -> int | None:
        data = self.coordinator.data
        if data is None:
            return None
        return data.error
