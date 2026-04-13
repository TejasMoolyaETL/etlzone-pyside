"""Shared UI helpers for user-role assignment flows (status choices, validity widgets, form rows)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QFormLayout, QLineEdit, QSizePolicy, QWidget

from app.user_management.users.user_create import _DatePickerEdit
from app.user_management.users.user_view import LABEL_STYLE, READONLY_INPUT_STYLE
from ui.form_page_styles import FORM_SINGLELINE_FIELD_HEIGHT_PX
from ui.widgets.required_label import field_caption_label

_STATUS_CHOICES = ("ACTIVE", "INACTIVE", "BLOCKED")

_VIEW_USER_ID_KEYS = ("id", "userId", "user_id")
_VIEW_USERNAME_KEYS = ("username", "userName", "user_name")

_VIEW_USER_FIELD_HEIGHT = FORM_SINGLELINE_FIELD_HEIGHT_PX

_DEFAULT_ROLE_ASSIGNMENT_KEYS = ("defaultRole", "default_role", "defaultrole")


def _default_role_checked_from_assignment(row: dict[str, Any], *, fallback: bool) -> bool:
    """Checkbox state from assignment dict; ``fallback`` when no usable flag (e.g. add vs edit)."""
    for k in _DEFAULT_ROLE_ASSIGNMENT_KEYS:
        if k not in row:
            continue
        v = row[k]
        if v is None:
            continue
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return v != 0
        s = str(v).strip().lower()
        if s in ("true", "1", "yes", "y", "on"):
            return True
        if s in ("false", "0", "no", "n", "off"):
            return False
    return fallback


def _add_view_user_form_row(form: QFormLayout, caption: str, field: QWidget) -> None:
    """Label and control on one row; captions match ViewUserPage (field_caption_label + LABEL_STYLE)."""
    lbl = field_caption_label(caption, LABEL_STYLE, required=False)
    lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    form.addRow(lbl, field)


def _normalize_role_name(role_text: str) -> str:
    r = (role_text or "").strip()
    if r.upper().startswith("ROLE_"):
        r = r[5:]
    return r


def _normalize_status_name(status_text: str) -> str:
    s = (status_text or "").strip().upper()
    if s == "DEACTIVE":
        return "INACTIVE"
    return s


def _qdate_from_validity_raw(text: str) -> QDate | None:
    """Parse API validity string to QDate (date part only; same idea as role-assignment / API)."""
    t = (text or "").strip()
    if not t or t == "\u2014":
        return None
    part = t.split("T", 1)[0].strip().split(" ", 1)[0]
    d = QDate.fromString(part, "yyyy-MM-dd")
    if d.isValid():
        return d
    return None


def _display_validity_cell(raw: str) -> str:
    s = (raw or "").strip()
    return s


def _make_current_validity_widget(
    raw: str, *, field_height: int, min_width: int
) -> QWidget:
    """Same _DatePickerEdit look as New valid from/to; disabled when a date exists; else empty read-only line."""
    qd = _qdate_from_validity_raw(raw)
    if qd is not None:
        w = _DatePickerEdit()
        w.setDate(qd)
        w.setEnabled(False)
        w.setMinimumWidth(min_width)
        w.setFixedHeight(field_height)
        w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return w
    empty = QLineEdit(_display_validity_cell(raw))
    empty.setReadOnly(True)
    empty.setFixedHeight(field_height)
    empty.setMinimumWidth(min_width)
    empty.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    empty.setStyleSheet(READONLY_INPUT_STYLE)
    return empty
