"""Record-log beans (APP_PARITY §4/§5)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Record:
    """``Record`` bean — shared by all record request contents."""

    channels: str = ""
    startTime: str = ""
    endTime: str = ""
    fileType: str = ""
    occurType: str = ""
    stream: str = ""
    id: str = ""

    def to_record_xml(self, *, with_time: bool = True) -> str:
        """Serialize the ``<record>`` element (time window optional)."""
        parts: list[tuple[str, object]] = []
        if self.fileType:
            parts.append(("filetype", self.fileType))
        if self.occurType:
            parts.append(("occurtype", self.occurType))
        if self.channels:
            parts.append(("channels", self.channels))
        if with_time and self.startTime:
            parts.append(("starttime", self.startTime))
        if with_time and self.endTime:
            parts.append(("endtime", self.endTime))
        if self.stream:
            parts.append(("stream", self.stream))
        if self.id:
            parts.append(("id", self.id))
        inner = "".join(f"<{tag}>{value}</{tag}>" for tag, value in parts)
        return f"<record>{inner}</record>"


@dataclass(frozen=True)
class GetRecordSessionContent:
    """get.record.session content."""

    record: Record = field(default_factory=Record)

    def to_content(self) -> str:
        return f"<content>{self.record.to_record_xml()}</content>"


@dataclass(frozen=True)
class GetRecordMessageContent:
    """get.record.message content (session id paging)."""

    record: Record = field(default_factory=Record)

    def to_content(self) -> str:
        # Page requests carry only the session id (legacy hardware-verified).
        return f"<content><record><id>{self.record.id}</id></record></content>"


@dataclass(frozen=True)
class GetRecordSearchContent:
    """get.record.search content (history listing)."""

    record: Record = field(default_factory=Record)

    def to_content(self) -> str:
        return f"<content>{self.record.to_record_xml()}</content>"


@dataclass(frozen=True)
class GetRecordAlarmContent:
    """get.record.alarmrecord content."""

    record: Record = field(default_factory=Record)

    def to_content(self) -> str:
        return f"<content>{self.record.to_record_xml(with_time=False)}</content>"
