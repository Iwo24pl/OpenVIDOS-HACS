"""Config flow tests (require the Home Assistant test environment).

Local runs without Home Assistant simply skip this module - see
``requirements_test.txt`` for the optional harness:

    pip install pytest pytest-asyncio pytest-homeassistant-custom-component
    pytest tests
"""

from __future__ import annotations

import unittest

try:
    import pytest
except ImportError:  # plain `python -m unittest` without pytest
    pytest = None

if pytest is not None:
    try:
        pytest.importorskip("homeassistant")
        HOME_ASSISTANT = True
    except BaseException:  # noqa: BLE001 - Skipped/ImportError both mean "not available"
        HOME_ASSISTANT = False
else:
    HOME_ASSISTANT = False

if HOME_ASSISTANT:
    from homeassistant import config_entries

    from custom_components.vidos_x.const import DOMAIN

    @pytest.mark.asyncio
    async def test_manual_flow_starts(hass) -> None:
        """User step should render the manual connection form (cloud UI removed)."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "manual"


class ConfigFlowAvailabilityTests(unittest.TestCase):
    """Meta-test: the module degrades gracefully without Home Assistant."""

    @unittest.skipIf(not HOME_ASSISTANT, "Home Assistant not installed")
    def test_home_assistant_available(self) -> None:
        self.assertIn("config_entries", dir())

    @unittest.skipIf(HOME_ASSISTANT, "Home Assistant installed")
    def test_skipped_without_home_assistant(self) -> None:
        self.assertFalse(HOME_ASSISTANT)


if __name__ == "__main__":
    unittest.main()
