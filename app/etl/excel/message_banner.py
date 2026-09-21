"""Shared inline alert banners for Excel All Import pages."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QLabel

from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message

_ALERT_BASE = (
    "font-size: 13px; font-weight: 500; border-radius: 6px; padding: 10px 14px; "
    "margin: 0;"
)

ALERT_ERROR_STYLE = (
    f"QLabel {{ {_ALERT_BASE} background: #fef2f2; color: #b91c1c; "
    "border: 1px solid #fecaca; }}"
)
ALERT_INFO_STYLE = (
    f"QLabel {{ {_ALERT_BASE} background: #eff6ff; color: #1d4ed8; "
    "border: 1px solid #bfdbfe; }}"
)
ALERT_SUCCESS_STYLE = (
    f"QLabel {{ {_ALERT_BASE} background: #f0fdf4; color: #15803d; "
    "border: 1px solid #bbf7d0; }}"
)


def configure_message_banner(label: QLabel) -> None:
    """Apply shared layout defaults for page alert labels."""
    label.setWordWrap(True)
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
    )
    label.setVisible(False)
    label.clear()


def friendly_error_text(message: str | None) -> str:
    """Normalize API / exception text into a short user-facing sentence."""
    text = " ".join(str(message or "").split()).strip()
    if not text:
        return "Something went wrong. Please try again."
    for prefix in (
        "Error:",
        "ERROR:",
        "Exception:",
        "HTTPError:",
        "URLError:",
        "Failed:",
    ):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    lower = text.lower()
    if "session expired" in lower or "unauthorized" in lower or "401" in lower:
        return "Session expired. Please log in again."
    if "not reachable" in lower or "timed out" in lower or "timeout" in lower:
        return "Backend not reachable. Check your connection and try again."
    if "403" in lower or "forbidden" in lower:
        return "You don’t have permission to complete this action."
    if "404" in lower or "not found" in lower:
        return "The requested import was not found."
    if len(text) > 220:
        return text[:217].rstrip() + "…"
    return text


def show_page_error(owner: QObject, label: QLabel, message: str | None) -> None:
    show_auto_hiding_message(
        owner,
        label,
        friendly_error_text(message),
        error=True,
        style_sheet=ALERT_ERROR_STYLE,
        clear_on_user_activity=True,
    )


def show_page_info(
    owner: QObject,
    label: QLabel,
    message: str,
    *,
    sticky: bool = True,
) -> None:
    show_auto_hiding_message(
        owner,
        label,
        str(message or "").strip(),
        error=False,
        hide_ms=0 if sticky else None,
        style_sheet=ALERT_INFO_STYLE,
        clear_on_user_activity=False,
    )


def show_page_success(owner: QObject, label: QLabel, message: str) -> None:
    show_auto_hiding_message(
        owner,
        label,
        str(message or "").strip(),
        error=False,
        style_sheet=ALERT_SUCCESS_STYLE,
        clear_on_user_activity=False,
    )


def clear_page_message(owner: QObject, label: QLabel) -> None:
    cancel_auto_hide_message(owner, label)
    label.clear()
    label.setStyleSheet("")
    label.setVisible(False)
