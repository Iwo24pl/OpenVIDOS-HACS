"""The Vidos X integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .cgi import DEFAULT_USERNAME, VidosCgiClient
from .const import (
    ATTR_DEVICE_ID,
    ATTR_DOOR,
    ATTR_LOCK,
    ATTR_PASSWORD,
    CONF_CAMERAS,
    CONF_CAMERAS_ORIGINAL,
    CONF_CGI_PORT,
    CONF_DEFAULT_DOOR,
    CONF_DEFAULT_LOCK,
    CONF_DEVICE_IP,
    CONF_DEVICE_PASSWORD,
    CONF_DEVICE_UID,
    CONF_DEVICE_USERNAME,
    CONF_ENABLE_ALARM_SWITCH,
    CONF_ENABLE_CAMERA,
    CONF_ENABLE_LAN_RUNG,
    CONF_ENABLE_RECORD_RUNG,
    CONF_RECORD_POLL_INTERVAL,
    CONF_SCHEME,
    CONF_VERIFY_SSL,
    DEFAULT_CGI_PORT,
    DEFAULT_DOOR,
    DEFAULT_ENABLE_CAMERA,
    DEFAULT_ENABLE_LAN_RUNG,
    DEFAULT_ENABLE_RECORD_RUNG,
    DEFAULT_LOCK,
    DEFAULT_RECORD_POLL_INTERVAL,
    DOMAIN,
    MAX_RECORD_POLL_INTERVAL,
    MIN_RECORD_POLL_INTERVAL,
    SERVICE_OPEN_DOOR,
)
from .coordinator import VidosXCoordinator
from .lan import AzenoLanListener
from .records import RecordRingWatcher

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.SENSOR,
    Platform.SWITCH,
]

SERVICE_OPEN_DOOR_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_DOOR): cv.positive_int,
        vol.Optional(ATTR_LOCK): cv.positive_int,
        vol.Optional(ATTR_PASSWORD, default=""): cv.string,
    }
)


@dataclass
class VidosRuntimeData:
    """Runtime objects for one config entry."""

    client: VidosCgiClient
    coordinator: VidosXCoordinator
    platforms: list[Platform] = field(default_factory=list)
    lan_listener: AzenoLanListener | None = None
    ring_watcher: RecordRingWatcher | None = None
    ring_watcher_task: asyncio.Task[None] | None = None


type VidosConfigEntry = ConfigEntry[VidosRuntimeData]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the domain (registers shared services)."""

    async def _async_handle_open_door(call: ServiceCall) -> None:
        entry, runtime = _resolve_entry_and_runtime(hass, call)
        door = call.data.get(
            ATTR_DOOR, entry.options.get(CONF_DEFAULT_DOOR, DEFAULT_DOOR)
        )
        lock = call.data.get(
            ATTR_LOCK, entry.options.get(CONF_DEFAULT_LOCK, DEFAULT_LOCK)
        )
        await runtime.client.async_open_door(
            door=door,
            password=call.data.get(ATTR_PASSWORD, ""),
            lock=lock,
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_OPEN_DOOR,
        _async_handle_open_door,
        schema=SERVICE_OPEN_DOOR_SCHEMA,
    )
    return True


def _resolve_entry_and_runtime(
    hass: HomeAssistant, call: ServiceCall
) -> tuple[VidosConfigEntry, VidosRuntimeData]:
    """Map ``device_id`` service targets onto config entry + runtime data."""
    dev_reg = dr.async_get(hass)
    for device_id in call.data[ATTR_DEVICE_ID]:
        device = dev_reg.async_get(device_id)
        if device is None:
            continue
        for entry_id in device.config_entries:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is not None and entry.domain == DOMAIN and entry.runtime_data:
                return entry, entry.runtime_data
    raise HomeAssistantError("No matching Vidos X device found for this service call")


def _platforms_for_entry(entry: ConfigEntry) -> list[Platform]:
    """Platforms enabled for an entry given its options."""
    platforms = list(PLATFORMS)
    if not entry.options.get(CONF_ENABLE_ALARM_SWITCH, False):
        platforms.remove(Platform.SWITCH)
    if entry.options.get(CONF_ENABLE_CAMERA, DEFAULT_ENABLE_CAMERA):
        platforms.append(Platform.CAMERA)
    return platforms


async def _async_associate_cameras(hass: HomeAssistant, entry: VidosConfigEntry) -> None:
    """Attach picked camera entities to this device (association, not restream).

    The entity registry entry of each selected camera is re-pointed at the
    Vidos device so it shows up on the intercom's device page. The original
    ``device_id`` is remembered in options and restored when the camera is
    unselected.
    """
    entity_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    uid = (
        entry.data.get(CONF_DEVICE_UID) or entry.data.get(CONF_DEVICE_IP) or entry.entry_id
    )
    device = dev_reg.async_get_device(identifiers={(DOMAIN, uid)})
    if device is None:
        return

    picked = list(entry.options.get(CONF_CAMERAS) or [])
    original: dict[str, str | None] = dict(entry.options.get(CONF_CAMERAS_ORIGINAL) or {})
    changed = False

    for entity_id, orig_device in list(original.items()):
        if entity_id in picked:
            continue
        registry_entry = entity_reg.async_get(entity_id)
        if registry_entry is not None and registry_entry.device_id != orig_device:
            entity_reg.async_update_entity(entity_id, device_id=orig_device)
        original.pop(entity_id)
        changed = True

    for entity_id in picked:
        registry_entry = entity_reg.async_get(entity_id)
        if registry_entry is None:
            continue
        if entity_id not in original:
            original[entity_id] = registry_entry.device_id
            changed = True
        if registry_entry.device_id != device.id:
            entity_reg.async_update_entity(entity_id, device_id=device.id)

    if changed:
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_CAMERAS_ORIGINAL: original}
        )


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

    lan_listener: AzenoLanListener | None = None
    if entry.options.get(CONF_ENABLE_LAN_RUNG, DEFAULT_ENABLE_LAN_RUNG):
        lan_listener = AzenoLanListener(
            lambda _ip, kind: coordinator.note_rung(f"lan-{kind}")
        )
        if not await lan_listener.async_start():
            lan_listener = None

    ring_watcher: RecordRingWatcher | None = None
    ring_watcher_task: asyncio.Task[None] | None = None
    if entry.options.get(CONF_ENABLE_RECORD_RUNG, DEFAULT_ENABLE_RECORD_RUNG):
        interval = entry.options.get(
            CONF_RECORD_POLL_INTERVAL, DEFAULT_RECORD_POLL_INTERVAL
        )
        try:
            interval = min(max(float(interval), MIN_RECORD_POLL_INTERVAL), MAX_RECORD_POLL_INTERVAL)
        except (TypeError, ValueError):
            interval = float(DEFAULT_RECORD_POLL_INTERVAL)
        ring_watcher = RecordRingWatcher(
            client,
            interval=interval,
            on_ring=lambda channel, _starttime: coordinator.note_rung(
                "records", channel
            ),
        )
        ring_watcher_task = hass.async_create_task(
            ring_watcher.async_run(), name=f"{DOMAIN}-ring-log-{entry.entry_id}"
        )

    platforms = _platforms_for_entry(entry)
    entry.runtime_data = VidosRuntimeData(
        client=client,
        coordinator=coordinator,
        platforms=platforms,
        lan_listener=lan_listener,
        ring_watcher=ring_watcher,
        ring_watcher_task=ring_watcher_task,
    )

    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    await _async_associate_cameras(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VidosConfigEntry) -> bool:
    """Unload a config entry."""
    if entry.runtime_data:
        if entry.runtime_data.lan_listener:
            entry.runtime_data.lan_listener.async_stop()
        if entry.runtime_data.ring_watcher:
            entry.runtime_data.ring_watcher.stop()
        if entry.runtime_data.ring_watcher_task:
            entry.runtime_data.ring_watcher_task.cancel()
        entry.runtime_data.coordinator.cancel_rung_pulse()
    platforms = entry.runtime_data.platforms if entry.runtime_data else list(PLATFORMS)
    return await hass.config_entries.async_unload_platforms(entry, platforms)


async def _async_update_listener(hass: HomeAssistant, entry: VidosConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
