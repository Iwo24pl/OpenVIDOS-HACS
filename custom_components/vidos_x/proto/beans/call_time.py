"""Call-time beans (get.call.time / set.call.time, JSON dialect §4).

Wire id: route ``$26``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GetDeviceCallTimeContentReq:
    """get.call.time request content."""

    channel: int = 1


@dataclass(frozen=True)
class SetDeviceCallTimeContentReq:
    """set.call.time request content."""

    channel: int = 1
    time: str = ""
