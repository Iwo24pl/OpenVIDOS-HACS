"""Streamkey beans (get.device.streamkey, APP_PARITY §4)."""

from __future__ import annotations

from dataclasses import dataclass

from ._content import content as _content


@dataclass(frozen=True)
class GetDeviceSecretContent:
    """get.device.streamkey request content.

    The app sends the device ``authcode`` (first-contact password, APP_PARITY
    §4); the legacy client historically sent empty content and it worked —
    keep parity with the app and send the bean.
    """

    authcode: str = ""

    def to_content(self) -> str:
        return _content(("authcode", self.authcode))


@dataclass(frozen=True)
class GetDeviceSecretResp:
    """get.device.streamkey response: Content{key, synctime, tdc}."""

    key: str = ""
    synctime: str = ""
    tdc: str = ""

    @classmethod
    def from_fields(cls, fields: dict[str, str]) -> GetDeviceSecretResp:
        return cls(
            key=fields.get("key", ""),
            synctime=fields.get("synctime", ""),
            tdc=fields.get("tdc", ""),
        )
