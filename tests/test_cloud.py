"""Unit tests for the cloud helpers (envelope + device list parsing)."""

from __future__ import annotations

import unittest

from _load import load_module

load_module("cgi")
cloud = load_module("cloud")


class CloudEnvelopeTests(unittest.TestCase):
    def test_client_id_format(self) -> None:
        client_id = cloud.make_client_id(0)
        self.assertRegex(client_id, r"^000-4108-[0-9a-f]{16}$")

    def test_envelope_shape(self) -> None:
        xml = cloud.build_cloud_envelope(
            "get-device-list",
            "<devlist></devlist>",
            client_id="000-4108-aabbccddeeff0011",
        )
        self.assertIn("<flag>tdkcloud</flag>", xml)
        self.assertIn("<command>get-device-list</command>", xml)
        self.assertIn("<oem>G0108</oem>", xml)
        self.assertIn("<app>4108</app>", xml)
        # content must precede header (mirrors the app's SimpleXML bean order)
        self.assertLess(xml.index("<content>"), xml.index("<header>"))


class ParseDevicesTests(unittest.TestCase):
    SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
    <envelope>
      <content>
        <devlist>
          <device>
            <uid>abc123</uid>
            <name>Hall door</name>
            <ip>192.168.1.50</ip>
            <cgiport>443</cgiport>
            <password>dynpwd</password>
            <model>IDS-7114</model>
          </device>
          <device>
            <uid>abc123</uid>
            <ip>192.168.1.50</ip>
          </device>
        </devlist>
      </content>
      <header><command>get-device-list</command></header>
    </envelope>
    """

    def test_parse_devices(self) -> None:
        devices = cloud.parse_devices(self.SAMPLE)
        self.assertEqual(len(devices), 1)  # duplicate uid filtered
        dev = devices[0]
        self.assertEqual(dev.uid, "abc123")
        self.assertEqual(dev.name, "Hall door")
        self.assertEqual(dev.ip, "192.168.1.50")
        self.assertEqual(dev.cgi_port, 443)
        self.assertEqual(dev.password, "dynpwd")
        self.assertEqual(dev.model, "IDS-7114")

    def test_parse_devices_garbage(self) -> None:
        self.assertEqual(cloud.parse_devices("not xml"), [])


if __name__ == "__main__":
    unittest.main()
