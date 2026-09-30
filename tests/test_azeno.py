"""Unit tests for the LAN ring detector (no sockets, no Home Assistant)."""

from __future__ import annotations

import unittest

from _load import load_module

lan = load_module("proto.azeno")

SCAN = b"ASZENO.SEARCH.V4.1"
REPLY = b"ASZENO.SEARCH.V4" + bytes(600)


class RungDetectorTests(unittest.TestCase):
    def test_burst_is_one_episode(self) -> None:
        det = lan.RungDetector()
        results = [
            det.feed(SCAN, lan.SCAN_PORT, now=t) for t in (0.0, 1.0, 2.0, 3.0)
        ]
        self.assertEqual(results, [True, False, False, False])
        self.assertEqual(det.episodes, 1)
        self.assertEqual(det.packets_in_episode, 4)

    def test_second_burst_is_new_episode(self) -> None:
        det = lan.RungDetector()
        self.assertTrue(det.feed(SCAN, lan.SCAN_PORT, now=0.0))
        self.assertFalse(det.feed(REPLY, lan.REPLY_PORT, now=1.0))
        # 30 s later: a new ring
        self.assertTrue(det.feed(SCAN, lan.SCAN_PORT, now=31.0))
        self.assertEqual(det.episodes, 2)

    def test_gap_just_under_threshold_continues_episode(self) -> None:
        det = lan.RungDetector()
        self.assertTrue(det.feed(SCAN, lan.SCAN_PORT, now=0.0))
        self.assertFalse(det.feed(SCAN, lan.SCAN_PORT, now=lan.EPISODE_GAP - 0.01))
        self.assertEqual(det.episodes, 1)

    def test_non_magic_ignored(self) -> None:
        det = lan.RungDetector()
        self.assertFalse(det.feed(b"SSDP stuff", lan.SCAN_PORT, now=0.0))
        self.assertFalse(det.feed(b"", lan.REPLY_PORT, now=1.0))
        self.assertEqual(det.episodes, 0)
        self.assertTrue(det.feed(SCAN, lan.SCAN_PORT, now=2.0))

    def test_magic_prefix(self) -> None:
        det = lan.RungDetector()
        self.assertTrue(det.feed(b"ASZENO.SEARCH.V4" + bytes(500), lan.REPLY_PORT, now=0.0))

    def test_kind_for_ports(self) -> None:
        self.assertEqual(lan.kind_for(lan.SCAN_PORT), lan.KIND_SCAN)
        self.assertEqual(lan.kind_for(lan.REPLY_PORT), lan.KIND_REPLY)
        self.assertEqual(lan.kind_for(1234), lan.KIND_REPLY)


class ProtocolTests(unittest.TestCase):
    def test_datagram_triggers_callback_once_per_burst(self) -> None:
        events: list[tuple[str, str]] = []
        det = lan.RungDetector()
        proto = lan._AzenoProtocol(det, lambda ip, kind: events.append((ip, kind)), lan.SCAN_PORT)
        proto.datagram_received(SCAN, ("192.168.1.17", 5003))
        proto.datagram_received(SCAN, ("192.168.1.17", 5003))
        self.assertEqual(events, [("192.168.1.17", lan.KIND_SCAN)])

    def test_reply_port_classified(self) -> None:
        events: list[tuple[str, str]] = []
        det = lan.RungDetector()
        proto = lan._AzenoProtocol(det, lambda ip, kind: events.append((ip, kind)), lan.REPLY_PORT)
        proto.datagram_received(REPLY, ("192.168.1.67", 42214))
        self.assertEqual(events, [("192.168.1.67", lan.KIND_REPLY)])


if __name__ == "__main__":
    unittest.main()
