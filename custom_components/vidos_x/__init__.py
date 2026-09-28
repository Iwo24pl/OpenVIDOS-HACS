"""The Vidos X integration."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .cgi import DEFAULT_USERNAME, VidosCgiClient
from .const import (
    ATTR_DEVICE_ID,
    ATTR_DOOR,
    ATTR_PASSWORD,
    CONF_CGI_PORT,
    CONF_DEVICE_IP,
    CONF_DEVICE_PASSWORD,
    CONF_DEVICE_USERNAME,
    CONF_ENABLE_ALARM_SWITCH,
    CONF_RTSP_URL,
    CONF_SCHEME,
    CONF_VERIFY_SSL,
    DEFAULT_CGI_PORT,
    DOMAIN,
    SERVICE_OPEN_DOOR,
)
from .coordinator import VidosXCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.SENSOR,
    Platform.SWITCH,
]

SERVICE_OPEN_DOOR_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_DOOR, default=0): cv.positive_int,
        vol.Optional(ATTR_PASSWORD, default=""): cv.string,
    }
)


@dataclass
class VidosRuntimeData:
    """Runtime objects for one config entry."""

    client: VidosCgiClient
    coordinator: VidosXCoordinator
    platforms: list[Platform] = field(default_factory=list)


type VidosConfigEntry = ConfigEntry[VidosRuntimeData]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the domain (registers shared services)."""

    async def _async_handle_open_door(call: ServiceCall) -> None:
        runtime = _resolve_runtime(hass, call)
        await runtime.client.async_open_door(
            door=call.data.get(ATTR_DOOR, 0),
            password=call.data.get(ATTR_PASSWORD, ""),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_OPEN_DOOR,
        _async_handle_open_door,
        schema=SERVICE_OPEN_DOOR_SCHEMA,
    )
    return True


def _resolve_runtime(hass: HomeAssistant, call: ServiceCall) -> VidosRuntimeData:
    """Map ``device_id`` service targets onto integration runtime data."""
    dev_reg = dr.async_get(hass)
    for device_id in call.data[ATTR_DEVICE_ID]:
        device = dev_reg.async_get(device_id)
        if device is None:
            continue
        for entry_id in device.config_entries:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is not None and entry.domain == DOMAIN and entry.runtime_data:
                return entry.runtime_data
    raise HomeAssistantError("No matching Vidos X device found for this service call")


def _platforms_for_entry(entry: ConfigEntry) -> list[Platform]:
    """Platforms enabled for an entry given its options."""
    platforms = list(PLATFORMS)
    if not entry.options.get(CONF_ENABLE_ALARM_SWITCH, False):
        platforms.remove(Platform.SWITCH)
    if not entry.options.get(CONF_RTSP_URL):
        platforms.remove(Platform.CAMERA)
    return platforms


async def async_setup_entry(hass: HomeAssistant, entry: VidosConfigEntry) -> bool:
    """Set up a Vidos X config entry."""
    verify_ssl = entry.options.get(
        CONF_VERIFY_SSL, entry.data.get(CONF_VERIFY_SSL, False)
    )
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    client = VidosCgiClient(
        entry.data[CONF_DEVICE_IP],
        int(entry.data.get(CONF_CGI_PORT, DEFAULT_CGI_PORT)),
        username=entry.data.get(CONF_DEVICE_USERNAME, DEFAULT_USERNAME),
        password=entry.data.get(CONF_DEVICE_PASSWORD, ""),
        session=session,
        scheme=entry.data.get(CONF_SCHEME, "https"),
        verify_ssl=verify_ssl,
    )
    coordinator = VidosXCoordinator(hass, entry=entry, client=client)
    await coordinator.async_config_entry_first_refresh()

    platforms = _platforms_for_entry(entry)
    entry.runtime_data = VidosRuntimeData(
        client=client, coordinator=coordinator, platforms=platforms
    )

    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VidosConfigEntry) -> bool:
    """Unload a config entry."""
    platforms = entry.runtime_data.platforms if entry.runtime_data else list(PLATFORMS)
    return await hass.config_entries.async_unload_platforms(entry, platforms)


async def _async_update_listener(hass: HomeAssistant, entry: VidosConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
