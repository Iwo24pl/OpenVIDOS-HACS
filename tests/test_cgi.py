"""Unit tests for the device CGI helpers (no Home Assistant / aiohttp needed)."""

from __future__ import annotations

from pathlib import Path
import unittest

from _load import load_module

cgi = load_module("cgi")
models = load_module("models")

FIXTURE = Path(__file__).parent / "fixtures" / "device_status_sample.xml"


class BuildEnvelopeTests(unittest.TestCase):
    def test_envelope_shape(self) -> None:
        xml = cgi.build_envelope(
            "set.device.opendoor",
            username="adminapp2",
            password="b94d27b9...",
            passwordencode=True,
            content=cgi.content_from_mapping(
                {"door": 0, "locknumber": 0, "password": "c93b..."}
            ),
        )
        self.assertIn('<?xml version="1.0" encoding="UTF-8"?>', xml)
        self.assertTrue(xml.startswith('<?xml version="1.0" encoding="UTF-8"?><Envelope>'))
        # body must come before header (mirrors the app's SimpleXML bean order)
        self.assertLess(xml.index("<body>"), xml.index("<header>"))
        self.assertIn("<command>set.device.opendoor</command>", xml)
        self.assertIn(
            "<content><door>0</door><locknumber>0</locknumber>"
            "<password>c93b...</password></content>",
            xml,
        )
        self.assertIn("<security>username</security>", xml)
        self.assertIn("<username>adminapp2</username>", xml)
        self.assertIn("<passwordencode>1</passwordencode>", xml)
        # XML special characters are escaped
        self.assertIn("<password>p&lt;&amp;1</password>",
                      cgi.build_header("u", "p<&1"))

    def test_header_without_passwordencode(self) -> None:
        header = cgi.build_header("adminapp2", "plain")
        self.assertNotIn("passwordencode", header)

    def test_content_order_is_preserved(self) -> None:
        content = cgi.content_from_mapping(
            {"door": 2, "locknumber": 1, "password": "9999"}
        )
        self.assertEqual(
            content,
            "<content><door>2</door><locknumber>1</locknumber><password>9999</password></content>",
        )

    def test_body_without_content(self) -> None:
        body = cgi.build_body("get.device.status")
        self.assertEqual(body, "<body><command>get.device.status</command></body>")

    def test_sha256_hex(self) -> None:
        self.assertEqual(cgi.sha256_hex(""), "")
        # sha256("test") - lowercase hex like QvEncrypt.EncodeDevicePassword
        self.assertEqual(
            cgi.sha256_hex("test"),
            "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        )
        # values >= 64 chars pass through unchanged
        long = "a" * 64
        self.assertEqual(cgi.sha256_hex(long), long)


class ClientPasswordTests(unittest.TestCase):
    def _client(self, **kwargs) -> object:
        return cgi.VidosCgiClient(
            "192.168.1.10", 443, username="adminapp2", password="s3cret",
            session=None, **kwargs,
        )

    def test_header_password_is_hashed_by_default(self) -> None:
        client = self._client()
        self.assertEqual(client.header_password, cgi.sha256_hex("s3cret"))

    def test_header_password_raw_when_hashing_disabled(self) -> None:
        client = self._client(hash_password=False)
        self.assertEqual(client.header_password, "s3cret")


class ParseResponseTests(unittest.TestCase):
    def test_ok_response(self) -> None:
        resp = cgi.parse_response(
            "<envelope><body><error>0</error><content><status>ok</status></content></body></envelope>"
        )
        self.assertTrue(resp.ok)
        self.assertEqual(resp.fields["status"], "ok")

    def test_error_response(self) -> None:
        resp = cgi.parse_response("<Envelope><body><error>-3</error></body></Envelope>")
        self.assertEqual(resp.error, -3)
        self.assertFalse(resp.ok)

    def test_invalid_xml_raises(self) -> None:
        with self.assertRaises(cgi.VidosCgiResponseError):
            cgi.parse_response("not xml at all")

    def test_flatten_fields_ignores_nesting(self) -> None:
        fields = cgi.flatten_fields("<a><b>1</b><c><d>two</d></c></a>")
        self.assertEqual(fields["b"], "1")
        self.assertEqual(fields["d"], "two")

    def test_flatten_fields_on_garbage(self) -> None:
        self.assertEqual(cgi.flatten_fields(""), {})
        self.assertEqual(cgi.flatten_fields("<broken"), {})


class FixtureTests(unittest.TestCase):
    """Parse the captured status fixture (Phase 0 hardware capture)."""

    def test_fixture_parses(self) -> None:
        resp = cgi.parse_response(FIXTURE.read_text(encoding="utf-8"))
        self.assertTrue(resp.ok)
        self.assertEqual(resp.fields["model"], "IDS9483AW")
        self.assertEqual(resp.fields["version"], "V100.R001.A311.00.G0108.B018")
        self.assertEqual(resp.fields["lockstatus"], "false")
        self.assertEqual(resp.fields["calling"], "false")

    def test_fixture_status_model(self) -> None:
        resp = cgi.parse_response(FIXTURE.read_text(encoding="utf-8"))
        status = models.VidosStatus(fields=resp.fields, error=resp.error)
        self.assertEqual(status.lock_state, "false")
        self.assertFalse(status.ringing)
        self.assertEqual(status.model, "IDS9483AW")
        self.assertIsNotNone(status.firmware)

    def test_ringing_from_calling_flag(self) -> None:
        status = models.VidosStatus(fields={"calling": "true"})
        self.assertTrue(status.ringing)


class ClientUrlTests(unittest.TestCase):
    def test_base_url(self) -> None:
        client = cgi.VidosCgiClient(
            "192.168.1.10",
            443,
            username="adminapp2",
            password="x",
            session=None,
            scheme="https",
        )
        self.assertEqual(client.base_url, "https://192.168.1.10:443/tdkcgi")
        self.assertEqual(client.configuration_url, "https://192.168.1.10:443/")


if __name__ == "__main__":
    unittest.main()
