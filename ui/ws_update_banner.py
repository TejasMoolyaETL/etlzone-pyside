"""Non-blocking top banner for WebSocket notifications (IDE-style update strip)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.ws_notification import WsNotificationPayload
from ui.theme import Theme


class WsUpdateBanner(QFrame):
    """Full-width strip below the menu bar; does not block interaction."""

    dismissed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("wsUpdateBanner")
        self.setVisible(False)
        self._url: str | None = None
        self.setStyleSheet(
            f"#wsUpdateBanner {{"
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f" stop:0 #1e3a5f, stop:1 #0f2340);"
            f"border: none;"
            f"border-bottom: 1px solid #2d4a73;"
            f"}}"
        )

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        accent = QFrame()
        accent.setFixedWidth(4)
        accent.setStyleSheet(
            f"QFrame {{ background: {Theme.WARNING}; border: none; }}"
        )
        outer.addWidget(accent)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        il = QVBoxLayout(inner)
        il.setContentsMargins(14, 10, 12, 10)
        il.setSpacing(2)

        self._title = QLabel()
        self._title.setWordWrap(True)
        self._title.setStyleSheet(
            "color: #f8fafc; font-size: 14px; font-weight: 600; "
            "background: transparent; border: none; line-height: 1.35;"
        )
        il.addWidget(self._title)

        self._subtitle = QLabel()
        self._subtitle.setWordWrap(True)
        self._subtitle.setStyleSheet(
            "color: #94a3b8; font-size: 12px; font-weight: 400; "
            "background: transparent; border: none; line-height: 1.4;"
        )
        il.addWidget(self._subtitle)

        outer.addWidget(inner, 1)

        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent;")
        br = QHBoxLayout(btn_row)
        br.setContentsMargins(0, 8, 12, 8)
        br.setSpacing(8)

        self._action_btn = QPushButton("Open")
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.setStyleSheet(
            f"QPushButton {{"
            f"background: {Theme.WARNING}; color: #0f172a; border: none; "
            f"border-radius: 5px; font-size: 12px; font-weight: 700; "
            f"padding: 6px 14px; min-height: 18px;"
            f"}}"
            f"QPushButton:hover {{ background: #fbbf24; }}"
            f"QPushButton:pressed {{ background: #d97706; color: #fff; }}"
        )
        self._action_btn.clicked.connect(self._on_action)
        br.addWidget(self._action_btn)

        dismiss = QPushButton("Dismiss")
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.setStyleSheet(
            "QPushButton {"
            "background: rgba(255,255,255,0.12); color: #e2e8f0; border: 1px solid rgba(255,255,255,0.22); "
            "border-radius: 5px; font-size: 12px; font-weight: 600; "
            "padding: 6px 14px; min-height: 18px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.2); }"
            "QPushButton:pressed { background: rgba(255,255,255,0.08); }"
        )
        dismiss.clicked.connect(self._on_dismiss)
        br.addWidget(dismiss)

        outer.addWidget(btn_row, 0, Qt.AlignmentFlag.AlignTop)

    def show_payload(self, payload: WsNotificationPayload) -> None:
        self._url = payload.action_url
        header = (payload.header_title or "Notification").strip()
        headline = (payload.headline or "").strip()
        self._title.setText(headline or header)

        sub_parts: list[str] = []
        if header and headline and header.lower() not in headline.lower():
            sub_parts.append(header)
        if payload.body.strip():
            sub_parts.append(payload.body.strip())
        for label, value in payload.meta[:4]:
            sub_parts.append(f"{label}: {value}")
        self._subtitle.setText(" · ".join(sub_parts) if sub_parts else "")
        self._subtitle.setVisible(bool(sub_parts))

        self._action_btn.setVisible(bool(self._url))
        if self._url:
            self._action_btn.setText(payload.action_label or "Open link")

        tip_lines = [payload.headline, payload.body]
        tip_lines.extend(f"{a}: {b}" for a, b in payload.meta)
        self.setToolTip("\n".join(x for x in tip_lines if x))

        self.setVisible(True)

    def _on_action(self) -> None:
        if self._url:
            QDesktopServices.openUrl(QUrl(self._url))

    def _on_dismiss(self) -> None:
        self._url = None
        self.setVisible(False)
        self.setToolTip("")
        self.dismissed.emit()
