"""Milestone-1 command constants + content builders.

Parity with `com.quvii.qvweb.device.DeviceRequestHelp` (APP_PARITY §4/§10):
`COMMAND_*` values are the dex strings verbatim; builders produce the
`<content>` XML for the beans in `.beans`.
"""

from __future__ import annotations

from .beans import (
    CheckUnlockPasswordContent,
    DeviceUnlockContent,
    GetDeviceSecretContent,
    OpenLockContent,
    SetUnlockPasswordContent,
)

# --- command constants (DeviceRequestHelp.COMMAND_* / dex command strings) ---
COMMAND_GET_DEVICE_STATUS = "get.device.status"
COMMAND_GET_DEVICE_SECRET = "get.device.streamkey"
COMMAND_GET_HEADER_CONTENT = "get.header.content"
COMMAND_OPEN_DOOR = "set.device.opendoor"
COMMAND_CHECK_UNLOCK_PASSWORD = "set.opendoor.checkpassword"
COMMAND_SET_UNLOCK_PASSWORD = "set.opendoor.password"
COMMAND_GET_RECORD_SESSION = "get.record.session"
COMMAND_GET_RECORD_MESSAGE = "get.record.message"
COMMAND_GET_RECORD_SEARCH = "get.record.search"
COMMAND_GET_RECORD_ALARM = "get.record.alarmrecord"
COMMAND_GET_RECORD_CONFIG = "get.record.config"
COMMAND_GET_ATTACHMENT_INFO = "get.device.attachInfo"
COMMAND_GET_LIVE_STATUS = "get.live.status"
COMMAND_GET_LOCK_STATUS = "get.lock.status"
COMMAND_GET_DEVICE_INFO = "get.device.info"
COMMAND_GET_SYSTEM_ABILITY = "get.system.ability"
COMMAND_GET_TIME_ZONE = "get.time.zone"
COMMAND_GET_SOUND_LIGHT = "get.soundandlight.state"
COMMAND_GET_CHANNEL_MANAGEMENT = "get.channelmanagement.config"
COMMAND_GET_AUTO_REBOOT = "get.system.automaintenance"
COMMAND_MODIFY_VERIFICATION_CODE = "set.seurity.verifycode"


def unlock_content(door: int, lock: int, password: str) -> str:
    """set.device.opendoor content (DeviceUnlockContent, verified wire tags)."""
    return DeviceUnlockContent(channelNum=door, lockNum=lock, password=password).to_content()


def open_lock_content(lock: int, password: str) -> str:
    """set.device.opendoor via openLock() (OpenLockContent; rename unverified)."""
    return OpenLockContent(lockNum=lock, password=password).to_content()


def check_password_content(password: str) -> str:
    """set.opendoor.checkpassword content."""
    return CheckUnlockPasswordContent(password=password).to_content()


def set_password_content(new_password: str, old_password: str) -> str:
    """set.opendoor.password content (bean typo `newPasswrod` kept)."""
    return SetUnlockPasswordContent(
        newPasswrod=new_password, oldPassword=old_password
    ).to_content()


def streamkey_content(authcode: str = "") -> str:
    """get.device.streamkey content (GetDeviceSecretContent)."""
    return GetDeviceSecretContent(authcode=authcode).to_content()
