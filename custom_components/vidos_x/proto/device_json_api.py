"""Layer-B JSON settings API (HttpDeviceJsonManager / DeviceJsonRequestHelp).

Provides the milestone-1 settings commands as JSON-serializable bodies
(APP_PARITY §4, §9 D7). Route ids (`$27`, `$26`, …) are recorded for the live
capture in Phase 4 (§11.7) — the same commands also work over the XML envelope
(legacy-verified for `get.lock.status`), so `device_api` remains the default
transport for reads.
"""

from __future__ import annotations

from dataclasses import asdict
import json

from .beans import (
    GetDeviceAutoUnlockContentReq,
    GetDeviceCallTimeContentReq,
    SetDeviceAutoUnlockContentReq,
    SetDeviceCallTimeContentReq,
)

# --- command strings (dex, HttpDeviceJsonManager methods) ---
COMMAND_GET_AUTO_UNLOCK = "get.auto.unlock"
COMMAND_SET_AUTO_UNLOCK = "set.auto.unlock"
COMMAND_GET_CALL_TIME = "get.call.time"
COMMAND_SET_CALL_TIME = "set.call.time"
COMMAND_GET_LOCK_STATUS = "get.lock.status"
COMMAND_SET_LOCK_STATUS = "set.lock.status"
COMMAND_GET_CUSTOM_RING = "get.custom.ring"
COMMAND_SET_CUSTOM_RING = "set.custom.ring"
COMMAND_SET_HOLD_UNLOCK = "set.hold.unlock"
COMMAND_SET_SMART_RELAY = "set.smart.relay"

#: Route ids observed in DeviceJsonRequestHelp (APP_PARITY §4).
ROUTE_IDS: dict[str, str] = {
    COMMAND_GET_AUTO_UNLOCK: "$27",
    COMMAND_SET_AUTO_UNLOCK: "$27",
    COMMAND_GET_CALL_TIME: "$26",
    COMMAND_SET_CALL_TIME: "$26",
    COMMAND_GET_LOCK_STATUS: "$20",
    COMMAND_SET_CUSTOM_RING: "$38",
    COMMAND_SET_HOLD_UNLOCK: "$29",
}


def _request(command: str, content: dict) -> dict:
    """Envelope used by the app's JSON dialect: command + content mapping."""
    return {"command": command, "content": content}


def auto_unlock_get_body(channel: int = 1, lock: int = 1) -> dict:
    req = GetDeviceAutoUnlockContentReq(channel=channel, lock=lock)
    return _request(COMMAND_GET_AUTO_UNLOCK, {"channel": req.channel, "lock": req.lock})


def auto_unlock_set_body(
    req: SetDeviceAutoUnlockContentReq,
) -> dict:
    return _request(
        COMMAND_SET_AUTO_UNLOCK,
        {
            "channel": req.channel,
            "lock": req.lock,
            "apply": list(req.apply),
            "schedule": [asdict(entry) for entry in req.schedule],
        },
    )


def call_time_get_body(channel: int = 1) -> dict:
    req = GetDeviceCallTimeContentReq(channel=channel)
    return _request(COMMAND_GET_CALL_TIME, {"channel": req.channel})


def call_time_set_body(channel: int, time: str) -> dict:
    req = SetDeviceCallTimeContentReq(channel=channel, time=time)
    return _request(COMMAND_SET_CALL_TIME, {"channel": req.channel, "time": req.time})


def dumps(body: dict) -> str:
    """Serialize a layer-B body (compact, app-style)."""
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False)
