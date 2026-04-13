"""Normalize API result dicts for UI display (success flag + non-empty messages)."""

from __future__ import annotations

from typing import Any, Mapping


def user_message_for_api_result(
    result: Mapping[str, Any],
    *,
    error_fallback: str,
    success_fallback: str = "",
) -> tuple[bool, str]:
    """Return (is_success, text) for showing the user.

    Failed results never return blank text: empty or missing ``message`` uses
    ``error_fallback``. Success uses ``message`` or ``success_fallback``.
    """
    ok = bool(result.get("success"))
    raw = result.get("message")
    if isinstance(raw, str):
        text = raw.strip()
    elif raw is not None:
        text = str(raw).strip()
    else:
        text = ""
    if ok:
        out = text or (success_fallback or "").strip()
        return True, out or "Done."
    out = text or (error_fallback or "").strip()
    return False, out or (error_fallback or "").strip() or "Something went wrong."
