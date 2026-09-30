"""Unit tests for envelope build/parse helpers (no Home Assistant)."""

from __future__ import annotations

from pathlib import Path
import unittest

from _load import load_module

env = load_module("proto.envelope")
models = load_module("proto.models")

FIXTURE = Path(__file__).parent / "fixtures" / "device_status_sample.xml"


class BuildEnvelopeTests(unittest.TestCase):
    def test_envelope_shape(self) -> None:
        xml = env.build_envelope(
            "set.device.opendoor",
            username="adminapp2",
            password="b94d27b9...",
            passwordencode=True,
            content=env.content_from_mapping(
                {"door": 0, "locknumber": 0, "password": "c93b..."}
            ),
        )
        self.assertTrue(xml.startswith('<?xml version="1.0" encoding="UTF-8"?><Envelope>'))
        # body must come before header (mirrors the app's SimpleXML bean order)
        self.assertLess(xml.index("<body>"), xml.index("<header>"))
        self.assertIn("<command>set.device.opendoor</command>", xml)
        self.assertIn(
            "<content><door>0</door><locknumber>0</locknumber>"
            "<password>c93b...</password></content>",
            xml,
        )
        # app parity default (DeviceRequestHelp.initHeader const)
        self.assertIn("<security>httpauthen</security>", xml)
        self.assertIn("<username>adminapp2</username>", xml)
        self.assertIn("<passwordencode>1</passwordencode>", xml)

    def test_legacy_security_fallback(self) -> None:
        header = env.build_header(
            "adminapp2", "hash", security=env.SECURITY_USERNAME_LEGACY
        )
        self.assertIn("<security>username</security>", header)

    def test_header_without_passwordencode(self) -> None:
        header = env.build_header("adminapp2", "plain")
        self.assertNotIn("passwordencode", header)

    def test_header_with_nc(self) -> None:
        header = env.build_header("adminapp2", "p", nc="00000001")
        self.assertIn("<nc>00000001</nc>", header)

    def test_content_order_is_preserved(self) -> None:
        content = env.content_from_mapping(
            {"door": 2, "locknumber": 1, "password": "9999"}
        )
        self.assertEqual(
            content,
            "<content><door>2</door><locknumber>1</locknumber><password>9999</password></content>",
        )

    def test_body_without_content(self) -> None:
        body = env.build_body("get.device.status")
        self.assertEqual(body, "<body><command>get.device.status</command></body>")

    def test_header_escapes_xml_specials(self) -> None:
        self.assertIn(
            "<password>p&lt;&amp;1</password>", env.build_header("u", "p<&1")
        )

    def test_sha256_hex(self) -> None:
        self.assertEqual(env.sha256_hex(""), "")
        self.assertEqual(
            env.sha256_hex("test"),
            "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        )
        long = "a" * 64
        self.assertEqual(env.sha256_hex(long), long)


class ParseResponseTests(unittest.TestCase):
    def test_ok_response(self) -> None:
        resp = env.parse_response(
            "<envelope><body><error>0</error><content><status>ok</status></content></body></envelope>"
        )
        self.assertTrue(resp.ok)
        self.assertEqual(resp.fields["status"], "ok")

    def test_error_response(self) -> None:
        resp = env.parse_response("<Envelope><body><error>-3</error></body></Envelope>")
        self.assertEqual(resp.error, -3)
        self.assertFalse(resp.ok)

    def test_invalid_xml_raises(self) -> None:
        with self.assertRaises(env.VidosCgiResponseError):
            env.parse_response("not xml at all")

    def test_flatten_fields_ignores_nesting(self) -> None:
        fields = env.flatten_fields("<a><b>1</b><c><d>two</d></c></a>")
        self.assertEqual(fields["b"], "1")
        self.assertEqual(fields["d"], "two")

    def test_flatten_fields_on_garbage(self) -> None:
        self.assertEqual(env.flatten_fields(""), {})
        self.assertEqual(env.flatten_fields("<broken"), {})


class FixtureTests(unittest.TestCase):
    """Parse the captured status fixture (Phase 0 hardware capture)."""

    def test_fixture_parses(self) -> None:
        resp = env.parse_response(FIXTURE.read_text(encoding="utf-8"))
        self.assertTrue(resp.ok)
        self.assertEqual(resp.fields["model"], "IDS9483AW")
        self.assertEqual(resp.fields["version"], "V100.R001.A311.00.G0108.B018")
        self.assertEqual(resp.fields["lockstatus"], "false")
        self.assertEqual(resp.fields["calling"], "false")

    def test_fixture_status_model(self) -> None:
        resp = env.parse_response(FIXTURE.read_text(encoding="utf-8"))
        status = models.VidosStatus(fields=resp.fields, error=resp.error)
        self.assertEqual(status.lock_state, "false")
        self.assertFalse(status.ringing)
        self.assertEqual(status.model, "IDS9483AW")
        self.assertIsNotNone(status.firmware)

    def test_ringing_from_calling_flag(self) -> None:
        status = models.VidosStatus(fields={"calling": "true"})
        self.assertTrue(status.ringing)


if __name__ == "__main__":
    unittest.main()
