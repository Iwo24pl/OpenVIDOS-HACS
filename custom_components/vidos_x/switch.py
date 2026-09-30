"""Switch platform for Vidos X (alarm arm/disarm - experimental)."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import VidosEntity
from .proto.envelope import VidosCgiError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the alarm switch (only when enabled in options)."""
    async_add_entities([VidosAlarmDisarmSwitch(entry.runtime_data.coordinator, entry)])


class VidosAlarmDisarmSwitch(VidosEntity, SwitchEntity):
    """Alarm 'disarmed' state via ``g.alm.disarm`` / ``s.alm.disarm``.

    Command semantics are **unverified** (Phase 0) - enable with care.
    """

    _attr_name = "Alarm disarmed"
    _attr_icon = "mdi:shield-off"

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if data is None:
            return None
        return data.disarmed

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_set_disarm(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_set_disarm(False)

    async def _async_set_disarm(self, disarmed: bool) -> None:
        try:
            await self.coordinator.client.async_set_alarm_disarm(disarmed)
        except VidosCgiError as err:
            raise HomeAssistantError(f"Changing alarm state failed: {err}") from err
        await self.coordinator.async_request_refresh()
