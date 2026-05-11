"""Normalize API result dicts for UI display (success flag + non-empty messages)."""

from __future__ import annotations

from typing import Any, Mapping


def coerce_api_success(result: Mapping[str, Any] | None) -> bool:
    """Coerce ``result['success']`` (and common ``status`` fallbacks) to a real bool.

    Backends sometimes send ``"false"`` / ``"true"`` strings; plain ``bool()`` would
    mis-classify ``"false"`` as success. Used for UI coloring and messages.
    """
    if not isinstance(result, Mapping):
        return False
    raw = result.get("success")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in ("false", "0", "no", "fail", "failed", "error"):
            return False
        if s in ("true", "1", "yes", "success", "ok"):
            return True
        return False
    if raw is None:
        st = result.get("status")
        if isinstance(st, str):
            u = st.strip().upper()
            if u in ("FAILURE", "FAILED", "FAIL", "ERROR", "FALSE", "0"):
                return False
            if u in ("SUCCESS", "OK", "SUCCEEDED", "200", "201", "TRUE", "1"):
                return True
        nested = result.get("data")
        if isinstance(nested, Mapping):
            nst = nested.get("status")
            if isinstance(nst, str):
                nu = nst.strip().upper()
                if nu in ("FAILURE", "FAILED", "FAIL", "ERROR", "FALSE", "0"):
                    return False
                if nu in ("SUCCESS", "OK", "SUCCEEDED", "200", "201", "TRUE", "1"):
                    return True
            if nested.get("success") is False:
                return False
            ns = nested.get("success")
            if isinstance(ns, str) and ns.strip().lower() in ("false", "0", "no", "fail", "failed", "error"):
                return False
        return False
    if isinstance(raw, (int, float)):
        return raw != 0
    return bool(raw)


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
    ok = coerce_api_success(result)
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
