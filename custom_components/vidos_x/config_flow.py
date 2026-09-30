"""Config flow for Vidos X (manual LAN setup)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from . import cgi as cgi_mod
from .const import (
    CONF_CAMERAS,
    CONF_CGI_PORT,
    CONF_CHANNEL_1_NAME,
    CONF_CHANNEL_2_NAME,
    CONF_DEFAULT_DOOR,
    CONF_DEFAULT_LOCK,
    CONF_DEVICE_IP,
    CONF_DEVICE_PASSWORD,
    CONF_DEVICE_UID,
    CONF_DEVICE_USERNAME,
    CONF_DOOR_PASSWORD,
    CONF_ENABLE_ALARM_SWITCH,
    CONF_ENABLE_CAMERA,
    CONF_ENABLE_LAN_RUNG,
    CONF_ENABLE_RECORD_RUNG,
    CONF_MODEL,
    CONF_RECORD_POLL_INTERVAL,
    CONF_SCHEME,
    CONF_SOURCE,
    CONF_VERIFY_SSL,
    DEFAULT_CGI_PORT,
    DEFAULT_CHANNEL_1_NAME,
    DEFAULT_CHANNEL_2_NAME,
    DEFAULT_DOOR,
    DEFAULT_ENABLE_CAMERA,
    DEFAULT_ENABLE_LAN_RUNG,
    DEFAULT_ENABLE_RECORD_RUNG,
    DEFAULT_LOCK,
    DEFAULT_RECORD_POLL_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_RECORD_POLL_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_RECORD_POLL_INTERVAL,
    MIN_SCAN_INTERVAL,
    SOURCE_MANUAL,
)

_LOGGER = logging.getLogger(__name__)


class VidosXConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manual setup only (cloud discovery lives in ``cloud.py``, UI removed)."""
        return await self.async_step_manual()

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(
                self.hass, verify_ssl=user_input.get(CONF_VERIFY_SSL, False)
            )
            client = cgi_mod.VidosCgiClient(
                user_input[CONF_DEVICE_IP],
                int(user_input[CONF_CGI_PORT]),
                username=user_input.get(CONF_DEVICE_USERNAME, cgi_mod.DEFAULT_USERNAME),
                password=user_input.get(CONF_DEVICE_PASSWORD, ""),
                session=session,
                scheme=user_input.get(CONF_SCHEME, "https"),
                verify_ssl=user_input.get(CONF_VERIFY_SSL, False),
            )
            try:
                await client.async_get_status()
            except cgi_mod.VidosCgiConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - device answered, possibly with an error
                _LOGGER.warning("device answered with an error during probe", exc_info=True)
            if not errors:
                return await self._async_create_from_manual(user_input)

        defaults = {
            CONF_DEVICE_IP: "",
            CONF_CGI_PORT: DEFAULT_CGI_PORT,
            CONF_DEVICE_USERNAME: cgi_mod.DEFAULT_USERNAME,
            CONF_DEVICE_PASSWORD: "",
            CONF_VERIFY_SSL: False,
        }
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_IP, default=defaults[CONF_DEVICE_IP]): cv.string,
                    vol.Required(CONF_CGI_PORT, default=defaults[CONF_CGI_PORT]): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=65535)
                    ),
                    vol.Optional(
                        CONF_DEVICE_USERNAME, default=defaults[CONF_DEVICE_USERNAME]
                    ): cv.string,
                    vol.Optional(CONF_DEVICE_PASSWORD, default=""): cv.string,
                    vol.Optional(CONF_VERIFY_SSL, default=False): bool,
                    vol.Optional(CONF_SCHEME, default="https"): vol.In(
                        {"https": "https", "http": "http"}
                    ),
                }
            ),
            errors=errors,
        )

    async def _async_create_from_manual(self, user_input: dict[str, Any]) -> FlowResult:
        ip = user_input[CONF_DEVICE_IP]
        await self.async_set_unique_id(ip)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"Vidos {ip}",
            data={
                CONF_SOURCE: SOURCE_MANUAL,
                CONF_DEVICE_UID: ip,
                CONF_DEVICE_IP: ip,
                CONF_CGI_PORT: int(user_input[CONF_CGI_PORT]),
                CONF_DEVICE_USERNAME: user_input.get(
                    CONF_DEVICE_USERNAME, cgi_mod.DEFAULT_USERNAME
                ),
                CONF_DEVICE_PASSWORD: user_input.get(CONF_DEVICE_PASSWORD, ""),
                CONF_VERIFY_SSL: bool(user_input.get(CONF_VERIFY_SSL, False)),
                CONF_MODEL: "",
                CONF_SCHEME: user_input.get(CONF_SCHEME, "https"),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> VidosXOptionsFlow:
        return VidosXOptionsFlow()


class VidosXOptionsFlow(OptionsFlow):
    """Poll interval and feature options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            # Merge so internal keys (e.g. cameras_original) survive options saves.
            return self.async_create_entry(
                title="", data={**self.config_entry.options, **user_input}
            )

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                    vol.Required(
                        CONF_VERIFY_SSL,
                        default=options.get(
                            CONF_VERIFY_SSL,
                            self.config_entry.data.get(CONF_VERIFY_SSL, False),
                        ),
                    ): bool,
                    vol.Required(
                        CONF_ENABLE_ALARM_SWITCH,
                        default=options.get(CONF_ENABLE_ALARM_SWITCH, False),
                    ): bool,
                    vol.Required(
                        CONF_ENABLE_LAN_RUNG,
                        default=options.get(
                            CONF_ENABLE_LAN_RUNG, DEFAULT_ENABLE_LAN_RUNG
                        ),
                    ): bool,
                    vol.Required(
                        CONF_ENABLE_CAMERA,
                        default=options.get(
                            CONF_ENABLE_CAMERA, DEFAULT_ENABLE_CAMERA
                        ),
                    ): bool,
                    vol.Required(
                        CONF_ENABLE_RECORD_RUNG,
                        default=options.get(
                            CONF_ENABLE_RECORD_RUNG, DEFAULT_ENABLE_RECORD_RUNG
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_RECORD_POLL_INTERVAL,
                        default=options.get(
                            CONF_RECORD_POLL_INTERVAL, DEFAULT_RECORD_POLL_INTERVAL
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_RECORD_POLL_INTERVAL,
                            max=MAX_RECORD_POLL_INTERVAL,
                        ),
                    ),
                    vol.Optional(
                        CONF_CHANNEL_1_NAME,
                        default=options.get(
                            CONF_CHANNEL_1_NAME, DEFAULT_CHANNEL_1_NAME
                        ),
                    ): cv.string,
                    vol.Optional(
                        CONF_CHANNEL_2_NAME,
                        default=options.get(
                            CONF_CHANNEL_2_NAME, DEFAULT_CHANNEL_2_NAME
                        ),
                    ): cv.string,
                    vol.Optional(
                        CONF_DOOR_PASSWORD,
                        default=options.get(
                            CONF_DOOR_PASSWORD,
                            self.config_entry.data.get(CONF_DEVICE_PASSWORD, ""),
                        ),
                    ): cv.string,
                    vol.Optional(
                        CONF_DEFAULT_DOOR,
                        default=options.get(CONF_DEFAULT_DOOR, DEFAULT_DOOR),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=16)),
                    vol.Optional(
                        CONF_DEFAULT_LOCK,
                        default=options.get(CONF_DEFAULT_LOCK, DEFAULT_LOCK),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=16)),
                    vol.Optional(
                        CONF_CAMERAS,
                        default=options.get(CONF_CAMERAS, []),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="camera", multiple=True
                        )
                    ),
                }
            ),
        )
