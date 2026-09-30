"""Base entity for Vidos X."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_CGI_PORT,
    CONF_DEVICE_IP,
    CONF_DEVICE_UID,
    CONF_MODEL,
    CONF_SCHEME,
    DOMAIN,
)
from .coordinator import VidosXCoordinator


class VidosEntity(CoordinatorEntity[VidosXCoordinator]):
    """Common base for all Vidos X entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: VidosXCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        uid = entry.data.get(CONF_DEVICE_UID) or entry.data.get(CONF_DEVICE_IP) or entry.entry_id
        self._attr_unique_id = f"{uid}-{self.__class__.__name__.lower()}"
        scheme = entry.data.get(CONF_SCHEME, "https")
        port = entry.data.get(CONF_CGI_PORT, 443)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid)},
            manufacturer="Vidos",
            name=entry.title,
            model=entry.data.get(CONF_MODEL) or "Vidos X intercom",
            configuration_url=f"{scheme}://{entry.data.get(CONF_DEVICE_IP)}:{port}/",
        )
