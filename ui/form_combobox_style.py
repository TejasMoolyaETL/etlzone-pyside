"""Shared QComboBox stylesheet for form dropdowns (uses :mod:`ui.form_page_styles`).

Use :func:`apply_form_combobox_field` after populating items so every combo matches the
Create API modal **HTTP method** row (style, fixed height, expanding width).

Vertical padding matches :data:`FORM_INPUT_STYLE` (2px) so combo height aligns with QLineEdit
when both use the same ``height_px`` (e.g. :data:`MODAL_FIELD_HEIGHT_PX` or
:data:`FORM_SINGLELINE_FIELD_HEIGHT_PX`).
"""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QSizePolicy

from ui.form_page_styles import APP_FONT_SIZE_PX

_fs = APP_FONT_SIZE_PX

FORM_COMBOBOX_STYLE = f"""
    QComboBox {{
        font-size: {_fs}px;
        font-weight: 400;
        color: #0f172a;
        margin: 0px;
        padding: 2px 22px 2px 8px;
        border: 1px solid #e2e8f0;
        border-radius: 4px;
        background-color: #ffffff;
        outline: none;
    }}
    QComboBox:disabled {{
        color: #64748b;
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
    }}
    QComboBox:hover:enabled {{
        border-color: #94a3b8;
    }}
    QComboBox:focus:enabled {{
        border: 1px solid #334155;
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        border: none;
        margin: 0px;
        padding: 0px;
        width: 18px;
    }}
    QComboBox QAbstractItemView {{
        border: 1px solid #e2e8f0;
        outline: 0;
        background: #ffffff;
        border-radius: 4px;
        margin: 0px;
        padding: 0px;
        selection-background-color: #e2e8f0;
        selection-color: #0f172a;
        font-size: {_fs}px;
        font-weight: 400;
    }}
    QComboBox QAbstractItemView::item {{
        margin: 0px;
        padding: 1px 4px;
        min-height: 0px;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background-color: #f1f5f9;
    }}
    QComboBox QAbstractItemView::item:selected {{
        background-color: #eef2ff;
        color: #4338ca;
    }}
"""


def apply_form_combobox_field(
    combo: QComboBox,
    *,
    height_px: int,
    min_width: int | None = None,
) -> None:
    """Apply shared combo chrome (same as Create API → HTTP method in modal).

    Call after ``addItem`` / ``addItems`` / ``configure_api_method_combo`` so the widget
    is fully configured before styling.
    """
    combo.setStyleSheet(FORM_COMBOBOX_STYLE)
    combo.setFixedHeight(height_px)
    combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    if min_width is not None:
        combo.setMinimumWidth(min_width)
