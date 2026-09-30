"""Channel-aware ring detection via the device's ring-picture log.

Hardware-verified (IDS9483AW, 2026-09-30): every doorbell press stores a
tiny picture record, retrievable with the two-phase protocol
(APP_PARITY §5, decision D1 — local substitute for the app's cloud push):

    get.record.session  ->  <record><id>N</id></record>
    get.record.message  ->  pages of <data> records

Each record carries the ringing ``<channel>`` - channel 1 = camera doorbell,
channel 2 = dummy button - plus ``starttime`` and ``filename``.

Hard-won protocol constraints (docs/VIDOS_X_PROTOCOL.md 4.6):

* Session requests MUST use ``filetype=picture``; other values (e.g.
  ``all``) make the firmware drop the CGI connection and refuse new
  connections for 1-2 minutes.
* Time filters use the ISO ``T`` separator (``2026-09-30T14:38:07``).
* Reuse the returned session id; reopening forces a full listing re-read.
* The device may answer with a *truncated* listing (prefix of the full
  set, oldest first). New records are therefore detected by filename set +
  a timestamp cutoff, never by "max starttime changed".
* ``get.record.session`` answering ``-1``/``-10`` means this firmware does
  not implement the command (seen on IDS9478W dialect variants).

Deliberately Home Assistant-free so it unit-tests without it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import re

from .envelope import CgiResponse, VidosCgiCommandError, VidosCgiError, VidosCgiResponseError

_LOGGER = logging.getLogger(__name__)

COMMAND_SESSION = "get.record.session"
COMMAND_MESSAGE = "get.record.message"

ERROR_COMMAND_UNKNOWN = -1
ERROR_NOT_SUPPORTED = -10

#: Ring log query: enabled cam channels of the IDS9483AW wiring table.
DEFAULT_RECORD_CHANNELS = "1,2"
DEFAULT_RECORD_POLL_INTERVAL = 3.0

#: wt7 sibling reads pages until empty with this hard cap.
MAX_PAGES = 20
#: Gentle pacing between page reads inside one cycle.
PAGE_GAP_SECONDS = 1.0
#: Backoff cap after repeated failures (device CGI throttles).
MAX_BACKOFF_SECONDS = 60.0

_TIME_RE = re.compile(r"<(starttime|filename|channel)>([^<]*)</\1>")
_DATA_RE = re.compile(r"<data>(.*?)</data>", re.S)
_ID_RE = re.compile(r"<id>([^<]+)</id>")


@dataclass(frozen=True)
class RingRecord:
    """One picture record from ``get.record.message``."""

    channel: int | None
    starttime: str
    filename: str

    @property
    def sort_time(self) -> str:
        """Device timestamps arrive as ``2026-09-30t14:38:07z``; normalize."""
        return self.starttime.strip().lower().replace("z", "").replace("t", "T")


def parse_records(raw: str) -> list[RingRecord]:
    """Extract all ``<data>`` records from a ``get.record.message`` response."""
    records: list[RingRecord] = []
    for block in _DATA_RE.findall(raw):
        fields = dict(_TIME_RE.findall(block))
        filename = (fields.get("filename") or "").strip()
        if not filename:
            continue
        channel_raw = (fields.get("channel") or "").strip()
        try:
            channel = int(channel_raw) if channel_raw else None
        except ValueError:
            channel = None
        records.append(
            RingRecord(
                channel=channel,
                starttime=(fields.get("starttime") or "").strip(),
                filename=filename,
            )
        )
    return records


def build_session_content(channels: str, start: datetime, end: datetime) -> str:
    """Session request body - exact field set verified on hardware."""
    return (
        "<content><record>"
        "<filetype>picture</filetype>"
        "<occurtype>all</occurtype>"
        f"<channels>{channels}</channels>"
        f"<starttime>{start.strftime('%Y-%m-%dT%H:%M:%S')}</starttime>"
        f"<endtime>{end.strftime('%Y-%m-%dT%H:%M:%S')}</endtime>"
        "<stream>all</stream>"
        "</record></content>"
    )


def build_message_content(session_id: str) -> str:
    """Page request body for an open session."""
    return f"<content><record><id>{session_id}</id></record></content>"


class RecordRingWatcher:
    """Polls the ring-picture log and reports new records with their channel.

    ``on_ring(channel, starttime)`` is invoked from the event loop thread for
    every record that appears after the baseline read. Call :meth:`stop` and
    cancel the driving task to shut down.
    """

    def __init__(
        self,
        client: object,
        *,
        channels: str = DEFAULT_RECORD_CHANNELS,
        interval: float = DEFAULT_RECORD_POLL_INTERVAL,
        on_ring: Callable[[int | None, str], None],
    ) -> None:
        self._client = client
        self._channels = channels
        self._interval = max(1.0, float(interval))
        self._on_ring = on_ring
        self._sid: str | None = None
        self._seen: set[str] = set()
        self._cutoff: str | None = None
        #: Two priming cycles: the cold listing may be truncated (missing the
        #: newest entries), so the first full read only raises the cutoff.
        self._prime_cycles_left = 2
        self._stopped = False
        self._unsupported = False
        self._failures = 0

    @property
    def unsupported(self) -> bool:
        """True when the firmware rejected the command as unknown."""
        return self._unsupported

    def stop(self) -> None:
        """Ask the run loop to exit after the current cycle."""
        self._stopped = True

    async def async_run(self) -> None:
        """Poll forever (until :meth:`stop`) with error backoff."""
        while not self._stopped:
            delay = self._interval
            try:
                await self.async_once()
                self._failures = 0
            except VidosCgiCommandError as err:
                self._failures += 1
                if self._unsupported:
                    _LOGGER.warning(
                        "ring log unsupported by this device (%s); "
                        "channel-aware ring detection disabled",
                        err,
                    )
                    return
                delay = self._backoff()
                _LOGGER.debug(
                    "ring log cycle failed (%s), backing off %.0fs", err, delay
                )
            except VidosCgiError as err:
                self._failures += 1
                delay = self._backoff()
                _LOGGER.debug(
                    "ring log cycle failed (%s), backing off %.0fs", err, delay
                )
            except Exception:  # noqa: BLE001 - keep the poller alive
                self._failures += 1
                delay = self._backoff()
                _LOGGER.debug(
                    "ring log cycle failed unexpectedly, backing off %.0fs",
                    delay,
                    exc_info=True,
                )
            if delay > 0 and not self._stopped:
                await asyncio.sleep(delay)

    def _backoff(self) -> float:
        return min(
            self._interval * (2 ** min(self._failures, 5)), MAX_BACKOFF_SECONDS
        )

    async def async_once(self) -> None:
        """One full cycle: ensure session, read all pages, fire callbacks."""
        if self._sid is None:
            await self._async_open_session()
        assert self._sid is not None
        pages = 0
        while pages < MAX_PAGES and not self._stopped:
            response: CgiResponse = await self._client.async_command(  # type: ignore[attr-defined]
                COMMAND_MESSAGE, build_message_content(self._sid), require_ok=False
            )
            if response.error != 0:
                # Session expired or rejected: reopen next cycle.
                self._sid = None
                raise VidosCgiCommandError(
                    COMMAND_MESSAGE, response.error, response.content
                )
            records = parse_records(response.raw)
            if not records:
                break
            self._handle_records(records)
            pages += 1
            await asyncio.sleep(PAGE_GAP_SECONDS)
        if self._prime_cycles_left > 0:
            self._prime_cycles_left -= 1
            if self._prime_cycles_left == 0:
                _LOGGER.debug(
                    "ring log baseline ready: %d known records, cutoff=%s",
                    len(self._seen),
                    self._cutoff,
                )

    async def _async_open_session(self) -> None:
        now = datetime.now()
        content = build_session_content(
            self._channels, now - timedelta(days=30), now + timedelta(days=1)
        )
        response: CgiResponse = await self._client.async_command(  # type: ignore[attr-defined]
            COMMAND_SESSION, content, require_ok=False
        )
        if response.error != 0:
            if response.error in (ERROR_COMMAND_UNKNOWN, ERROR_NOT_SUPPORTED):
                self._unsupported = True
            raise VidosCgiCommandError(
                COMMAND_SESSION, response.error, response.content
            )
        match = _ID_RE.search(response.raw)
        if match is None or not match.group(1).strip():
            raise VidosCgiResponseError("get.record.session returned no id")
        self._sid = match.group(1).strip()

    def _handle_records(self, records: list[RingRecord]) -> None:
        for record in records:
            if record.filename in self._seen:
                continue
            self._seen.add(record.filename)
            sort_time = record.sort_time
            if self._prime_cycles_left > 0:
                # Priming: remember the newest known timestamp so later
                # truncated-read leftovers can be told apart from new rings.
                if self._cutoff is None or sort_time > self._cutoff:
                    self._cutoff = sort_time
                continue
            if self._cutoff is not None and sort_time <= self._cutoff:
                _LOGGER.debug(
                    "ignoring stale ring-log record %s (%s)",
                    record.filename,
                    record.starttime,
                )
                continue
            self._cutoff = sort_time
            _LOGGER.debug(
                "ring log: channel=%s time=%s file=%s",
                record.channel,
                record.starttime,
                record.filename,
            )
            self._on_ring(record.channel, record.starttime)
