"""ETL: Excel — bulk import all files from a folder path."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QShowEvent
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.etl.excel.upload_file_page import _enrich_analyze_sheets_unicode
from core.api import (
    api_analyze_import_file,
    api_create_import,
    api_execute_import_sheet,
    api_save_import_mapping,
    api_upload_import_file,
)
from core.etl_connection_context import (
    etl_connection_display_label,
    etl_connection_id,
    get_etl_connection_context,
)
from core.user_context import get_user_profile
from ui.data_table import apply_data_table_appearance, attach_table_copy_shortcut
from ui.form_combobox_style import apply_form_combobox_field, install_combo_popup_below_field
from app.etl.excel.message_banner import (
    clear_page_message,
    configure_message_banner,
    show_page_error,
    show_page_success,
)
from ui.form_page_styles import FORM_INPUT_STYLE

_ASSETS = Path(__file__).resolve().parents[3] / "assets" / "excel"
_FOLDER_MUTED_SVG = _ASSETS / "folder_muted.svg"
_FOLDER_BROWSE_SVG = _ASSETS / "folder_browse.svg"
_CHECK_GREEN_SVG = _ASSETS / "check_green.svg"
_LOADER_SVG = _ASSETS / "loader.svg"
_CHECK_SUCCESS_SVG = _ASSETS / "check_success.svg"
_FILE_MUTED_SVG = _ASSETS / "file_muted.svg"

_SUPPORTED_SUFFIXES = {".xlsx", ".xls", ".csv", ".json"}

_SOURCE_TYPE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Excel", "EXCEL"),
    ("CSV", "CSV"),
    ("JSON", "JSON"),
)

_ENCODING_OPTIONS: tuple[tuple[str, str], ...] = (
    ("UTF-8", "65001"),
    ("Windows Arabic — 1256", "1256"),
    ("Windows Western European — 1252", "1252"),
)

_PAGE_BG = "#f7f7fa"
_ACCENT = "#2e73f5"
_TEXT_DARK = "#111827"
_TEXT_MUTED = "#6b7280"
_BORDER = "#e8eaed"
_BORDER_INPUT = "#d1d6de"
_CARD_BG = "#f6f7f9"

_PAGE_STYLE = f"""
    QWidget#bulkBody {{ background: {_PAGE_BG}; }}
    QLabel#bulkTitle {{
        color: {_TEXT_DARK}; font-size: 22px; font-weight: 700;
        background: transparent; border: none;
    }}
    QPushButton#bulkPrimary {{
        background: {_ACCENT}; color: #ffffff; border: none; border-radius: 4px;
        padding: 10px 24px; font-size: 13px; font-weight: 600;
    }}
    QPushButton#bulkPrimary:hover {{ background: #1f63e0; }}
    QPushButton#bulkPrimary:disabled {{
        background: #94a1b0; color: #ffffff;
    }}
    QPushButton#bulkSecondary {{
        background: #ffffff; color: {_TEXT_MUTED}; border: 1px solid {_BORDER_INPUT};
        border-radius: 4px; padding: 10px 24px; font-size: 13px; font-weight: 600;
    }}
    QPushButton#bulkSecondary:hover {{ background: #f8fafc; border-color: #94a3b8; }}
    QFrame#bulkTabBar {{
        background: transparent; border: none; border-bottom: 2px solid {_BORDER};
    }}
    QPushButton#bulkTabHit {{
        background: transparent;
        border: none;
        border-bottom: 2px solid transparent;
        padding: 8px 18px;
        margin-bottom: -2px;
        font-size: 13px;
        font-weight: 500;
        color: {_TEXT_MUTED};
    }}
    QPushButton#bulkTabHit:checked {{
        color: {_ACCENT};
        font-weight: 600;
        border-bottom: 2px solid {_ACCENT};
    }}
    QPushButton#bulkTabHit:hover {{ color: {_ACCENT}; }}
    QFrame#bulkLeftCard, QFrame#bulkRightCard {{
        background: {_CARD_BG}; border: 1px solid {_BORDER}; border-radius: 8px;
    }}
    QLabel#bulkSectionTitle {{
        color: {_TEXT_DARK}; font-size: 14px; font-weight: 600;
        background: transparent; border: none;
    }}
    QLabel#bulkFieldCaption {{
        color: {_TEXT_MUTED}; font-size: 11px; font-weight: 600;
        background: transparent; border: none;
    }}
    QRadioButton#bulkOpRadio {{
        color: {_TEXT_MUTED}; font-size: 13px; font-weight: 400; spacing: 8px;
    }}
    QRadioButton#bulkOpRadio:checked {{
        color: {_TEXT_DARK}; font-weight: 600;
    }}
    QFrame#bulkNoteBox {{
        background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px;
    }}
    QLabel#bulkNoteText {{
        color: #1e40af; font-size: 12px; background: transparent; border: none;
    }}
    QPushButton#bulkFolderBtn {{
        background: {_CARD_BG}; border: 1px solid {_BORDER_INPUT}; border-radius: 4px;
        padding: 4px 8px; min-width: 28px; max-width: 36px;
    }}
    QPushButton#bulkFolderBtn:hover {{ background: #eef2f7; }}
    QFrame#bulkEmptyState {{
        background: #ffffff; border: 1px dashed {_TEXT_MUTED}; border-radius: 8px;
    }}
    QLabel#bulkEmptyTitle {{
        color: {_TEXT_DARK}; font-size: 14px; font-weight: 600;
        background: transparent; border: none;
    }}
    QFrame#bulkScanBadge {{
        background: #dcfce7; border: none; border-radius: 100px;
    }}
    QLabel#bulkScanBadgeText {{
        color: #22c55e; font-size: 11px; font-weight: 600;
        background: transparent; border: none;
    }}
    QLabel#bulkFilesDiscovered {{
        color: {_ACCENT}; font-size: 12px; font-weight: 600;
        background: transparent; border: none;
    }}
    QLabel#bulkScanFooter {{
        color: {_TEXT_MUTED}; font-size: 12px; font-weight: 400;
        background: transparent; border: none;
    }}
    QTableWidget#bulkFileTable {{
        background: #ffffff; alternate-background-color: #ffffff;
        border: 1px solid {_BORDER}; border-radius: 6px; gridline-color: {_BORDER};
        font-size: 12px; color: {_TEXT_DARK};
    }}
    QHeaderView::section {{
        background: {_CARD_BG}; color: {_TEXT_MUTED}; font-size: 11px; font-weight: 700;
        border: none; border-bottom: 1px solid {_BORDER}; border-right: 1px solid {_BORDER};
        padding: 8px 12px;
    }}
    QLabel#bulkReadyBadge {{
        background: #dcfce7; color: #22c55e; font-size: 10px; font-weight: 600;
        border: none; border-radius: 4px; padding: 2px 6px;
    }}
    QLineEdit#bulkReadonlyField {{
        background: #ffffff; border: 1px solid {_BORDER_INPUT}; border-radius: 4px;
        padding: 0 12px; font-size: 13px; color: {_TEXT_DARK};
    }}
    QFrame#bulkAlertBox {{
        background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px;
    }}
    QLabel#bulkAlertText {{
        color: #92400e; font-size: 12px; background: transparent; border: none;
    }}
    QFrame#bulkProgressCard {{
        background: #ffffff; border: 1px solid {_BORDER}; border-radius: 6px;
    }}
    QLabel#bulkProgressStatus {{
        color: {_TEXT_DARK}; font-size: 14px; font-weight: 600;
        background: transparent; border: none;
    }}
    QLabel#bulkProgressPct {{
        color: {_ACCENT}; font-size: 13px; font-weight: 600;
        background: transparent; border: none;
    }}
    QProgressBar#bulkProgressBar {{
        background: {_CARD_BG}; border: none; border-radius: 4px; min-height: 8px; max-height: 8px;
    }}
    QProgressBar#bulkProgressBar::chunk {{
        background: {_ACCENT}; border-radius: 4px;
    }}
    QTableWidget#bulkExecTable {{
        background: #ffffff; border: 1px solid {_BORDER}; border-radius: 6px;
        gridline-color: {_BORDER}; font-size: 12px; color: {_TEXT_DARK};
    }}
    QLabel#bulkMetricLabel {{
        color: {_TEXT_MUTED}; font-size: 13px; font-weight: 400;
        background: transparent; border: none;
    }}
    QLabel#bulkMetricValue {{
        color: {_TEXT_DARK}; font-size: 13px; font-weight: 600;
        background: transparent; border: none;
    }}
    QLabel#bulkMetricSuccess {{
        color: #22c55e; font-size: 13px; font-weight: 600;
        background: transparent; border: none;
    }}
    QLabel#bulkMetricFailed {{
        color: #d92e2e; font-size: 13px; font-weight: 600;
        background: transparent; border: none;
    }}
    QFrame#bulkSuccessPanel {{
        background: #ffffff; border: 1px solid {_BORDER}; border-radius: 12px;
    }}
    QLabel#bulkSuccessTitle {{
        color: {_TEXT_DARK}; font-size: 20px; font-weight: 700;
        background: transparent; border: none;
    }}
    QLabel#bulkSuccessSubtitle {{
        color: {_TEXT_MUTED}; font-size: 14px; font-weight: 400;
        background: transparent; border: none;
    }}
    QLabel#bulkSuccessHeading {{
        color: {_TEXT_MUTED}; font-size: 12px; font-weight: 700;
        background: transparent; border: none;
    }}
    QLabel#bulkSuccessRowLabel {{
        color: {_TEXT_MUTED}; font-size: 13px; font-weight: 400;
        background: transparent; border: none;
    }}
    QLabel#bulkSuccessRowValue {{
        color: {_TEXT_DARK}; font-size: 13px; font-weight: 600;
        background: transparent; border: none;
    }}
    QLabel#bulkSuccessRowOk {{
        color: #22c55e; font-size: 13px; font-weight: 600;
        background: transparent; border: none;
    }}
    QLabel#bulkSuccessRowFail {{
        color: #d92e2e; font-size: 13px; font-weight: 600;
        background: transparent; border: none;
    }}
    QLabel#bulkStatusBadge {{
        background: #dcfce7; color: #22c55e; font-size: 11px; font-weight: 600;
        border: none; border-radius: 4px; padding: 2px 8px;
    }}
    QFrame#bulkSuccessDivider {{
        background: {_BORDER}; border: none; max-height: 1px; min-height: 1px;
    }}
    QFrame#bulkSuccessVDivider {{
        background: {_BORDER}; border: none; max-width: 1px; min-width: 1px;
    }}
    QLabel#bulkFileBreakName {{
        color: {_TEXT_DARK}; font-size: 13px; font-weight: 500;
        background: transparent; border: none;
    }}
    QLabel#bulkFileBreakMeta {{
        color: {_TEXT_MUTED}; font-size: 12px; font-weight: 400;
        background: transparent; border: none;
    }}
    QLabel#bulkFileBreakOk {{
        color: #22c55e; font-size: 12px; font-weight: 600;
        background: transparent; border: none;
    }}
    QLabel#bulkFileBreakFail {{
        color: #d92e2e; font-size: 12px; font-weight: 600;
        background: transparent; border: none;
    }}
    QPushButton#bulkViewDetails {{
        background: #ffffff; color: {_TEXT_MUTED}; border: 1px solid {_BORDER_INPUT};
        border-radius: 4px; padding: 10px 24px; font-size: 13px; font-weight: 600;
    }}
    QPushButton#bulkViewDetails:hover {{ background: {_CARD_BG}; }}
    QPushButton#bulkNewImport {{
        background: {_ACCENT}; color: #ffffff; border: none;
        border-radius: 4px; padding: 10px 24px; font-size: 13px; font-weight: 600;
    }}
    QPushButton#bulkNewImport:hover {{ background: #2563eb; }}
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


def _source_type_for_path(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".xlsx", ".xls"}:
        return "EXCEL"
    if ext == ".csv":
        return "CSV"
    if ext == ".json":
        return "JSON"
    return ""


def _sanitize_table_name(name: str) -> str:
    cleaned = re.sub(r"[^\w]+", "_", (name or "").strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("_")
    if not cleaned:
        return "imported_table"
    if cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    return cleaned[:120]


def _format_file_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    kb = num_bytes / 1024
    if kb < 1024:
        return f"{kb:.1f} KB"
    return f"{kb / 1024:.1f} MB"


def _table_name_for_file(path: Path) -> str:
    return f"tbl_{_sanitize_table_name(path.stem)}"


def _session_id_from_create(result: dict[str, Any]) -> str:
    data = result.get("data")
    candidates: list[Any] = []
    if isinstance(data, dict):
        candidates.append(data)
        nested = data.get("data")
        if isinstance(nested, dict):
            candidates.append(nested)
    candidates.append(result)
    keys = (
        "sessionId",
        "sessionID",
        "session_id",
        "importSessionId",
        "importId",
        "id",
        "uuid",
    )
    for obj in candidates:
        if not isinstance(obj, dict):
            continue
        for key in keys:
            value = obj.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def _first_id(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    raw = row.get("_raw")
    if isinstance(raw, dict):
        for key in keys:
            if key in raw and raw.get(key) is not None:
                return raw.get(key)
    return None


def _list_folder_files(folder: str) -> list[Path]:
    root = Path(folder)
    if not root.is_dir():
        return []
    return [
        p
        for p in sorted(root.iterdir(), key=lambda x: x.name.lower())
        if p.is_file() and p.suffix.lower() in _SUPPORTED_SUFFIXES
    ]


class BulkFolderImportPage(QWidget):
    """Bulk import wizard: Configure & Scan → Execute & Result."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._running = False
        self._cancel_requested = False
        self._step_index = 0
        self._folder = ""
        self._files: list[Path] = []
        self._scanned = False
        self._ok_count = 0
        self._fail_count = 0
        self._file_results: list[dict[str, Any]] = []
        self._import_complete = False
        self._ctx = get_etl_connection_context()
        self._ctx.connections_changed.connect(self._reload_connection_combo)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QWidget()
        body.setObjectName("bulkBody")
        body.setStyleSheet(_PAGE_STYLE)
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(46, 20, 46, 24)
        body_l.setSpacing(16)

        header_row = QHBoxLayout()
        header_row.setSpacing(12)
        title = QLabel("Excel Import")
        title.setObjectName("bulkTitle")
        header_row.addWidget(title, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.primary_btn = QPushButton("Scan Folder")
        self.primary_btn.setObjectName("bulkPrimary")
        self.primary_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.primary_btn.clicked.connect(self._on_primary)
        btn_row.addWidget(self.primary_btn)
        self.secondary_btn = QPushButton("Cancel")
        self.secondary_btn.setObjectName("bulkSecondary")
        self.secondary_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.secondary_btn.clicked.connect(self._on_secondary)
        btn_row.addWidget(self.secondary_btn)
        header_row.addLayout(btn_row)
        body_l.addLayout(header_row)

        tab_bar = QFrame()
        tab_bar.setObjectName("bulkTabBar")
        tab_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tab_l = QHBoxLayout(tab_bar)
        tab_l.setContentsMargins(0, 0, 0, 0)
        tab_l.setSpacing(0)
        tab_l.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        self._tab_buttons: list[QPushButton] = []
        self._tab_step_labels = ("Configure & Scan", "Execute & Result")
        for index, label in enumerate(self._tab_step_labels):
            tab = QPushButton(f"  {index + 1}   {label}")
            tab.setObjectName("bulkTabHit")
            tab.setCheckable(True)
            tab.setChecked(index == 0)
            tab.setCursor(Qt.CursorShape.PointingHandCursor)
            tab.setFlat(True)
            tab.setMinimumHeight(36)
            tab.clicked.connect(lambda _c=False, i=index: self._on_tab_clicked(i))
            tab_l.addWidget(tab)
            self._tab_buttons.append(tab)
        tab_l.addStretch(1)
        body_l.addWidget(tab_bar)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_configure_step())
        self.stack.addWidget(self._build_execute_step())
        body_l.addWidget(self.stack, 1)

        self.message_label = QLabel()
        self.message_label.setObjectName("bulkMessageBanner")
        configure_message_banner(self.message_label)
        body_l.addWidget(self.message_label)

        root.addWidget(body, 1)
        self._reload_connection_combo()
        self._apply_step_chrome()

    def _build_configure_step(self) -> QWidget:
        page = QWidget()
        split = QHBoxLayout(page)
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(24)

        left = QFrame()
        left.setObjectName("bulkLeftCard")
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(16, 16, 16, 16)
        left_l.setSpacing(16)
        left_title = QLabel("Import Configuration")
        left_title.setObjectName("bulkSectionTitle")
        left_l.addWidget(left_title)

        left_l.addWidget(self._field_caption("IMPORT NAME *"))
        self.import_name_edit = QLineEdit()
        self.import_name_edit.setPlaceholderText("Enter import name")
        self.import_name_edit.setStyleSheet(FORM_INPUT_STYLE)
        self.import_name_edit.setFixedHeight(40)
        left_l.addWidget(self.import_name_edit)

        type_enc = QHBoxLayout()
        type_enc.setSpacing(16)
        type_col = QVBoxLayout()
        type_col.setSpacing(6)
        type_col.addWidget(self._field_caption("FILE TYPE *"))
        self.file_type_combo = QComboBox()
        for label, value in _SOURCE_TYPE_OPTIONS:
            self.file_type_combo.addItem(label, value)
        self.file_type_combo.setCurrentIndex(0)
        apply_form_combobox_field(self.file_type_combo, height_px=40, min_width=120)
        install_combo_popup_below_field(self.file_type_combo)
        type_col.addWidget(self.file_type_combo)
        type_enc.addLayout(type_col, 1)

        enc_col = QVBoxLayout()
        enc_col.setSpacing(6)
        enc_col.addWidget(self._field_caption("ENCODING *"))
        self.encoding_combo = QComboBox()
        for label, value in _ENCODING_OPTIONS:
            self.encoding_combo.addItem(label, value)
        apply_form_combobox_field(self.encoding_combo, height_px=40, min_width=120)
        install_combo_popup_below_field(self.encoding_combo)
        enc_col.addWidget(self.encoding_combo)
        type_enc.addLayout(enc_col, 1)
        left_l.addLayout(type_enc)

        left_l.addWidget(self._field_caption("TARGET DATABASE CONNECTION *"))
        self.connection_combo = QComboBox()
        self.connection_combo.setPlaceholderText("Select connection")
        apply_form_combobox_field(self.connection_combo, height_px=40, min_width=200)
        install_combo_popup_below_field(self.connection_combo)
        left_l.addWidget(self.connection_combo)

        left_l.addWidget(self._field_caption("TABLE OPERATION *"))
        op_row = QHBoxLayout()
        op_row.setSpacing(16)
        self.radio_drop_create = QRadioButton("DROP & CREATE")
        self.radio_drop_create.setObjectName("bulkOpRadio")
        self.radio_drop_create.setChecked(True)
        self.radio_drop_create.setCursor(Qt.CursorShape.PointingHandCursor)
        self.radio_delete = QRadioButton("DELETE")
        self.radio_delete.setObjectName("bulkOpRadio")
        self.radio_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.op_group = QButtonGroup(self)
        self.op_group.addButton(self.radio_drop_create)
        self.op_group.addButton(self.radio_delete)
        op_row.addWidget(self.radio_drop_create)
        op_row.addWidget(self.radio_delete)
        op_row.addStretch(1)
        left_l.addLayout(op_row)

        note = QFrame()
        note.setObjectName("bulkNoteBox")
        note_l = QVBoxLayout(note)
        note_l.setContentsMargins(12, 12, 12, 12)
        note_text = QLabel(
            "All columns will be imported as NVARCHAR(255). "
            "Table names are auto-generated from file names."
        )
        note_text.setObjectName("bulkNoteText")
        note_text.setWordWrap(True)
        note_l.addWidget(note_text)
        left_l.addWidget(note)
        left_l.addStretch(1)
        split.addWidget(left, 1)

        right = QFrame()
        right.setObjectName("bulkRightCard")
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(16, 16, 16, 16)
        right_l.setSpacing(12)
        right_title = QLabel("Source Folder")
        right_title.setObjectName("bulkSectionTitle")
        right_l.addWidget(right_title)

        right_l.addWidget(self._field_caption("SOURCE FOLDER PATH *"))
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("/path/to/source/folder")
        self.folder_edit.setStyleSheet(FORM_INPUT_STYLE)
        self.folder_edit.setFixedHeight(40)
        path_row.addWidget(self.folder_edit, 1)
        browse_btn = QPushButton()
        browse_btn.setObjectName("bulkFolderBtn")
        browse_btn.setFixedSize(36, 28)
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_icon = _svg_pixmap(_FOLDER_BROWSE_SVG, 14)
        browse_btn.setIcon(QIcon(browse_icon))
        browse_btn.setIconSize(QSize(14, 14))
        browse_btn.clicked.connect(self._browse_folder)
        path_row.addWidget(browse_btn)
        right_l.addLayout(path_row)

        self._empty_state = QFrame()
        self._empty_state.setObjectName("bulkEmptyState")
        self._empty_state.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        empty_l = QVBoxLayout(self._empty_state)
        empty_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_l.setSpacing(12)
        folder_icon = QLabel()
        folder_icon.setFixedSize(32, 32)
        folder_icon.setPixmap(_svg_pixmap(_FOLDER_MUTED_SVG, 32))
        empty_l.addWidget(folder_icon, 0, Qt.AlignmentFlag.AlignHCenter)
        empty_title = QLabel("Select a source folder to scan for files")
        empty_title.setObjectName("bulkEmptyTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_l.addWidget(empty_title)
        right_l.addWidget(self._empty_state, 1)

        self._scan_results = QWidget()
        self._scan_results.setVisible(False)
        scan_l = QVBoxLayout(self._scan_results)
        scan_l.setContentsMargins(0, 0, 0, 0)
        scan_l.setSpacing(12)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(8)
        scan_badge = QFrame()
        scan_badge.setObjectName("bulkScanBadge")
        badge_l = QHBoxLayout(scan_badge)
        badge_l.setContentsMargins(10, 4, 10, 4)
        badge_l.setSpacing(4)
        check_icon = QLabel()
        check_icon.setFixedSize(12, 12)
        check_icon.setPixmap(_svg_pixmap(_CHECK_GREEN_SVG, 12))
        badge_l.addWidget(check_icon)
        badge_text = QLabel("Scan Complete")
        badge_text.setObjectName("bulkScanBadgeText")
        badge_l.addWidget(badge_text)
        status_row.addWidget(scan_badge)
        status_row.addStretch(1)
        self._files_discovered_label = QLabel("0 files discovered")
        self._files_discovered_label.setObjectName("bulkFilesDiscovered")
        status_row.addWidget(self._files_discovered_label)
        scan_l.addLayout(status_row)

        self.file_table = QTableWidget()
        self.file_table.setObjectName("bulkFileTable")
        self.file_table.setColumnCount(4)
        self.file_table.setHorizontalHeaderLabels(
            ["FILE NAME", "SIZE", "TARGET TABLE", "STATUS"]
        )
        apply_data_table_appearance(
            self.file_table,
            read_only=True,
            stretch_last_section=False,
            hide_vertical_header=True,
            sort_indicator_shown=False,
            alternating_row_colors=False,
        )
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.file_table.setShowGrid(False)
        hh = self.file_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.file_table.setColumnWidth(1, 70)
        self.file_table.setColumnWidth(2, 130)
        self.file_table.setColumnWidth(3, 70)
        attach_table_copy_shortcut(self.file_table)
        scan_l.addWidget(self.file_table, 1)

        self._scan_footer = QLabel("Total: 0 files · 0 B total")
        self._scan_footer.setObjectName("bulkScanFooter")
        scan_l.addWidget(self._scan_footer)
        right_l.addWidget(self._scan_results, 1)

        split.addWidget(right, 1)
        return page

    def _build_execute_step(self) -> QWidget:
        self._execute_stack = QStackedWidget()
        self._execute_stack.addWidget(self._build_execute_progress_page())
        self._execute_stack.addWidget(self._build_success_page())
        return self._execute_stack

    def _build_execute_progress_page(self) -> QWidget:
        page = QWidget()
        split = QHBoxLayout(page)
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(24)

        left = QFrame()
        left.setObjectName("bulkLeftCard")
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(16, 16, 16, 16)
        left_l.setSpacing(16)
        left_title = QLabel("Execution Summary")
        left_title.setObjectName("bulkSectionTitle")
        left_l.addWidget(left_title)

        left_l.addWidget(self._field_caption("TARGET CONNECTION"))
        self.exec_connection_edit = QLineEdit()
        self.exec_connection_edit.setObjectName("bulkReadonlyField")
        self.exec_connection_edit.setReadOnly(True)
        self.exec_connection_edit.setFixedHeight(40)
        left_l.addWidget(self.exec_connection_edit)

        left_l.addWidget(self._field_caption("TABLE OPERATION"))
        self.exec_operation_edit = QLineEdit()
        self.exec_operation_edit.setObjectName("bulkReadonlyField")
        self.exec_operation_edit.setReadOnly(True)
        self.exec_operation_edit.setFixedHeight(40)
        left_l.addWidget(self.exec_operation_edit)

        stats = QHBoxLayout()
        stats.setSpacing(16)
        total_col = QVBoxLayout()
        total_col.setSpacing(6)
        total_col.addWidget(self._field_caption("TOTAL FILES"))
        self.exec_total_files_edit = QLineEdit()
        self.exec_total_files_edit.setObjectName("bulkReadonlyField")
        self.exec_total_files_edit.setReadOnly(True)
        self.exec_total_files_edit.setFixedHeight(40)
        total_col.addWidget(self.exec_total_files_edit)
        stats.addLayout(total_col, 1)

        cols_col = QVBoxLayout()
        cols_col.setSpacing(6)
        cols_col.addWidget(self._field_caption("ALL COLUMNS"))
        self.exec_columns_edit = QLineEdit("NVARCHAR(255)")
        self.exec_columns_edit.setObjectName("bulkReadonlyField")
        self.exec_columns_edit.setReadOnly(True)
        self.exec_columns_edit.setFixedHeight(40)
        cols_col.addWidget(self.exec_columns_edit)
        stats.addLayout(cols_col, 1)
        left_l.addLayout(stats)

        alert = QFrame()
        alert.setObjectName("bulkAlertBox")
        alert_l = QVBoxLayout(alert)
        alert_l.setContentsMargins(12, 12, 12, 12)
        alert_text = QLabel(
            "Import operation is currently executing. "
            "Do not close or navigate away from this screen."
        )
        alert_text.setObjectName("bulkAlertText")
        alert_text.setWordWrap(True)
        alert_l.addWidget(alert_text)
        self._exec_alert = alert
        left_l.addWidget(alert)
        left_l.addStretch(1)
        split.addWidget(left, 1)

        right = QFrame()
        right.setObjectName("bulkRightCard")
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(20, 20, 20, 20)
        right_l.setSpacing(16)
        right_title = QLabel("Import Progress")
        right_title.setObjectName("bulkSectionTitle")
        right_l.addWidget(right_title)

        progress_card = QFrame()
        progress_card.setObjectName("bulkProgressCard")
        progress_l = QVBoxLayout(progress_card)
        progress_l.setContentsMargins(16, 16, 16, 16)
        progress_l.setSpacing(12)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self._progress_spinner = QLabel()
        self._progress_spinner.setFixedSize(16, 16)
        self._progress_spinner.setPixmap(_svg_pixmap(_LOADER_SVG, 16))
        status_row.addWidget(self._progress_spinner)
        self._progress_status = QLabel("Importing...")
        self._progress_status.setObjectName("bulkProgressStatus")
        status_row.addWidget(self._progress_status, 1)
        self._progress_pct = QLabel("0%")
        self._progress_pct.setObjectName("bulkProgressPct")
        status_row.addWidget(self._progress_pct)
        progress_l.addLayout(status_row)

        self._progress_bar = QProgressBar()
        self._progress_bar.setObjectName("bulkProgressBar")
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(8)
        progress_l.addWidget(self._progress_bar)
        right_l.addWidget(progress_card)

        self.log_table = QTableWidget()
        self.log_table.setObjectName("bulkExecTable")
        self.log_table.setColumnCount(4)
        self.log_table.setHorizontalHeaderLabels(
            ["FILE", "TARGET TABLE", "ROWS", "STATUS"]
        )
        apply_data_table_appearance(
            self.log_table,
            read_only=True,
            stretch_last_section=False,
            hide_vertical_header=True,
            sort_indicator_shown=False,
            alternating_row_colors=False,
        )
        self.log_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.log_table.setShowGrid(False)
        hh = self.log_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.log_table.setColumnWidth(1, 130)
        self.log_table.setColumnWidth(2, 100)
        self.log_table.setColumnWidth(3, 100)
        attach_table_copy_shortcut(self.log_table)
        right_l.addWidget(self.log_table, 1)

        metrics = QVBoxLayout()
        metrics.setSpacing(10)
        metrics.setContentsMargins(0, 8, 0, 0)
        self._metric_processed = self._metric_row(metrics, "TOTAL ROWS PROCESSED", "0 / 0")
        self._metric_success = self._metric_row(
            metrics, "SUCCESSFUL", "0", value_object="bulkMetricSuccess"
        )
        self._metric_failed = self._metric_row(
            metrics, "FAILED", "0", value_object="bulkMetricFailed"
        )
        right_l.addLayout(metrics)
        split.addWidget(right, 1)
        return page

    def _metric_row(
        self,
        parent_layout: QVBoxLayout,
        label: str,
        value: str,
        *,
        value_object: str = "bulkMetricValue",
    ) -> QLabel:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label)
        lbl.setObjectName("bulkMetricLabel")
        row.addWidget(lbl)
        row.addStretch(1)
        val = QLabel(value)
        val.setObjectName(value_object)
        row.addWidget(val)
        parent_layout.addLayout(row)
        return val

    def _build_success_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        hero = QVBoxLayout()
        hero.setSpacing(12)
        hero.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        icon_wrap = QFrame()
        icon_wrap.setFixedSize(64, 64)
        icon_wrap.setStyleSheet(
            "QFrame { background: #dcfce7; border: none; border-radius: 32px; }"
        )
        icon_l = QVBoxLayout(icon_wrap)
        icon_l.setContentsMargins(0, 0, 0, 0)
        icon_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel()
        icon.setFixedSize(32, 32)
        icon.setPixmap(_svg_pixmap(_CHECK_SUCCESS_SVG, 32))
        icon_l.addWidget(icon)
        hero.addWidget(icon_wrap, 0, Qt.AlignmentFlag.AlignHCenter)

        title = QLabel("Bulk Import Successful")
        title.setObjectName("bulkSuccessTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero.addWidget(title)

        self._success_subtitle = QLabel("All files have been imported successfully.")
        self._success_subtitle.setObjectName("bulkSuccessSubtitle")
        self._success_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._success_subtitle.setWordWrap(True)
        hero.addWidget(self._success_subtitle)
        layout.addLayout(hero)

        card = QFrame()
        card.setObjectName("bulkSuccessPanel")
        card.setFixedWidth(820)
        card_l = QHBoxLayout(card)
        card_l.setContentsMargins(20, 20, 20, 20)
        card_l.setSpacing(20)

        summary = QVBoxLayout()
        summary.setSpacing(14)
        summary_heading = QLabel("SUMMARY DETAILS")
        summary_heading.setObjectName("bulkSuccessHeading")
        summary.addWidget(summary_heading)

        self._success_operation = self._success_detail_row(
            summary, "Operation Type", "DROP & CREATE"
        )
        self._success_total_files = self._success_detail_row(summary, "Total Files", "0")
        self._success_detail_row(summary, "Column Type", "NVARCHAR(255)")

        status_row = QHBoxLayout()
        status_lbl = QLabel("Status")
        status_lbl.setObjectName("bulkSuccessRowLabel")
        status_row.addWidget(status_lbl)
        status_row.addStretch(1)
        status_badge = QLabel("200 OK")
        status_badge.setObjectName("bulkStatusBadge")
        status_row.addWidget(status_badge)
        summary.addLayout(status_row)

        divider = QFrame()
        divider.setObjectName("bulkSuccessDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        summary.addWidget(divider)

        self._success_total_rows = self._success_detail_row(summary, "Total Rows", "0")
        self._success_ok_rows = self._success_detail_row(
            summary, "Successful Rows", "0", value_object="bulkSuccessRowOk"
        )
        self._success_fail_rows = self._success_detail_row(
            summary, "Failed Rows", "0", value_object="bulkSuccessRowFail"
        )
        summary_w = QWidget()
        summary_w.setFixedWidth(380)
        summary_w.setLayout(summary)
        card_l.addWidget(summary_w)

        vdiv = QFrame()
        vdiv.setObjectName("bulkSuccessVDivider")
        vdiv.setFixedWidth(1)
        card_l.addWidget(vdiv)

        breakdown = QVBoxLayout()
        breakdown.setSpacing(12)
        break_heading = QLabel("FILE BREAKDOWN")
        break_heading.setObjectName("bulkSuccessHeading")
        breakdown.addWidget(break_heading)
        self._file_breakdown_layout = QVBoxLayout()
        self._file_breakdown_layout.setSpacing(8)
        breakdown.addLayout(self._file_breakdown_layout)
        breakdown.addStretch(1)
        break_w = QWidget()
        break_w.setFixedWidth(380)
        break_w.setLayout(breakdown)
        card_l.addWidget(break_w)

        layout.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        actions.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        view_btn = QPushButton("View Details")
        view_btn.setObjectName("bulkViewDetails")
        view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        view_btn.clicked.connect(self._on_view_details)
        actions.addWidget(view_btn)
        new_btn = QPushButton("New Import")
        new_btn.setObjectName("bulkNewImport")
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.clicked.connect(self._on_new_import)
        actions.addWidget(new_btn)
        layout.addLayout(actions)

        outer.addWidget(panel)
        return page

    def _success_detail_row(
        self,
        parent_layout: QVBoxLayout,
        label: str,
        value: str,
        *,
        value_object: str = "bulkSuccessRowValue",
    ) -> QLabel:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label)
        lbl.setObjectName("bulkSuccessRowLabel")
        row.addWidget(lbl)
        row.addStretch(1)
        val = QLabel(value)
        val.setObjectName(value_object)
        row.addWidget(val)
        parent_layout.addLayout(row)
        return val

    @staticmethod
    def _field_caption(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("bulkFieldCaption")
        return lbl

    def go_to_nav_item(self, _nav_item: str) -> None:
        self._refresh_connections_from_api()
        self._set_step(0)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._refresh_connections_from_api()

    def _token(self) -> str | None:
        profile = get_user_profile() or {}
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _refresh_connections_from_api(self) -> None:
        """Fetch connections once; combo reload happens via connections_changed."""
        self._ctx.refresh_connections(self._token())

    def _reload_connection_combo(self) -> None:
        current = self.connection_combo.currentData()
        current_id = etl_connection_id(current) if isinstance(current, dict) else None
        self.connection_combo.blockSignals(True)
        self.connection_combo.clear()
        self.connection_combo.addItem("Select connection", None)
        for conn in self._ctx.connections():
            if isinstance(conn, dict):
                self.connection_combo.addItem(etl_connection_display_label(conn), conn)
        restored = False
        if current_id is not None:
            for i in range(self.connection_combo.count()):
                data = self.connection_combo.itemData(i)
                if isinstance(data, dict) and etl_connection_id(data) == current_id:
                    self.connection_combo.setCurrentIndex(i)
                    restored = True
                    break
        if not restored:
            self.connection_combo.setCurrentIndex(0)
        self.connection_combo.blockSignals(False)

    def _selected_connection_id(self) -> int | None:
        conn = self.connection_combo.currentData()
        conn_id = etl_connection_id(conn) if isinstance(conn, dict) else None
        if conn_id is None or str(conn_id).strip() == "":
            return None
        try:
            return int(conn_id)
        except (TypeError, ValueError):
            return None

    def _selected_operation(self) -> str:
        return "DELETE" if self.radio_delete.isChecked() else "DROP_CREATE"

    def _show_error(self, message: str) -> None:
        show_page_error(self, self.message_label, message)

    def _show_success(self, message: str) -> None:
        show_page_success(self, self.message_label, message)

    def _clear_message(self) -> None:
        clear_page_message(self, self.message_label)

    def _set_step(self, index: int) -> None:
        self._step_index = index
        self.stack.setCurrentIndex(index)
        self._apply_step_chrome()

    def _apply_step_chrome(self) -> None:
        for i, btn in enumerate(self._tab_buttons):
            active = i == self._step_index
            completed = i < self._step_index
            btn.setChecked(active)
            label = self._tab_step_labels[i]
            if completed:
                btn.setText(f"  ✓   {label}")
            else:
                btn.setText(f"  {i + 1}   {label}")
        showing_success = (
            self._step_index == 1
            and getattr(self, "_execute_stack", None) is not None
            and self._execute_stack.currentIndex() == 1
        )
        if showing_success:
            self.primary_btn.setVisible(False)
            self.secondary_btn.setVisible(False)
            return
        self.primary_btn.setVisible(True)
        self.secondary_btn.setVisible(True)
        if self._step_index == 0:
            self.primary_btn.setEnabled(True)
            if self._scanned and self._files:
                self.primary_btn.setText("Import")
            else:
                self.primary_btn.setText("Scan Folder")
            self.secondary_btn.setText("Cancel")
        elif self._running:
            self.primary_btn.setEnabled(False)
            self.primary_btn.setText("Importing...")
            self.secondary_btn.setText("Cancel")
        else:
            self.primary_btn.setEnabled(True)
            self.primary_btn.setText("Import")
            self.secondary_btn.setText("Back")

    def _on_tab_clicked(self, index: int) -> None:
        if self._running:
            self._apply_step_chrome()
            return
        if index == 1 and not self._scanned:
            self._show_error("Scan a folder before Execute & Result.")
            self._apply_step_chrome()
            return
        if index == 1:
            self._execute_stack.setCurrentIndex(0)
            self._prepare_execute_ui()
        self._set_step(index)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select folder with files to import")
        if not folder:
            return
        self.folder_edit.setText(folder)
        self._folder = folder
        self._clear_message()
        self._apply_scan_results(folder)

    def _validate_configure(self) -> bool:
        if not self.import_name_edit.text().strip():
            self._show_error("Import name is required.")
            return False
        if not isinstance(self.connection_combo.currentData(), dict):
            self._show_error("Select a target database connection.")
            return False
        folder = self.folder_edit.text().strip()
        if not folder:
            self._show_error("Select a source folder path.")
            return False
        if not Path(folder).is_dir():
            self._show_error("Source folder path is not a valid directory.")
            return False
        return True

    def _ready_badge(self) -> QWidget:
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge = QLabel("Ready")
        badge.setObjectName("bulkReadyBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(badge)
        return wrap

    def _apply_scan_results(self, folder: str) -> None:
        self._folder = folder
        self._files = _list_folder_files(folder)
        self._scanned = True
        if not self._files:
            self._empty_state.setVisible(True)
            self._scan_results.setVisible(False)
            self._show_error("No .xlsx / .xls / .csv / .json files found in that folder.")
            self._apply_step_chrome()
            return

        self._empty_state.setVisible(False)
        self._scan_results.setVisible(True)
        count = len(self._files)
        self._files_discovered_label.setText(
            f"{count} file{'s' if count != 1 else ''} discovered"
        )
        total_bytes = 0
        self.file_table.setRowCount(count)
        for row, path in enumerate(self._files):
            try:
                size = path.stat().st_size if path.is_file() else 0
            except OSError:
                size = 0
            total_bytes += size
            name_item = QTableWidgetItem(path.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.file_table.setItem(row, 0, name_item)

            size_item = QTableWidgetItem(_format_file_size(size))
            size_item.setFlags(size_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            size_item.setForeground(QColor(_TEXT_MUTED))
            self.file_table.setItem(row, 1, size_item)

            table_item = QTableWidgetItem(_table_name_for_file(path))
            table_item.setFlags(table_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.file_table.setItem(row, 2, table_item)

            self.file_table.setCellWidget(row, 3, self._ready_badge())
            self.file_table.setRowHeight(row, 36)

        self._scan_footer.setText(
            f"Total: {count} file{'s' if count != 1 else ''} · {_format_file_size(total_bytes)} total"
        )
        self._apply_step_chrome()

    def _scan_folder(self) -> None:
        self._clear_message()
        if not self._validate_configure():
            return
        folder = self.folder_edit.text().strip()
        self._apply_scan_results(folder)

    def _prepare_execute_ui(self) -> None:
        self._execute_stack.setCurrentIndex(0)
        self._import_complete = False
        self._file_results = []
        conn = self.connection_combo.currentData()
        if isinstance(conn, dict):
            self.exec_connection_edit.setText(etl_connection_display_label(conn))
        else:
            self.exec_connection_edit.setText(self.connection_combo.currentText())
        operation = "DROP & CREATE" if self.radio_drop_create.isChecked() else "DELETE"
        self.exec_operation_edit.setText(operation)
        self.exec_total_files_edit.setText(str(len(self._files)))
        self.exec_columns_edit.setText("NVARCHAR(255)")
        self._exec_alert.setVisible(True)

        self._progress_spinner.setVisible(True)
        self._progress_status.setText("Importing...")
        self._progress_pct.setText("0%")
        self._progress_bar.setValue(0)
        self._ok_count = 0
        self._fail_count = 0
        self._metric_processed.setText(f"0 / {len(self._files)}")
        self._metric_success.setText("0")
        self._metric_failed.setText("0")

        self.log_table.setRowCount(0)
        self.log_table.setRowCount(len(self._files))
        for row, path in enumerate(self._files):
            name_item = QTableWidgetItem(path.name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.log_table.setItem(row, 0, name_item)

            table_item = QTableWidgetItem(_table_name_for_file(path))
            table_item.setFlags(table_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table_item.setForeground(QColor(_TEXT_MUTED))
            self.log_table.setItem(row, 1, table_item)

            rows_item = QTableWidgetItem("—")
            rows_item.setFlags(rows_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.log_table.setItem(row, 2, rows_item)

            status_item = QTableWidgetItem("Pending")
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            status_item.setForeground(QColor(_TEXT_MUTED))
            status_item.setTextAlignment(
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            )
            self.log_table.setItem(row, 3, status_item)
            self.log_table.setRowHeight(row, 36)

    def _update_exec_progress(self, completed: int) -> None:
        total = max(len(self._files), 1)
        pct = int(completed * 100 / total)
        self._progress_bar.setValue(pct)
        self._progress_pct.setText(f"{pct}%")
        self._metric_processed.setText(f"{completed} / {len(self._files)}")
        self._metric_success.setText(str(self._ok_count))
        self._metric_failed.setText(str(self._fail_count))

    def _set_exec_row(
        self,
        row: int,
        *,
        table: str | None = None,
        rows_text: str | None = None,
        status: str,
        kind: str = "pending",
    ) -> None:
        if table is not None and self.log_table.item(row, 1) is not None:
            self.log_table.item(row, 1).setText(table)
        if rows_text is not None and self.log_table.item(row, 2) is not None:
            self.log_table.item(row, 2).setText(rows_text)
        status_item = self.log_table.item(row, 3)
        if status_item is None:
            status_item = QTableWidgetItem()
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            status_item.setTextAlignment(
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            )
            self.log_table.setItem(row, 3, status_item)
        status_item.setText(status)
        if kind == "ok":
            status_item.setForeground(QColor("#22c55e"))
        elif kind == "fail":
            status_item.setForeground(QColor("#d92e2e"))
        elif kind == "running":
            status_item.setForeground(QColor(_ACCENT))
        else:
            status_item.setForeground(QColor(_TEXT_MUTED))
        self.log_table.scrollToItem(status_item)
        QApplication.processEvents()

    def _on_primary(self) -> None:
        if self._step_index == 0:
            if self.primary_btn.text() == "Import" and self._scanned and self._files:
                if not self._validate_configure():
                    return
                self._prepare_execute_ui()
                self._set_step(1)
                self._handle_submit()
                return
            self._scan_folder()
            return
        if self._running:
            return
        self._handle_submit()

    def _on_secondary(self) -> None:
        if self._step_index == 0:
            self._reset_form()
            return
        if self._running:
            self._cancel_requested = True
            self._show_error("Cancelling import…")
            return
        self._clear_message()
        self._execute_stack.setCurrentIndex(0)
        self._set_step(0)

    def _on_view_details(self) -> None:
        self._execute_stack.setCurrentIndex(0)
        self._apply_step_chrome()

    def _on_new_import(self) -> None:
        self._reset_form()
        self._execute_stack.setCurrentIndex(0)
        self._set_step(0)

    def _reset_form(self) -> None:
        self.import_name_edit.clear()
        self.file_type_combo.setCurrentIndex(0)
        self.encoding_combo.setCurrentIndex(0)
        self.connection_combo.setCurrentIndex(0)
        self.radio_drop_create.setChecked(True)
        self.folder_edit.clear()
        self._folder = ""
        self._files = []
        self._scanned = False
        self._import_complete = False
        self._file_results = []
        self._empty_state.setVisible(True)
        self._scan_results.setVisible(False)
        self.file_table.setRowCount(0)
        self._clear_message()
        self._apply_step_chrome()

    def _populate_success_page(self) -> None:
        total = len(self._files)
        operation = "DROP & CREATE" if self.radio_drop_create.isChecked() else "DELETE"
        self._success_operation.setText(operation)
        self._success_total_files.setText(str(total))
        self._success_total_rows.setText(str(total))
        self._success_ok_rows.setText(str(self._ok_count))
        self._success_fail_rows.setText(str(self._fail_count))
        if self._fail_count == 0:
            self._success_subtitle.setText(
                f"All {total} file{'s' if total != 1 else ''} have been imported successfully."
            )
        else:
            self._success_subtitle.setText(
                f"{self._ok_count} of {total} files imported successfully."
            )

        while self._file_breakdown_layout.count():
            item = self._file_breakdown_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for result in self._file_results:
            row_w = QWidget()
            row = QHBoxLayout(row_w)
            row.setContentsMargins(0, 4, 0, 4)
            row.setSpacing(8)
            left = QHBoxLayout()
            left.setSpacing(8)
            icon = QLabel()
            icon.setFixedSize(14, 14)
            icon.setPixmap(_svg_pixmap(_FILE_MUTED_SVG, 14))
            left.addWidget(icon)
            name = QLabel(str(result.get("name") or ""))
            name.setObjectName("bulkFileBreakName")
            left.addWidget(name)
            row.addLayout(left, 1)
            meta = QHBoxLayout()
            meta.setSpacing(8)
            rows_lbl = QLabel(str(result.get("rows") or "—"))
            rows_lbl.setObjectName("bulkFileBreakMeta")
            meta.addWidget(rows_lbl)
            ok = bool(result.get("ok"))
            status = QLabel("✓ Success" if ok else "Failed")
            status.setObjectName("bulkFileBreakOk" if ok else "bulkFileBreakFail")
            meta.addWidget(status)
            row.addLayout(meta)
            self._file_breakdown_layout.addWidget(row_w)

    def _set_log_row(self, row: int, status: str, message: str, *, ok: bool | None = None) -> None:
        kind = "pending"
        label = status
        if ok is True:
            kind = "ok"
            label = "✓ Complete"
        elif ok is False:
            kind = "fail"
            label = "Failed"
        elif "Running" in status or "Importing" in status:
            kind = "running"
            label = "Importing"
        self._set_exec_row(row, status=label, kind=kind)

    def _build_mapping_body(
        self,
        sheet: dict[str, Any],
        *,
        target_table: str,
        target_connection_id: int,
    ) -> tuple[dict[str, Any] | None, str | None]:
        sheet_id = _first_id(sheet, "sheetId", "sheet_id", "sheetID", "id")
        try:
            sheet_id_int = int(sheet_id) if sheet_id is not None and str(sheet_id).strip() else None
        except (TypeError, ValueError):
            sheet_id_int = None
        if sheet_id_int is None:
            return None, "Sheet ID missing from analyze result."

        columns = sheet.get("columns") if isinstance(sheet.get("columns"), list) else []
        if not columns:
            return None, "No columns found in workbook."

        mappings: list[dict[str, Any]] = []
        for col in columns:
            if not isinstance(col, dict):
                continue
            source_column_id = _first_id(
                col,
                "sourceColumnId",
                "source_column_id",
                "columnId",
                "column_id",
                "fieldId",
                "id",
            )
            try:
                source_id_int = (
                    int(source_column_id)
                    if source_column_id is not None and str(source_column_id).strip()
                    else None
                )
            except (TypeError, ValueError):
                source_id_int = None
            if source_id_int is None:
                return None, "A column is missing sourceColumnId."
            target_column_name = str(col.get("tgtColumnName") or col.get("name") or "").strip()
            if not target_column_name:
                return None, "A column is missing target column name."
            nullable = True
            if col.get("nullable") in ("FALSE", "false", "0", False):
                nullable = False
            mappings.append(
                {
                    "sourceColumnId": source_id_int,
                    "targetColumnName": target_column_name,
                    "targetDataType": "STRING",
                    "nullable": nullable,
                    "primaryKey": bool(col.get("primaryKey", False)),
                    "selected": bool(col.get("selected", True)),
                    "length": 255,
                }
            )

        if not mappings:
            return None, "No column mappings to save."
        return (
            {
                "sheetId": sheet_id_int,
                "targetTableName": target_table,
                "targetConnectionId": target_connection_id,
                "mappings": mappings,
            },
            None,
        )

    def _import_one_file(
        self,
        path: Path,
        *,
        connection_id: int,
        operation: str,
        multi_language: bool,
        token: str | None,
    ) -> tuple[bool, str, str]:
        table_name = _table_name_for_file(path)
        source_type = self.file_type_combo.currentData() or _source_type_for_path(path)
        if not source_type:
            source_type = _source_type_for_path(path)
        if not source_type:
            return False, table_name, "Unsupported file type."

        create = api_create_import(table_name, str(source_type), token=token)
        if not create.get("success"):
            return False, table_name, str(create.get("message") or "Failed to create import session.")
        session_id = _session_id_from_create(create)
        if not session_id:
            data = create.get("data") if isinstance(create.get("data"), dict) else {}
            session_id = str(data.get("name") or table_name).strip()
        if not session_id:
            return False, table_name, "Import created but session ID was not returned."

        codepage = str(self.encoding_combo.currentData() or "65001")
        upload = api_upload_import_file(
            session_id,
            str(path),
            token=token,
            codepage=codepage if multi_language else None,
            multi_language=multi_language,
        )
        if not upload.get("success"):
            return False, table_name, str(upload.get("message") or "Upload failed.")

        analyze = api_analyze_import_file(
            session_id,
            token=token,
            codepage=codepage if multi_language else None,
            multi_language=multi_language,
        )
        if not analyze.get("success"):
            return False, table_name, str(analyze.get("message") or "Analyze failed.")
        sheets = analyze.get("data") if isinstance(analyze.get("data"), list) else []
        sheets = _enrich_analyze_sheets_unicode(
            sheets,
            file_path=str(path),
            multi_language=multi_language,
        )
        if not sheets:
            return False, table_name, "Analyze returned no sheets."

        sheet = sheets[0] if isinstance(sheets[0], dict) else {}
        body, err = self._build_mapping_body(
            sheet,
            target_table=table_name,
            target_connection_id=connection_id,
        )
        if err or body is None:
            return False, table_name, err or "Could not build mapping."

        save = api_save_import_mapping(session_id, body, token=token)
        if not save.get("success"):
            return False, table_name, str(save.get("message") or "Failed to save mapping.")

        sheet_id = body.get("sheetId")
        execute = api_execute_import_sheet(
            session_id,
            sheet_id,
            operation=operation,
            token=token,
        )
        if not execute.get("success"):
            return False, table_name, str(execute.get("message") or "Execute/import failed.")
        return True, table_name, str(execute.get("message") or "Imported successfully.")

    def _handle_submit(self) -> None:
        if self._running:
            return
        self._clear_message()
        if not self._folder or not self._files:
            self._show_error("Select a folder that contains importable files.")
            return
        connection_id = self._selected_connection_id()
        if connection_id is None:
            self._show_error("Select a target database connection.")
            return
        token = self._token()
        if not token:
            self._show_error("Session expired. Please log in again.")
            return

        operation = self._selected_operation()
        multi_language = True
        self._running = True
        self._cancel_requested = False
        self._ok_count = 0
        self._fail_count = 0
        self._file_results = []
        self._import_complete = False
        self._execute_stack.setCurrentIndex(0)
        self._exec_alert.setVisible(True)
        self._progress_spinner.setVisible(True)
        self._progress_status.setText("Importing...")
        self._apply_step_chrome()
        completed = 0
        was_cancelled = False
        try:
            for row, path in enumerate(self._files):
                if self._cancel_requested:
                    was_cancelled = True
                    for pending in range(row, len(self._files)):
                        self._set_exec_row(pending, status="Pending", kind="pending")
                    break
                self._set_exec_row(row, status="Importing", kind="running", rows_text="—")
                self._update_exec_progress(completed)
                try:
                    ok, table, message = self._import_one_file(
                        path,
                        connection_id=connection_id,
                        operation=operation,
                        multi_language=multi_language,
                        token=token,
                    )
                except Exception as exc:  # noqa: BLE001 — keep batch going
                    ok, table, message = False, _table_name_for_file(path), str(exc)
                self._file_results.append(
                    {
                        "name": path.name,
                        "ok": ok,
                        "rows": "—",
                        "table": table,
                        "message": message,
                    }
                )
                if ok:
                    self._ok_count += 1
                    self._set_exec_row(
                        row, table=table, rows_text="—", status="✓ Complete", kind="ok"
                    )
                else:
                    self._fail_count += 1
                    self._set_exec_row(
                        row, table=table, rows_text="—", status="Failed", kind="fail"
                    )
                completed += 1
                self._update_exec_progress(completed)
        finally:
            self._running = False
            self._cancel_requested = False
            self._progress_spinner.setVisible(False)
            if was_cancelled:
                self._progress_status.setText("Import cancelled")
            elif self._fail_count == 0 and completed == len(self._files):
                self._progress_status.setText("Import complete")
                self._progress_bar.setValue(100)
                self._progress_pct.setText("100%")
            else:
                self._progress_status.setText("Import finished with errors")
            self._exec_alert.setVisible(False)
            self._apply_step_chrome()

        if was_cancelled:
            self._show_error("Import was cancelled.")
            return

        self._import_complete = True
        self._populate_success_page()
        self._execute_stack.setCurrentIndex(1)
        self._apply_step_chrome()
        self._clear_message()
