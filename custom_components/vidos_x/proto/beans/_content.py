"""Shared ``<content>`` builder for bean serialization (XML-escaped)."""

from __future__ import annotations

from xml.sax.saxutils import escape


def content(*pairs: tuple[str, object]) -> str:
    """Build ``<content><tag>value</tag>…</content>`` with escaped values."""
    inner = "".join(
        f"<{tag}>{escape(str(value))}</{tag}>" for tag, value in pairs
    )
    return f"<content>{inner}</content>"
