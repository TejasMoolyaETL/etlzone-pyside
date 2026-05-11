"""Comments panel for the selected API validation (API: All in One)."""

from __future__ import annotations

import base64
import html
import json
import math
import re
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Any

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import (
    QAction,
    QColor,
    QEnterEvent,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPen,
    QPalette,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextListFormat,
    QTextOption,
    QPixmap,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.api_dev.api_dev_validation_all_in_one.api_dev_validation_details_list_panel import (
    _format_cell,
)
from app.api_dev.api_dev_validation_all_in_one.api_dev_validation_list_panel import (
    APIValidationsListPanel,
)
from core.api import (
    api_add_validation_comment,
    api_delete_validation_comment_by_id,
    api_get_all_validation_comments_by_id,
    api_update_validation_comment_by_id,
)
from core.nav_access import collect_allowed_action_names, nav_action_visible
from core.user_context import get_nav_access_steps, get_user_email, get_user_profile
from ui.form_page_styles import (
    APP_FONT_SIZE_PX,
    FORM_ERROR_LABEL_STYLE,
    MODAL_FEEDBACK_SUCCESS_STYLE,
)
from ui.theme import Theme

# Compact strip for the right-hand Comments panel (API: All in One).
_COMMENT_PANEL_HEADER_HEIGHT_PX = 22
_COMMENT_PANEL_HEADER_MARGINS = (5, 0, 5, 0)
_COMMENT_PANEL_HEADER_SPACING = 3
_COMMENT_AUX_LABEL_STYLE = "color: #64748b; font-size: 9px; font-weight: 500;"
# Section canvas matches data table / Theme.BG_WHITE (not Theme.BG_APP — scroll viewport is often transparent in QSS).
_COMMENT_SECTION_BG = Theme.BG_WHITE
_COMMENT_BLOCK_BG = "#F3F3F6"
_COMMENT_BLOCK_BORDER = "#e2e8f0"


def _force_widget_window_bg(widget: QWidget, hex_color: str) -> None:
    """Solid background; QScrollArea viewport often ignores QSS-only fills and shows QStackedWidget BG_APP."""
    widget.setAutoFillBackground(True)
    pal = widget.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor(hex_color))
    widget.setPalette(pal)


def _force_textedit_surface_bg(editor: QTextEdit, hex_color: str) -> None:
    """QTextEdit often uses Base for the document area; match QSS so placeholder row is white on Windows."""
    editor.setAutoFillBackground(True)
    pal = editor.palette()
    c = QColor(hex_color)
    pal.setColor(QPalette.ColorRole.Base, c)
    pal.setColor(QPalette.ColorRole.Window, c)
    editor.setPalette(pal)


def _comment_message_text_only_stylesheet(font_size_px: int) -> str:
    return f"QLabel {{ color: #0f172a; font-size: {font_size_px}px; background: transparent; border: none; }}"


def _comment_message_textedit_stylesheet(
    font_size_px: int, *, padding: str = "1px 8px", bg: str | None = None
) -> str:
    fill = bg if bg is not None else _COMMENT_BLOCK_BG
    return (
        f"QTextEdit {{ color: #0f172a; font-size: {font_size_px}px; "
        f"background-color: {fill}; padding: {padding}; "
        f"border: 1px solid {_COMMENT_BLOCK_BORDER}; border-radius: 6px; }}"
    )


_COMMENT_BODY_MIN_HEIGHT_PX = 18


class _RichCommentBodyLabel(QLabel):
    """Rich-text comment body that keeps a compact single-line height, then grows with wrapping."""

    def __init__(self, font_size_px: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fs = max(9, int(font_size_px))
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def setText(self, text: str) -> None:
        super().setText(text)
        QTimer.singleShot(0, self._sync_height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_height()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_height()

    def _sync_height(self) -> None:
        # During first layout passes, contentsRect width can be 0 even though the widget already
        # has a reasonable outer width — falling back prevents "stuck tall" default QLabel sizing.
        w = int(self.contentsRect().width())
        if w <= 1:
            w = int(self.width())
        if w <= 1:
            pw = self.parentWidget()
            if pw is not None:
                w = int(pw.width())
        if w <= 1:
            return
        # Stylesheet padding/border on QLabel is not always reflected in contentsRect the same way
        # across styles; keep a safety margin that covers 4px top + 4px bottom padding plus border.
        horiz_extra = 18
        vert_extra = 10
        text_w = max(1, w - horiz_extra)

        raw = self.text() or ""
        fm = QFontMetrics(self.font())
        line_h = max(1, fm.height())

        if not _looks_like_rich_html(raw):
            flags = Qt.TextFlag.TextWordWrap
            br = fm.boundingRect(
                0,
                0,
                text_w,
                10_000,
                flags,
                raw.replace("\r\n", "\n"),
            )
            h = int(math.ceil(br.height())) + vert_extra
            lines = max(1, int(round(br.height() / float(line_h))) if line_h else 1)
        else:
            doc = QTextDocument()
            doc.setDefaultFont(self.font())
            doc.setDocumentMargin(0.0)
            doc.setHtml(raw)
            doc.setTextWidth(float(text_w))
            opt = QTextOption()
            opt.setWrapMode(QTextOption.WrapMode.WordWrap)
            doc.setDefaultTextOption(opt)
            doc_h = float(doc.size().height())
            h = int(math.ceil(doc_h)) + vert_extra
            # Rich HTML from QTextEdit can report a slightly taller single-line doc due to tag/layout
            # overhead; use a looser threshold so one-line comments keep the same compact bubble height.
            lines = 1 if doc_h <= float(line_h) * 1.6 else max(2, int(math.ceil(doc_h / float(line_h))))

        if lines <= 1:
            # Keep one-line rich HTML and one-line plain text at the same visual height.
            one_line_target = max(_COMMENT_BODY_MIN_HEIGHT_PX, line_h + vert_extra)
            h = one_line_target
        self.setMinimumHeight(h)
        self.setMaximumHeight(h)


def _looks_like_rich_html(s: str) -> bool:
    """True if stored comment is likely QTextEdit / HTML (vs plain text)."""
    lead = (s or "").lstrip()
    if not lead.startswith("<"):
        return False
    low = lead[:200].lower()
    if "<!doctype" in low or "<html" in low or "<head" in low or "<body" in low:
        return True
    return "</" in s and any(
        t in low for t in ("<p", "<div", "<span", "<ul", "<ol", "<li", "<br", "<table")
    )


def _comment_body_display_html(raw: str) -> str:
    """Rich text for chat bubble with trimmed default HTML block/list margins."""
    s = raw or ""
    if _looks_like_rich_html(s):
        inner = re.sub(r"(?is)^.*?<body[^>]*>", "", s).strip()
        inner = re.sub(r"(?is)</body>.*$", "", inner).strip()
        # Remove trailing empty paragraphs generated by QTextEdit after list edits.
        inner = re.sub(r"(?is)(<p[^>]*>(?:\s|&nbsp;|<br\s*/?>)*</p>\s*)+$", "", inner).strip()
        if not inner:
            return ""
        return (
            '<div style="margin:0; padding:0;">'
            "<style>"
            "body{margin:0;padding:0;}"
            "p{margin-top:0;margin-bottom:0;}"
            "ul,ol{margin-top:0;margin-bottom:0;padding-top:0;padding-bottom:0;}"
            "li{margin-top:0;margin-bottom:0;}"
            "</style>"
            f"{inner}"
            "</div>"
        )
    esc = html.escape(s)
    return f'<span style="white-space: pre-wrap;">{esc.replace(chr(10), "<br/>")}</span>'


def _comment_panel_header_stylesheet() -> str:
    t = Theme
    return (
        f"QWidget {{ background: {t.HEADER_NAV}; }}"
        f"QLabel#commentPanelHeaderTitle {{ color: {t.PANEL_TEXT_BRIGHT}; font-size: 9px; font-weight: 600; }}"
        f"QPushButton {{ background: {t.HEADER_ACCENT}; color: {t.PANEL_TEXT_BRIGHT}; border: none; border-radius: 2px; "
        f"padding: 0px 5px; font-size: 8px; font-weight: 500; min-height: 0px; max-height: 16px; }}"
        f"QPushButton:hover {{ background: {t.HEADER_ACCENT_HOVER}; }}"
        f"QPushButton:pressed {{ background: {t.HEADER_ACCENT_PRESSED}; }}"
    )


# Word ribbon–style blue for list preview icons (similar to Microsoft 365 list buttons).
# Size tracks :data:`APP_FONT_SIZE_PX` (slightly tighter than before).
_WORD_LIST_ICON_INK = QColor("#2b579a")
_WORD_LIST_ICON_SIZE = QSize(
    max(10, APP_FONT_SIZE_PX + 4),
    max(8, APP_FONT_SIZE_PX + 1),
)

_BULLET_LIST_STYLES: frozenset[QTextListFormat.Style] = frozenset(
    (
        QTextListFormat.Style.ListDisc,
        QTextListFormat.Style.ListCircle,
        QTextListFormat.Style.ListSquare,
    )
)
_NUMBERED_LIST_STYLES: frozenset[QTextListFormat.Style] = frozenset(
    (
        QTextListFormat.Style.ListDecimal,
        QTextListFormat.Style.ListLowerAlpha,
        QTextListFormat.Style.ListUpperAlpha,
        QTextListFormat.Style.ListLowerRoman,
        QTextListFormat.Style.ListUpperRoman,
    )
)

# Comment row hover actions: neutral outline icons (Teams / Fluent–adjacent).
_COMMENT_ROW_ACTION_INK = QColor("#475569")
_COMMENT_ROW_ACTION_INK_DISABLED = QColor("#94a3b8")


def _comment_row_action_icon_px() -> int:
    return max(16, APP_FONT_SIZE_PX + 4)


def _paint_comment_row_edit_icon(p: QPainter, s: int, ink: QColor) -> None:
    """Document corner + diagonal pen stroke (readable at small sizes)."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen_w = max(1.05, s / 14.0)
    pen = QPen(ink, pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    m = s * 0.11
    doc_x, doc_y = m, m + s * 0.1
    doc_w, doc_h = s * 0.52, s * 0.58
    p.drawRoundedRect(doc_x, doc_y, doc_w, doc_h, 1.2, 1.2)
    fx = doc_x + doc_w * 0.72
    fy = doc_y + doc_h * 0.08
    p.drawLine(int(fx), int(fy), int(doc_x + doc_w), int(doc_y))
    p.drawLine(int(fx), int(fy), int(doc_x + doc_w), int(fy))
    p.drawLine(
        int(doc_x + doc_w * 0.35),
        int(doc_y + doc_h * 0.72),
        int(s - m - 0.5),
        int(m + 0.5),
    )


def _paint_comment_row_delete_icon(p: QPainter, s: int, ink: QColor) -> None:
    """Trash outline with lid and two inner ribs."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen_w = max(1.05, s / 14.0)
    pen = QPen(ink, pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    m = s * 0.11
    lid_y = m + s * 0.14
    p.drawLine(int(m + s * 0.08), int(lid_y), int(s - m - s * 0.08), int(lid_y))
    p.drawLine(int(m + s * 0.08), int(lid_y), int(m + s * 0.08), int(lid_y + s * 0.06))
    p.drawLine(int(s - m - s * 0.08), int(lid_y), int(s - m - s * 0.08), int(lid_y + s * 0.06))
    body_x = m + s * 0.16
    body_y = lid_y + s * 0.06
    body_w = s - 2 * body_x
    body_h = s * 0.52
    p.drawRoundedRect(body_x, body_y, body_w, body_h, 1.0, 1.0)
    ix1 = body_x + body_w * 0.32
    ix2 = body_x + body_w * 0.68
    iy0 = body_y + body_h * 0.28
    iy1 = body_y + body_h * 0.88
    p.drawLine(int(ix1), int(iy0), int(ix1), int(iy1))
    p.drawLine(int(ix2), int(iy0), int(ix2), int(iy1))


_COMMENT_ROW_EDIT_ICON_CACHE: dict[int, QIcon] = {}
_COMMENT_ROW_DELETE_ICON_CACHE: dict[int, QIcon] = {}


def _comment_row_edit_icon() -> QIcon:
    s = _comment_row_action_icon_px()
    if s in _COMMENT_ROW_EDIT_ICON_CACHE:
        return _COMMENT_ROW_EDIT_ICON_CACHE[s]

    def _pix(ink: QColor) -> QPixmap:
        pm = QPixmap(s, s)
        pm.fill(Qt.GlobalColor.transparent)
        pr = QPainter(pm)
        _paint_comment_row_edit_icon(pr, s, ink)
        pr.end()
        return pm

    ic = QIcon()
    ic.addPixmap(_pix(_COMMENT_ROW_ACTION_INK), QIcon.Mode.Normal)
    ic.addPixmap(_pix(_COMMENT_ROW_ACTION_INK_DISABLED), QIcon.Mode.Disabled)
    _COMMENT_ROW_EDIT_ICON_CACHE[s] = ic
    return ic


def _comment_row_delete_icon() -> QIcon:
    s = _comment_row_action_icon_px()
    if s in _COMMENT_ROW_DELETE_ICON_CACHE:
        return _COMMENT_ROW_DELETE_ICON_CACHE[s]

    def _pix(ink: QColor) -> QPixmap:
        pm = QPixmap(s, s)
        pm.fill(Qt.GlobalColor.transparent)
        pr = QPainter(pm)
        _paint_comment_row_delete_icon(pr, s, ink)
        pr.end()
        return pm

    ic = QIcon()
    ic.addPixmap(_pix(_COMMENT_ROW_ACTION_INK), QIcon.Mode.Normal)
    ic.addPixmap(_pix(_COMMENT_ROW_ACTION_INK_DISABLED), QIcon.Mode.Disabled)
    _COMMENT_ROW_DELETE_ICON_CACHE[s] = ic
    return ic


_COMMENT_ROW_TICK_INK = QColor("#15803d")
_COMMENT_ROW_TICK_INK_DISABLED = QColor("#86efac")
_COMMENT_ROW_CROSS_INK = QColor("#64748b")
_COMMENT_ROW_CROSS_INK_DISABLED = QColor("#cbd5e1")
_COMMENT_ROW_TICK_ICON_CACHE: dict[int, QIcon] = {}
_COMMENT_ROW_CROSS_ICON_CACHE: dict[int, QIcon] = {}


def _paint_comment_row_tick_icon(p: QPainter, s: int, ink: QColor) -> None:
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(
        ink,
        max(1.15, s / 9.0),
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    p.setPen(pen)
    m = s * 0.14
    p.drawPolyline(
        [
            QPoint(int(m * 0.9), int(s * 0.52)),
            QPoint(int(s * 0.4), int(s - m * 0.85)),
            QPoint(int(s - m * 0.55), int(m * 0.95)),
        ]
    )


def _paint_comment_row_cross_icon(p: QPainter, s: int, ink: QColor) -> None:
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(
        ink,
        max(1.15, s / 9.0),
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    p.setPen(pen)
    m = s * 0.24
    p.drawLine(int(m), int(m), int(s - m), int(s - m))
    p.drawLine(int(m), int(s - m), int(s - m), int(m))


def _comment_row_tick_icon() -> QIcon:
    s = _comment_row_action_icon_px()
    if s in _COMMENT_ROW_TICK_ICON_CACHE:
        return _COMMENT_ROW_TICK_ICON_CACHE[s]

    def _pix(ink: QColor) -> QPixmap:
        pm = QPixmap(s, s)
        pm.fill(Qt.GlobalColor.transparent)
        pr = QPainter(pm)
        _paint_comment_row_tick_icon(pr, s, ink)
        pr.end()
        return pm

    ic = QIcon()
    ic.addPixmap(_pix(_COMMENT_ROW_TICK_INK), QIcon.Mode.Normal)
    ic.addPixmap(_pix(_COMMENT_ROW_TICK_INK_DISABLED), QIcon.Mode.Disabled)
    _COMMENT_ROW_TICK_ICON_CACHE[s] = ic
    return ic


def _comment_row_cross_icon() -> QIcon:
    s = _comment_row_action_icon_px()
    if s in _COMMENT_ROW_CROSS_ICON_CACHE:
        return _COMMENT_ROW_CROSS_ICON_CACHE[s]

    def _pix(ink: QColor) -> QPixmap:
        pm = QPixmap(s, s)
        pm.fill(Qt.GlobalColor.transparent)
        pr = QPainter(pm)
        _paint_comment_row_cross_icon(pr, s, ink)
        pr.end()
        return pm

    ic = QIcon()
    ic.addPixmap(_pix(_COMMENT_ROW_CROSS_INK), QIcon.Mode.Normal)
    ic.addPixmap(_pix(_COMMENT_ROW_CROSS_INK_DISABLED), QIcon.Mode.Disabled)
    _COMMENT_ROW_CROSS_ICON_CACHE[s] = ic
    return ic


def _comment_list_gallery_menu_stylesheet() -> str:
    """Bullets / numbering popup rows: global font size + tighter row height."""
    px = APP_FONT_SIZE_PX
    row_h = px + 4
    return (
        f"QMenu {{ padding: 1px; font-size: {px}px; }}"
        f"QMenu::item {{ padding: 1px 8px 1px 4px; min-height: {row_h}px; max-height: {row_h}px; "
        f"font-size: {px}px; }}"
    )


def _word_toolbar_bullets_icon() -> QIcon:
    """Bulleted list (lines + dots), common toolbar pattern — distinct from stacked shapes."""
    w, h = _WORD_LIST_ICON_SIZE.width(), _WORD_LIST_ICON_SIZE.height()
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    ink = _WORD_LIST_ICON_INK
    dot_r = max(2, min(w, h) // 5)
    x_dot = max(1, w // 12)
    gap_x = max(1, w // 10)
    bar_x = x_dot + dot_r + gap_x
    bar_w = max(3, w - bar_x - 2)
    bar_h = max(1, dot_r // 2 + 1)
    row_gap = max(2, (h - 3 * max(dot_r, bar_h)) // 4)
    y_start = max(1, (h - (3 * dot_r + 2 * row_gap)) // 2)
    for i in range(3):
        y = y_start + i * (dot_r + row_gap)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ink)
        p.drawEllipse(x_dot, int(y + dot_r * 0.1), dot_r, dot_r)
        by = int(y + (dot_r - bar_h) / 2 + 0.5)
        p.drawRoundedRect(bar_x, by, bar_w, bar_h, 1, 1)
    p.end()
    return QIcon(pm)


def _word_toolbar_numbering_icon() -> QIcon:
    """Word ribbon *Numbering*: stacked 1 / 2 / 3 at left, horizontal rules to the right (same layout as bullets)."""
    w, h = _WORD_LIST_ICON_SIZE.width(), _WORD_LIST_ICON_SIZE.height()
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    ink = _WORD_LIST_ICON_INK
    dot_r = max(2, min(w, h) // 5)
    x_num = max(1, w // 12)
    gap_x = max(1, w // 10)
    fs = max(4, min(dot_r + 1, APP_FONT_SIZE_PX - 1))
    f = QFont("Segoe UI", fs, QFont.Weight.Bold)
    f.setStyleHint(QFont.StyleHint.SansSerif)
    p.setFont(f)
    fm = QFontMetrics(f)
    digit_col_w = min(w // 2, max(fm.horizontalAdvance("1"), fm.horizontalAdvance("2"), fm.horizontalAdvance("3")) + 1)
    bar_x = x_num + digit_col_w + gap_x
    bar_w = max(3, w - bar_x - 2)
    bar_h = max(1, dot_r // 2 + 1)
    row_gap = max(2, (h - 3 * max(dot_r, bar_h)) // 4)
    y_start = max(1, (h - (3 * dot_r + 2 * row_gap)) // 2)
    for i, ch in enumerate(("1", "2", "3")):
        y = y_start + i * (dot_r + row_gap)
        p.setPen(QPen(ink))
        p.drawText(
            x_num,
            y,
            digit_col_w,
            dot_r,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            ch,
        )
        by = int(y + (dot_r - bar_h) / 2 + 0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ink)
        p.drawRoundedRect(bar_x, by, bar_w, bar_h, 1, 1)
    p.end()
    return QIcon(pm)


def _list_style_menu_icon(style: QTextListFormat.Style) -> QIcon:
    """Small preview for each list style (bullets + numbering)."""
    w, h = _WORD_LIST_ICON_SIZE.width(), _WORD_LIST_ICON_SIZE.height()
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    ink = _WORD_LIST_ICON_INK
    p.setPen(ink)
    fs = max(5, APP_FONT_SIZE_PX - 2)
    f = QFont("Segoe UI", fs, QFont.Weight.Bold)
    p.setFont(f)
    r = max(2, min(w, h) // 2 - 3)
    cx, cy = w // 2, h // 2
    if style == QTextListFormat.Style.ListDisc:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ink)
        p.drawEllipse(cx - r // 2, cy - r // 2, r, r)
    elif style == QTextListFormat.Style.ListCircle:
        p.setBrush(Qt.GlobalColor.transparent)
        p.setPen(QPen(ink, 1.1))
        p.drawEllipse(cx - r // 2, cy - r // 2, r, r)
    elif style == QTextListFormat.Style.ListSquare:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(ink)
        p.drawRect(cx - r // 2, cy - r // 2, r, r)
    elif style == QTextListFormat.Style.ListDecimal:
        p.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, "1.")
    elif style == QTextListFormat.Style.ListLowerAlpha:
        p.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, "a.")
    elif style == QTextListFormat.Style.ListUpperAlpha:
        p.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, "A.")
    elif style == QTextListFormat.Style.ListLowerRoman:
        p.setFont(QFont("Segoe UI", max(4, APP_FONT_SIZE_PX - 3), QFont.Weight.Bold))
        p.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, "iii.")
    elif style == QTextListFormat.Style.ListUpperRoman:
        p.setFont(QFont("Segoe UI", max(4, APP_FONT_SIZE_PX - 3), QFont.Weight.Bold))
        p.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, "III.")
    else:
        p.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, "•")
    p.end()
    return QIcon(pm)


# Same key tuple as API Details list "Created At" column (timezone + display format).
_COMMENT_CREATED_AT_KEYS: tuple[str, ...] = (
    "createdAt",
    "created_at",
    "CreatedAt",
    "createDate",
    "creationDate",
    "dateCreated",
)


def _auth_token() -> str | None:
    profile = get_user_profile()
    t = (
        profile.get("token")
        or profile.get("accessToken")
        or profile.get("access_token")
        or profile.get("bearerToken")
        or profile.get("bearer_token")
        or profile.get("jwt")
        or profile.get("idToken")
        or profile.get("id_token")
    )
    return str(t) if t else None


def _add_identity(identities: set[str], value: Any) -> None:
    if value is None:
        return
    s = str(value).strip()
    if s:
        identities.add(s.lower())


def _current_user_identities() -> set[str]:
    profile = get_user_profile()
    identities: set[str] = set()
    for key in (
        "username",
        "userName",
        "user_name",
        "userId",
        "userid",
        "loginId",
        "login_id",
        "email",
        "createdBy",
        "sub",
    ):
        _add_identity(identities, profile.get(key))
    _add_identity(identities, get_user_email())
    nested = profile.get("user")
    if isinstance(nested, dict):
        for key in ("username", "userName", "user_name", "loginId", "email", "userId"):
            _add_identity(identities, nested.get(key))
    # Some sessions keep identity only inside JWT claims (e.g. sub=s11111).
    token = (
        profile.get("token")
        or profile.get("accessToken")
        or profile.get("access_token")
        or profile.get("jwt")
        or profile.get("idToken")
        or profile.get("id_token")
    )
    t = str(token or "").strip()
    if t and "." in t:
        try:
            payload_part = t.split(".")[1]
            payload_part += "=" * ((4 - len(payload_part) % 4) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_part.encode("utf-8")).decode("utf-8"))
            if isinstance(payload, dict):
                for key in ("sub", "username", "userName", "loginId", "userId", "email"):
                    _add_identity(identities, payload.get(key))
        except Exception:
            pass
    return identities


def _author_is_current_user(author: str, identities: set[str]) -> bool:
    au = (author or "").strip().lower()
    if not au or au == "unknown":
        return False
    if au in identities:
        return True
    profile = get_user_profile()
    for key in ("userName", "username", "loginId", "email"):
        v = profile.get(key)
        if v is not None and str(v).strip().lower() == au:
            return True
    nested = profile.get("user")
    if isinstance(nested, dict):
        for key in ("userName", "username", "loginId", "email"):
            v = nested.get(key)
            if v is not None and str(v).strip().lower() == au:
                return True
    if (get_user_email() or "").strip().lower() == au:
        return True
    return False


def _comment_id_from_row(row: dict[str, Any]) -> Any:
    cid = row.get("commentId")
    if cid is not None:
        return cid
    raw = row.get("raw")
    if isinstance(raw, dict):
        return (
            raw.get("commentId")
            or raw.get("comment_id")
            or raw.get("validationCommentId")
            or raw.get("validation_comment_id")
        )
    return None


def _created_at_from_row(row: dict[str, Any]) -> Any:
    v = row.get("createdAt")
    if v is not None and str(v).strip():
        return v
    raw = row.get("raw")
    if isinstance(raw, dict):
        return raw.get("createdAt") or raw.get("created_at")
    return None


def _dt_to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _validation_internal_id(row: dict[str, Any]) -> Any:
    return row.get("id") or row.get("internalId") or row.get("internal_id")


class _CommentMessageHoverRow(QWidget):
    """Message body with edit/delete on the right, shown on row hover (Teams-style)."""

    def __init__(self, body: QLabel, actions: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("commentMessageBubble")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._actions = actions
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(3)
        lay.addWidget(body, 1, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(actions, 0, Qt.AlignmentFlag.AlignTop)
        actions.setVisible(False)
        self.setStyleSheet(
            f"QWidget#commentMessageBubble {{ background-color: {_COMMENT_BLOCK_BG}; border: 1px solid {_COMMENT_BLOCK_BORDER}; "
            "border-radius: 6px; }}"
            f"QWidget#commentMessageBubble:hover {{ background-color: {_COMMENT_BLOCK_BG}; border: 1px solid {_COMMENT_BLOCK_BORDER}; }}"
        )

    def enterEvent(self, event: QEnterEvent) -> None:
        self._actions.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._actions.setVisible(False)
        super().leaveEvent(event)


class _OwnCommentChatRow(QWidget):
    """Own message: read-only bubble with hover actions, or in-place rich editor (Teams-style)."""

    def __init__(
        self,
        panel: "ValidationCommentPanel",
        row: dict[str, Any],
        *,
        author: str,
        when_suffix: str,
        text: str,
        pencil_enabled: bool,
        can_delete: bool,
    ) -> None:
        super().__init__(panel)
        self._panel = panel
        self._row = row
        self._comment_id = _comment_id_from_row(row)
        self._created_at = _created_at_from_row(row)
        self._pencil_enabled = pencil_enabled
        fs = max(9, APP_FONT_SIZE_PX - 3)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 1, 0, 1)
        outer.setSpacing(1)

        meta = QLabel(author + when_suffix)
        meta.setStyleSheet(_COMMENT_AUX_LABEL_STYLE)
        meta.setWordWrap(True)
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(6)
        meta_row.addWidget(meta, 1)
        outer.addLayout(meta_row)

        self._body = _RichCommentBodyLabel(fs, self)
        self._body.setMargin(0)
        self._body.setText(_comment_body_display_html(text))
        self._body.setStyleSheet(_comment_message_text_only_stylesheet(fs))

        actions_host = QWidget()
        actions_host.setStyleSheet("background: transparent; border: none;")
        al = QHBoxLayout(actions_host)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(0)
        icon_px = _comment_row_action_icon_px()
        icon_side = max(18, icon_px + 4)
        action_style = (
            "QToolButton { background: transparent; border: none; border-radius: 4px; "
            "padding: 0px; }"
            "QToolButton:hover { background: transparent; }"
            "QToolButton:pressed { background: transparent; }"
            "QToolButton:disabled { background: transparent; }"
        )

        if pencil_enabled:
            edit_btn = QToolButton()
            edit_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            edit_btn.setIcon(_comment_row_edit_icon())
            edit_btn.setIconSize(QSize(icon_px, icon_px))
            edit_btn.setFixedSize(icon_side, icon_side)
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_btn.setToolTip("Edit (within 5 minutes of post time)")
            edit_btn.setStyleSheet(action_style)
            edit_btn.setAutoRaise(True)
            edit_btn.clicked.connect(self._on_edit_clicked)

        del_btn: QToolButton | None = None
        if can_delete:
            del_btn = QToolButton()
            del_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            del_btn.setIcon(_comment_row_delete_icon())
            del_btn.setIconSize(QSize(icon_px, icon_px))
            del_btn.setFixedSize(icon_side, icon_side)
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setToolTip("Delete this message")
            del_btn.setStyleSheet(action_style)
            del_btn.setAutoRaise(True)
            del_btn.clicked.connect(partial(self._panel._request_delete_comment, dict(row)))

        if pencil_enabled:
            al.addWidget(edit_btn)
        if del_btn is not None:
            al.addWidget(del_btn)

        self._view_page = _CommentMessageHoverRow(self._body, actions_host, self)

        edit_wrap = QWidget()
        edit_wrap.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        ev = QVBoxLayout(edit_wrap)
        ev.setContentsMargins(0, 0, 0, 0)
        ev.setSpacing(2)
        self._inline_editor = QTextEdit()
        self._inline_editor.setAcceptRichText(True)
        self._inline_editor.document().setDocumentMargin(0)
        self._inline_editor.setMinimumHeight(30)
        self._inline_editor.setMaximumHeight(200)
        self._inline_editor.setStyleSheet(_comment_message_textedit_stylesheet(fs))
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        inline_btn_side = max(26, icon_px + 10)
        inline_btn_style = (
            "QToolButton { background: transparent; border: none; border-radius: 4px; padding: 2px; }"
            "QToolButton:hover { background: transparent; }"
            "QToolButton:pressed { background: transparent; }"
            "QToolButton:disabled { background: transparent; }"
        )
        self._btn_cancel = QToolButton()
        self._btn_cancel.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._btn_cancel.setIcon(_comment_row_cross_icon())
        self._btn_cancel.setIconSize(QSize(icon_px, icon_px))
        self._btn_cancel.setFixedSize(inline_btn_side, inline_btn_side)
        self._btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cancel.setToolTip("Cancel editing")
        self._btn_cancel.setStyleSheet(inline_btn_style)
        self._btn_cancel.setAutoRaise(True)
        self._btn_cancel.clicked.connect(self.cancel_edit)

        self._btn_save = QToolButton()
        self._btn_save.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._btn_save.setIcon(_comment_row_tick_icon())
        self._btn_save.setIconSize(QSize(icon_px, icon_px))
        self._btn_save.setFixedSize(inline_btn_side, inline_btn_side)
        self._btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save.setToolTip("Save changes")
        self._btn_save.setStyleSheet(inline_btn_style)
        self._btn_save.setAutoRaise(True)
        self._btn_save.clicked.connect(self._on_save_clicked)
        btn_row.addWidget(self._btn_cancel)
        btn_row.addWidget(self._btn_save)
        ev.addWidget(self._inline_editor)
        ev.addLayout(btn_row)

        # Avoid QStackedWidget sizing to the tallest page: the editor has a non-trivial minimum height,
        # which was keeping the whole chat row tall even in read-only bubble mode.
        self._mode_stack = QWidget()
        ms = QVBoxLayout(self._mode_stack)
        ms.setContentsMargins(0, 0, 0, 0)
        ms.setSpacing(0)
        ms.addWidget(self._view_page)
        ms.addWidget(edit_wrap)
        outer.addWidget(self._mode_stack)

        self._edit_wrap = edit_wrap
        self._collapse_edit_ui()

    def _expand_edit_ui(self) -> None:
        self._view_page.setVisible(False)
        self._edit_wrap.setVisible(True)
        self._edit_wrap.setMaximumHeight(16777215)

    def _collapse_edit_ui(self) -> None:
        self._edit_wrap.setVisible(False)
        self._edit_wrap.setMaximumHeight(0)
        self._view_page.setVisible(True)

    def _on_edit_clicked(self) -> None:
        if not self._pencil_enabled or not self._panel._can_comment_edit:
            return
        self._panel._register_inline_edit(self)
        self._expand_edit_ui()
        raw = str(self._row.get("comment", "") or "")
        if _looks_like_rich_html(raw):
            self._inline_editor.setHtml(raw)
        else:
            self._inline_editor.setPlainText(raw)
        QTimer.singleShot(0, lambda: self._inline_editor.setFocus())

    def cancel_edit(self) -> None:
        if self._edit_wrap.isVisible():
            self._collapse_edit_ui()
        if getattr(self._panel, "_inline_edit_row", None) is self:
            self._panel._inline_edit_row = None

    def set_edit_busy(self, busy: bool) -> None:
        self._inline_editor.setReadOnly(busy)
        self._btn_save.setEnabled(not busy)
        self._btn_cancel.setEnabled(not busy)

    def _on_save_clicked(self) -> None:
        if not self._panel._can_comment_edit:
            self._panel._flash_status("Require Permission.", error=True)
            self.cancel_edit()
            return
        if not self._panel._is_edit_window_open(self._created_at):
            self._panel._flash_status("Edit time expired (5 min).", error=True)
            self.cancel_edit()
            return
        plain = self._inline_editor.toPlainText().strip()
        if not plain:
            self._panel._flash_status("Message cannot be empty.", error=True)
            return
        body_html = self._inline_editor.toHtml().strip()
        self._panel._run_worker("update", self._comment_id, body_html)


class _CommentWorker(QObject):
    finished = Signal(dict)

    def __init__(self, op: str, validation_id: Any, text: str) -> None:
        super().__init__()
        self._op = op
        self._validation_id = validation_id
        self._text = text

    @Slot()
    def run(self) -> None:
        tk = _auth_token()
        if self._op == "get_all":
            self.finished.emit(
                api_get_all_validation_comments_by_id(self._validation_id, token=tk)
            )
        elif self._op == "add":
            self.finished.emit(api_add_validation_comment(self._validation_id, self._text, token=tk))
        elif self._op == "update":
            self.finished.emit(
                api_update_validation_comment_by_id(self._validation_id, self._text, token=tk)
            )
        elif self._op == "delete":
            self.finished.emit(
                api_delete_validation_comment_by_id(self._validation_id, token=tk)
            )
        else:
            self.finished.emit({"success": False, "message": "Unknown operation."})


class ValidationCommentPanel(QWidget):
    def __init__(self, validations_panel: APIValidationsListPanel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vp = validations_panel
        self._thread: QThread | None = None
        self._worker: _CommentWorker | None = None
        self._pending_op = ""
        self._busy = False
        self._chat_rows: list[dict[str, Any]] = []
        self._my_identities = _current_user_identities()
        self._show_loading_on_next_get = False
        self._chat_loading = False
        self._inline_edit_row: _OwnCommentChatRow | None = None
        self._pending_delete_comment_id: Any = None
        self._can_comment_display = True
        self._can_comment_create = True
        self._can_comment_edit = True
        self._can_comment_delete = True

        self._load_timer = QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.setInterval(250)
        self._load_timer.timeout.connect(self._start_load_comments)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.setObjectName("validationCommentPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QWidget#validationCommentPanel {{ background-color: {_COMMENT_SECTION_BG}; }}"
        )
        _force_widget_window_bg(self, _COMMENT_SECTION_BG)

        header = QWidget()
        header.setStyleSheet(_comment_panel_header_stylesheet())
        header.setFixedHeight(_COMMENT_PANEL_HEADER_HEIGHT_PX)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(*_COMMENT_PANEL_HEADER_MARGINS)
        header_layout.setSpacing(_COMMENT_PANEL_HEADER_SPACING)
        title = QLabel("Comments")
        title.setObjectName("commentPanelHeaderTitle")
        title.setMaximumHeight(_COMMENT_PANEL_HEADER_HEIGHT_PX)
        header_layout.addWidget(title)
        header_layout.addStretch()
        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setFixedWidth(52)
        self._btn_refresh.setMaximumHeight(_COMMENT_PANEL_HEADER_HEIGHT_PX - 2)
        self._btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_refresh.setEnabled(False)
        self._btn_refresh.clicked.connect(self._on_refresh_clicked)
        header_layout.addWidget(self._btn_refresh)
        layout.addWidget(header)

        self._format_bar = QWidget()
        self._format_bar.setObjectName("commentFormatBar")
        self._format_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        _force_widget_window_bg(self._format_bar, _COMMENT_SECTION_BG)
        self._format_bar.setStyleSheet(
            f"QWidget#commentFormatBar {{ background: {_COMMENT_SECTION_BG}; border: 1px solid #e2e8f0; border-radius: 3px; }}"
            f"QWidget#commentFormatBar QToolButton {{ background: transparent; border: 1px solid transparent; "
            f"border-radius: 2px; padding: 0px 2px; color: #334155; font-size: {APP_FONT_SIZE_PX}px; "
            f"min-width: {APP_FONT_SIZE_PX + 5}px; max-height: {APP_FONT_SIZE_PX + 5}px; }}"
            "QWidget#commentFormatBar QToolButton:hover { background: #e2e8f0; border-color: #cbd5e1; }"
            "QWidget#commentFormatBar QToolButton::menu-indicator { image: none; width: 0px; height: 0px; border: none; }"
            "QWidget#commentFormatBar QToolButton:checked { background: #dbeafe; border: 1px solid #93c5fd; color: #1e40af; }"
            "QWidget#commentFormatBar QToolButton:checked:hover { background: #bfdbfe; border-color: #60a5fa; }"
            "QWidget#commentFormatBar QToolButton#commentFmtBullet[fmtBarOn=\"true\"], "
            "QWidget#commentFormatBar QToolButton#commentFmtNumber[fmtBarOn=\"true\"] "
            "{ background: #dbeafe; border: 1px solid #93c5fd; border-radius: 2px; }"
        )
        fmt_layout = QHBoxLayout(self._format_bar)
        fmt_layout.setContentsMargins(3, 1, 3, 1)
        fmt_layout.setSpacing(1)

        def _ft_btn(label: str, tip: str, slot) -> QToolButton:
            b = QToolButton()
            b.setText(label)
            b.setToolTip(tip)
            b.setCheckable(True)
            b.setAutoRaise(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            return b

        self._fmt_bold_btn = _ft_btn("B", "Bold", self._fmt_bold)
        self._fmt_italic_btn = _ft_btn("I", "Italic", self._fmt_italic)
        self._fmt_underline_btn = _ft_btn("U", "Underline", self._fmt_underline)
        fmt_layout.addWidget(self._fmt_bold_btn)
        fmt_layout.addWidget(self._fmt_italic_btn)
        fmt_layout.addWidget(self._fmt_underline_btn)

        _menu_sheet = _comment_list_gallery_menu_stylesheet()
        _list_btn_max = APP_FONT_SIZE_PX + 5

        bullet_btn = QToolButton()
        bullet_btn.setObjectName("commentFmtBullet")
        bullet_btn.setIcon(_word_toolbar_bullets_icon())
        bullet_btn.setIconSize(_WORD_LIST_ICON_SIZE)
        bullet_btn.setFixedSize(_list_btn_max, _list_btn_max)
        bullet_btn.setToolTip("Bullets (Word-style gallery)")
        bullet_btn.setAutoRaise(True)
        bullet_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        bullet_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        bullet_menu = QMenu(bullet_btn)
        bullet_menu.setStyleSheet(_menu_sheet)
        bullet_specs: tuple[tuple[QTextListFormat.Style, str, str], ...] = (
            (QTextListFormat.Style.ListDisc, "Solid round bullet", "Filled circle (default bullet)"),
            (QTextListFormat.Style.ListCircle, "Hollow round bullet", "Open circle"),
            (QTextListFormat.Style.ListSquare, "Square bullet", "Filled square"),
        )
        for style, title, tip in bullet_specs:
            act = QAction(_list_style_menu_icon(style), title, bullet_menu)
            act.setToolTip(tip)
            act.triggered.connect(partial(self._apply_bullet_list_style, style))
            bullet_menu.addAction(act)
        bullet_menu.addSeparator()
        extra_bullets: tuple[tuple[str, QTextListFormat.Style, str, str], ...] = (
            ("\u2794", QTextListFormat.Style.ListDisc, "Arrow-style marker", "Uses solid bullet with arrow prefix (Word-style)"),
            ("\u2713", QTextListFormat.Style.ListCircle, "Check-style marker", "Uses hollow circle list with check prefix"),
            ("\u2014", QTextListFormat.Style.ListSquare, "Em dash marker", "Uses square list with dash prefix"),
        )
        for sym, style, title, tip in extra_bullets:
            act = QAction(_list_style_menu_icon(style), f"{sym}  {title}", bullet_menu)
            act.setToolTip(tip)
            act.triggered.connect(partial(self._apply_bullet_list_with_prefix, style, sym + " "))
            bullet_menu.addAction(act)
        # Avoid setMenu() so the style does not paint a menu-button ▼ on the icon.
        bullet_btn.clicked.connect(
            lambda: bullet_menu.popup(bullet_btn.mapToGlobal(QPoint(0, bullet_btn.height())))
        )
        self._fmt_bullet_btn = bullet_btn
        fmt_layout.addWidget(bullet_btn)

        number_btn = QToolButton()
        number_btn.setObjectName("commentFmtNumber")
        number_btn.setIcon(_word_toolbar_numbering_icon())
        number_btn.setIconSize(_WORD_LIST_ICON_SIZE)
        number_btn.setFixedSize(_list_btn_max, _list_btn_max)
        number_btn.setToolTip("Numbering (Word-style gallery)")
        number_btn.setAutoRaise(True)
        number_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        number_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        number_menu = QMenu(number_btn)
        number_menu.setStyleSheet(_menu_sheet)
        numbering_specs: tuple[tuple[QTextListFormat.Style, str, str, str, str], ...] = (
            (QTextListFormat.Style.ListDecimal, "", ".", "1. 2. 3.", "Numbered with period"),
            (QTextListFormat.Style.ListDecimal, "", ")", "1) 2) 3)", "Numbered with closing parenthesis"),
            (QTextListFormat.Style.ListDecimal, "(", ")", "(1) (2) (3)", "Numbered in parentheses"),
            (QTextListFormat.Style.ListLowerAlpha, "", ".", "a. b. c.", "Lowercase letters with period"),
            (QTextListFormat.Style.ListLowerAlpha, "", ")", "a) b) c)", "Lowercase letters with )"),
            (QTextListFormat.Style.ListUpperAlpha, "", ".", "A. B. C.", "Uppercase letters with period"),
            (QTextListFormat.Style.ListUpperAlpha, "", ")", "A) B) C)", "Uppercase letters with )"),
            (QTextListFormat.Style.ListLowerRoman, "", ".", "i. ii. iii.", "Lowercase Roman numerals"),
            (QTextListFormat.Style.ListUpperRoman, "", ".", "I. II. III.", "Uppercase Roman numerals"),
        )
        for style, prefix, suffix, title, tip in numbering_specs:
            act = QAction(_list_style_menu_icon(style), title, number_menu)
            act.setToolTip(tip)
            act.triggered.connect(partial(self._apply_numbered_list_variant, style, prefix, suffix))
            number_menu.addAction(act)
        number_btn.clicked.connect(
            lambda: number_menu.popup(number_btn.mapToGlobal(QPoint(0, number_btn.height())))
        )
        self._fmt_number_btn = number_btn
        fmt_layout.addWidget(number_btn)
        fmt_layout.addStretch(1)
        layout.addWidget(self._format_bar)
        self._format_bar.setEnabled(False)

        self._chat_scroll = QScrollArea()
        self._chat_scroll.setObjectName("commentChatScroll")
        self._chat_scroll.setWidgetResizable(True)
        self._chat_scroll.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._chat_scroll.setStyleSheet(
            f"QScrollArea#commentChatScroll {{ border: 1px solid #e2e8f0; border-radius: 3px; "
            f"background-color: {_COMMENT_SECTION_BG}; }}"
        )
        self._chat_host = QWidget()
        self._chat_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        _force_widget_window_bg(self._chat_host, _COMMENT_SECTION_BG)
        self._chat_layout = QVBoxLayout(self._chat_host)
        self._chat_layout.setContentsMargins(2, 2, 2, 2)
        self._chat_layout.setSpacing(1)
        self._chat_scroll.setWidget(self._chat_host)
        _force_widget_window_bg(self._chat_scroll.viewport(), _COMMENT_SECTION_BG)
        layout.addWidget(self._chat_scroll, 1)

        input_row = QHBoxLayout()
        input_row.setSpacing(3)
        self._editor = QTextEdit()
        self._editor.setAcceptRichText(True)
        self._editor.document().setDocumentMargin(0)
        self._editor.setPlaceholderText("Type a message…")
        self._editor.setMinimumHeight(28)
        self._editor.setMaximumHeight(44)
        self._editor.setStyleSheet(
            _comment_message_textedit_stylesheet(
                max(9, APP_FONT_SIZE_PX - 3), padding="1px 6px", bg=_COMMENT_SECTION_BG
            )
        )
        _force_textedit_surface_bg(self._editor, _COMMENT_SECTION_BG)
        self._editor.installEventFilter(self)
        self._editor.cursorPositionChanged.connect(self._sync_format_toolbar)
        self._editor.selectionChanged.connect(self._sync_format_toolbar)
        input_row.addWidget(self._editor, 1)
        self._btn_send = QPushButton("Send")
        self._btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_send.setFixedWidth(50)
        self._btn_send.setFixedHeight(22)
        self._btn_send.setStyleSheet(
            "QPushButton { background: #e2e8f0; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 8px; "
            "font-size: 9px; font-weight: 600; padding: 0 5px; }"
            "QPushButton:hover { background: #cbd5e1; }"
            "QPushButton:pressed { background: #94a3b8; }"
            "QPushButton:disabled { background: #f1f5f9; color: #94a3b8; border: 1px solid #e2e8f0; }"
        )
        self._btn_send.setEnabled(False)
        self._btn_send.clicked.connect(self._on_send_clicked)
        input_row.addWidget(self._btn_send)
        layout.addLayout(input_row)
        self._hint = QLabel(
            "Enter sends. In a bullet/number list, Enter adds another row; Ctrl+Enter sends. "
            "Shift+Enter starts a new line inside the same row."
        )
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet(_COMMENT_AUX_LABEL_STYLE)
        layout.addWidget(self._hint)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setVisible(False)
        layout.addWidget(self._status)

        table = getattr(self._vp, "table", None)
        if table is not None and hasattr(table, "itemSelectionChanged"):
            table.itemSelectionChanged.connect(self._on_selection_changed)
        else:
            register_listener = getattr(self._vp, "register_comment_context_listener", None)
            if callable(register_listener):
                register_listener(self._on_selection_changed)
        self._refresh_comment_access()
        self._update_context()
        self._render_chat()
        self._sync_format_toolbar()

    def _refresh_comment_access(self) -> None:
        steps = get_nav_access_steps()
        if steps is None:
            self._can_comment_display = True
            self._can_comment_create = True
            self._can_comment_edit = True
            self._can_comment_delete = True
            return
        allowed_actions = collect_allowed_action_names(steps)
        self._can_comment_display = nav_action_visible(
            "API: All in One", "comment_display", allowed_actions
        )
        self._can_comment_create = nav_action_visible(
            "API: All in One", "comment_create", allowed_actions
        )
        self._can_comment_edit = nav_action_visible(
            "API: All in One", "comment_edit", allowed_actions
        )
        self._can_comment_delete = nav_action_visible(
            "API: All in One", "comment_delete", allowed_actions
        )

    def _list_format_at_cursor(self) -> QTextListFormat | None:
        b = self._editor.textCursor().block()
        if not b.isValid():
            return None
        tl = b.textList()
        if tl is None:
            return None
        return tl.format()

    def _editor_cursor_in_list(self) -> bool:
        return self._list_format_at_cursor() is not None

    @Slot()
    def _sync_format_toolbar(self) -> None:
        if not hasattr(self, "_editor") or getattr(self, "_fmt_bold_btn", None) is None:
            return
        tc = self._editor.textCursor()
        cf = tc.charFormat()
        bold_on = cf.fontWeight() == QFont.Weight.Bold
        italic_on = cf.fontItalic()
        underline_on = cf.fontUnderline()
        for btn, on in (
            (self._fmt_bold_btn, bold_on),
            (self._fmt_italic_btn, italic_on),
            (self._fmt_underline_btn, underline_on),
        ):
            btn.blockSignals(True)
            btn.setChecked(on)
            btn.blockSignals(False)
        lf = self._list_format_at_cursor()
        st = lf.style() if lf is not None else None
        bullet_on = (st in _BULLET_LIST_STYLES) if st is not None else False
        number_on = (st in _NUMBERED_LIST_STYLES) if st is not None else False
        self._fmt_bullet_btn.setProperty("fmtBarOn", bullet_on)
        self._fmt_number_btn.setProperty("fmtBarOn", number_on)
        self._restyle_format_bar_list_btn(self._fmt_bullet_btn)
        self._restyle_format_bar_list_btn(self._fmt_number_btn)

    def _restyle_format_bar_list_btn(self, btn: QToolButton) -> None:
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _merge_char_format(self, fmt: QTextCharFormat) -> None:
        tc = self._editor.textCursor()
        if tc.hasSelection():
            tc.mergeCharFormat(fmt)
        else:
            self._editor.mergeCurrentCharFormat(fmt)

    @Slot()
    def _fmt_bold(self) -> None:
        tc = self._editor.textCursor()
        w = (
            QFont.Weight.Normal
            if tc.charFormat().fontWeight() == QFont.Weight.Bold
            else QFont.Weight.Bold
        )
        f = QTextCharFormat()
        f.setFontWeight(w)
        self._merge_char_format(f)
        self._sync_format_toolbar()

    @Slot()
    def _fmt_italic(self) -> None:
        tc = self._editor.textCursor()
        f = QTextCharFormat()
        f.setFontItalic(not tc.charFormat().fontItalic())
        self._merge_char_format(f)
        self._sync_format_toolbar()

    @Slot()
    def _fmt_underline(self) -> None:
        tc = self._editor.textCursor()
        f = QTextCharFormat()
        f.setFontUnderline(not tc.charFormat().fontUnderline())
        self._merge_char_format(f)
        self._sync_format_toolbar()

    def _apply_bullet_list_style(self, style: QTextListFormat.Style) -> None:
        fmt = QTextListFormat()
        fmt.setStyle(style)
        self._editor.textCursor().createList(fmt)
        self._sync_format_toolbar()

    def _apply_bullet_list_with_prefix(self, style: QTextListFormat.Style, prefix: str) -> None:
        fmt = QTextListFormat()
        fmt.setStyle(style)
        if prefix:
            fmt.setNumberPrefix(prefix)
        self._editor.textCursor().createList(fmt)
        self._sync_format_toolbar()

    def _apply_numbered_list_variant(
        self, style: QTextListFormat.Style, number_prefix: str, number_suffix: str
    ) -> None:
        fmt = QTextListFormat()
        fmt.setStyle(style)
        if number_prefix:
            fmt.setNumberPrefix(number_prefix)
        if number_suffix:
            fmt.setNumberSuffix(number_suffix)
        self._editor.textCursor().createList(fmt)
        self._sync_format_toolbar()

    def _current_validation_id(self) -> Any:
        row = self._vp.get_selected_row()
        if not row:
            return None
        return _validation_internal_id(row)

    def _update_context(self) -> None:
        vid = self._current_validation_id()
        enabled = vid is not None and not self._busy
        self._btn_send.setEnabled(enabled and self._can_comment_create)
        self._btn_refresh.setEnabled(enabled and self._can_comment_display)
        self._format_bar.setEnabled(enabled and self._can_comment_create)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._editor and event.type() == QEvent.Type.KeyPress:
            key_event = event
            key = key_event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                mods = key_event.modifiers()
                if mods & Qt.KeyboardModifier.ShiftModifier:
                    return False
                if mods & Qt.KeyboardModifier.ControlModifier:
                    self._on_send_clicked()
                    return True
                if self._editor_cursor_in_list():
                    return False
                self._on_send_clicked()
                return True
        return super().eventFilter(watched, event)

    def _on_selection_changed(self) -> None:
        self._refresh_comment_access()
        ir = self._inline_edit_row
        if ir is not None:
            ir.cancel_edit()
        self._inline_edit_row = None
        self._update_context()
        if self._current_validation_id() is not None:
            self._show_loading_on_next_get = True
            self._chat_loading = True
            self._render_chat()
            self._load_timer.start()
        else:
            self._load_timer.stop()
            self._chat_rows = []
            self._show_loading_on_next_get = False
            self._chat_loading = False
            self._editor.clear()
            self._sync_format_toolbar()
            self._status.setVisible(False)
            self._render_chat()

    def _on_refresh_clicked(self) -> None:
        if not self._can_comment_display:
            self._flash_status("Require Permission.", error=True)
            return
        self._show_loading_on_next_get = False
        self._start_load_comments()

    def _start_load_comments(self) -> None:
        if self._busy:
            return
        if not self._can_comment_display:
            self._chat_rows = []
            self._chat_loading = False
            self._render_chat()
            return
        vid = self._current_validation_id()
        if vid is None:
            return
        self._run_worker(
            "get_all",
            vid,
            "",
            show_chat_loading=self._show_loading_on_next_get,
        )
        self._show_loading_on_next_get = False

    def _on_send_clicked(self) -> None:
        if not self._can_comment_create:
            self._flash_status("Require Permission.", error=True)
            return
        vid = self._current_validation_id()
        if vid is None:
            return
        text = self._editor.toPlainText().strip()
        if not text:
            self._flash_status("Type a message before sending.", error=True)
            return
        body_html = self._editor.toHtml().strip()
        self._run_worker("add", vid, body_html)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._editor.setReadOnly(busy)
        ir = self._inline_edit_row
        if ir is not None:
            ir.set_edit_busy(busy)
        self._update_context()

    def _run_worker(
        self,
        op: str,
        validation_id: Any,
        text: str,
        *,
        show_chat_loading: bool = False,
    ) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        self._cleanup_worker()
        self._pending_op = op
        if op == "get_all" and show_chat_loading:
            self._chat_loading = True
            self._render_chat()
        self._set_busy(True)
        self._status.setVisible(False)
        self._thread = QThread(self)
        self._worker = _CommentWorker(op, validation_id, text)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()

    @Slot()
    def _on_worker_finished(self, result: dict[str, Any]) -> None:
        self._set_busy(False)
        op = self._pending_op
        self._pending_op = ""
        ok = result.get("success") is True
        msg = str(result.get("message", "") or "").strip()

        if op == "get_all":
            self._chat_loading = False
            if ok:
                rows = result.get("comments")
                self._chat_rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
                self._render_chat()
                if msg:
                    self._flash_status(msg, error=False)
            else:
                self._chat_rows = []
                self._render_chat()
                self._flash_status(msg or "Failed to load comments.", error=True)
            return

        if op == "delete":
            dc = self._pending_delete_comment_id
            self._pending_delete_comment_id = None
            if ok:
                ir = self._inline_edit_row
                if ir is not None and dc is not None and str(ir._comment_id) == str(dc):
                    self._inline_edit_row = None
                self._flash_status(msg or "Comment deleted.", error=False)
                QTimer.singleShot(60, self._start_load_comments)
            else:
                self._flash_status(msg or "Delete failed.", error=True)
            return

        if ok:
            self._editor.clear()
            self._sync_format_toolbar()
            if op == "update":
                self._inline_edit_row = None
                self._flash_status(msg or "Message updated.", error=False)
            else:
                self._flash_status(msg or "Message sent.", error=False)
            QTimer.singleShot(60, self._start_load_comments)
        else:
            if op == "update" and "expired" in msg.lower():
                ir = self._inline_edit_row
                if ir is not None:
                    ir.cancel_edit()
                self._inline_edit_row = None
            self._flash_status(msg or "Request failed.", error=True)

    def _parse_dt(self, value: Any) -> datetime | None:
        s = str(value or "").strip()
        if not s:
            return None
        s = s.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            pass
        # Fallback: some Python versions / fractional lengths choke on fromisoformat.
        base = s.split("+", 1)[0].strip()
        if "T" in base:
            head = base.split("T", 1)[0] + "T" + base.split("T", 1)[1].split(".", 1)[0]
        else:
            head = base[:19] if len(base) >= 19 else base
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(head[:19], fmt)
            except ValueError:
                continue
        return None

    def _is_edit_window_open(self, created_at: Any) -> bool:
        """5-minute edit window. Naive API timestamps are treated as UTC (typical server time)."""
        dt = self._parse_dt(created_at)
        if dt is None:
            return False
        posted = _dt_to_utc(dt)
        now = datetime.now(timezone.utc)
        return now - posted <= timedelta(minutes=5)

    def _register_inline_edit(self, row_widget: _OwnCommentChatRow) -> None:
        prev = self._inline_edit_row
        if prev is not None and prev is not row_widget:
            prev.cancel_edit()
        self._inline_edit_row = row_widget

    def _request_delete_comment(self, row: dict[str, Any]) -> None:
        if not self._can_comment_delete:
            self._flash_status("Require Permission.", error=True)
            return
        cid = _comment_id_from_row(row)
        if cid is None:
            self._flash_status("Unable to delete this message.", error=True)
            return
        r = QMessageBox.question(
            self,
            "Delete comment",
            "Delete this message permanently?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        self._pending_delete_comment_id = cid
        self._run_worker("delete", cid, "")

    def _clear_chat_widgets(self) -> None:
        while self._chat_layout.count():
            item = self._chat_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _render_chat(self) -> None:
        self._my_identities = _current_user_identities()
        self._clear_chat_widgets()
        if self._current_validation_id() is None:
            blank = QLabel("Select a validation row to view its chat.")
            blank.setStyleSheet(_COMMENT_AUX_LABEL_STYLE)
            self._chat_layout.addWidget(blank)
            self._chat_layout.addStretch(1)
            return
        if not self._can_comment_display:
            blank = QLabel("Require Permission.")
            blank.setStyleSheet(_COMMENT_AUX_LABEL_STYLE)
            self._chat_layout.addWidget(blank)
            self._chat_layout.addStretch(1)
            return
        if self._chat_loading:
            loading = QLabel("Loading chat...")
            loading.setStyleSheet(_COMMENT_AUX_LABEL_STYLE)
            self._chat_layout.addWidget(loading)
            self._chat_layout.addStretch(1)
            return
        if not self._chat_rows:
            blank = QLabel("No comments yet. Start the conversation.")
            blank.setStyleSheet(_COMMENT_AUX_LABEL_STYLE)
            self._chat_layout.addWidget(blank)
            self._chat_layout.addStretch(1)
            return
        for row in self._chat_rows:
            self._chat_layout.addWidget(self._build_chat_row(row))
        self._chat_layout.addStretch(1)
        QTimer.singleShot(0, self._scroll_chat_to_bottom)

    def _scroll_chat_to_bottom(self) -> None:
        bar = self._chat_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _build_chat_row(self, row: dict[str, Any]) -> QWidget:
        author = str(row.get("author", "") or "").strip() or "Unknown"
        when_raw = _created_at_from_row(row)
        when = _format_cell(when_raw, "createdAt", _COMMENT_CREATED_AT_KEYS)
        cid = _comment_id_from_row(row)
        window_open = self._is_edit_window_open(when_raw)
        show_row_actions = _author_is_current_user(author, self._my_identities) and cid is not None
        can_edit = show_row_actions and self._can_comment_edit
        can_delete = show_row_actions and self._can_comment_delete
        pencil_enabled = can_edit and window_open
        text = str(row.get("comment", "") or "")

        if show_row_actions:
            row_copy = dict(row)
            if cid is not None and "commentId" not in row_copy:
                row_copy["commentId"] = cid
            when_suffix = f"  ·  {when}" if when else ""
            return _OwnCommentChatRow(
                self,
                row_copy,
                author=author,
                when_suffix=when_suffix,
                text=text,
                pencil_enabled=pencil_enabled,
                can_delete=can_delete,
            )

        wrap = QWidget()
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 1, 0, 1)
        outer.setSpacing(1)

        meta = QLabel(author + (f"  ·  {when}" if when else ""))
        meta.setStyleSheet(_COMMENT_AUX_LABEL_STYLE)
        meta.setWordWrap(True)
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(6)
        meta_row.addWidget(meta, 1)
        outer.addLayout(meta_row)

        fs = max(9, APP_FONT_SIZE_PX - 3)
        body = _RichCommentBodyLabel(fs, wrap)
        body.setMargin(0)
        body.setText(_comment_body_display_html(text))
        # Use the same text-only body + bubble wrapper as own rows so heights stay consistent.
        body.setStyleSheet(_comment_message_text_only_stylesheet(fs))

        actions_host = QWidget()
        actions_host.setStyleSheet("background: transparent; border: none;")
        al = QHBoxLayout(actions_host)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(0)
        bubble = _CommentMessageHoverRow(body, actions_host, wrap)
        outer.addWidget(bubble)

        return wrap

    def _flash_status(self, text: str, *, error: bool) -> None:
        self._status.setText(text)
        self._status.setStyleSheet(FORM_ERROR_LABEL_STYLE if error else MODAL_FEEDBACK_SUCCESS_STYLE)
        self._status.setVisible(True)

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None
