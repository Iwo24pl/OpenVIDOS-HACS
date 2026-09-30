"""Request/response bean parity (com.quvii.qvweb.device.bean.requset/respond).

Field names mirror the dex dump verbatim (including typos such as
``newPasswrod``); wire tags follow the SimpleXML ``@Element`` renames where the
legacy Phase-0 hardware capture proved them (APP_PARITY §3/§4).
"""

from __future__ import annotations

from .auto_unlock import (
    AutoUnlockLock,
    AutoUnlockSchedule,
    AutoUnlockScheduleEntry,
    GetDeviceAutoUnlockContentReq,
    SetDeviceAutoUnlockContentReq,
)
from .call_time import GetDeviceCallTimeContentReq, SetDeviceCallTimeContentReq
from .record import (
    GetRecordAlarmContent,
    GetRecordMessageContent,
    GetRecordSearchContent,
    GetRecordSessionContent,
    Record,
)
from .secret import GetDeviceSecretContent, GetDeviceSecretResp
from .status import DeviceStatus
from .unlock import (
    CheckUnlockPasswordContent,
    DeviceUnlockContent,
    OpenLockContent,
    SetUnlockPasswordContent,
)

__all__ = [
    "AutoUnlockLock",
    "AutoUnlockSchedule",
    "AutoUnlockScheduleEntry",
    "CheckUnlockPasswordContent",
    "DeviceStatus",
    "DeviceUnlockContent",
    "GetDeviceAutoUnlockContentReq",
    "GetDeviceCallTimeContentReq",
    "GetRecordAlarmContent",
    "GetRecordMessageContent",
    "GetRecordSearchContent",
    "GetRecordSessionContent",
    "GetDeviceSecretContent",
    "GetDeviceSecretResp",
    "OpenLockContent",
    "Record",
    "SetDeviceAutoUnlockContentReq",
    "SetDeviceCallTimeContentReq",
    "SetUnlockPasswordContent",
]
