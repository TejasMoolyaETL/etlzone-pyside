"""Wizard step breadcrumb."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

from app.etl.data_transformation.constants import SECTION_LABELS
from ui.form_page_styles import FORM_PAGE_FONT_SIZE_PX


class StepIndicatorWidget(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        self._labels: list[QLabel] = []
        for index, text in enumerate(SECTION_LABELS):
            if index > 0:
                arrow = QLabel("›")
                arrow.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: #94a3b8;")
                layout.addWidget(arrow)
            lbl = QLabel(text)
            lbl.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: #94a3b8;")
            self._labels.append(lbl)
            layout.addWidget(lbl)
        layout.addStretch()

    def set_active_step(self, step: int) -> None:
        for index, lbl in enumerate(self._labels):
            if index == step:
                lbl.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; font-weight: 600; color: #0f172a;")
            elif index < step:
                lbl.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: #16a34a;")
            else:
                lbl.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: #94a3b8;")
