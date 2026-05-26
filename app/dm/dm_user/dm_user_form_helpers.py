"""Shared email/mobile helpers for DM User create and update forms."""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QSizePolicy, QWidget

from core.validators import COUNTRY_CODES, parse_mobile, validate_mobile
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_PAGE_FONT_SIZE_PX,
    FORM_READONLY_INPUT_STYLE as READONLY_INPUT_STYLE,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    MODAL_FIELD_HEIGHT_PX,
)

_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

DM_USER_STATUS_FIELD_NAME = "dm_user_status"


def create_mobile_field_row(*, field_h: int | None = None) -> tuple[QWidget, QComboBox, QLineEdit]:
    """Country code combo + national number field (same layout as User Management Create User)."""
    h = field_h if field_h is not None else MODAL_FIELD_HEIGHT_PX
    container = QWidget()
    container.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
    row = QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)
    country = QComboBox()
    for code, country_name in COUNTRY_CODES:
        country.addItem(f"{country_name} ({code})", code)
    apply_form_combobox_field(country, height_px=h, min_width=120)
    number = QLineEdit()
    number.setValidator(QRegularExpressionValidator(QRegularExpression(r"^\d*$")))
    number.setStyleSheet(INPUT_STYLE)
    number.setFixedHeight(h)
    number.setMinimumWidth(120)
    number.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    row.addWidget(country)
    row.addWidget(number, 1)
    return container, country, number


def wire_mobile_live_validation(country: QComboBox, number: QLineEdit) -> None:
    country.currentIndexChanged.connect(lambda: update_mobile_style(country, number))
    number.textChanged.connect(lambda: update_mobile_style(country, number))


def update_email_style(widget: QLineEdit, text: str, *, readonly: bool = False) -> None:
    if readonly:
        widget.setStyleSheet(READONLY_INPUT_STYLE)
        return
    base = f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; padding: 4px 8px; border-radius: 4px; background-color: #ffffff;"
    if not text.strip():
        widget.setStyleSheet(f"{base} border: 1px solid #e2e8f0;")
    elif _EMAIL_REGEX.match(text.strip()):
        widget.setStyleSheet(f"{base} border: 1px solid #22c55e;")
    else:
        widget.setStyleSheet(f"{base} border: 1px solid #ef4444;")


def update_mobile_style(country: QComboBox, number: QLineEdit, *, readonly: bool = False) -> None:
    if readonly:
        number.setStyleSheet(READONLY_INPUT_STYLE)
        return
    base = f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; padding: 4px 8px; border-radius: 4px; background-color: #ffffff;"
    national = number.text().strip()
    country_code = country.currentData() or "+91"
    if not national:
        number.setStyleSheet(f"{base} border: 1px solid #e2e8f0;")
    else:
        valid, _ = validate_mobile(country_code, national)
        color = "#22c55e" if valid else "#ef4444"
        number.setStyleSheet(f"{base} border: 1px solid {color};")


def mobile_parts_from_record(rec: dict[str, Any]) -> tuple[str, str]:
    """Return (country_code, national_digits) from a user record."""
    cc_raw = rec.get("countryCode") or rec.get("country_code")
    if cc_raw is not None and str(cc_raw).strip():
        national = (
            rec.get("mobile")
            or rec.get("mobileNumber")
            or rec.get("mobile_number")
            or ""
        )
        return str(cc_raw).strip(), str(national).strip()
    combined = (
        rec.get("mobile")
        or rec.get("mobileNumber")
        or rec.get("mobile_number")
        or ""
    )
    return parse_mobile(str(combined) if combined is not None else None)


def apply_mobile_to_widgets(
    country: QComboBox,
    number: QLineEdit,
    rec: dict[str, Any],
) -> None:
    cc, national = mobile_parts_from_record(rec)
    country.blockSignals(True)
    number.blockSignals(True)
    while country.count() > 0 and country.itemText(0).startswith("Other ("):
        country.removeItem(0)
    idx = country.findData(cc)
    if idx >= 0:
        country.setCurrentIndex(idx)
    else:
        country.insertItem(0, f"Other ({cc})", cc)
        country.setCurrentIndex(0)
    number.setText(national or "")
    country.blockSignals(False)
    number.blockSignals(False)
    update_mobile_style(country, number, readonly=number.isReadOnly())


def validate_email_input(email: str) -> str | None:
    if not email.strip():
        return "Email is required."
    if not _EMAIL_REGEX.match(email.strip()):
        return "Please enter a valid email address."
    return None


def validate_mobile_input(country: QComboBox, number: QLineEdit) -> tuple[str | None, str, str]:
    """Return (error_message, country_code, national_digits)."""
    country_code = str(country.currentData() or "+91").strip()
    national = number.text().strip()
    if not national:
        return "Mobile number is required.", country_code, national
    valid, msg = validate_mobile(country_code, national)
    if not valid:
        return msg or "Invalid mobile number.", country_code, national
    return None, country_code, national


def full_mobile_number(country_code: str, national_digits: str) -> str:
    """Merge country code and national digits for DM user API ``mobile`` field (E.164-style)."""
    cc = str(country_code or "+91").strip()
    num = str(national_digits or "").strip().replace(" ", "").replace("-", "")
    if not num:
        return ""
    if num.startswith("+"):
        return num
    return f"{cc}{num}"
