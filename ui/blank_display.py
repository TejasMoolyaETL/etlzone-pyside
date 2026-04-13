"""When a field has no meaningful value, show an empty string in tables, views, and modals (not 0, not em dash)."""

from __future__ import annotations

from typing import Any

_EM_DASH = "\u2014"


def is_blank_display_value(value: Any) -> bool:
    """True for None, whitespace-only strings, numeric/string zero, empty collections, and legacy placeholder dash."""
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)) and value == 0:
        return True
    if isinstance(value, str):
        t = value.strip()
        if not t or t == "0":
            return True
        low = t.lower()
        if low in ("null", "none", "undefined", "n/a"):
            return True
        if t in ("-", _EM_DASH, "\u2013"):  # hyphen, en dash
            return True
        return False
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False
