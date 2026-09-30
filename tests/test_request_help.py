"""Unit tests for milestone-1 command constants + content builders."""

from __future__ import annotations

import unittest

from _load import load_module

beans = load_module("proto.beans")
rh = load_module("proto.request_help")


class CommandConstantTests(unittest.TestCase):
    def test_dex_command_strings_verbatim(self) -> None:
        self.assertEqual(rh.COMMAND_GET_DEVICE_STATUS, "get.device.status")
        self.assertEqual(rh.COMMAND_GET_DEVICE_SECRET, "get.device.streamkey")
        self.assertEqual(rh.COMMAND_OPEN_DOOR, "set.device.opendoor")
        self.assertEqual(rh.COMMAND_GET_HEADER_CONTENT, "get.header.content")
        self.assertEqual(rh.COMMAND_GET_LIVE_STATUS, "get.live.status")
        self.assertEqual(rh.COMMAND_GET_ATTACHMENT_INFO, "get.device.attachInfo")
        self.assertEqual(
            rh.COMMAND_MODIFY_VERIFICATION_CODE, "set.seurity.verifycode"
        )


class UnlockContentTests(unittest.TestCase):
    def test_device_unlock_wire_tags(self) -> None:
        # channelNum/lockNum -> door/locknumber (@Element renames, hw-verified)
        content = rh.unlock_content(2, 1, "cafe")
        self.assertEqual(
            content,
            "<content><door>2</door><locknumber>1</locknumber>"
            "<password>cafe</password></content>",
        )

    def test_device_unlock_escapes_password(self) -> None:
        content = rh.unlock_content(0, 0, "a<b&c")
        self.assertIn("<password>a&lt;b&amp;c</password>", content)

    def test_open_lock_content(self) -> None:
        content = rh.open_lock_content(2, "pw")
        self.assertEqual(
            content, "<content><locknumber>2</locknumber><password>pw</password></content>"
        )

    def test_check_password_content(self) -> None:
        self.assertEqual(
            rh.check_password_content("1234"),
            "<content><password>1234</password></content>",
        )

    def test_set_password_keeps_bean_typo(self) -> None:
        content = rh.set_password_content("new", "old")
        self.assertIn("<newPasswrod>new</newPasswrod>", content)
        self.assertIn("<oldPassword>old</oldPassword>", content)

    def test_streamkey_content_carries_authcode(self) -> None:
        self.assertEqual(
            rh.streamkey_content("4366"),
            "<content><authcode>4366</authcode></content>",
        )
        self.assertEqual(rh.streamkey_content(), "<content><authcode></authcode></content>")


class BeanShapeTests(unittest.TestCase):
    def test_record_session_content(self) -> None:
        rec = beans.Record(
            channels="1,2",
            startTime="2026-09-30T14:00:00",
            endTime="2026-09-30T15:00:00",
            fileType="picture",
            occurType="all",
            stream="all",
        )
        content = beans.GetRecordSessionContent(record=rec).to_content()
        self.assertIn("<filetype>picture</filetype>", content)
        self.assertIn("<channels>1,2</channels>", content)
        self.assertIn("<starttime>2026-09-30T14:00:00</starttime>", content)
        self.assertIn("<stream>all</stream>", content)

    def test_record_message_content_is_session_id_only(self) -> None:
        content = beans.GetRecordMessageContent(
            record=beans.Record(id="7")
        ).to_content()
        self.assertEqual(content, "<content><record><id>7</id></record></content>")

    def test_secret_resp_from_fields(self) -> None:
        resp = beans.GetDeviceSecretResp.from_fields(
            {"key": "streamkey", "synctime": "1", "tdc": "x"}
        )
        self.assertEqual(resp.key, "streamkey")

    def test_device_status_from_fields(self) -> None:
        status = beans.DeviceStatus.from_fields(
            {"calling": "true", "lockstatus": "false", "model": "IDS9483AW"}
        )
        self.assertTrue(status.calling)
        self.assertFalse(status.lockstatus)
        self.assertEqual(status.model, "IDS9483AW")


if __name__ == "__main__":
    unittest.main()
