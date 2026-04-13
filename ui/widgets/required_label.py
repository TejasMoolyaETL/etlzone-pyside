"""Field caption labels: mandatory fields use a red asterisk (Create User style)."""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget


def parse_mandatory_marker(label_text: str) -> tuple[str, bool]:
    """Trailing '*' in specs (e.g. 'API Method*') marks a required field."""
    t = label_text.rstrip()
    if t.endswith("*"):
        return t[:-1].rstrip(), True
    return t, False


def field_caption_label(
    label_text: str,
    plain_label_stylesheet: str,
    *,
    required: bool | None = None,
    muted_color: str = "#64748b",
    star_color: str = "#dc2626",
    font_size_px: int = 10,
) -> QLabel:
    """
    Plain label: ``Label:`` with ``plain_label_stylesheet``.
    Required: grey caption + red ``*`` + ``:`` (RichText), matching Create User.
    If ``required`` is None, a trailing ``*`` on ``label_text`` sets required.
    ``muted_color`` / ``star_color`` / ``font_size_px`` apply to the RichText spans only.
    """
    base, inferred = parse_mandatory_marker(label_text)
    req = inferred if required is None else bool(required)
    safe = html.escape(base)
    span_muted = (
        f"color:{muted_color};font-size:{font_size_px}px;font-weight:600;"
        f"letter-spacing:0.5px;text-transform:uppercase;"
    )
    span_star = f"color:{star_color};font-weight:700"
    # Use RichText for optional and required captions so Qt lays out the same height
    # (plain QLabel vs RichText QLabel otherwise mismatches vertical gap to the field below).
    w = QLabel()
    w.setTextFormat(Qt.TextFormat.RichText)
    w.setWordWrap(False)
    if not req:
        w.setText(f"<span style='{span_muted}'>{safe}:</span>")
    else:
        w.setText(
            f"<span style='{span_muted}'>{safe}</span>"
            f"<span style='{span_star}'>*</span>"
            f"<span style='{span_muted}'>:</span>"
        )
    w.setStyleSheet(plain_label_stylesheet)
    return w


def labeled_field_block(label: QWidget, field: QWidget, *, spacing_px: int | None = None) -> QWidget:
    """Stack a caption above a control with :data:`FORM_LABEL_FIELD_SPACING_PX` (tight) vertical gap."""
    from ui.form_page_styles import FORM_LABEL_FIELD_SPACING_PX

    sp = FORM_LABEL_FIELD_SPACING_PX if spacing_px is None else spacing_px
    block = QWidget()
    block.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    lay = QVBoxLayout(block)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(sp)
    lay.addWidget(label)
    lay.addWidget(field)
    return block
