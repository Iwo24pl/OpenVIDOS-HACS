"""``DeviceAllInfoResp`` status slice (APP_PARITY §6).

The response is consumed via ``flatten_fields`` (device answers with nested
XML); this bean maps the flattened keys of ``status``/``info`` to typed
attributes. Key names are the dex field names verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass


def _bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class DeviceStatus:
    """Flattened ``status`` slice of get.device.status."""

    calling: bool | None = None
    lockstatus: bool | None = None
    tfCard: bool | None = None
    volume: bool | None = None
    humandete: bool | None = None
    model: str | None = None
    version: str | None = None

    @classmethod
    def from_fields(cls, fields: dict[str, str]) -> DeviceStatus:
        return cls(
            calling=_bool(fields.get("calling")),
            lockstatus=_bool(fields.get("lockstatus")),
            tfCard=_bool(fields.get("tfCard")),
            volume=_bool(fields.get("volume")),
            humandete=_bool(fields.get("humandete")),
            model=fields.get("model"),
            version=fields.get("version"),
        )
