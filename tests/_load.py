"""Test helper: load integration modules by file path (no Home Assistant needed)."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

PKG_DIR = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "vidos_x"
PKG_NAME = "vidos_x"


def _ensure_package() -> None:
    if PKG_NAME not in sys.modules:
        pkg = types.ModuleType(PKG_NAME)
        pkg.__path__ = [str(PKG_DIR)]
        sys.modules[PKG_NAME] = pkg


def load_module(name: str):
    """Load ``custom_components/vidos_x/<name>.py`` as part of a stub package."""
    _ensure_package()
    full_name = f"{PKG_NAME}.{name}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    spec = importlib.util.spec_from_file_location(full_name, PKG_DIR / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module
