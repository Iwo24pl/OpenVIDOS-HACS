"""Button platform for Vidos X (momentary door open)."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DEFAULT_DOOR,
    CONF_DEFAULT_LOCK,
    CONF_DEVICE_PASSWORD,
    CONF_DOOR_PASSWORD,
    DEFAULT_DOOR,
    DEFAULT_LOCK,
)
from .entity import VidosEntity
from .proto.envelope import VidosCgiError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the open-door button."""
    async_add_entities([VidosOpenDoorButton(entry.runtime_data.coordinator, entry)])


class VidosOpenDoorButton(VidosEntity, ButtonEntity):
    """Press to open the door (``set.device.opendoor``)."""

    _attr_name = "Open door"
    _attr_icon = "mdi:door-open"

    async def async_press(self) -> None:
        password = self._entry.options.get(
            CONF_DOOR_PASSWORD, self._entry.data.get(CONF_DEVICE_PASSWORD, "")
        )
        door = self._entry.options.get(CONF_DEFAULT_DOOR, DEFAULT_DOOR)
        lock = self._entry.options.get(CONF_DEFAULT_LOCK, DEFAULT_LOCK)
        try:
            await self.coordinator.client.async_open_door(
                door=door, lock=lock, password=password
            )
        except VidosCgiError as err:
            raise HomeAssistantError(f"Opening the door failed: {err}") from err
        await self.coordinator.async_request_refresh()
