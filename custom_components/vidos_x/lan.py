"""LAN ring detection for Vidos X (Azeno discovery broadcasts).

Hardware findings (2026-10-02, IDS9483AW + Vidos X iOS app):

* The Vidos app broadcasts ``ASZENO.SEARCH.V4.1`` to UDP **5000** (source
  port 5003) when its connect flow wakes - observed 6 s after a bell press
  with the app **closed** (silent push wake), 4 packets at 1 Hz.
* The door station answers each probe 15-85 ms later with a 616-byte
  ``ASZENO.SEARCH.V4`` broadcast on UDP **5001**: 392-byte fixed identity
  blob + 224-byte varying tail.
* ``get.device.status`` does NOT change on a ring, so this broadcast chain
  is the only LAN-observable ring signal found.

Detection = one "ring episode" per burst (packets separated by >= 6 s are a
new ring). Known caveat: opening the Vidos app may run the same discovery
scan and produce a false ring event.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging
import socket
import time

_LOGGER = logging.getLogger(__name__)

MAGIC = b"ASZENO.SEARCH.V4"
SCAN_PORT = 5000
REPLY_PORT = 5001
#: Bursts are 2-4 packets at 1 Hz; a gap this long starts a new episode.
EPISODE_GAP = 6.0

KIND_SCAN = "scan"
KIND_REPLY = "reply"


class RungDetector:
    """Turn a burst of ASZENO packets into one ring event per press."""

    def __init__(self) -> None:
        self._last_packet_at: float | None = None
        self.episodes = 0
        self.packets_in_episode = 0

    def feed(
        self, data: bytes, port: int, now: float | None = None
    ) -> bool:
        """Feed one datagram; return True when a new ring episode starts."""
        if not data.startswith(MAGIC):
            return False
        stamp = time.monotonic() if now is None else now
        if self._last_packet_at is None or stamp - self._last_packet_at >= EPISODE_GAP:
            self._last_packet_at = stamp
            self.packets_in_episode = 1
            self.episodes += 1
            return True
        self._last_packet_at = stamp
        self.packets_in_episode += 1
        return False


def kind_for(port: int) -> str:
    """Classify a datagram by the port it was received on."""
    return KIND_SCAN if port == SCAN_PORT else KIND_REPLY


class _AzenoProtocol(asyncio.DatagramProtocol):
    """Feeds received datagrams into a shared :class:`RungDetector`."""

    def __init__(
        self,
        detector: RungDetector,
        on_rung: Callable[[str, str], None],
        port: int,
    ) -> None:
        self._detector = detector
        self._on_rung = on_rung
        self._port = port

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if self._detector.feed(data, self._port):
            _LOGGER.debug(
                "Azeno %s from %s (episode %s)",
                kind_for(self._port),
                addr[0],
                self._detector.episodes,
            )
            self._on_rung(addr[0], kind_for(self._port))


class AzenoLanListener:
    """Listens on UDP 5000/5001 for the Azeno ring signal.

    ``on_rung(source_ip, kind)`` is invoked from the event loop thread on the
    first packet of each burst.
    """

    def __init__(self, on_rung: Callable[[str, str], None]) -> None:
        self._on_rung = on_rung
        self.detector = RungDetector()
        self._transports: list[asyncio.DatagramTransport] = []

    @property
    def listening(self) -> bool:
        return bool(self._transports)

    async def async_start(self) -> bool:
        """Bind the discovery ports; True if at least one bound."""
        loop = asyncio.get_running_loop()
        for port in (SCAN_PORT, REPLY_PORT):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("", port))
                _transport, _protocol = await loop.create_datagram_endpoint(
                    lambda p=port: _AzenoProtocol(self.detector, self._on_rung, p),
                    sock=sock,
                )
            except OSError as exc:
                _LOGGER.warning("lan ring detection: cannot bind UDP %s: %s", port, exc)
                sock.close()
                continue
            self._transports.append(_transport)
        return self.listening

    def async_stop(self) -> None:
        """Close both sockets."""
        for transport in self._transports:
            transport.close()
        self._transports.clear()
