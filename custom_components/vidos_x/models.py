"""Data models for the Vidos X integration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class VidosDevice:
    """A discovered Vidos/Quvii device (from the cloud device list)."""

    uid: str
    name: str
    ip: str
    cgi_port: int = 443
    username: str = "adminapp2"
    password: str = ""
    model: str | None = None


@dataclass(frozen=True)
class VidosStatus:
    """Result of one device poll."""

    fields: dict[str, str] = field(default_factory=dict)
    error: int = 0
    content: str = ""

    @property
    def lock_state(self) -> str | None:
        for key in ("lockstatus", "lockstate", "lock", "doorstate"):
            if key in self.fields:
                return self.fields[key]
        return None

    @property
    def disarmed(self) -> bool | None:
        value = self.fields.get("disarm")
        if value is None:
            return None
        return value in {"1", "true", "on", "yes"}

    @property
    def ringing(self) -> bool:
        # Fixture (IDS9483AW): devicestatus.calling = "true" while the bell rings.
        return _is_ringing(self.fields)

    @property
    def model(self) -> str | None:
        return self.fields.get("model")

    @property
    def firmware(self) -> str | None:
        return self.fields.get("version")


def _is_ringing(fields: dict[str, str] | None) -> bool:
    if not fields:
        return False
    for key in ("calling", "ring", "ding", "doorbell", "ringing", "event"):
        value = fields.get(key)
        if value in {"1", "true", "on", "yes", "ring", "ding", "doorbell"}:
            return True
    return False


def ring_started(
    prev_fields: dict[str, str] | None, new_fields: dict[str, str] | None
) -> bool:
    """True when a poll transitions idle -> ringing (a new doorbell press)."""
    if prev_fields is None:
        return False  # first poll: no known previous state, never a fresh press
    return not _is_ringing(prev_fields) and _is_ringing(new_fields)
