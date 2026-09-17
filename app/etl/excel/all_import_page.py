"""ETL: Excel — All Import (placeholder page for the left-nav item)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.form_page_styles import (
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
)
from ui.theme import Theme

_CARD_STYLE = f"""
    QFrame#allImportCard {{
        background: {Theme.BG_WHITE};
        border: 1px solid {Theme.BORDER_DEFAULT};
        border-radius: 10px;
    }}
    QLabel#allImportCardTitle {{
        color: {Theme.TEXT_PRIMARY};
        font-size: 15px;
        font-weight: 700;
        background: transparent;
        border: none;
    }}
    QLabel#allImportCardHint {{
        color: {Theme.TEXT_SECONDARY};
        font-size: 11px;
        background: transparent;
        border: none;
    }}
"""


class AllImportPage(QWidget):
    """Excel All Import section page."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        hl.addWidget(QLabel("Excel: All Import"))
        hl.addStretch()
        root.addWidget(header)

        body = QWidget()
        body.setStyleSheet(f"background: {Theme.BG_PAGE_ALT};")
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(24, 20, 24, 20)
        body_l.setSpacing(12)

        card = QFrame()
        card.setObjectName("allImportCard")
        card.setStyleSheet(_CARD_STYLE)
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(20, 16, 20, 16)
        card_l.setSpacing(6)
        title = QLabel("Excel All Import")
        title.setObjectName("allImportCardTitle")
        hint = QLabel("Use this section to run the full Excel import flow.")
        hint.setObjectName("allImportCardHint")
        hint.setWordWrap(True)
        card_l.addWidget(title)
        card_l.addWidget(hint)
        body_l.addWidget(card, 0, Qt.AlignmentFlag.AlignTop)
        body_l.addStretch(1)

        root.addWidget(body, 1)

    def go_to_nav_item(self, _nav_item: str) -> None:
        return
