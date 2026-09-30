"""Unit tests for the QUII media client (pure, no Home Assistant needed).

``tests/fixtures/quii_stream.bin`` is a real IDS9483AW capture re-encrypted
with a dummy key (the device streamkey never enters the repository).
"""

from __future__ import annotations

import hashlib
import pathlib
import struct
import unittest

try:
    import cryptography  # noqa: F401

    HAVE_CRYPTO = True
except ImportError:  # pragma: no cover - CI without cryptography
    HAVE_CRYPTO = False

from _load import load_module

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "quii_stream.bin"
DUMMY_KEY = "teststreamkeyteststreamkeytestst"


@unittest.skipUnless(HAVE_CRYPTO, "cryptography not installed")
class SetupAndPlayTests(unittest.TestCase):
    """Handshake packet builders."""

    def setUp(self) -> None:
        self.quii = load_module("proto.live_player")

    def test_setup_packet(self) -> None:
        packet = self.quii.build_setup()
        self.assertEqual(len(packet), 32)
        self.assertEqual(packet[0], 0xA9)
        self.assertEqual(packet[9], 0)

    def test_play_header_fields(self) -> None:
        packet = self.quii.build_play(
            "adminapp2", "a" * 64, DUMMY_KEY, idc=1, ids=1
        )
        hdr = self.quii.decrypt_header(packet, DUMMY_KEY, 2)
        self.assertEqual(hdr[0], 0x01)
        self.assertEqual(struct.unpack_from("<H", hdr, 9)[0], len(packet) - 32)
        self.assertEqual(struct.unpack_from("<H", hdr, 0x0B)[0], 11 + 64 + 2)
        self.assertEqual(struct.unpack_from("<H", hdr, 0x0D)[0], 1)
        self.assertEqual(hdr[0x10], 1)

    def test_play_sha256_trailer(self) -> None:
        packet = self.quii.build_play("adminapp2", "pw", DUMMY_KEY)
        hdr = self.quii.decrypt_header(packet, DUMMY_KEY, 2)
        body_len = struct.unpack_from("<H", hdr, 0x0B)[0]
        body = self.quii._aes(packet[32:], DUMMY_KEY, 2, decrypt=True)
        digest = hashlib.sha256(hdr + body[:body_len]).hexdigest()
        self.assertEqual(body[body_len : body_len + 32].hex(), digest)
        self.assertTrue(body.startswith(b"adminapp2&&pw\x00\x00"))

    def test_keepalive_roundtrip(self) -> None:
        packet = self.quii.build_keepalive(DUMMY_KEY)
        hdr = self.quii.decrypt_header(packet, DUMMY_KEY, 2)
        self.assertEqual(hdr[0], 0x00)
        self.assertEqual(struct.unpack_from("<H", hdr, 0x0B)[0], 0)
        self.assertEqual(len(packet) % 16, 0)

    def test_key_material_too_short(self) -> None:
        with self.assertRaises(ValueError):
            self.quii._key_bytes("short", 2)


@unittest.skipUnless(HAVE_CRYPTO, "cryptography not installed")
class MediaParsingTests(unittest.TestCase):
    """Message parsing helpers."""

    def setUp(self) -> None:
        self.quii = load_module("proto.live_player")

    def test_media_body_len(self) -> None:
        hdr = bytearray(32)
        struct.pack_into("<I", hdr, 0x0B, 5971)
        self.assertEqual(self.quii.media_body_len(bytes(hdr)), 5971)

    def test_qv_frame_type(self) -> None:
        idr = b"\x00\x00\x01\xe1\x00\x00\x00\x00" + b"\x00" * 24
        self.assertEqual(self.quii.qv_frame_type(idr), 1)
        pframe = b"\x00\x00\x01\xe0\x00\x00\x00\x00" + b"\x00" * 24
        self.assertEqual(self.quii.qv_frame_type(pframe), 0)
        self.assertIsNone(self.quii.qv_frame_type(b"\x47\x44"))

    def test_strip_and_keyframe_markers(self) -> None:
        sps = b"\x00\x00\x00\x01\x27\x4d\x00\x1e"
        idr = b"\x00\x00\x00\x01\x65\x88\x84"
        junk = b"\xaa" * 5
        payload = junk + sps + b"\x00\x00\x00\x01\x68" + idr
        stripped = self.quii.strip_to_annexb(payload)
        self.assertTrue(stripped.startswith(sps))
        self.assertTrue(self.quii.is_keyframe(payload))
        self.assertFalse(self.quii.is_keyframe(sps))  # SPS alone is not a keyframe

    def test_unpack_media_payload(self) -> None:
        hdr = bytearray(32)
        hdr[0] = 0xA0
        struct.pack_into("<H", hdr, 9, 32)
        struct.pack_into("<H", hdr, 0x10, 0)
        hdr[0x0F] = 0
        qv = b"\x00\x00\x01\xe1" + b"\x00" * 16  # 20-byte QV header
        annexb = b"\x00\x00\x00\x01\x27\x4d\x00\x1e" + b"\x11" * 20
        body_plain = qv + annexb
        enc_head = self.quii._aes(body_plain[:32], DUMMY_KEY, 2, decrypt=False)
        body = enc_head + body_plain[32:]
        payload = self.quii.unpack_media_payload(bytes(hdr), body, DUMMY_KEY, 2)
        self.assertEqual(payload, qv + annexb)


@unittest.skipUnless(HAVE_CRYPTO, "cryptography not installed")
class FixtureStreamTests(unittest.TestCase):
    """End-to-end parse of a real (re-keyed) device capture."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.quii = load_module("proto.live_player")

    def test_fixture_exists(self) -> None:
        self.assertTrue(FIXTURE.is_file(), f"missing fixture {FIXTURE}")

    def test_fixture_extracts_keyframe(self) -> None:
        data = FIXTURE.read_bytes()
        stream = self.quii.QuiiStream.__new__(self.quii.QuiiStream)
        stream._key = DUMMY_KEY
        stream._enc_mode = 2
        stream._buf = bytearray(data)
        fallback = bytearray()
        keyframe = stream._parse_buffer(fallback)

        self.assertIsNotNone(keyframe, "no keyframe extracted from fixture")
        assert keyframe is not None
        self.assertGreater(len(keyframe), 1000)
        self.assertTrue(
            any(m in keyframe[:16] for m in (b"\x00\x00\x00\x01\x27", b"\x00\x00\x01\x27")),
            f"keyframe does not start at SPS: {keyframe[:8].hex()}",
        )
        self.assertTrue(self.quii.is_keyframe(keyframe))
        # Whole fixture walked: buffer drains down to the trailing partial msg.
        self.assertLess(len(stream._buf), 32)


if __name__ == "__main__":
    unittest.main()
