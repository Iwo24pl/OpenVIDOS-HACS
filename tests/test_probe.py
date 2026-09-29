"""Tests for tools/probe.py (Phase 0 probe helpers)."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import pathlib
import unittest

PROBE_PATH = pathlib.Path(__file__).resolve().parents[1] / "tools" / "probe.py"


def _load_probe():
    spec = importlib.util.spec_from_file_location("vidos_probe", PROBE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = _load_probe()

SAMPLE_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<envelope>
  <body>
    <error>0</error>
    <content>
      <doorstatus>1</doorstatus>
      <devstatus><lockstate>2</lockstate></devstatus>
    </content>
  </body>
</envelope>"""


def _args(**kwargs) -> argparse.Namespace:
    defaults = {
        "password": "",
        "qr": "",
        "unlock_password": "",
        "door": 0,
        "lock": 0,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class EncodePasswordTests(unittest.TestCase):
    def test_sha256_hex(self) -> None:
        self.assertEqual(
            probe.encode_device_password("123456"), hashlib.sha256(b"123456").hexdigest()
        )
        self.assertEqual(len(probe.encode_device_password("123456")), 64)

    def test_passthrough_long_hex(self) -> None:
        long_hex = "a" * 64
        self.assertEqual(probe.encode_device_password(long_hex), long_hex)

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(probe.encode_device_password(""), "")


class ComboTests(unittest.TestCase):
    def test_both_secrets_first_contact_first(self) -> None:
        combos = probe.build_combos(_args(password="pwd1", qr="qr1"))
        # primary pass: 2 secrets x 5 variants, first-contact leads
        self.assertEqual(combos[0][0], "first-contact")
        self.assertEqual(combos[0][1], "pwd1")
        self.assertEqual(combos[5][0], "qr-passcode")
        self.assertEqual(combos[5][1], "qr1")
        # fallbacks appended after primaries
        self.assertEqual(combos[10][0], "fallback")

    def test_single_secret(self) -> None:
        combos = probe.build_combos(_args(password="pwd1"))
        labels = {label for label, _secret, _variant in combos if label != "fallback"}
        self.assertEqual(labels, {"first-contact"})

    def test_variant_order(self) -> None:
        names = [variant[0] for variant in probe.HEADER_VARIANTS]
        self.assertEqual(
            names,
            ["hs-plain", "hash-encode", "raw-encode", "lan-hash", "lan-plain"],
        )


class BuildRequestTests(unittest.TestCase):
    def test_status_request_plain(self) -> None:
        body = probe.build_status_request("adminapp", 'p<w&d"').decode()
        self.assertIn("<command>get.device.status</command>", body)
        self.assertIn("<security>username</security>", body)
        self.assertIn("<username>adminapp</username>", body)
        self.assertIn("<password>p&lt;w&amp;d&quot;</password>", body)
        self.assertNotIn("passwordencode", body)
        self.assertLess(
            body.index("<body>"), body.index("<header>"), "body must precede header"
        )

    def test_status_request_hashed_with_encode_flag(self) -> None:
        body = probe.build_status_request(
            "adminapp2", probe.encode_device_password("123456"), passwordencode=True
        ).decode()
        expected = hashlib.sha256(b"123456").hexdigest()
        self.assertIn(f"<password>{expected}</password>", body)
        self.assertIn("<passwordencode>1</passwordencode>", body)
        self.assertIn("<username>adminapp2</username>", body)

    def test_raw_encode_flag_keeps_plain_password(self) -> None:
        body = probe.build_status_request(
            "adminapp", "rawsecret", passwordencode=True
        ).decode()
        self.assertIn("<password>rawsecret</password>", body)
        self.assertIn("<passwordencode>1</passwordencode>", body)

    def test_transform_password_modes(self) -> None:
        self.assertEqual(
            probe.transform_password("abc", "hash"), hashlib.sha256(b"abc").hexdigest()
        )
        self.assertEqual(probe.transform_password("abc", "plain"), "abc")
        self.assertEqual(probe.transform_password("abc", "raw"), "abc")

    def test_opendoor_request_full_shape(self) -> None:
        body = probe.build_opendoor_request(
            "adminapp2", probe.encode_device_password("123456"), True, 0, 1, "pwd"
        ).decode()
        self.assertIn("<command>set.device.opendoor</command>", body)
        self.assertIn("<door>0</door>", body)
        self.assertIn("<locknumber>1</locknumber>", body)
        self.assertIn("<password>pwd</password>", body)
        self.assertLess(
            body.index("<content>"), body.index("<header>"), "body must precede header"
        )
        self.assertLess(body.index("<door>"), body.index("<locknumber>"))
        self.assertLess(body.index("<locknumber>"), body.index("<password>"))

    def test_opendoor_request_legacy_shape(self) -> None:
        body = probe.build_opendoor_request(
            "adminapp2", "hdr", False, 0, 3, "pwd", shape="legacy"
        ).decode()
        self.assertIn("<door>3</door>", body)
        self.assertNotIn("locknumber", body)

    def test_describe_error(self) -> None:
        self.assertEqual(probe.describe_error(0), "(ok)")
        self.assertEqual(probe.describe_error(-10028), "(incorrect password)")
        self.assertEqual(probe.describe_error(-10029), "(device busy)")
        self.assertEqual(probe.describe_error(-42), "")
        self.assertEqual(probe.describe_error(None), "")

    def test_door_attempt_order(self) -> None:
        args = _args(password="pwd1", qr="qr1", unlock_password="", lock=0)
        attempts = probe.build_door_attempts(args)
        # first: first-contact hash, full shape, lock 0
        label, value, lock, shape = attempts[0]
        self.assertEqual(label, "first-contact-hash")
        self.assertEqual(value, hashlib.sha256(b"pwd1").hexdigest())
        self.assertEqual((lock, shape), (0, "full"))
        # legacy shape and empty password are included later
        shapes = {shape for _l, _v, _lock, shape in attempts}
        self.assertEqual(shapes, {"full", "legacy"})
        labels = [label for label, _v, _lock, _s in attempts]
        self.assertIn("empty", labels)
        self.assertIn("qr-hash", labels)

    def test_door_attempt_given_password(self) -> None:
        args = _args(password="pwd1", qr="qr1", unlock_password="9999", lock=2)
        attempts = probe.build_door_attempts(args)
        labels = [label for label, _v, _lock, _s in attempts]
        self.assertEqual(labels[0], "given-raw")
        self.assertIn("given-hash", labels)
        self.assertNotIn("first-contact-hash", labels)
        self.assertIn(2, [lock for _l, _v, lock, _s in attempts])


class ResponseTests(unittest.TestCase):
    def test_extract_error(self) -> None:
        self.assertEqual(probe.extract_error(SAMPLE_RESPONSE), 0)
        self.assertEqual(probe.extract_error("<error>-3</error>"), -3)
        self.assertIsNone(probe.extract_error("garbage"))

    def test_flatten_xml(self) -> None:
        flat = probe.flatten_xml(SAMPLE_RESPONSE)
        self.assertEqual(flat["envelope>body>error"], "0")
        self.assertEqual(flat["envelope>body>content>doorstatus"], "1")
        self.assertEqual(flat["envelope>body>content>devstatus>lockstate"], "2")

    def test_flatten_invalid_xml(self) -> None:
        self.assertEqual(probe.flatten_xml("not xml at all"), {})


class DumpTests(unittest.TestCase):
    def test_dump_creates_missing_parent_dirs(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "nested" / "fixtures" / "sample.xml"
            probe._dump(SAMPLE_RESPONSE, str(target))
            self.assertEqual(target.read_text(encoding="utf-8"), SAMPLE_RESPONSE)

    def test_dump_swallows_oserror(self) -> None:
        probe._dump(SAMPLE_RESPONSE, "?:/invalid/path/x.xml")  # must not raise

    def test_dump_without_path_is_noop(self) -> None:
        probe._dump(SAMPLE_RESPONSE, None)


class UrlTests(unittest.TestCase):
    def test_candidate_urls_skip_rtsp(self) -> None:
        urls = probe.candidate_urls("10.0.0.5", [554, 80, 443])
        self.assertNotIn("http://10.0.0.5:554/tdkcgi", urls)
        self.assertIn("https://10.0.0.5:443/tdkcgi", urls)
        self.assertIn("http://10.0.0.5:80/tdkcgi", urls)

    def test_port443_https_only(self) -> None:
        urls = probe.candidate_urls("10.0.0.5", [443])
        self.assertEqual(urls, ["https://10.0.0.5:443/tdkcgi"])


if __name__ == "__main__":
    unittest.main()


class DiffFieldsTests(unittest.TestCase):
    def test_changed_value(self) -> None:
        self.assertEqual(
            probe.diff_fields({"calling": "false"}, {"calling": "true"}),
            [("calling", "false", "true")],
        )

    def test_added_and_removed(self) -> None:
        changes = probe.diff_fields({"a": "1"}, {"b": "2"})
        self.assertEqual(changes, [("a", "1", None), ("b", None, "2")])

    def test_no_changes(self) -> None:
        self.assertEqual(probe.diff_fields({"x": "1"}, {"x": "1"}), [])


class JsonProtocolTests(unittest.TestCase):
    def test_extract_error_json(self) -> None:
        body = '{"body":{"error":-10,"content":{}}}'
        self.assertEqual(probe.extract_error(body), -10)
        self.assertEqual(probe.extract_error('{"body":{"error":0}}'), 0)

    def test_flatten_json(self) -> None:
        flat = probe.flatten_json('{"body":{"error":0,"content":{"a":{"b":"1"}}}}')
        self.assertEqual(flat["json>body>content>a>b"], "1")

    def test_flatten_json_list(self) -> None:
        flat = probe.flatten_json('{"x":[{"v":"a"},{"v":"b"}]}')
        self.assertEqual(flat["json>x>1>v"], "b")

    def test_flatten_json_garbage(self) -> None:
        self.assertEqual(probe.flatten_json("not json"), {})

    def test_flatten_any_routes_by_shape(self) -> None:
        self.assertEqual(
            probe.flatten_any('{"a":"b"}'), probe.flatten_json('{"a":"b"}')
        )
        self.assertEqual(
            probe.flatten_any("<envelope><a>b</a></envelope>"),
            probe.flatten_xml("<envelope><a>b</a></envelope>"),
        )

    def test_build_json_request_shape(self) -> None:
        import json

        payload = json.loads(
            probe.build_json_request("get.lock.status", "adminapp2", "cafe", True)
        )
        self.assertEqual(payload["header"]["username"], "adminapp2")
        self.assertEqual(payload["header"]["password"], "cafe")
        self.assertEqual(payload["header"]["passwordencode"], 1)
        self.assertEqual(payload["header"]["security"], "username")
        self.assertEqual(payload["body"]["command"], "get.lock.status")

    def test_watch_commands_are_quads_with_formats(self) -> None:
        for label, command, _content, fmt in probe.build_watch_commands():
            self.assertTrue(label and command)
            self.assertIn(fmt, ("xml", "json"))
        labels = [c[0] for c in probe.build_watch_commands()]
        self.assertIn("status", labels)
        self.assertIn("jlock", labels)
        self.assertIn("alarmrec", labels)

    def test_noise_filters_clocks_and_audio_uptime(self) -> None:
        self.assertTrue(probe._is_noise("envelope>body>content>time>datatime"))
        self.assertTrue(probe._is_noise("envelope>body>content>synctime"))
        self.assertTrue(probe._is_noise("json>body>content>session"))
        self.assertFalse(probe._is_noise("json>body>content>calling"))
