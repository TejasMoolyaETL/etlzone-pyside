"""Password input with inline eye toggle icon."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QSizePolicy, QWidget

from ui.form_page_styles import APP_FONT_SIZE_PX, INPUT_PLACEHOLDER_COLOR


def _eye_icon(visible: bool) -> QIcon:
    """Create a simple eye icon (show/hide) as QIcon from unicode."""
    from PySide6.QtGui import QPainter
    pm = QPixmap(20, 20)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setPen(Qt.GlobalColor.darkGray)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if visible:
        painter.drawEllipse(4, 4, 12, 12)
        painter.drawEllipse(8, 8, 4, 4)
    else:
        painter.drawEllipse(4, 4, 12, 12)
        painter.drawLine(4, 4, 16, 16)
        painter.drawLine(16, 4, 4, 16)
    painter.end()
    return QIcon(pm)


class PasswordLineEdit(QWidget):
    """Password input with eye toggle icon inside the field. Exposes QLineEdit API."""

    _DEFAULT_STYLE = (
        "border: 1px solid #e2e8f0; border-radius: 4px; background-color: #ffffff; "
        "font-size: 13px; padding: 8px 12px;"
    )

    def __init__(self, parent: QWidget | None = None, *, use_default_style: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("passwordLineEdit")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._use_default_style = use_default_style
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._edit = QLineEdit()
        self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._edit.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(
            self._edit,
            1,
            Qt.AlignmentFlag.AlignVCenter,
        )

        self._toggle_btn = QPushButton()
        self._toggle_btn.setFixedSize(22, 20)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #64748b; } "
            "QPushButton:hover { color: #0f172a; background: #f1f5f9; border-radius: 4px; } "
            "QPushButton:pressed { color: #475569; }"
        )
        self._toggle_btn.setIcon(_eye_icon(False))
        self._toggle_btn.setToolTip("Show password")
        self._toggle_btn.setIconSize(QSize(16, 16))
        self._toggle_btn.clicked.connect(self._toggle_visibility)
        layout.addWidget(
            self._toggle_btn,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        if self._use_default_style:
            super().setStyleSheet(
                f"#passwordLineEdit {{ {self._DEFAULT_STYLE} }} "
                "#passwordLineEdit QLineEdit { border: none; background: transparent; padding: 0; }"
            )

    def _toggle_visibility(self) -> None:
        if self._edit.echoMode() == QLineEdit.EchoMode.Password:
            self._edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._toggle_btn.setIcon(_eye_icon(True))
            self._toggle_btn.setToolTip("Hide password")
        else:
            self._edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._toggle_btn.setIcon(_eye_icon(False))
            self._toggle_btn.setToolTip("Show password")

    def text(self) -> str:
        return self._edit.text()

    def setText(self, text: str) -> None:
        self._edit.setText(text)

    def clear(self) -> None:
        self._edit.clear()

    def setEchoMode(self, mode: QLineEdit.EchoMode) -> None:
        self._edit.setEchoMode(mode)
        self._toggle_btn.setIcon(_eye_icon(mode == QLineEdit.EchoMode.Normal))

    def setPlaceholderText(self, text: str) -> None:
        self._edit.setPlaceholderText(text)

    def set_inner_padding(
        self,
        padding: str,
        *,
        font_size_px: int | None = None,
        color: str | None = None,
        font_weight: int = 400,
    ) -> None:
        """Style the inner QLineEdit (padding required). Optional font matches sibling QLineEdits."""
        parts = [
            "border: none",
            "background: transparent",
            f"padding: {padding}",
        ]
        if font_size_px is not None:
            parts.append(f"font-size: {font_size_px}px")
            parts.append(f"font-weight: {font_weight}")
        if color is not None:
            parts.append(f"color: {color}")
        fs = font_size_px if font_size_px is not None else APP_FONT_SIZE_PX
        ph = f"QLineEdit::placeholder {{ color: {INPUT_PLACEHOLDER_COLOR}; font-size: {fs}px; }}"
        self._edit.setStyleSheet("; ".join(parts) + "; " + ph)

    def setStyleSheet(self, styleSheet: str) -> None:
        styleSheet = styleSheet.strip()
        if "QLineEdit" in styleSheet:
            # Selector-based stylesheet (e.g. "QLineEdit { ... } QLineEdit:focus { ... }")
            wrapped = styleSheet.replace("QLineEdit", "#passwordLineEdit")
            wrapped = re.sub(r"#passwordLineEdit:focus\s*\{[^}]*\}", "", wrapped)
            wrapped = re.sub(r"#passwordLineEdit:hover\s*\{[^}]*\}", "", wrapped)
            wrapped = re.sub(r"#passwordLineEdit\[[^\]]+\]\s*\{[^}]*\}", "", wrapped)
        else:
            # Plain properties (e.g. "font-size: 12px; padding: 4px 8px; ...")
            wrapped = f"#passwordLineEdit {{ {styleSheet} }}"
        wrapped += " #passwordLineEdit QLineEdit { border: none; background: transparent; padding: 0; }"
        super().setStyleSheet(wrapped)

    def setReadOnly(self, readOnly: bool) -> None:
        self._edit.setReadOnly(readOnly)

    def setFocus(self) -> None:
        self._edit.setFocus()

    @property
    def textChanged(self):
        return self._edit.textChanged

    @property
    def editingFinished(self):
        return self._edit.editingFinished
