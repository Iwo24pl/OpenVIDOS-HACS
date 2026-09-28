"""Binary sensors for Vidos X."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import VidosEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    async_add_entities(
        [
            VidosOnlineBinarySensor(entry),
            VidosDoorbellBinarySensor(entry),
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
    """Doorbell / ring event (device field ``devicestatus.calling``)."""

    _attr_name = "Doorbell"
    _attr_device_class = BinarySensorDeviceClass.DOORBELL

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data
        return bool(data and data.ringing)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        last_rung = self.coordinator.last_rung
        return {"last_rung": last_rung.isoformat(timespec="seconds") if last_rung else None}
