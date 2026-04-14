"""Full-width strip below the menu bar for WebSocket notifications (no layout shift)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics, QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from core.ws_notification import WsNotificationPayload
from ui.form_page_styles import list_page_header_push_button_stylesheet
from ui.theme import Theme

# Compact bar height (single row, professional IDE-style strip).
_BAR_HEIGHT_PX = 40

# Match API: Projects (and other list headers) — Refresh / Create button width.
_BANNER_ACTION_BTN_WIDTH_PX = 100


class WsUpdateBanner(QFrame):
    """Edge-to-edge bar under the menu bar; shown only on the signed-in dashboard."""

    dismissed = Signal()
    # Install on strip: same flow as Help → Check for update (AutoUpdateDialog, not browser download).
    install_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("wsUpdateBanner")
        self.setVisible(False)
        self._url: str | None = None
        self._full_line: str = ""
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedHeight(_BAR_HEIGHT_PX)
        self.setStyleSheet(
            f"#wsUpdateBanner {{"
            f"background-color: #1e293b;"
            f"border: none;"
            f"border-bottom: 1px solid #334155;"
            f"}}"
        )

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        accent = QFrame()
        accent.setFixedWidth(3)
        accent.setStyleSheet(
            f"QFrame {{ background: {Theme.WARNING}; border: none; }}"
        )
        outer.addWidget(accent)

        self._text = QLabel()
        self._text.setWordWrap(False)
        self._text.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self._text.setStyleSheet(
            "color: #e2e8f0; font-size: 12px; font-weight: 500; "
            "background: transparent; border: none; padding: 0 12px;"
        )
        outer.addWidget(self._text, 1)

        btn_wrap = QWidget()
        btn_wrap.setStyleSheet("background: transparent;")
        br = QHBoxLayout(btn_wrap)
        br.setContentsMargins(0, 0, 10, 0)
        br.setSpacing(6)

        _header_btn_style = list_page_header_push_button_stylesheet()
        self._install_btn = QPushButton("Install")
        self._install_btn.setFixedWidth(_BANNER_ACTION_BTN_WIDTH_PX)
        self._install_btn.setAutoDefault(False)
        self._install_btn.setDefault(False)
        self._install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._install_btn.setStyleSheet(_header_btn_style)
        self._install_btn.clicked.connect(self._on_install)
        self._install_btn.setVisible(False)
        br.addWidget(self._install_btn)

        self._dismiss_btn = QPushButton("Dismiss")
        self._dismiss_btn.setFixedWidth(_BANNER_ACTION_BTN_WIDTH_PX)
        self._dismiss_btn.setAutoDefault(False)
        self._dismiss_btn.setDefault(False)
        self._dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dismiss_btn.setStyleSheet(_header_btn_style)
        self._dismiss_btn.clicked.connect(self._on_dismiss)
        br.addWidget(self._dismiss_btn)

        outer.addWidget(btn_wrap, 0, Qt.AlignmentFlag.AlignVCenter)

    def position_overlay(self) -> None:
        """Full width, directly under the menu bar."""
        mw = self.parentWidget()
        if mw is None:
            return
        mb = mw.menuBar()
        y_off = mb.height() if mb is not None and mb.isVisible() else 0
        w = mw.width()
        self.setFixedWidth(w)
        self.setFixedHeight(_BAR_HEIGHT_PX)
        self.move(0, y_off)
        self.raise_()
        self._apply_elided_text()

    def _apply_elided_text(self) -> None:
        raw = self._full_line
        if not raw:
            self._text.setText("")
            return
        reserve = 3 + 12 + 10  # accent, text left pad, btn row right margin
        for btn in (self._install_btn, self._dismiss_btn):
            if btn.isVisible():
                reserve += btn.sizeHint().width() + 6
        avail = max(80, self.width() - reserve - 12)
        fm = QFontMetrics(self._text.font())
        self._text.setText(fm.elidedText(raw, Qt.TextElideMode.ElideRight, avail))

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._apply_elided_text()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_elided_text()

    def show_payload(self, payload: WsNotificationPayload) -> None:
        self._url = payload.action_url
        header = (payload.header_title or "Notification").strip()
        headline = (payload.headline or "").strip()
        primary = headline or header

        parts: list[str] = [primary]
        if header and headline and header.lower() not in headline.lower():
            parts.append(header)
        if payload.body.strip():
            parts.append(payload.body.strip())
        for label, value in payload.meta[:3]:
            parts.append(f"{label}: {value}")
        self._full_line = " · ".join(p for p in parts if p)

        self._install_btn.setVisible(bool(self._url))

        tip_lines = [payload.headline, payload.body, header]
        tip_lines.extend(f"{a}: {b}" for a, b in payload.meta)
        self.setToolTip("\n".join(x for x in tip_lines if x))

        self.setVisible(True)
        self.position_overlay()
        self._apply_elided_text()

    def _on_install(self) -> None:
        if self._url:
            self.install_requested.emit()

    def _on_dismiss(self) -> None:
        self._url = None
        self._full_line = ""
        self.setVisible(False)
        self.setToolTip("")
        self.dismissed.emit()
