"""Test helper: load proto modules by file path (no Home Assistant needed).

Registers stub packages ``vidos_x`` and ``vidos_x.proto`` pointing at
``custom_components/vidos_x`` so relative imports inside the proto package
resolve without executing the integration's ``__init__`` (which imports HA).
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

PKG_DIR = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "vidos_x"
PKG_NAME = "vidos_x"
PROTO_NAME = f"{PKG_NAME}.proto"
PROTO_DIR = PKG_DIR / "proto"


def _ensure_packages() -> None:
    if PKG_NAME not in sys.modules:
        pkg = types.ModuleType(PKG_NAME)
        pkg.__path__ = [str(PKG_DIR)]
        sys.modules[PKG_NAME] = pkg
    if PROTO_NAME not in sys.modules:
        proto = types.ModuleType(PROTO_NAME)
        proto.__path__ = [str(PROTO_DIR)]
        proto.__package__ = PROTO_NAME
        sys.modules[PROTO_NAME] = proto


def load_module(name: str):
    """Load ``custom_components/vidos_x/<name>``.

    ``name`` is a package-relative dotted path: ``const`` (flat integration
    module), ``proto.envelope``, ``proto.beans`` (package), ...
    """
    _ensure_packages()
    full_name = name if name.startswith(PKG_NAME) else f"{PKG_NAME}.{name}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    rel = full_name.split(".")[1:]  # strip "vidos_x"
    if rel[0] == "proto":
        base = PROTO_DIR.joinpath(*rel[1:])
    else:
        base = PKG_DIR.joinpath(*rel)
    if base.is_dir() and (base / "__init__.py").is_file():
        path = base / "__init__.py"
        spec = importlib.util.spec_from_file_location(
            full_name, path, submodule_search_locations=[str(base)]
        )
    else:
        path = base.with_suffix(".py")
        spec = importlib.util.spec_from_file_location(full_name, path)
    assert spec and spec.loader, f"cannot load {full_name} from {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module
