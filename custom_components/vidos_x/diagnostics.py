"""Diagnostics support for Vidos X."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DEVICE_PASSWORD,
    CONF_DEVICE_UID,
    CONF_DOOR_PASSWORD,
    DOMAIN,
)

REDACT_KEYS = {
    CONF_DEVICE_PASSWORD,
    CONF_DOOR_PASSWORD,
    "password",
    "access_token",
    "refresh_token",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry (secrets redacted)."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator if runtime else None
    data = coordinator.data if coordinator else None
    return {
        "entry": async_redact_data(dict(entry.data), REDACT_KEYS),
        "options": async_redact_data(dict(entry.options), REDACT_KEYS),
        "coordinator": {
            "last_update_success": coordinator.last_update_success
            if coordinator
            else None,
            "update_interval": str(coordinator.update_interval) if coordinator else None,
            "error_code": data.error if data else None,
            "fields": async_redact_data(dict(data.fields), REDACT_KEYS) if data else {},
        },
        "domain": DOMAIN,
        "device_uid": entry.data.get(CONF_DEVICE_UID),
    }
