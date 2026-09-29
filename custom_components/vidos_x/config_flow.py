"""Config flow for Vidos X (cloud discovery or manual LAN setup)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from . import cgi as cgi_mod
from . import cloud as cloud_mod
from .const import (
    CONF_CGI_PORT,
    CONF_DEVICE_IP,
    CONF_DEVICE_PASSWORD,
    CONF_DEVICE_UID,
    CONF_DEVICE_USERNAME,
    CONF_DOOR_PASSWORD,
    CONF_ENABLE_ALARM_SWITCH,
    CONF_ENABLE_LAN_RUNG,
    CONF_MODEL,
    CONF_RTSP_URL,
    CONF_SCHEME,
    CONF_SOURCE,
    CONF_VERIFY_SSL,
    DEFAULT_CGI_PORT,
    DEFAULT_ENABLE_LAN_RUNG,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    SOURCE_CLOUD,
    SOURCE_MANUAL,
)

_LOGGER = logging.getLogger(__name__)

MODE_CLOUD = "cloud"
MODE_MANUAL = "manual"


class VidosXConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._mode: str = MODE_MANUAL
        self._cloud_devices: list[cloud_mod.VidosDevice] = []
        self._client_id: str = cloud_mod.make_client_id()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._mode = user_input["mode"]
            if self._mode == MODE_CLOUD:
                return await self.async_step_cloud()
            return await self.async_step_manual()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("mode", default=MODE_MANUAL): vol.In(
                        {
                            MODE_MANUAL: "Manual (device IP on your LAN)",
                            MODE_CLOUD: "Cloud account (discover devices)",
                        }
                    )
                }
            ),
        )

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            try:
                token = await cloud_mod.async_login(
                    session,
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                    client_id=self._client_id,
                )
                self._cloud_devices = await cloud_mod.async_get_device_list(
                    session, token, client_id=self._client_id
                )
            except cloud_mod.VidosCloudAuthError:
                errors["base"] = "invalid_auth"
            except cloud_mod.VidosCloudConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - surface any protocol surprise as unknown
                _LOGGER.exception("unexpected cloud error")
                errors["base"] = "unknown"
            else:
                if not self._cloud_devices:
                    errors["base"] = "no_devices"
                elif len(self._cloud_devices) == 1:
                    return await self._async_create_from_device(self._cloud_devices[0])
                else:
                    return await self.async_step_select_device()

        return self.async_show_form(
            step_id="cloud",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): cv.string,
                    vol.Required(CONF_PASSWORD): cv.string,
                }
            ),
            errors=errors,
        )

    async def async_step_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            uid = user_input[CONF_DEVICE_UID]
            device = next(d for d in self._cloud_devices if d.uid == uid)
            return await self._async_create_from_device(device)

        options = {d.uid: f"{d.name} ({d.ip})" for d in self._cloud_devices}
        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema({vol.Required(CONF_DEVICE_UID): vol.In(options)}),
        )

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

    async def _async_create_from_device(self, device: cloud_mod.VidosDevice) -> FlowResult:
        await self.async_set_unique_id(device.uid)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=device.name,
            data={
                CONF_SOURCE: SOURCE_CLOUD,
                CONF_DEVICE_UID: device.uid,
                CONF_DEVICE_IP: device.ip,
                CONF_CGI_PORT: device.cgi_port,
                CONF_DEVICE_USERNAME: device.username,
                CONF_DEVICE_PASSWORD: device.password,
                CONF_MODEL: device.model or "",
                CONF_SCHEME: "https",
            },
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
            return self.async_create_entry(title="", data=user_input)

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
                    vol.Optional(
                        CONF_DOOR_PASSWORD,
                        default=options.get(
                            CONF_DOOR_PASSWORD,
                            self.config_entry.data.get(CONF_DEVICE_PASSWORD, ""),
                        ),
                    ): cv.string,
                    vol.Optional(
                        CONF_RTSP_URL,
                        default=options.get(CONF_RTSP_URL, ""),
                    ): cv.string,
                }
            ),
        )
