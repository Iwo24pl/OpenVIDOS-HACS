"""Unit tests for the ring-picture-log watcher (no Home Assistant)."""

from __future__ import annotations

import unittest
from unittest import mock

from _load import load_module

env = load_module("proto.envelope")
records = load_module("proto.records")
models = load_module("proto.models")


def session_response(session_id: str) -> env.CgiResponse:
    return env.CgiResponse(
        error=0,
        content="",
        raw=(
            "<response><error>0</error><content><record>"
            f"<id>{session_id}</id>"
            "</record></content></response>"
        ),
    )


def data_block(
    channel: int, starttime: str, filename: str, filetype: str = "picture"
) -> str:
    return (
        "<data>"
        f"<filetype>{filetype}</filetype>"
        "<occurtype>unknown</occurtype>"
        f"<channel>{channel}</channel>"
        f"<starttime>{starttime}</starttime>"
        "<endtime>2026-09-30t14:38:09z</endtime>"
        f"<filename>{filename}</filename>"
        "<filesize>20480</filesize>"
        "</data>"
    )


def message_response(*blocks: str) -> env.CgiResponse:
    body = "".join(blocks)
    return env.CgiResponse(
        error=0,
        content="",
        raw=(
            "<response><error>0</error><content><record><datalist>"
            f"{body}"
            "</datalist></record></content></response>"
        ),
    )


EMPTY_PAGE = message_response()


class FakeClient:
    """Queued get.record.* responses, one per call."""

    def __init__(self, responses: list[env.CgiResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str | None]] = []

    async def async_command(self, command, content=None, *, require_ok=True):
        self.calls.append((command, content))
        if not self._responses:
            raise AssertionError(f"unexpected command: {command}")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_watcher(client, **kwargs):
    events: list[tuple[int | None, str]] = []
    watcher = records.RecordRingWatcher(
        client, on_ring=lambda ch, ts: events.append((ch, ts)), **kwargs
    )
    return watcher, events


OLD_1 = data_block(1, "2026-09-30t14:38:07z", "/mnt/sd/record/a_1.jpg")
OLD_2 = data_block(1, "2026-09-30t15:24:10z", "/mnt/sd/record/b_1.jpg")
NEW_2 = data_block(2, "2026-09-30t16:00:00z", "/mnt/sd/record/c_2.jpg")
STALE = data_block(1, "2026-09-30t14:00:00z", "/mnt/sd/record/old_1.jpg")


class ParseTests(unittest.TestCase):
    def test_parse_records_extracts_channel_time_file(self) -> None:
        found = records.parse_records(message_response(OLD_1, NEW_2).raw)
        self.assertEqual(len(found), 2)
        self.assertEqual(found[0].channel, 1)
        self.assertEqual(found[0].starttime, "2026-09-30t14:38:07z")
        self.assertEqual(found[0].filename, "/mnt/sd/record/a_1.jpg")
        self.assertEqual(found[1].channel, 2)

    def test_parse_records_skips_blocks_without_filename(self) -> None:
        raw = "<data><channel>1</channel></data>" + OLD_1
        self.assertEqual(len(records.parse_records(raw)), 1)

    def test_parse_records_bad_channel_is_none(self) -> None:
        block = data_block(99, "2026-09-30t14:38:07z", "/mnt/x.jpg")
        block = block.replace("<channel>99</channel>", "<channel>x</channel>")
        found = records.parse_records(message_response(block).raw)
        self.assertEqual(found[0].channel, None)

    def test_sort_time_normalizes_device_iso(self) -> None:
        rec = records.RingRecord(
            channel=1, starttime="2026-09-30t14:38:07z", filename="f"
        )
        self.assertEqual(rec.sort_time, "2026-09-30T14:38:07")


class RequestContentTests(unittest.TestCase):
    def test_session_content_uses_safe_picture_params(self) -> None:
        from datetime import datetime

        content = records.build_session_content(
            "1,2", datetime(2026, 9, 30, 14, 0, 0), datetime(2026, 9, 30, 15, 0, 0)
        )
        self.assertIn("<filetype>picture</filetype>", content)
        self.assertNotIn("<filetype>all</filetype>", content)
        self.assertIn("<channels>1,2</channels>", content)
        self.assertIn("<starttime>2026-09-30T14:00:00</starttime>", content)
        self.assertIn("<endtime>2026-09-30T15:00:00</endtime>", content)
        self.assertIn("<occurtype>all</occurtype>", content)
        self.assertIn("<stream>all</stream>", content)

    def test_message_content(self) -> None:
        self.assertEqual(
            records.build_message_content("7"),
            "<content><record><id>7</id></record></content>",
        )


class WatcherTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(records, "PAGE_GAP_SECONDS", 0.0)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_baseline_cycles_do_not_fire(self) -> None:
        client = FakeClient(
            [
                session_response("7"),
                message_response(OLD_1, OLD_2),
                EMPTY_PAGE,
                message_response(OLD_1, OLD_2),
                EMPTY_PAGE,
            ]
        )
        watcher, events = make_watcher(client)
        await watcher.async_once()
        await watcher.async_once()
        self.assertEqual(events, [])
        kinds = [cmd for cmd, _ in client.calls]
        self.assertEqual(kinds.count("get.record.session"), 1)

    async def test_new_record_fires_with_channel(self) -> None:
        client = FakeClient(
            [
                session_response("7"),
                message_response(OLD_1, OLD_2),
                EMPTY_PAGE,
                message_response(OLD_1, OLD_2),
                EMPTY_PAGE,
                message_response(OLD_1, OLD_2, NEW_2),
                EMPTY_PAGE,
            ]
        )
        watcher, events = make_watcher(client)
        await watcher.async_once()
        await watcher.async_once()
        await watcher.async_once()
        self.assertEqual(events, [(2, "2026-09-30t16:00:00z")])

    async def test_same_record_never_fires_twice(self) -> None:
        client = FakeClient(
            [
                session_response("7"),
                message_response(OLD_1),
                EMPTY_PAGE,
                message_response(OLD_1),
                EMPTY_PAGE,
                message_response(OLD_1, NEW_2),
                EMPTY_PAGE,
                message_response(OLD_1, NEW_2),
                EMPTY_PAGE,
            ]
        )
        watcher, events = make_watcher(client)
        for _ in range(4):
            await watcher.async_once()
        self.assertEqual(len(events), 1)

    async def test_stale_leftover_after_truncated_read_is_suppressed(self) -> None:
        client = FakeClient(
            [
                session_response("7"),
                message_response(OLD_2),
                EMPTY_PAGE,
                message_response(OLD_2),
                EMPTY_PAGE,
                message_response(STALE, OLD_2),
                EMPTY_PAGE,
            ]
        )
        watcher, events = make_watcher(client)
        await watcher.async_once()
        await watcher.async_once()
        await watcher.async_once()
        self.assertEqual(events, [])

    async def test_unsupported_firmware_sets_flag_and_raises(self) -> None:
        client = FakeClient(
            [env.CgiResponse(error=-10, content="", raw="<response><error>-10</error></response>")]
        )
        watcher, events = make_watcher(client)
        with self.assertRaises(env.VidosCgiCommandError):
            await watcher.async_once()
        self.assertTrue(watcher.unsupported)
        self.assertEqual(events, [])

    async def test_message_error_reopens_session(self) -> None:
        client = FakeClient(
            [
                session_response("7"),
                message_response(OLD_1),
                EMPTY_PAGE,
                message_response(OLD_1),
                EMPTY_PAGE,
                env.CgiResponse(error=-10029, content="", raw="<response><error>-10029</error></response>"),
                session_response("8"),
                message_response(OLD_1),
                EMPTY_PAGE,
            ]
        )
        watcher, events = make_watcher(client)
        await watcher.async_once()
        await watcher.async_once()
        with self.assertRaises(env.VidosCgiCommandError):
            await watcher.async_once()
        await watcher.async_once()  # reopens session "8"
        kinds = [cmd for cmd, _ in client.calls]
        self.assertEqual(kinds.count("get.record.session"), 2)
        self.assertEqual(events, [])

    async def test_run_stops_on_unsupported(self) -> None:
        client = FakeClient(
            [env.CgiResponse(error=-1, content="", raw="<response><error>-1</error></response>")]
        )
        watcher, _ = make_watcher(client)
        await watcher.async_run()  # must return, not loop forever
        self.assertTrue(watcher.unsupported)

    async def test_stop_flag_ends_run(self) -> None:
        client = FakeClient([])
        watcher, _ = make_watcher(client)
        watcher.stop()
        await watcher.async_run()


class DedupTests(unittest.TestCase):
    def test_within_window_is_duplicate(self) -> None:
        from datetime import datetime

        now = datetime(2026, 9, 30, 16, 0, 5)
        last = datetime(2026, 9, 30, 16, 0, 0)
        self.assertTrue(models.rung_is_duplicate(last, now, 10.0))

    def test_beyond_window_is_not_duplicate(self) -> None:
        from datetime import datetime

        now = datetime(2026, 9, 30, 16, 0, 20)
        last = datetime(2026, 9, 30, 16, 0, 0)
        self.assertFalse(models.rung_is_duplicate(last, now, 10.0))

    def test_no_previous_rung(self) -> None:
        from datetime import datetime

        self.assertFalse(
            models.rung_is_duplicate(None, datetime(2026, 9, 30, 16, 0, 0), 10.0)
        )


if __name__ == "__main__":
    unittest.main()
