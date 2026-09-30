"""Unlock-related beans (APP_PARITY §4).

``DeviceUnlockContent`` Java fields are ``channelNum``/``lockNum``; the wire
tags are ``door``/``locknumber`` — SimpleXML ``@Element`` renames, proven on
hardware (Phase-0: `DeviceRequestHelp.deviceUnlock:152` path, `shape=full`
accepted).
"""

from __future__ import annotations

from dataclasses import dataclass

from ._content import content as _content


@dataclass(frozen=True)
class DeviceUnlockContent:
    """set.device.opendoor content (hardware-verified wire shape)."""

    channelNum: int = 0  # wire: <door>
    lockNum: int = 0  # wire: <locknumber>
    password: str = ""

    def to_content(self) -> str:
        return _content(
            ("door", self.channelNum),
            ("locknumber", self.lockNum),
            ("password", self.password),
        )


@dataclass(frozen=True)
class OpenLockContent:
    """set.device.opendoor via openLock() — wire tag rename unverified (§11)."""

    lockNum: int = 0
    password: str = ""

    def to_content(self) -> str:
        return _content(("locknumber", self.lockNum), ("password", self.password))


@dataclass(frozen=True)
class CheckUnlockPasswordContent:
    """set.opendoor.checkpassword content."""

    password: str = ""

    def to_content(self) -> str:
        return _content(("password", self.password))


@dataclass(frozen=True)
class SetUnlockPasswordContent:
    """set.opendoor.password content — field typo `newPasswrod` kept verbatim
    (SimpleXML serializes the Java field name; APP_PARITY §4)."""

    newPasswrod: str = ""
    oldPassword: str = ""

    def to_content(self) -> str:
        return _content(
            ("newPasswrod", self.newPasswrod),
            ("oldPassword", self.oldPassword),
        )
