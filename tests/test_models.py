"""Unit tests for models.py (pure dataclasses, no HA needed)."""

from __future__ import annotations

import unittest

from _load import load_module

models = load_module("models")


class RingStartedTests(unittest.TestCase):
    def test_idle_to_ringing(self) -> None:
        self.assertTrue(
            models.ring_started({"calling": "false"}, {"calling": "true"})
        )

    def test_still_ringing_no_new_event(self) -> None:
        self.assertFalse(
            models.ring_started({"calling": "true"}, {"calling": "true"})
        )

    def test_ringing_to_idle(self) -> None:
        self.assertFalse(
            models.ring_started({"calling": "true"}, {"calling": "false"})
        )

    def test_first_poll_ringing_does_not_fire(self) -> None:
        # No previous poll yet - must not count as a fresh press
        self.assertFalse(models.ring_started(None, {"calling": "true"}))

    def test_missing_fields(self) -> None:
        self.assertFalse(models.ring_started({}, {}))
        self.assertFalse(models.ring_started(None, None))

    def test_alternate_field_names(self) -> None:
        self.assertTrue(models.ring_started({"ring": "0"}, {"ring": "1"}))
        self.assertTrue(models.ring_started({}, {"event": "ring"}))


class VidosStatusTests(unittest.TestCase):
    def test_ringing_property(self) -> None:
        self.assertTrue(models.VidosStatus(fields={"calling": "true"}).ringing)
        self.assertFalse(models.VidosStatus(fields={"calling": "false"}).ringing)
        self.assertFalse(models.VidosStatus().ringing)

    def test_lock_state_prefers_lockstatus(self) -> None:
        status = models.VidosStatus(fields={"lockstatus": "false"})
        self.assertEqual(status.lock_state, "false")

    def test_model_and_firmware(self) -> None:
        status = models.VidosStatus(
            fields={"model": "IDS9483AW", "version": "V100.R001"}
        )
        self.assertEqual(status.model, "IDS9483AW")
        self.assertEqual(status.firmware, "V100.R001")


if __name__ == "__main__":
    unittest.main()
