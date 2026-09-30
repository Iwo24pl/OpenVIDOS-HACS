"""Auto-unlock beans (set.auto.unlock / get.auto.unlock, JSON dialect §4).

Wire id: route ``$27`` (DeviceJsonRequestHelp). Schedule semantics from the
dex dump: mode 0 = MOMENTARY, 1 = HOLD; time slots ``TIME1..TIME6`` with
``enabled``/``start``/``end``/``section``; JSON body shape pending live
capture (APP_PARITY §11.7).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AutoUnlockScheduleEntry:
    """One time slot (bean: time[] entry)."""

    TIME1: str = ""  # slot identity as used by the device JSON
    enabled: int = 0
    start: str = ""
    end: str = ""
    section: str = ""


@dataclass(frozen=True)
class AutoUnlockSchedule:
    """schedule[] entry: mode (0=MOMENTARY, 1=HOLD) + slots + weekday mask."""

    mode: int = 0
    time: list[AutoUnlockScheduleEntry] = field(default_factory=list)
    week: str = ""


@dataclass(frozen=True)
class AutoUnlockLock:
    """locks[] entry of the response channels[].locks[]."""

    number: int = 1
    schedule: AutoUnlockSchedule | None = None


@dataclass(frozen=True)
class GetDeviceAutoUnlockContentReq:
    """get.auto.unlock request content."""

    channel: int = 1
    lock: int = 1


@dataclass(frozen=True)
class SetDeviceAutoUnlockContentReq:
    """set.auto.unlock request content."""

    channel: int = 1
    lock: int = 1
    apply: list[dict[str, int]] = field(default_factory=list)
    schedule: list[AutoUnlockSchedule] = field(default_factory=list)
