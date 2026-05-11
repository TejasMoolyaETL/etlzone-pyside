"""Show success/error text on a QLabel; success clears after a delay, errors stay until cleared."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTableWidget,
    QTextEdit,
    QWidget,
)

from ui.form_page_styles import FORM_ERROR_LABEL_STYLE, MODAL_FEEDBACK_SUCCESS_STYLE

DEFAULT_HIDE_MS = 4500

# Success: same green as modal feedback; errors: shared form error red (global).
_STYLE_SUCCESS = MODAL_FEEDBACK_SUCCESS_STYLE


def _timer_attr(label: QLabel) -> str:
    return f"_auto_hide_timer_{id(label)}"


def _kind_attr(label: QLabel) -> str:
    return f"_auto_hide_kind_{id(label)}"


def _activity_hook_attr(label: QLabel) -> str:
    return f"_auto_hide_activity_hook_{id(label)}"


def _sticky_until_attr(label: QLabel) -> str:
    """Monotonic deadline; while ``time.monotonic() < deadline``, ignore activity-driven clears."""
    return f"_auto_hide_sticky_until_{id(label)}"


def cancel_auto_hide_message(owner: QObject, label: QLabel) -> None:
    attr = _timer_attr(label)
    timer = getattr(owner, attr, None)
    if isinstance(timer, QTimer):
        timer.stop()
        timer.deleteLater()
    setattr(owner, attr, None)
    setattr(owner, _sticky_until_attr(label), 0.0)
    try:
        label.setStyleSheet("")
    except RuntimeError:
        pass


def _is_descendant(ancestor: QWidget, widget: QWidget | None) -> bool:
    w = widget
    while w is not None:
        if w is ancestor:
            return True
        w = w.parentWidget()
    return False


def _clear_error_if_showing(owner: QObject, label: QLabel) -> None:
    until = getattr(owner, _sticky_until_attr(label), 0.0)
    try:
        if isinstance(until, (int, float)) and float(until) > 0.0 and time.monotonic() < float(until):
            return
    except (TypeError, ValueError):
        pass
    if getattr(owner, _kind_attr(label), None) != "error":
        return
    if not (label.text() or "").strip():
        setattr(owner, _kind_attr(label), None)
        setattr(owner, _sticky_until_attr(label), 0.0)
        return
    cancel_auto_hide_message(owner, label)
    label.setText("")
    label.setStyleSheet("")
    label.setVisible(False)
    setattr(owner, _kind_attr(label), None)
    setattr(owner, _sticky_until_attr(label), 0.0)


def _attach_clear_error_on_activity(page: QWidget, label: QLabel) -> None:
    """Clear persistent error when user interacts inside this page (focus, typing, table, etc.)."""
    app = QApplication.instance()
    if app is None:
        return

    def on_activity(*_args: object) -> None:
        try:
            if not page.isVisible():
                return
        except RuntimeError:
            return
        _clear_error_if_showing(page, label)

    def on_focus(_old: QWidget | None, now: QWidget | None) -> None:
        try:
            if not page.isVisible():
                return
        except RuntimeError:
            return
        if now is None or now is label:
            return
        if not _is_descendant(page, now):
            return
        _clear_error_if_showing(page, label)

    app.focusChanged.connect(on_focus)

    def _disconnect() -> None:
        try:
            app.focusChanged.disconnect(on_focus)
        except (TypeError, RuntimeError):
            pass

    page.destroyed.connect(_disconnect)

    for w in page.findChildren(QLineEdit):
        if _is_descendant(page, w) and w is not label:
            w.textChanged.connect(on_activity)
    for w in page.findChildren(QPlainTextEdit):
        if _is_descendant(page, w) and w is not label:
            w.textChanged.connect(on_activity)
    for w in page.findChildren(QTextEdit):
        if _is_descendant(page, w) and w is not label:
            w.textChanged.connect(on_activity)
    for w in page.findChildren(QComboBox):
        if _is_descendant(page, w):
            w.currentIndexChanged.connect(on_activity)
    for w in page.findChildren(QCheckBox):
        if _is_descendant(page, w):
            w.toggled.connect(on_activity)
    for w in page.findChildren(QAbstractSpinBox):
        if _is_descendant(page, w):
            w.valueChanged.connect(on_activity)
    for w in page.findChildren(QTableWidget):
        if _is_descendant(page, w):
            w.itemSelectionChanged.connect(on_activity)


def _ensure_clear_error_on_activity(owner: QObject, label: QLabel) -> None:
    if not isinstance(owner, QWidget):
        return
    attr = _activity_hook_attr(label)
    if getattr(owner, attr, False):
        return
    setattr(owner, attr, True)
    _attach_clear_error_on_activity(owner, label)


def show_auto_hiding_message(
    owner: QObject,
    label: QLabel,
    text: str,
    *,
    error: bool = True,
    hide_ms: int | None = None,
    style_sheet: str | None = None,
    clear_on_user_activity: bool = True,
) -> None:
    """Show message on label. Success auto-hides after hide_ms; errors stay until cleared.

    hide_ms None: success uses DEFAULT_HIDE_MS; errors never auto-hide (same as hide_ms=0).
    Explicit hide_ms (including 0) applies to both success and error.

    For QWidget owners, persistent errors are cleared when the user focuses another control
    in the same page, edits a field, or changes table or combo selection. When
    clear_on_user_activity is False (e.g. load-time failures), a short grace period ignores those
    clears right after the message appears so layout and programmatic combo updates do not
    remove it instantly.
    """
    cancel_auto_hide_message(owner, label)
    _ensure_clear_error_on_activity(owner, label)
    if not (text or "").strip():
        setattr(owner, _kind_attr(label), None)
        setattr(owner, _sticky_until_attr(label), 0.0)
        label.setText("")
        label.setStyleSheet("")
        label.setVisible(False)
        return
    if style_sheet is not None:
        label.setStyleSheet(style_sheet)
    else:
        label.setStyleSheet(FORM_ERROR_LABEL_STYLE if error else _STYLE_SUCCESS)
    label.setText(text)
    label.setVisible(True)
    setattr(owner, _kind_attr(label), "error" if error else "success")
    # Global safeguard: avoid instant error disappearance when handlers set focus
    # right after showing an error (common in validation flows).
    if error:
        sticky_for_s = 0.5 if clear_on_user_activity else 0.8
        setattr(owner, _sticky_until_attr(label), time.monotonic() + sticky_for_s)
    else:
        setattr(owner, _sticky_until_attr(label), 0.0)
    if hide_ms is None:
        ms = 0 if error else DEFAULT_HIDE_MS
    else:
        ms = int(hide_ms)
    if ms <= 0:
        return
    attr = _timer_attr(label)
    old = getattr(owner, attr, None)
    if isinstance(old, QTimer):
        old.stop()
        old.deleteLater()
    timer = QTimer(owner)
    setattr(owner, attr, timer)
    timer.setSingleShot(True)

    def _clear() -> None:
        try:
            label.setText("")
            label.setStyleSheet("")
            label.setVisible(False)
            setattr(owner, _kind_attr(label), None)
            setattr(owner, _sticky_until_attr(label), 0.0)
        except RuntimeError:
            pass

    timer.timeout.connect(_clear)
    timer.start(ms)


def show_api_result_message(
    owner: QObject,
    label: QLabel,
    result: Mapping[str, Any],
    *,
    error_fallback: str,
    success_fallback: str = "",
) -> bool:
    """Display ``result`` from ``core.api`` helpers on ``label``.

    Uses :func:`core.api_result.user_message_for_api_result` so errors never
    show as blank when the backend omits ``message``. Returns ``True`` if
    ``result["success"]`` is truthy.
    """
    from core.api_result import user_message_for_api_result

    ok, text = user_message_for_api_result(
        result,
        error_fallback=error_fallback,
        success_fallback=success_fallback,
    )
    show_auto_hiding_message(owner, label, text, error=not ok)
    return ok
