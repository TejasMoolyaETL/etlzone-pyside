"""Excel All Import — activity dashboard (Import Sessions / History)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QFontMetrics, QIcon, QMouseEvent, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.api import (
    api_analyze_import_if_present,
    api_get_all_import_session_ids,
    api_get_import_sheets_by_uuid,
)
from app.etl.excel.message_banner import (
    clear_page_message,
    configure_message_banner,
    show_page_error,
    show_page_info,
)
from core.user_context import get_user_profile
from ui.form_combobox_style import apply_form_combobox_field, install_combo_popup_below_field

_ASSETS = Path(__file__).resolve().parents[3] / "assets" / "excel"
_PLUS_SVG = _ASSETS / "plus_white.svg"
_SEARCH_SVG = _ASSETS / "search_muted.svg"
_CHEVRON_LEFT_SVG = _ASSETS / "chevron_left.svg"
_CHEVRON_RIGHT_SVG = _ASSETS / "chevron_right.svg"

_PAGE_BG = "#f7f7fa"
_ACCENT = "#2e73f5"
_TEXT_DARK = "#111827"
_TEXT_MUTED = "#6b7280"
_BORDER = "#e8eaed"
_BORDER_INPUT = "#d1d6de"
_HEADER_BG = "#f2f5f7"
_ROW_ALT = "#f2f5f7"
_PAGE_SIZE = 8

# Figma 54:91 — Import Sessions columns (widths abut).
_SESSION_COLUMNS: tuple[tuple[str, str, int], ...] = (
    ("name", "IMPORT NAME", 200),
    ("file", "FILE NAME", 180),
    ("connection", "TARGET CONNECTION", 160),
    ("table", "TARGET TABLE", 150),
    ("type", "FILE TYPE", 90),
    ("operation", "OPERATION", 140),
    ("status", "STATUS", 110),
)

# Figma 62:207 — Import History columns.
_HISTORY_COLUMNS: tuple[tuple[str, str, int], ...] = (
    ("name", "IMPORT NAME", 180),
    ("date", "EXECUTION DATE", 170),
    ("duration", "DURATION", 110),
    ("processed", "ROWS PROCESSED", 140),
    ("failed", "ROWS FAILED", 110),
    ("status", "STATUS", 110),
    ("by", "EXECUTED BY", 120),
)

_ROW_H = 48
_HEADER_H = 42
_PAGER_H = 28
_NEW_BTN_H = 34

_STATUS_STYLES: dict[str, tuple[str, str]] = {
    "completed": ("#dcfce7", "#15803d"),
    "failed": ("#fee2e2", "#b91c1c"),
    "in_progress": ("#dbeafe", "#1d4ed8"),
    "pending": ("#f3f4f6", "#374151"),
}

_PAGE_STYLE = f"""
    QWidget#allImportActivityBody {{ background: {_PAGE_BG}; }}
    QLabel#allImportActivityTitle {{
        color: {_TEXT_DARK}; font-size: 22px; font-weight: 700;
        background: transparent; border: none;
    }}
    QPushButton#allImportActivityNew {{
        background: {_ACCENT}; color: #ffffff; border: none; border-radius: 4px;
        padding: 0 18px 0 14px; font-size: 13px; font-weight: 600;
    }}
    QPushButton#allImportActivityNew:hover {{ background: #1f63e0; }}
    QFrame#allImportActivityTabBar {{
        background: transparent; border: none; border-bottom: 2px solid {_BORDER};
    }}
    QPushButton#allImportActivityTab {{
        background: transparent; border: none; border-bottom: 2px solid transparent;
        color: {_TEXT_MUTED}; font-size: 13px; font-weight: 500;
        padding: 10px 20px; margin-bottom: -2px; min-height: 36px;
    }}
    QPushButton#allImportActivityTab:checked {{
        color: {_ACCENT}; font-weight: 600; border-bottom: 2px solid {_ACCENT};
    }}
    QPushButton#allImportActivityTab:hover {{ color: {_ACCENT}; }}
    QLabel#allImportActivityCaption {{
        color: {_TEXT_MUTED}; font-size: 10px; font-weight: 600;
        letter-spacing: 0.4px; background: transparent; border: none;
    }}
    QFrame#allImportActivityTableCard {{
        background: #ffffff; border: 1px solid {_BORDER}; border-radius: 8px;
    }}
    QFrame#allImportActivityHeaderRow {{
        background: {_HEADER_BG}; border: none; border-bottom: 1px solid {_BORDER};
        border-top-left-radius: 8px; border-top-right-radius: 8px;
    }}
    QLabel#allImportActivityColHead {{
        color: {_TEXT_MUTED}; font-size: 11px; font-weight: 700;
        background: transparent; border: none;
    }}
    QFrame#allImportActivityDataRow {{
        border: none; border-bottom: 1px solid {_BORDER};
    }}
    QLabel#allImportActivityCellMuted {{
        color: {_TEXT_MUTED}; font-size: 13px; font-weight: 400;
        background: transparent; border: none;
    }}
    QLabel#allImportActivityCellDark {{
        color: {_TEXT_DARK}; font-size: 13px; font-weight: 400;
        background: transparent; border: none;
    }}
    QLabel#allImportActivityCellOp {{
        color: {_TEXT_MUTED}; font-size: 12px; font-weight: 600;
        background: transparent; border: none;
    }}
    QLabel#allImportActivityCellFailed {{
        color: #b91c1c; font-size: 13px; font-weight: 600;
        background: transparent; border: none;
    }}
    QLabel#allImportActivityCellFailedZero {{
        color: {_TEXT_DARK}; font-size: 13px; font-weight: 600;
        background: transparent; border: none;
    }}
    QPushButton#allImportActivityNameLink {{
        background: transparent; border: none; color: {_ACCENT};
        font-size: 13px; font-weight: 600; text-align: left; padding: 0;
    }}
    QPushButton#allImportActivityNameLink:hover {{ color: #1f63e0; }}
    QLabel#allImportActivityEmpty {{
        color: {_TEXT_MUTED}; font-size: 13px; background: transparent;
        border: none; padding: 40px 16px;
    }}
    QFrame#allImportActivityFooter {{
        background: #ffffff; border: none; border-top: 1px solid {_BORDER};
        border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;
    }}
    QLabel#allImportActivityFooterText {{
        color: {_TEXT_MUTED}; font-size: 13px; background: transparent; border: none;
    }}
    QPushButton#allImportActivityPageBtn {{
        background: #ffffff; color: {_TEXT_MUTED}; border: 1px solid {_BORDER_INPUT};
        border-radius: 4px; padding: 0 10px; font-size: 13px; font-weight: 500;
        min-width: {_PAGER_H}px;
    }}
    QPushButton#allImportActivityPageBtn:checked {{
        background: {_ACCENT}; color: #ffffff; border-color: {_ACCENT}; font-weight: 600;
    }}
    QPushButton#allImportActivityNavBtn {{
        background: #ffffff; border: 1px solid {_BORDER_INPUT}; border-radius: 4px;
        padding: 0; min-width: {_PAGER_H}px; max-width: {_PAGER_H}px;
    }}
    QPushButton#allImportActivityNavBtn:disabled {{
        background: {_HEADER_BG}; border-color: {_BORDER};
    }}
    QScrollArea#allImportActivityScroll {{
        background: transparent; border: none;
    }}
    QScrollArea#allImportActivityScroll > QWidget > QWidget {{
        background: transparent;
    }}
"""


def _svg_pixmap(path: Path, size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    if path.is_file():
        renderer = QSvgRenderer(str(path))
        painter = QPainter(pm)
        renderer.render(painter)
        painter.end()
    return pm


def _token() -> str | None:
    profile = get_user_profile() or {}
    token = (
        profile.get("token")
        or profile.get("accessToken")
        or profile.get("access_token")
        or profile.get("jwt")
    )
    return str(token) if token else None


def _normalize_status(raw: Any) -> tuple[str, str]:
    text = str(raw or "").strip()
    if not text:
        return "Pending", "pending"
    key = text.lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "new": ("Pending", "pending"),
        "created": ("Pending", "pending"),
        "pending": ("Pending", "pending"),
        "file_uploaded": ("In Progress", "in_progress"),
        "uploaded": ("In Progress", "in_progress"),
        "analyzed": ("In Progress", "in_progress"),
        "mapped": ("In Progress", "in_progress"),
        "in_progress": ("In Progress", "in_progress"),
        "running": ("In Progress", "in_progress"),
        "executing": ("In Progress", "in_progress"),
        "executed": ("Completed", "completed"),
        "completed": ("Completed", "completed"),
        "success": ("Completed", "completed"),
        "succeeded": ("Completed", "completed"),
        "failed": ("Failed", "failed"),
        "failure": ("Failed", "failed"),
        "error": ("Failed", "failed"),
    }
    return mapping.get(key, (text.replace("_", " ").title(), "pending"))


def _format_file_type(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return "—"
    upper = text.upper()
    mapping = {
        "EXCEL": "Excel",
        "XLSX": "Excel",
        "XLS": "Excel",
        "CSV": "CSV",
        "JSON": "JSON",
    }
    if upper in mapping:
        return mapping[upper]
    lower = text.lower()
    if lower.endswith((".xlsx", ".xls")):
        return "Excel"
    if lower.endswith(".csv"):
        return "CSV"
    if lower.endswith(".json"):
        return "JSON"
    return text.title()


def _file_type_from_row(row: dict[str, Any]) -> str:
    typed = _format_file_type(row.get("sourceType") or row.get("fileType") or "")
    if typed != "—":
        return typed
    from_name = _format_file_type(str(row.get("fileName") or ""))
    if from_name != "—":
        return from_name
    state = str(row.get("state") or "").strip().upper()
    if state in {"FILE_UPLOADED", "ANALYZED", "MAPPED", "EXECUTED", "COMPLETED"}:
        return "Excel"
    return "—"


def _format_operation(raw: Any) -> str:
    text = str(raw or "").strip().upper().replace("-", "_").replace(" ", "_")
    if not text:
        return "—"
    if text in {"DROP_CREATE", "DROP_AND_CREATE", "DROPANDCREATE"}:
        return "DROP & CREATE"
    if text == "DELETE":
        return "DELETE"
    return text.replace("_", " ")


def _pick(row: dict[str, Any], *keys: str) -> Any:
    raw = row.get("_raw") if isinstance(row.get("_raw"), dict) else {}
    for key in keys:
        if row.get(key) is not None and str(row.get(key)).strip() != "":
            return row.get(key)
        if isinstance(raw, dict) and raw.get(key) is not None and str(raw.get(key)).strip() != "":
            return raw.get(key)
    return None


def _format_execution_date(raw: Any) -> str:
    if raw is None or str(raw).strip() == "":
        return "—"
    text = str(raw).strip()
    if " AM" in text.upper() or " PM" in text.upper():
        return text
    try:
        from datetime import datetime

        cleaned = text.replace("Z", "+00:00")
        dt = None
        try:
            dt = datetime.fromisoformat(cleaned)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(text[:19], fmt)
                    break
                except ValueError:
                    continue
        if dt is None:
            return text
        return dt.strftime("%Y-%m-%d %I:%M %p")
    except Exception:
        return text


def _format_duration(raw: Any) -> str:
    if raw is None or str(raw).strip() == "":
        return "—"
    text = str(raw).strip()
    if "m" in text.lower() and "s" in text.lower():
        return text
    try:
        value = float(text)
    except (TypeError, ValueError):
        return text
    # Heuristic: large numbers are milliseconds.
    seconds = int(value / 1000) if value >= 1000 else int(value)
    minutes, secs = divmod(max(0, seconds), 60)
    return f"{minutes}m {secs:02d}s"


def _format_count(raw: Any) -> str:
    if raw is None or str(raw).strip() == "":
        return "—"
    try:
        return f"{int(float(str(raw).replace(',', ''))):,}"
    except (TypeError, ValueError):
        return str(raw).strip()


def _failed_display(row: dict[str, Any], status_label: str) -> tuple[str, str]:
    """Return (text, object_name) for ROWS FAILED column."""
    raw = _pick(
        row,
        "rowsFailed",
        "failedRows",
        "failCount",
        "failedCount",
        "errorRows",
    )
    if status_label == "In Progress" and (raw is None or str(raw).strip() == ""):
        return "-", "allImportActivityCellFailedZero"
    if raw is None or str(raw).strip() == "":
        return "—", "allImportActivityCellFailedZero"
    try:
        n = int(float(str(raw).replace(",", "")))
    except (TypeError, ValueError):
        return str(raw).strip(), "allImportActivityCellFailedZero"
    if n > 0:
        return f"{n:,}", "allImportActivityCellFailed"
    return "0", "allImportActivityCellFailedZero"


def _executed_by(row: dict[str, Any]) -> str:
    value = _pick(
        row,
        "executedBy",
        "executedByUser",
        "executedByUsername",
        "createdBy",
        "createdByUser",
        "username",
        "userName",
        "owner",
        "user",
    )
    if isinstance(value, dict):
        for key in ("username", "userName", "name", "email"):
            if value.get(key):
                return str(value.get(key)).strip()
        return "—"
    text = str(value or "").strip()
    return text or "—"


def _connection_label(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("connectionName", "name", "label"):
            if value.get(key) is not None and str(value.get(key)).strip():
                return str(value.get(key)).strip()
        for key in ("id", "connectionId"):
            if value.get(key) is not None and str(value.get(key)).strip():
                return str(value.get(key)).strip()
        return "—"
    text = str(value or "").strip()
    return text or "—"


def _pick_target_table(sheets: list[dict[str, Any]]) -> str:
    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        for key in ("tableName", "targetTableName"):
            value = sheet.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        raw = sheet.get("_raw") if isinstance(sheet.get("_raw"), dict) else {}
        for key in ("tableName", "targetTableName", "target_table_name"):
            value = raw.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def _enrich_session_row(row: dict[str, Any], token: str) -> dict[str, Any]:
    """Fill file/table/connection via sheet + analyze-if-present APIs."""
    if row.get("_enriched"):
        return row
    sid = str(row.get("sessionId") or "").strip()
    if not sid:
        row["_enriched"] = True
        return row
    state = str(row.get("state") or "").strip().upper()
    if state in {"NEW", "CREATED", ""}:
        row["_enriched"] = True
        return row

    sheets_result = api_get_import_sheets_by_uuid(sid, token=token)
    if sheets_result.get("success"):
        sheets = [s for s in (sheets_result.get("data") or []) if isinstance(s, dict)]
        table = _pick_target_table(sheets)
        if table:
            row["targetTableName"] = table
        for sheet in sheets:
            for src, dst in (
                ("rowsProcessed", "rowsProcessed"),
                ("totalRows", "rowsProcessed"),
                ("failedRows", "rowsFailed"),
                ("failCount", "rowsFailed"),
                ("duration", "duration"),
                ("durationMs", "duration"),
                ("executedBy", "executedBy"),
                ("executionDate", "executionDate"),
                ("executedAt", "executionDate"),
                ("updatedAt", "executionDate"),
                ("createdAt", "executionDate"),
            ):
                if sheet.get(src) is not None and not row.get(dst):
                    row[dst] = sheet.get(src)

    present = api_analyze_import_if_present(sid, token=token)
    raw = present.get("raw") if isinstance(present.get("raw"), dict) else {}
    if raw.get("fileName") and not row.get("fileName"):
        row["fileName"] = raw.get("fileName")
    conn = raw.get("connectionId") or raw.get("connection")
    if conn is not None and not row.get("targetConnectionName"):
        row["targetConnectionName"] = _connection_label(conn)
    if present.get("targetTableName") and not row.get("targetTableName"):
        row["targetTableName"] = present.get("targetTableName")
    data_sheets = [s for s in (present.get("data") or []) if isinstance(s, dict)]
    if data_sheets and not row.get("targetTableName"):
        table = _pick_target_table(data_sheets)
        if table:
            row["targetTableName"] = table
    for src, dst in (
        ("rowsProcessed", "rowsProcessed"),
        ("totalRows", "rowsProcessed"),
        ("successfulRows", "rowsProcessed"),
        ("failedRows", "rowsFailed"),
        ("failCount", "rowsFailed"),
        ("duration", "duration"),
        ("durationMs", "duration"),
        ("executedBy", "executedBy"),
        ("executionDate", "executionDate"),
        ("executedAt", "executionDate"),
        ("updatedAt", "executionDate"),
        ("createdAt", "executionDate"),
    ):
        if raw.get(src) is not None and not row.get(dst):
            row[dst] = raw.get(src)
        if present.get(src) is not None and not row.get(dst):
            row[dst] = present.get(src)
    row["_enriched"] = True
    return row


class _SessionListWorker(QThread):
    """Fetch session list off the UI thread (one GET)."""

    succeeded = Signal(list)
    failed = Signal(str)

    def __init__(self, token: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._token = token

    def run(self) -> None:  # noqa: N802
        try:
            sessions = api_get_all_import_session_ids(token=self._token)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc) or "Failed to load imports.")
            return
        if not sessions.get("success"):
            self.failed.emit(str(sessions.get("message") or "Failed to load imports."))
            return
        rows = [dict(r) for r in (sessions.get("data") or []) if isinstance(r, dict)]
        self.succeeded.emit(rows)


class _EnrichPageWorker(QThread):
    """Enrich only the visible page of sessions (2 APIs each, max 8)."""

    finished_ok = Signal(int)

    def __init__(
        self,
        rows: list[dict[str, Any]],
        token: str,
        generation: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._rows = rows
        self._token = token
        self._generation = generation

    def run(self) -> None:  # noqa: N802
        if not self._rows:
            self.finished_ok.emit(self._generation)
            return
        workers = min(4, len(self._rows))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_enrich_session_row, row, self._token) for row in self._rows]
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception:
                    pass
        self.finished_ok.emit(self._generation)


def _status_badge(label: str, style_key: str) -> QLabel:
    bg, fg = _STATUS_STYLES.get(style_key, _STATUS_STYLES["pending"])
    badge = QLabel(label)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(
        f"QLabel {{ background: {bg}; color: {fg}; font-size: 11px; font-weight: 600; "
        "border: none; border-radius: 4px; padding: 4px 8px; }}"
    )
    badge.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    badge.setFixedHeight(24)
    return badge


def _elide(label: QLabel, text: str, max_width: int) -> None:
    metrics = QFontMetrics(label.font())
    elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(24, max_width - 4))
    label.setText(elided)
    label.setToolTip(text if elided != text else "")


def _col_shell(width: int) -> tuple[QWidget, QHBoxLayout]:
    shell = QWidget()
    shell.setStyleSheet("background: transparent; border: none;")
    shell.setFixedWidth(width)
    shell.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
    lay = QHBoxLayout(shell)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
    return shell, lay


def _text_col(
    text: str,
    *,
    object_name: str,
    width: int,
    elide: bool = True,
    align_right: bool = False,
) -> QWidget:
    shell, lay = _col_shell(width)
    lbl = QLabel()
    lbl.setObjectName(object_name)
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lbl.setWordWrap(False)
    align = Qt.AlignmentFlag.AlignVCenter | (
        Qt.AlignmentFlag.AlignRight if align_right else Qt.AlignmentFlag.AlignLeft
    )
    lbl.setAlignment(align)
    if elide:
        _elide(lbl, text, width)
    else:
        lbl.setText(text)
        lbl.setToolTip(text if text and text != "—" else "")
    lay.addWidget(lbl, 1)
    return shell


def _fill_row(layout: QHBoxLayout, cells: list[QWidget]) -> None:
    layout.setContentsMargins(16, 0, 16, 0)
    layout.setSpacing(0)
    for cell in cells:
        layout.addWidget(cell, 0)
    layout.addStretch(1)


class _ClickableSessionRow(QFrame):
    """Table row that opens the session when clicked anywhere."""

    clicked = Signal(dict)

    def __init__(self, row: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row = row
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("allImportActivityDataRow")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._row)
        super().mousePressEvent(event)


class AllImportActivityPage(QWidget):
    """Figma Excel Import dashboard: sessions table + New Import."""

    new_import_requested = Signal()
    view_session_requested = Signal(dict)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []
        self._filtered: list[dict[str, Any]] = []
        self._page = 0
        self._tab = "sessions"  # sessions | history
        self._page_buttons: list[QPushButton] = []
        self._load_generation = 0
        self._enrich_generation = 0
        self._list_worker: _SessionListWorker | None = None
        self._enrich_worker: _EnrichPageWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QWidget()
        body.setObjectName("allImportActivityBody")
        body.setStyleSheet(_PAGE_STYLE)
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(46, 20, 46, 24)
        body_l.setSpacing(16)

        # Title + New Import
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Excel Import")
        title.setObjectName("allImportActivityTitle")
        header.addWidget(title, 1)
        self.new_btn = QPushButton("New Import")
        self.new_btn.setObjectName("allImportActivityNew")
        self.new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_btn.setFixedHeight(_NEW_BTN_H)
        plus_pm = _svg_pixmap(_PLUS_SVG, 14)
        self.new_btn.setIcon(QIcon(plus_pm))
        self.new_btn.setIconSize(plus_pm.size())
        self.new_btn.clicked.connect(self.new_import_requested.emit)
        header.addWidget(self.new_btn, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        body_l.addLayout(header)

        # Tabs
        tab_bar = QFrame()
        tab_bar.setObjectName("allImportActivityTabBar")
        tab_l = QHBoxLayout(tab_bar)
        tab_l.setContentsMargins(0, 0, 0, 0)
        tab_l.setSpacing(0)
        self._tab_sessions = QPushButton("Import Sessions")
        self._tab_sessions.setObjectName("allImportActivityTab")
        self._tab_sessions.setCheckable(True)
        self._tab_sessions.setChecked(True)
        self._tab_sessions.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_sessions.clicked.connect(lambda: self._set_tab("sessions"))
        tab_l.addWidget(self._tab_sessions)
        self._tab_history = QPushButton("Import History")
        self._tab_history.setObjectName("allImportActivityTab")
        self._tab_history.setCheckable(True)
        self._tab_history.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_history.clicked.connect(lambda: self._set_tab("history"))
        tab_l.addWidget(self._tab_history)
        tab_l.addStretch(1)
        body_l.addWidget(tab_bar)

        # Filters
        filters = QHBoxLayout()
        filters.setContentsMargins(0, 0, 0, 4)
        filters.setSpacing(16)
        filters.setAlignment(Qt.AlignmentFlag.AlignBottom)

        search_col = QVBoxLayout()
        search_col.setSpacing(6)
        search_cap = QLabel("SEARCH")
        search_cap.setObjectName("allImportActivityCaption")
        search_col.addWidget(search_cap)
        search_wrap = QFrame()
        search_wrap.setStyleSheet(
            f"QFrame {{ background: #ffffff; border: 1px solid {_BORDER_INPUT}; "
            "border-radius: 4px; }}"
        )
        search_wrap.setFixedHeight(36)
        search_row = QHBoxLayout(search_wrap)
        search_row.setContentsMargins(12, 0, 12, 0)
        search_row.setSpacing(8)
        search_icon = QLabel()
        search_icon.setFixedSize(14, 14)
        search_icon.setPixmap(_svg_pixmap(_SEARCH_SVG, 14))
        search_row.addWidget(search_icon)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search imports")
        self.search_edit.setFrame(False)
        self.search_edit.setStyleSheet(
            "QLineEdit { background: transparent; border: none; font-size: 13px; "
            f"color: {_TEXT_DARK}; padding: 0; }}"
        )
        self.search_edit.textChanged.connect(self._on_filters_changed)
        search_row.addWidget(self.search_edit, 1)
        search_col.addWidget(search_wrap)
        filters.addLayout(search_col, 1)

        status_col = QVBoxLayout()
        status_col.setSpacing(6)
        status_cap = QLabel("STATUS")
        status_cap.setObjectName("allImportActivityCaption")
        status_col.addWidget(status_cap)
        self.status_combo = QComboBox()
        self.status_combo.setFixedWidth(180)
        self.status_combo.addItem("All", "")
        for label in ("Completed", "Failed", "In Progress", "Pending"):
            self.status_combo.addItem(label, label)
        apply_form_combobox_field(self.status_combo, height_px=36, min_width=180)
        install_combo_popup_below_field(self.status_combo)
        self.status_combo.currentIndexChanged.connect(self._on_filters_changed)
        status_col.addWidget(self.status_combo)
        filters.addLayout(status_col)

        type_col = QVBoxLayout()
        type_col.setSpacing(6)
        type_cap = QLabel("FILE TYPE")
        type_cap.setObjectName("allImportActivityCaption")
        type_col.addWidget(type_cap)
        self.type_combo = QComboBox()
        self.type_combo.setFixedWidth(180)
        self.type_combo.addItem("All", "")
        for label in ("Excel", "CSV", "JSON"):
            self.type_combo.addItem(label, label)
        apply_form_combobox_field(self.type_combo, height_px=36, min_width=180)
        install_combo_popup_below_field(self.type_combo)
        self.type_combo.currentIndexChanged.connect(self._on_filters_changed)
        type_col.addWidget(self.type_combo)
        self._type_filter_wrap = QWidget()
        self._type_filter_wrap.setLayout(type_col)
        filters.addWidget(self._type_filter_wrap)
        body_l.addLayout(filters)

        self.message_label = QLabel("")
        self.message_label.setObjectName("allImportActivityMessageBanner")
        configure_message_banner(self.message_label)
        body_l.addWidget(self.message_label)

        # Table — header + rows share one scroll so columns stay aligned.
        card = QFrame()
        card.setObjectName("allImportActivityTableCard")
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(0, 0, 0, 0)
        card_l.setSpacing(0)

        self._table_content = QWidget()
        self._table_content.setStyleSheet("background: #ffffff;")
        table_content_l = QVBoxLayout(self._table_content)
        table_content_l.setContentsMargins(0, 0, 0, 0)
        table_content_l.setSpacing(0)

        self._header_row = QFrame()
        self._header_row.setObjectName("allImportActivityHeaderRow")
        self._header_row.setFixedHeight(_HEADER_H)
        self._header_layout = QHBoxLayout(self._header_row)
        self._rebuild_header()
        table_content_l.addWidget(self._header_row)

        self._rows_host = QWidget()
        self._rows_host.setStyleSheet("background: #ffffff; border: none;")
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)
        self._rows_layout.addStretch(1)
        table_content_l.addWidget(self._rows_host, 1)

        scroll = QScrollArea()
        scroll.setObjectName("allImportActivityScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(self._table_content)
        card_l.addWidget(scroll, 1)

        footer = QFrame()
        footer.setObjectName("allImportActivityFooter")
        footer_l = QHBoxLayout(footer)
        footer_l.setContentsMargins(16, 12, 16, 12)
        footer_l.setSpacing(8)
        self.footer_label = QLabel("Showing 0-0 of 0 imports")
        self.footer_label.setObjectName("allImportActivityFooterText")
        footer_l.addWidget(self.footer_label, 1)

        self.prev_btn = QPushButton()
        self.prev_btn.setObjectName("allImportActivityNavBtn")
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_btn.setFixedSize(_PAGER_H, _PAGER_H)
        self.prev_btn.setIcon(QIcon(_svg_pixmap(_CHEVRON_LEFT_SVG, 12)))
        self.prev_btn.clicked.connect(self._prev_page)
        footer_l.addWidget(self.prev_btn)

        self._page_btn_row = QHBoxLayout()
        self._page_btn_row.setSpacing(8)
        self._page_btn_row.setContentsMargins(0, 0, 0, 0)
        footer_l.addLayout(self._page_btn_row)

        self.next_btn = QPushButton()
        self.next_btn.setObjectName("allImportActivityNavBtn")
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.setFixedSize(_PAGER_H, _PAGER_H)
        self.next_btn.setIcon(QIcon(_svg_pixmap(_CHEVRON_RIGHT_SVG, 12)))
        self.next_btn.clicked.connect(self._next_page)
        footer_l.addWidget(self.next_btn)
        card_l.addWidget(footer)
        body_l.addWidget(card, 1)
        root.addWidget(body)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.reload()

    def _set_tab(self, tab: str) -> None:
        self._tab = tab
        self._tab_sessions.setChecked(tab == "sessions")
        self._tab_history.setChecked(tab == "history")
        self._type_filter_wrap.setVisible(tab == "sessions")
        if tab == "history":
            self.type_combo.blockSignals(True)
            self.type_combo.setCurrentIndex(0)
            self.type_combo.blockSignals(False)
        self._rebuild_header()
        self._apply_filters(reset_page=True)

    def _active_columns(self) -> tuple[tuple[str, str, int], ...]:
        return _HISTORY_COLUMNS if self._tab == "history" else _SESSION_COLUMNS

    def _rebuild_header(self) -> None:
        while self._header_layout.count():
            item = self._header_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        header_cells: list[QWidget] = []
        for _key, title, width in self._active_columns():
            header_cells.append(
                _text_col(
                    title,
                    object_name="allImportActivityColHead",
                    width=width,
                    elide=False,
                )
            )
        _fill_row(self._header_layout, header_cells)

    def reload(self) -> None:
        """Show the page immediately; load sessions and details asynchronously."""
        token = _token()
        if not token:
            self._show_error("Session expired. Please log in again.")
            self._rows = []
            self._apply_filters(reset_page=True)
            return

        self._load_generation += 1
        load_gen = self._load_generation
        self._enrich_generation += 1
        if self._list_worker is not None and self._list_worker.isRunning():
            self._list_worker.succeeded.disconnect()
            self._list_worker.failed.disconnect()
            self._list_worker.requestInterruption()
        if self._enrich_worker is not None and self._enrich_worker.isRunning():
            self._enrich_worker.finished_ok.disconnect()
            self._enrich_worker.requestInterruption()

        show_page_info(self, self.message_label, "Loading imports…", sticky=True)

        worker = _SessionListWorker(token, self)
        self._list_worker = worker

        def _on_ok(rows: list) -> None:
            if load_gen != self._load_generation:
                return
            clear_page_message(self, self.message_label)
            self._rows = list(rows)
            self._apply_filters(reset_page=True)

        def _on_err(message: str) -> None:
            if load_gen != self._load_generation:
                return
            self._show_error(message)
            self._rows = []
            self._apply_filters(reset_page=True)

        worker.succeeded.connect(_on_ok)
        worker.failed.connect(_on_err)
        worker.start()

    def _queue_enrich_visible(self) -> None:
        token = _token()
        if not token:
            return
        start = self._page * _PAGE_SIZE
        page_rows = [
            r
            for r in self._filtered[start : start + _PAGE_SIZE]
            if not r.get("_enriched")
        ]
        if not page_rows:
            return

        self._enrich_generation += 1
        gen = self._enrich_generation
        if self._enrich_worker is not None and self._enrich_worker.isRunning():
            try:
                self._enrich_worker.finished_ok.disconnect()
            except RuntimeError:
                pass
            self._enrich_worker.requestInterruption()

        show_page_info(self, self.message_label, "Loading import details…", sticky=True)

        worker = _EnrichPageWorker(page_rows, token, gen, self)
        self._enrich_worker = worker

        def _on_done(done_gen: int) -> None:
            if done_gen != self._enrich_generation:
                return
            clear_page_message(self, self.message_label)
            self._render_table()

        worker.finished_ok.connect(_on_done)
        worker.start()

    def _show_error(self, message: str) -> None:
        show_page_error(self, self.message_label, message)

    def _clear_message(self) -> None:
        clear_page_message(self, self.message_label)

    def _on_filters_changed(self, *_args: Any) -> None:
        self._apply_filters(reset_page=True)

    def _apply_filters(self, *, reset_page: bool) -> None:
        query = self.search_edit.text().strip().lower()
        status_filter = str(self.status_combo.currentData() or "")
        type_filter = str(self.type_combo.currentData() or "")
        filtered: list[dict[str, Any]] = []
        for row in self._rows:
            status_label, _ = _normalize_status(row.get("status") or row.get("state"))
            # History (Figma 62:173): execution rows — Completed / Failed / In Progress.
            if self._tab == "history" and status_label not in {
                "Completed",
                "Failed",
                "In Progress",
            }:
                continue
            name = str(row.get("sessionName") or "")
            sid = str(row.get("sessionId") or "")
            file_name = str(row.get("fileName") or "")
            table = str(row.get("targetTableName") or row.get("tableName") or "")
            conn = str(row.get("targetConnectionName") or "")
            file_type = _file_type_from_row(row)
            executed_by = _executed_by(row)
            if query:
                blob = " ".join(
                    [
                        name,
                        sid,
                        file_name,
                        table,
                        conn,
                        file_type,
                        status_label,
                        executed_by,
                    ]
                ).lower()
                if query not in blob:
                    continue
            if status_filter and status_label != status_filter:
                continue
            if type_filter and file_type != type_filter:
                continue
            filtered.append(row)
        self._filtered = filtered
        if reset_page:
            self._page = 0
        max_page = max(0, (len(self._filtered) - 1) // _PAGE_SIZE) if self._filtered else 0
        self._page = min(self._page, max_page)
        self._render_table()
        self._queue_enrich_visible()

    def _clear_rows(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _build_data_row(self, row: dict[str, Any], *, alt: bool) -> QFrame:
        if self._tab == "history":
            return self._build_history_row(row, alt=alt)
        return self._build_session_row(row, alt=alt)

    def _row_frame(self, row: dict[str, Any], *, alt: bool) -> tuple[QFrame, QHBoxLayout]:
        frame = _ClickableSessionRow(row)
        bg = _ROW_ALT if alt else "#ffffff"
        frame.setStyleSheet(
            f"QFrame#allImportActivityDataRow {{ background: {bg}; "
            f"border: none; border-bottom: 1px solid {_BORDER}; }}"
            f"QFrame#allImportActivityDataRow:hover {{ background: #eef2ff; }}"
        )
        frame.setFixedHeight(_ROW_H)
        frame.clicked.connect(self.view_session_requested.emit)
        layout = QHBoxLayout(frame)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        return frame, layout

    def _name_link(self, row: dict[str, Any], width: int) -> QWidget:
        name = str(row.get("sessionName") or "—")
        name_shell, name_l = _col_shell(width)
        name_l.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        name_btn = QPushButton()
        name_btn.setObjectName("allImportActivityNameLink")
        name_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        name_btn.setFlat(True)
        name_btn.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        font = name_btn.font()
        font.setUnderline(True)
        font.setWeight(QFont.Weight.DemiBold)
        name_btn.setFont(font)
        metrics = QFontMetrics(name_btn.font())
        elided_name = metrics.elidedText(name, Qt.TextElideMode.ElideRight, width - 4)
        name_btn.setText(elided_name)
        name_btn.setToolTip(name)
        name_btn.setFixedHeight(22)
        name_l.addWidget(name_btn, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        name_l.addStretch(1)
        return name_shell

    def _status_cell(self, row: dict[str, Any], width: int = 110) -> QWidget:
        status_label, style_key = _normalize_status(row.get("status") or row.get("state"))
        status_shell, status_l = _col_shell(width)
        status_l.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        status_l.addWidget(_status_badge(status_label, style_key), 0, Qt.AlignmentFlag.AlignVCenter)
        status_l.addStretch(1)
        return status_shell

    def _build_session_row(self, row: dict[str, Any], *, alt: bool) -> QFrame:
        file_name = str(row.get("fileName") or "—")
        conn = str(row.get("targetConnectionName") or "—")
        table = str(row.get("targetTableName") or row.get("tableName") or "—")
        file_type = _file_type_from_row(row)
        operation = _format_operation(row.get("operation"))
        frame, layout = self._row_frame(row, alt=alt)
        cells = [
            self._name_link(row, 200),
            _text_col(file_name, object_name="allImportActivityCellMuted", width=180),
            _text_col(conn, object_name="allImportActivityCellMuted", width=160),
            _text_col(table, object_name="allImportActivityCellMuted", width=150),
            _text_col(
                file_type,
                object_name="allImportActivityCellDark",
                width=90,
                elide=False,
            ),
            _text_col(operation, object_name="allImportActivityCellOp", width=140),
            self._status_cell(row, 110),
        ]
        _fill_row(layout, cells)
        return frame

    def _build_history_row(self, row: dict[str, Any], *, alt: bool) -> QFrame:
        status_label, _ = _normalize_status(row.get("status") or row.get("state"))
        exec_date = _format_execution_date(
            _pick(
                row,
                "executionDate",
                "executedAt",
                "completedAt",
                "updatedAt",
                "createdAt",
                "startTime",
            )
        )
        duration = _format_duration(
            _pick(row, "duration", "durationMs", "durationSeconds", "elapsed", "elapsedMs")
        )
        processed = _format_count(
            _pick(
                row,
                "rowsProcessed",
                "totalRows",
                "successfulRows",
                "successCount",
                "rowCount",
            )
        )
        failed_text, failed_obj = _failed_display(row, status_label)
        executed_by = _executed_by(row)
        frame, layout = self._row_frame(row, alt=alt)
        cells = [
            self._name_link(row, 180),
            _text_col(exec_date, object_name="allImportActivityCellDark", width=170),
            _text_col(duration, object_name="allImportActivityCellMuted", width=110, elide=False),
            _text_col(processed, object_name="allImportActivityCellDark", width=140, elide=False),
            _text_col(failed_text, object_name=failed_obj, width=110, elide=False),
            self._status_cell(row, 110),
            _text_col(executed_by, object_name="allImportActivityCellMuted", width=120),
        ]
        _fill_row(layout, cells)
        return frame

    def _render_table(self) -> None:
        self._clear_rows()
        total = len(self._filtered)
        start = self._page * _PAGE_SIZE
        page_rows = self._filtered[start : start + _PAGE_SIZE]
        if not page_rows:
            empty = QLabel(
                "No import history yet."
                if self._tab == "history"
                else "No import sessions found."
            )
            empty.setObjectName("allImportActivityEmpty")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._rows_layout.addWidget(empty)
        else:
            for i, row in enumerate(page_rows):
                self._rows_layout.addWidget(
                    self._build_data_row(row, alt=((start + i) % 2 == 1))
                )
        self._rows_layout.addStretch(1)

        end = start + len(page_rows)
        if total == 0:
            self.footer_label.setText("Showing 0-0 of 0 imports")
        else:
            self.footer_label.setText(f"Showing {start + 1}-{end} of {total} imports")

        self._rebuild_page_buttons(total)
        page_count = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE) if total else 1
        self.prev_btn.setEnabled(self._page > 0)
        self.next_btn.setEnabled(self._page < page_count - 1)

    def _rebuild_page_buttons(self, total: int) -> None:
        while self._page_btn_row.count():
            item = self._page_btn_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._page_buttons = []
        page_count = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE) if total else 1
        window = 3
        start_p = max(0, min(self._page - window // 2, page_count - window))
        end_p = min(page_count, start_p + window)
        if end_p - start_p < window and page_count >= window:
            start_p = max(0, end_p - window)
        for p in range(start_p, end_p):
            btn = QPushButton(str(p + 1))
            btn.setObjectName("allImportActivityPageBtn")
            btn.setCheckable(True)
            btn.setChecked(p == self._page)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(_PAGER_H)
            btn.clicked.connect(lambda _c=False, page=p: self._goto_page(page))
            self._page_btn_row.addWidget(btn)
            self._page_buttons.append(btn)

    def _goto_page(self, page: int) -> None:
        self._page = max(0, page)
        self._render_table()
        self._queue_enrich_visible()

    def _prev_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._render_table()
            self._queue_enrich_visible()

    def _next_page(self) -> None:
        page_count = max(1, (len(self._filtered) + _PAGE_SIZE - 1) // _PAGE_SIZE)
        if self._page < page_count - 1:
            self._page += 1
            self._render_table()
            self._queue_enrich_visible()
