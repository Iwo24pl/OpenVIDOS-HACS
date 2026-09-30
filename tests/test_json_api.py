"""Unit tests for layer-B JSON settings bodies (no Home Assistant)."""

from __future__ import annotations

import json
import unittest

from _load import load_module

beans = load_module("proto.beans")
json_api = load_module("proto.device_json_api")


class CommandTests(unittest.TestCase):
    def test_dex_command_strings(self) -> None:
        self.assertEqual(json_api.COMMAND_GET_AUTO_UNLOCK, "get.auto.unlock")
        self.assertEqual(json_api.COMMAND_SET_AUTO_UNLOCK, "set.auto.unlock")
        self.assertEqual(json_api.COMMAND_GET_CALL_TIME, "get.call.time")
        self.assertEqual(json_api.COMMAND_SET_HOLD_UNLOCK, "set.hold.unlock")

    def test_route_ids_recorded(self) -> None:
        self.assertEqual(json_api.ROUTE_IDS[json_api.COMMAND_GET_AUTO_UNLOCK], "$27")
        self.assertEqual(json_api.ROUTE_IDS[json_api.COMMAND_GET_CALL_TIME], "$26")
        self.assertEqual(json_api.ROUTE_IDS[json_api.COMMAND_GET_LOCK_STATUS], "$20")


class BodyTests(unittest.TestCase):
    def test_auto_unlock_get_body(self) -> None:
        body = json_api.auto_unlock_get_body(channel=1, lock=1)
        self.assertEqual(body["command"], "get.auto.unlock")
        self.assertEqual(body["content"], {"channel": 1, "lock": 1})

    def test_auto_unlock_set_body_serializes_schedule(self) -> None:
        slot = beans.AutoUnlockScheduleEntry(
            TIME1="", enabled=1, start="08:00", end="18:00", section=""
        )
        schedule = beans.AutoUnlockSchedule(mode=0, time=[slot], week="1111111")
        req = beans.SetDeviceAutoUnlockContentReq(
            channel=1,
            lock=1,
            apply=[{"channel": 1, "lock": 1}],
            schedule=[schedule],
        )
        body = json_api.auto_unlock_set_body(req)
        self.assertEqual(body["command"], "set.auto.unlock")
        self.assertEqual(len(body["content"]["schedule"]), 1)
        entry = body["content"]["schedule"][0]
        self.assertEqual(entry["mode"], 0)
        self.assertEqual(entry["week"], "1111111")
        self.assertEqual(entry["time"][0]["start"], "08:00")
        # round-trips as JSON
        again = json.loads(json_api.dumps(body))
        self.assertEqual(again["command"], "set.auto.unlock")

    def test_call_time_bodies(self) -> None:
        get_body = json_api.call_time_get_body(channel=2)
        self.assertEqual(get_body["content"], {"channel": 2})
        set_body = json_api.call_time_set_body(channel=2, time="30")
        self.assertEqual(set_body["command"], "set.call.time")
        self.assertEqual(set_body["content"], {"channel": 2, "time": "30"})


if __name__ == "__main__":
    unittest.main()
