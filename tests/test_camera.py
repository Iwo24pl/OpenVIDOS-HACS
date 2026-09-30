"""Camera platform tests.

Constants load without Home Assistant; platform gating follows the same
graceful-degradation pattern as ``test_config_flow.py``.
"""

from __future__ import annotations

import unittest

from _load import PKG_DIR, load_module

const = load_module("const")

try:
    import homeassistant  # noqa: F401

    HOME_ASSISTANT = True
except ImportError:  # plain `python -m unittest` without Home Assistant
    HOME_ASSISTANT = False


class CameraConstTests(unittest.TestCase):
    """Snapshot camera constants exist and are sane."""

    def test_camera_option_const(self) -> None:
        self.assertEqual(const.CONF_ENABLE_CAMERA, "enable_camera")
        self.assertTrue(const.DEFAULT_ENABLE_CAMERA)

    def test_snapshot_timings(self) -> None:
        self.assertGreater(const.SNAPSHOT_TTL_SECONDS, 0)
        self.assertGreaterEqual(
            const.SNAPSHOT_COOLDOWN_SECONDS, const.SNAPSHOT_TTL_SECONDS
        )
        self.assertGreaterEqual(
            const.SNAPSHOT_TIMEOUT_SECONDS, const.SNAPSHOT_TTL_SECONDS
        )
        self.assertGreater(const.STREAM_KEY_CACHE_SECONDS, 0)

    def test_camera_avoids_removed_ha_apis(self) -> None:
        """``hass.config.temp_dir`` was removed from HA core (500 regression)."""
        source = (PKG_DIR / "camera.py").read_text(encoding="utf-8")
        self.assertNotIn("config.temp_dir", source)


if HOME_ASSISTANT:
    from homeassistant.const import Platform

    from custom_components.vidos_x import _platforms_for_entry
    from custom_components.vidos_x.const import CONF_ENABLE_CAMERA

    class _FakeEntry:
        def __init__(self, options: dict) -> None:
            self.options = options

    class CameraPlatformTests(unittest.TestCase):
        """Platform gating for the snapshot camera."""

        def test_camera_on_by_default(self) -> None:
            self.assertIn(
                Platform.CAMERA, _platforms_for_entry(_FakeEntry({}))
            )

        def test_camera_off_when_disabled(self) -> None:
            self.assertNotIn(
                Platform.CAMERA,
                _platforms_for_entry(_FakeEntry({CONF_ENABLE_CAMERA: False})),
            )


if __name__ == "__main__":
    unittest.main()
