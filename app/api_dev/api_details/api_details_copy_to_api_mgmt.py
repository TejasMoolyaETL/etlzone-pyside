"""Copy dev API catalog rows to management — API Dev + API MGMT (apis/get-all-apis), queue, POST replicate."""

from __future__ import annotations

import traceback
from typing import Any, Callable
from urllib.parse import urlparse

from PySide6.QtCore import QObject, QPoint, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.api_management.api_registry_list import (
    _API_COLUMN_SPEC,
    _api_catalog_endpoint,
    _api_catalog_id,
    _api_catalog_name,
    _app_catalog_row_description,
    _app_catalog_row_id_effective,
    _app_id_value_for_api,
    _format_cell,
    _value_for_column,
)
from core.api import (
    api_get_all_api_details,
    api_get_all_apis,
    api_get_all_app_id,
    api_replicate_api_dev_to_mgmt,
)
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.data_table import (
    apply_data_table_appearance,
    attach_table_copy_shortcut,
    clear_filter_row_widgets,
    FILTER_ROW_HEIGHT_PX,
    filter_dict_rows_by_column_edits,
    install_filter_row,
    MIN_DATA_COL_WIDTH_PX,
    resize_data_table_columns_to_content,
    sync_vertical_header_labels,
)
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    MODAL_FIELD_HEIGHT_PX,
    MODAL_FIELD_LABEL_STYLE,
)
from ui.styles import CONTEXT_MENU_STYLESHEET
from ui.theme import Theme

# API Dev + Queue: get-all-api-details rows (apiMethod, apiStatusResponse.keyValue, projectName).
_STATUS_FROM_API_STATUS_RESPONSE = ("__apiStatusResponse_keyValue__",)
_API_DEV_REPLICATE_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("API Id", ("apiId", "api_id", "id")),
    ("Name", ("apiName", "api_name", "name", "title")),
    ("Method", ("apiMethod", "httpMethod", "http_method", "method", "verb")),
    ("Status", _STATUS_FROM_API_STATUS_RESPONSE),
    ("Project", ("projectName", "project_name")),
    ("Created By", ("createdBy", "created_by")),
    ("Created At", ("createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified At", ("modifiedAt", "modified_at", "updatedAt", "updated_at")),
)


def _replicate_dev_value_for_column(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    if keys == _STATUS_FROM_API_STATUS_RESPONSE:
        nested = row.get("apiStatusResponse")
        if isinstance(nested, dict):
            v = nested.get("keyValue")
            return (v, "keyValue")
        return (None, "keyValue")
    return _value_for_column(row, keys)


def _replicate_api_identity_norm(row: dict[str, Any]) -> str:
    """Stable key to match API Dev (details) rows with API MGMT (registry) rows — ``apiId`` differs across systems."""
    ep = _api_catalog_endpoint(row).strip()
    nm = _api_catalog_name(row).strip()
    path = ep or nm
    if not path:
        return ""
    low = path.lower()
    if low.startswith("http://") or low.startswith("https://"):
        parsed = urlparse(path)
        path = (parsed.path or "").strip()
        if not path:
            return ""
    out = path.strip().lower()
    if "://" not in low and out and not out.startswith("/"):
        out = "/" + out.lstrip("/")
    return out


# Section title bars — same height, margins, and label chrome as API: All in One → Comments
# (``api_dev_validation_comment_panel``: header strip + ``commentPanelHeaderTitle``).
_REPLICATE_SECTION_TITLE_BAR_HEIGHT_PX = 22
_REPLICATE_SECTION_TITLE_BAR_MARGINS = (5, 0, 5, 0)
_REPLICATE_SECTION_TITLE_BAR_SPACING = 3


def _replicate_section_header_stylesheet(title_object_name: str) -> str:
    t = Theme
    return (
        f"QWidget {{ background: {t.HEADER_NAV}; }}"
        f"QLabel#{title_object_name} {{ color: {t.PANEL_TEXT_BRIGHT}; font-size: 9px; font-weight: 600; }}"
        f"QPushButton {{ background: {t.HEADER_ACCENT}; color: {t.PANEL_TEXT_BRIGHT}; border: none; border-radius: 2px; "
        f"padding: 0px 5px; font-size: 8px; font-weight: 500; min-height: 0px; max-height: 16px; }}"
        f"QPushButton:hover {{ background: {t.HEADER_ACCENT_HOVER}; }}"
        f"QPushButton:pressed {{ background: {t.HEADER_ACCENT_PRESSED}; }}"
        f"QPushButton:checked {{ background: {t.HEADER_ACCENT_PRESSED}; }}"
    )


def _make_replicate_section_header(
    initial_title_text: str,
    title_object_name: str,
    *,
    bar_tool_tip: str | None = None,
) -> tuple[QWidget, QLabel, QPushButton]:
    bar = QWidget()
    if bar_tool_tip:
        bar.setToolTip(bar_tool_tip)
    bar.setStyleSheet(_replicate_section_header_stylesheet(title_object_name))
    bar.setFixedHeight(_REPLICATE_SECTION_TITLE_BAR_HEIGHT_PX)
    lay = QHBoxLayout(bar)
    lay.setContentsMargins(*_REPLICATE_SECTION_TITLE_BAR_MARGINS)
    lay.setSpacing(_REPLICATE_SECTION_TITLE_BAR_SPACING)
    lab = QLabel(initial_title_text)
    lab.setObjectName(title_object_name)
    lab.setMaximumHeight(_REPLICATE_SECTION_TITLE_BAR_HEIGHT_PX)
    lay.addWidget(lab)
    lay.addStretch()
    btn_h = _REPLICATE_SECTION_TITLE_BAR_HEIGHT_PX - 2
    filt = QPushButton("Filters")
    filt.setCheckable(True)
    filt.setFixedWidth(52)
    filt.setMaximumHeight(btn_h)
    filt.setCursor(Qt.CursorShape.PointingHandCursor)
    lay.addWidget(filt)
    return bar, lab, filt


class _ApisPairLoadWorker(QObject):
    """Load API Dev catalog and API MGMT catalog (apis/get-all-apis) in one background pass."""

    finished = Signal(bool, object, object, str)

    def __init__(self, token: str | None) -> None:
        super().__init__()
        self._token = token

    @Slot()
    def run(self) -> None:
        dev_res = api_get_all_api_details(token=self._token)
        if not dev_res.get("success"):
            self.finished.emit(
                False,
                [],
                [],
                str(dev_res.get("message", "Failed to load API Dev.")),
            )
            return
        dev_raw = dev_res.get("data") or []
        dev_rows = [r for r in dev_raw if isinstance(r, dict)]
        mgmt_res = api_get_all_apis(token=self._token)
        if not mgmt_res.get("success"):
            self.finished.emit(
                True,
                dev_rows,
                [],
                str(mgmt_res.get("message", "Failed to load API MGMT (apis/get-all-apis).")),
            )
            return
        mgmt_raw = mgmt_res.get("data") or []
        mgmt_rows = [r for r in mgmt_raw if isinstance(r, dict)]
        self.finished.emit(True, dev_rows, mgmt_rows, "")


class _ReplicateWorker(QObject):
    finished = Signal(object)

    def __init__(self, *, token: str, app_id: int | str, api_detail_ids: list[Any]) -> None:
        super().__init__()
        self._token = token
        self._app_id = app_id
        self._api_detail_ids = list(api_detail_ids)

    @Slot()
    def run(self) -> None:
        result = api_replicate_api_dev_to_mgmt(
            self._app_id, self._api_detail_ids, token=self._token
        )
        self.finished.emit(result)


class CopyApiDevToMgmtPage(QWidget):
    """API: Details → management replicate — dev catalog, checkbox queue, target App Id, POST."""

    def __init__(self, on_back: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.on_back = on_back
        self._loading = False
        self._pending_refresh = False
        self._pending_replicate_success_msg: str | None = None
        self._load_thread: QThread | None = None
        self._load_worker: _ApisPairLoadWorker | None = None
        self._repl_thread: QThread | None = None
        self._repl_worker: _ReplicateWorker | None = None
        self._source_rows: list[dict[str, Any]] = []
        self._column_spec: list[tuple[str, tuple[str, ...]]] = []
        self._mgmt_rows: list[dict[str, Any]] = []
        self._staging_rows: list[dict[str, Any]] = []
        self._mgmt_column_spec: list[tuple[str, tuple[str, ...]]] = []
        self._dev_filter_visible = False
        self._mgmt_filter_visible = False
        self._queue_filter_visible = False
        self._right_split: QSplitter | None = None
        self._dev_filter_timer = QTimer(self)
        self._dev_filter_timer.setSingleShot(True)
        self._dev_filter_timer.setInterval(200)
        self._dev_filter_timer.timeout.connect(self._apply_dev_filter_refresh)
        self._mgmt_filter_timer = QTimer(self)
        self._mgmt_filter_timer.setSingleShot(True)
        self._mgmt_filter_timer.setInterval(200)
        self._mgmt_filter_timer.timeout.connect(self._apply_mgmt_filter_refresh)
        self._queue_filter_timer = QTimer(self)
        self._queue_filter_timer.setSingleShot(True)
        self._queue_filter_timer.setInterval(200)
        self._queue_filter_timer.timeout.connect(self._apply_queue_filter_refresh)
        self._build_ui()

    def _data_row_offset(self) -> int:
        return 1 if self._dev_filter_visible else 0

    def _queue_data_row_offset(self) -> int:
        return 1 if self._queue_filter_visible else 0

    def _is_data_table_row(self, table_row: int) -> bool:
        return table_row >= self._data_row_offset()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        self._back_btn = QPushButton("Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._back_btn.clicked.connect(self._handle_back)
        hl.addWidget(self._back_btn)
        title = QLabel("API Replicate")
        hl.addWidget(title)
        hl.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        hl.addWidget(refresh_btn)
        layout.addWidget(header)

        self._message_label = QLabel()
        self._message_label.setWordWrap(True)
        self._message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._message_label.setVisible(False)
        msg_wrap = QHBoxLayout()
        msg_wrap.setContentsMargins(12, 4, 12, 0)
        msg_wrap.addWidget(self._message_label)
        layout.addLayout(msg_wrap)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left_wrap = QWidget()
        left_l = QVBoxLayout(left_wrap)
        left_l.setContentsMargins(8, 0, 4, 8)
        left_l.setSpacing(4)
        dev_bar, self._dev_title_label, self._dev_filter_btn = _make_replicate_section_header(
            "API Dev (0)", "apiReplicateSectionTitleDev"
        )
        self._dev_filter_btn.toggled.connect(self._on_dev_filter_toggle)
        left_l.addWidget(dev_bar)
        self._left_table = QTableWidget()
        apply_data_table_appearance(self._left_table)
        # Disabled checkbox (API already in MGMT or queue): same indicator fill as Role-API Assignment.
        self._left_table.setStyleSheet(
            self._left_table.styleSheet()
            + (
                f"QTableWidget::indicator:unchecked:disabled {{ background: {Theme.BG_PAGE_ALT}; "
                f"border: 1px solid {Theme.BORDER_INPUT}; border-radius: 2px; }}"
                f"QTableWidget::indicator:checked:disabled {{ background: {Theme.BG_PAGE_ALT}; "
                f"border: 1px solid {Theme.BORDER_INPUT}; border-radius: 2px; }}"
            )
        )
        self._left_table.setSortingEnabled(False)
        attach_table_copy_shortcut(self._left_table)
        left_l.addWidget(self._left_table, 1)

        mid = QWidget()
        mid.setFixedWidth(40)
        mid_l = QVBoxLayout(mid)
        mid_l.setContentsMargins(4, 0, 4, 0)
        mid_l.addStretch(1)
        self._btn_to_staging = QPushButton("\u003e")
        self._btn_to_staging.setFixedSize(30, 26)
        self._btn_to_staging.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_to_staging.setToolTip("Move checked APIs from API Dev to Queue for Replicate")
        self._btn_to_staging.clicked.connect(self._move_checked_to_staging)
        mid_l.addWidget(self._btn_to_staging, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._btn_from_staging = QPushButton("\u003c")
        self._btn_from_staging.setFixedSize(30, 26)
        self._btn_from_staging.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_from_staging.setToolTip("Remove checked rows from Queue for Replicate")
        self._btn_from_staging.clicked.connect(self._remove_checked_from_staging)
        mid_l.addWidget(self._btn_from_staging, alignment=Qt.AlignmentFlag.AlignHCenter)
        mid_l.addStretch(1)

        right_wrap = QWidget()
        right_l = QVBoxLayout(right_wrap)
        right_l.setContentsMargins(4, 0, 8, 8)
        right_l.setSpacing(4)
        right_split = QSplitter(Qt.Orientation.Vertical)
        right_split.setChildrenCollapsible(False)
        right_split.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._right_split = right_split

        mgmt_block = QWidget()
        mgmt_block_l = QVBoxLayout(mgmt_block)
        mgmt_block_l.setContentsMargins(0, 0, 0, 0)
        mgmt_block_l.setSpacing(4)
        mgmt_bar, self._mgmt_title_label, self._mgmt_filter_btn = _make_replicate_section_header(
            "API MGMT (0)",
            "apiReplicateSectionTitleMgmt",
            bar_tool_tip="Catalog from apis/get-all-apis",
        )
        self._mgmt_filter_btn.toggled.connect(self._on_mgmt_filter_toggle)
        mgmt_block_l.addWidget(mgmt_bar)
        self._mgmt_catalog_table = QTableWidget()
        apply_data_table_appearance(self._mgmt_catalog_table)
        self._mgmt_catalog_table.setSortingEnabled(False)
        self._mgmt_catalog_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        attach_table_copy_shortcut(self._mgmt_catalog_table)
        mgmt_block_l.addWidget(self._mgmt_catalog_table, 1)

        queue_block = QWidget()
        queue_block_l = QVBoxLayout(queue_block)
        queue_block_l.setContentsMargins(0, 0, 0, 0)
        queue_block_l.setSpacing(4)
        queue_bar, self._queue_title_label, self._queue_filter_btn = _make_replicate_section_header(
            "Queue for Replicate (0)",
            "apiReplicateSectionTitleQueue",
        )
        self._queue_filter_btn.toggled.connect(self._on_queue_filter_toggle)
        queue_block_l.addWidget(queue_bar)
        self._queue_table = QTableWidget()
        apply_data_table_appearance(self._queue_table)
        self._queue_table.setSortingEnabled(False)
        self._queue_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._queue_table.customContextMenuRequested.connect(self._on_staging_context_menu)
        attach_table_copy_shortcut(self._queue_table)
        queue_block_l.addWidget(self._queue_table, 1)

        right_split.addWidget(queue_block)
        right_split.addWidget(mgmt_block)
        right_split.setStretchFactor(0, 1)
        right_split.setStretchFactor(1, 1)
        right_l.addWidget(right_split, 1)

        splitter.addWidget(left_wrap)
        splitter.addWidget(mid)
        splitter.addWidget(right_wrap)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 1)
        layout.addWidget(splitter, 1)

        bottom = QWidget()
        bottom_l = QHBoxLayout(bottom)
        bottom_l.setContentsMargins(12, 8, 12, 12)
        bottom_l.setSpacing(12)
        app_lbl = QLabel("App Id (MGMT)")
        app_lbl.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        bottom_l.addWidget(app_lbl)
        self._app_combo = QComboBox()
        self._app_combo.currentIndexChanged.connect(lambda _i: self._update_replicate_enabled())
        bottom_l.addWidget(self._app_combo, 1)
        bottom_l.addStretch(1)
        self._replicate_btn = QPushButton("Replicate")
        self._replicate_btn.setFixedWidth(120)
        self._replicate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._replicate_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._replicate_btn.setEnabled(False)
        self._replicate_btn.clicked.connect(self._on_replicate_clicked)
        bottom_l.addWidget(self._replicate_btn)
        layout.addWidget(bottom)

        self._update_section_filter_buttons_enabled()

    def _handle_back(self) -> None:
        if self.on_back:
            self.on_back()

    def _show_message(self, text: str, *, error: bool) -> None:
        show_auto_hiding_message(self, self._message_label, text, error=error)

    def _reset_replicate_page_for_reload(self) -> None:
        """Each time the page is shown: drop filters, queue, and transient state before reloading data."""
        self._pending_refresh = False
        self._pending_replicate_success_msg = None
        self._dev_filter_timer.stop()
        self._mgmt_filter_timer.stop()
        self._queue_filter_timer.stop()
        cancel_auto_hide_message(self, self._message_label)
        self._message_label.clear()
        self._message_label.setVisible(False)

        self._dev_filter_btn.blockSignals(True)
        self._dev_filter_btn.setChecked(False)
        self._dev_filter_btn.blockSignals(False)
        self._on_dev_filter_toggle(False)

        self._mgmt_filter_btn.blockSignals(True)
        self._mgmt_filter_btn.setChecked(False)
        self._mgmt_filter_btn.blockSignals(False)
        self._on_mgmt_filter_toggle(False)

        self._staging_rows.clear()
        self._write_staging_table()

    def _schedule_dev_filter_apply(self) -> None:
        if self._dev_filter_visible:
            self._dev_filter_timer.start()

    @staticmethod
    def _checkbox_item() -> QTableWidgetItem:
        it = QTableWidgetItem()
        it.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        it.setCheckState(Qt.CheckState.Unchecked)
        return it

    def _blocked_api_identity_norms(self) -> set[str]:
        """Paths/names already in MGMT catalog or queue (``apiId`` is not comparable across Dev vs MGMT)."""
        keys: set[str] = set()
        for row in self._mgmt_rows:
            k = _replicate_api_identity_norm(row)
            if k:
                keys.add(k)
        for row in self._staging_rows:
            k = _replicate_api_identity_norm(row)
            if k:
                keys.add(k)
        return keys

    def _refresh_dev_row_blocked_state(self) -> None:
        """Grey out and disable checkbox for API Dev rows already listed in MGMT or queue."""
        if self._left_table.columnCount() < 2 or not self._column_spec:
            return
        blocked = self._blocked_api_identity_norms()
        off = self._data_row_offset()
        cb_enabled = Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
        cb_blocked = Qt.ItemFlag.ItemIsUserCheckable
        data_enabled = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        data_blocked = Qt.ItemFlag.ItemIsSelectable
        for tr in range(off, self._left_table.rowCount()):
            it1 = self._left_table.item(tr, 1)
            if it1 is None:
                continue
            raw = it1.data(Qt.ItemDataRole.UserRole)
            key = _replicate_api_identity_norm(raw) if isinstance(raw, dict) else ""
            is_blocked = bool(key) and key in blocked
            it0 = self._left_table.item(tr, 0)
            if it0 is not None:
                if is_blocked:
                    it0.setCheckState(Qt.CheckState.Unchecked)
                    it0.setFlags(cb_blocked)
                    it0.setForeground(QBrush(QColor(Theme.TEXT_SECONDARY)))
                    # Checkbox cell matches disabled indicator (#f6f8fb — Theme.BG_PAGE_ALT).
                    it0.setBackground(QBrush(QColor(Theme.BG_PAGE_ALT)))
                else:
                    it0.setFlags(cb_enabled)
                    it0.setForeground(QBrush())
                    it0.setBackground(QBrush())
            for c in range(1, self._left_table.columnCount()):
                cell = self._left_table.item(tr, c)
                if cell is None:
                    continue
                cell.setFlags(data_blocked if is_blocked else data_enabled)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)

    def _filtered_source_rows(self) -> list[dict[str, Any]]:
        rows = list(self._source_rows)
        if not self._dev_filter_visible or not self._column_spec:
            return rows
        for col, (_, keys) in enumerate(self._column_spec):
            w = self._left_table.cellWidget(0, col + 1)
            if not isinstance(w, QLineEdit):
                continue
            q = w.text().strip().lower()
            if not q:
                continue

            def cell_text(row: dict[str, Any], k: tuple[str, ...] = keys) -> str:
                v, ku = _replicate_dev_value_for_column(row, k)
                return _format_cell(v, ku, k).lower()

            rows = [r for r in rows if q in cell_text(r)]
        return rows

    def _resize_left_columns(self, data_rows: list[dict[str, Any]]) -> None:
        self._left_table.setColumnWidth(0, 40)
        if not self._column_spec:
            return
        fm_cell = QFontMetrics(self._left_table.font())
        fm_header = QFontMetrics(self._left_table.horizontalHeader().font())
        for col, (header_text, keys) in enumerate(self._column_spec):
            pc = col + 1
            w = fm_header.horizontalAdvance(header_text) + 18
            for row in data_rows:
                if not isinstance(row, dict):
                    continue
                value, key_used = _replicate_dev_value_for_column(row, keys)
                text = _format_cell(value, key_used, keys)
                w = max(w, fm_cell.horizontalAdvance(text) + 12)
            self._left_table.setColumnWidth(pc, max(MIN_DATA_COL_WIDTH_PX, w))

    def _resize_staging_columns(self, sample_rows: list[dict[str, Any]] | None = None) -> None:
        self._queue_table.setColumnWidth(0, 40)
        spec = self._column_spec or list(_API_DEV_REPLICATE_COLUMN_SPEC)
        if not spec:
            return
        rows = sample_rows if sample_rows is not None else self._staging_rows
        fm_cell = QFontMetrics(self._queue_table.font())
        fm_header = QFontMetrics(self._queue_table.horizontalHeader().font())
        for col, (header_text, keys) in enumerate(spec):
            pc = col + 1
            w = fm_header.horizontalAdvance(header_text) + 18
            for row in rows:
                if not isinstance(row, dict):
                    continue
                value, key_used = _replicate_dev_value_for_column(row, keys)
                text = _format_cell(value, key_used, keys)
                w = max(w, fm_cell.horizontalAdvance(text) + 12)
            self._queue_table.setColumnWidth(pc, max(MIN_DATA_COL_WIDTH_PX, w))

    def _selected_mgmt_app_id(self) -> Any | None:
        i = self._app_combo.currentIndex()
        if i < 0:
            return None
        d = self._app_combo.itemData(i)
        return None if d is None else _app_id_value_for_api(d)

    def _update_replicate_enabled(self) -> None:
        self._replicate_btn.setEnabled(bool(self._staging_rows))

    def _fetch_and_fill_app_combo(self) -> None:
        self._app_combo.blockSignals(True)
        self._app_combo.clear()
        self._app_combo.addItem("— Select App Id —", None)
        tok = self._token()
        if tok:
            res = api_get_all_app_id(token=tok)
            if res.get("success"):
                raw = res.get("data") or []
                seen_display: set[str] = set()
                for r in sorted(
                    (x for x in raw if isinstance(x, dict)),
                    key=lambda row: (_app_catalog_row_description(row) or "").lower(),
                ):
                    aid = _app_catalog_row_id_effective(r)
                    if aid is None:
                        continue
                    desc = (_app_catalog_row_description(r) or "").strip()
                    label = desc if desc else f"App {aid}"
                    if label in seen_display:
                        label = f"{label} · {aid}"
                    seen_display.add(label)
                    self._app_combo.addItem(label, aid)
            else:
                self._show_message(str(res.get("message") or "Failed to load App Ids."), error=True)
        self._app_combo.setCurrentIndex(0)
        self._app_combo.blockSignals(False)
        apply_form_combobox_field(self._app_combo, height_px=MODAL_FIELD_HEIGHT_PX, min_width=280)
        self._update_replicate_enabled()

    def _append_to_staging(self, row: dict[str, Any], *, refresh: bool = True) -> bool:
        rid = _api_catalog_id(row)
        if rid is None:
            self._show_message("Row has no API id; skipped.", error=True)
            return False
        nk = _replicate_api_identity_norm(row)
        for existing in self._staging_rows:
            if _api_catalog_id(existing) == rid:
                return False
            if nk and _replicate_api_identity_norm(existing) == nk:
                return False
        self._staging_rows.append(dict(row))
        if refresh:
            self._write_staging_table()
        return True

    def _move_checked_to_staging(self) -> None:
        off = self._data_row_offset()
        n_before = len(self._staging_rows)
        any_checked = False
        moved = 0
        for tr in range(off, self._left_table.rowCount()):
            it0 = self._left_table.item(tr, 0)
            it1 = self._left_table.item(tr, 1)
            if it0 is None or not (it0.flags() & Qt.ItemFlag.ItemIsEnabled):
                continue
            if it0.checkState() != Qt.CheckState.Checked:
                continue
            any_checked = True
            raw = it1.data(Qt.ItemDataRole.UserRole) if it1 is not None else None
            if not isinstance(raw, dict):
                continue
            if self._append_to_staging(dict(raw), refresh=False):
                it0.setCheckState(Qt.CheckState.Unchecked)
                moved += 1
        if moved:
            self._write_staging_table()
        if not any_checked:
            self._show_message("Check one or more APIs in API Dev, then click \u003e.", error=False)
            return
        if moved == 0:
            self._show_message("No new rows moved (already queued or missing API id).", error=False)

    def _remove_checked_from_staging(self) -> None:
        if not self._staging_rows:
            return
        ids_remove: set[Any] = set()
        any_checked = False
        q_off = self._queue_data_row_offset()
        for tr in range(q_off, self._queue_table.rowCount()):
            it0 = self._queue_table.item(tr, 0)
            it1 = self._queue_table.item(tr, 1)
            if it0 is None or it0.checkState() != Qt.CheckState.Checked:
                continue
            any_checked = True
            raw = it1.data(Qt.ItemDataRole.UserRole) if it1 is not None else None
            if isinstance(raw, dict):
                rid = _api_catalog_id(raw)
                if rid is not None:
                    ids_remove.add(rid)
        if not any_checked:
            self._show_message("Check one or more rows in Queue for Replicate, then click \u003c.", error=False)
            return
        self._staging_rows = [r for r in self._staging_rows if _api_catalog_id(r) not in ids_remove]
        self._write_staging_table()

    def _write_left_data_rows(self, data_rows: list[dict[str, Any]]) -> None:
        off = self._data_row_offset()
        self._left_table.setSortingEnabled(False)
        total = off + len(data_rows)
        if self._dev_filter_visible and total < 1:
            total = 1
        self._left_table.setRowCount(total)
        if self._dev_filter_visible:
            for c in range(self._left_table.columnCount()):
                self._left_table.takeItem(0, c)
            install_filter_row(
                self._left_table,
                1 + len(self._column_spec),
                on_text_changed=self._schedule_dev_filter_apply,
            )
            w0 = self._left_table.cellWidget(0, 0)
            if w0 is not None:
                self._left_table.removeCellWidget(0, 0)
            spacer = QWidget()
            spacer.setFixedSize(40, FILTER_ROW_HEIGHT_PX)
            self._left_table.setCellWidget(0, 0, spacer)
        for r, row in enumerate(data_rows):
            tr = off + r
            self._left_table.setItem(tr, 0, self._checkbox_item())
            for col, (_, keys) in enumerate(self._column_spec):
                value, key_used = _replicate_dev_value_for_column(row, keys)
                item = QTableWidgetItem(_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self._left_table.setItem(tr, col + 1, item)
        sync_vertical_header_labels(
            self._left_table,
            filter_visible=self._dev_filter_visible,
            data_row_count=len(data_rows),
        )
        self._resize_left_columns(data_rows)
        self._left_table.setSortingEnabled(not self._dev_filter_visible)
        self._refresh_dev_row_blocked_state()

    def _apply_dev_filter_refresh(self) -> None:
        if not self._dev_filter_visible or not self._column_spec or not self._source_rows:
            return
        try:
            filtered = self._filtered_source_rows()
            self._write_left_data_rows(filtered)
        except Exception:
            traceback.print_exc()

    def _on_dev_filter_toggle(self, checked: bool) -> None:
        self._dev_filter_visible = checked
        if not checked:
            self._dev_filter_timer.stop()
            clear_filter_row_widgets(self._left_table)
        if self._column_spec and self._source_rows:
            try:
                to_show = self._filtered_source_rows() if checked else list(self._source_rows)
                self._write_left_data_rows(to_show)
            except Exception:
                traceback.print_exc()
        elif not self._source_rows:
            self._show_empty_left_table()
        self._refresh_dev_section_title()

    def _schedule_mgmt_filter_apply(self) -> None:
        if self._mgmt_filter_visible:
            self._mgmt_filter_timer.start()

    def _schedule_queue_filter_apply(self) -> None:
        if self._queue_filter_visible:
            self._queue_filter_timer.start()

    def _refresh_dev_section_title(self) -> None:
        n = len(self._source_rows)
        self._dev_title_label.setText(f"API Dev ({n})")

    def _refresh_mgmt_section_title(self) -> None:
        n = len(self._mgmt_rows)
        self._mgmt_title_label.setText(f"API MGMT ({n})")

    def _refresh_queue_section_title(self) -> None:
        n = len(self._staging_rows)
        self._queue_title_label.setText(f"Queue for Replicate ({n})")

    def _equalize_right_split(self) -> None:
        if self._right_split is None:
            return
        h = int(self._right_split.height())
        if h < 24:
            return
        half = max(1, h // 2)
        self._right_split.setSizes([half, max(1, h - half)])

    def _update_section_filter_buttons_enabled(self) -> None:
        self._dev_filter_btn.setEnabled(bool(self._source_rows))
        self._mgmt_filter_btn.setEnabled(bool(self._mgmt_rows))
        self._queue_filter_btn.setEnabled(bool(self._staging_rows))

    def _mgmt_data_row_offset(self) -> int:
        return 1 if self._mgmt_filter_visible else 0

    def _filtered_mgmt_rows(self) -> list[dict[str, Any]]:
        if not self._mgmt_filter_visible or not self._mgmt_column_spec:
            return list(self._mgmt_rows)
        return filter_dict_rows_by_column_edits(
            self._mgmt_rows,
            self._mgmt_catalog_table,
            self._mgmt_column_spec,
            self._mgmt_filter_visible,
            _value_for_column,
            _format_cell,
        )

    def _write_mgmt_data_rows(self, data_rows: list[dict[str, Any]]) -> None:
        spec = self._mgmt_column_spec
        if not spec:
            return
        self._mgmt_catalog_table.setColumnCount(len(spec))
        self._mgmt_catalog_table.setHorizontalHeaderLabels([s[0] for s in spec])
        hh = self._mgmt_catalog_table.horizontalHeader()
        hh.setStretchLastSection(False)
        for col in range(self._mgmt_catalog_table.columnCount()):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
        off = self._mgmt_data_row_offset()
        self._mgmt_catalog_table.setSortingEnabled(False)
        total = off + len(data_rows)
        if self._mgmt_filter_visible and total < 1:
            total = 1
        self._mgmt_catalog_table.setRowCount(total)
        if self._mgmt_filter_visible:
            for c in range(self._mgmt_catalog_table.columnCount()):
                self._mgmt_catalog_table.takeItem(0, c)
            install_filter_row(
                self._mgmt_catalog_table,
                len(spec),
                on_text_changed=self._schedule_mgmt_filter_apply,
            )
        for r, row in enumerate(data_rows):
            tr = off + r
            for col, (_, keys) in enumerate(spec):
                value, key_used = _value_for_column(row, keys)
                item = QTableWidgetItem(_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self._mgmt_catalog_table.setItem(tr, col, item)
        sync_vertical_header_labels(
            self._mgmt_catalog_table,
            filter_visible=self._mgmt_filter_visible,
            data_row_count=len(data_rows),
        )
        resize_data_table_columns_to_content(
            self._mgmt_catalog_table,
            spec,
            self._mgmt_rows,
            _value_for_column,
            _format_cell,
        )
        self._mgmt_catalog_table.setSortingEnabled(not self._mgmt_filter_visible)
        self._refresh_dev_row_blocked_state()

    def _apply_mgmt_filter_refresh(self) -> None:
        if not self._mgmt_filter_visible or not self._mgmt_column_spec or not self._mgmt_rows:
            return
        try:
            filtered = self._filtered_mgmt_rows()
            self._write_mgmt_data_rows(filtered)
        except Exception:
            traceback.print_exc()

    def _on_mgmt_filter_toggle(self, checked: bool) -> None:
        self._mgmt_filter_visible = checked
        if not checked:
            self._mgmt_filter_timer.stop()
            clear_filter_row_widgets(self._mgmt_catalog_table)
        if self._mgmt_column_spec and self._mgmt_rows:
            try:
                to_show = self._filtered_mgmt_rows() if checked else list(self._mgmt_rows)
                self._write_mgmt_data_rows(to_show)
            except Exception:
                traceback.print_exc()
        elif not self._mgmt_rows:
            self._show_empty_mgmt_catalog()
        self._refresh_mgmt_section_title()
        self._update_section_filter_buttons_enabled()

    def _filtered_queue_rows(self) -> list[dict[str, Any]]:
        rows = list(self._staging_rows)
        if not self._queue_filter_visible or not (self._column_spec or _API_DEV_REPLICATE_COLUMN_SPEC):
            return rows
        spec = self._column_spec or list(_API_DEV_REPLICATE_COLUMN_SPEC)
        for col, (_, keys) in enumerate(spec):
            w = self._queue_table.cellWidget(0, col + 1)
            if not isinstance(w, QLineEdit):
                continue
            q = w.text().strip().lower()
            if not q:
                continue

            def cell_text(row: dict[str, Any], k: tuple[str, ...] = keys) -> str:
                v, ku = _replicate_dev_value_for_column(row, k)
                return _format_cell(v, ku, k).lower()

            rows = [r for r in rows if q in cell_text(r)]
        return rows

    def _apply_queue_filter_refresh(self) -> None:
        if not self._queue_filter_visible or not self._staging_rows:
            return
        try:
            filtered = self._filtered_queue_rows()
            self._write_staging_table_rows(filtered)
        except Exception:
            traceback.print_exc()

    def _on_queue_filter_toggle(self, checked: bool) -> None:
        self._queue_filter_visible = checked
        if not checked:
            self._queue_filter_timer.stop()
            clear_filter_row_widgets(self._queue_table)
        if self._staging_rows:
            try:
                to_show = self._filtered_queue_rows() if checked else list(self._staging_rows)
                self._write_staging_table_rows(to_show)
            except Exception:
                traceback.print_exc()
        else:
            self._queue_filter_btn.blockSignals(True)
            self._queue_filter_btn.setChecked(False)
            self._queue_filter_btn.blockSignals(False)
            self._queue_filter_visible = False
            self._queue_table.setRowCount(0)
            self._queue_table.setColumnCount(0)
        self._refresh_queue_section_title()
        self._update_section_filter_buttons_enabled()

    def _show_empty_left_table(self) -> None:
        self._source_rows = []
        self._column_spec = []
        self._left_table.setSortingEnabled(False)
        clear_filter_row_widgets(self._left_table)
        self._left_table.setRowCount(0)
        self._left_table.setColumnCount(0)
        self._dev_filter_btn.blockSignals(True)
        self._dev_filter_btn.setChecked(False)
        self._dev_filter_btn.blockSignals(False)
        self._dev_filter_visible = False
        self._refresh_dev_section_title()
        self._update_section_filter_buttons_enabled()

    def _populate_left(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            self._show_empty_left_table()
            return
        try:
            self._source_rows = [dict(r) for r in rows if isinstance(r, dict)]
            self._column_spec = list(_API_DEV_REPLICATE_COLUMN_SPEC)
            self._left_table.setSortingEnabled(False)
            self._left_table.setColumnCount(1 + len(self._column_spec))
            self._left_table.setHorizontalHeaderLabels([""] + [s[0] for s in self._column_spec])
            hh = self._left_table.horizontalHeader()
            hh.setStretchLastSection(False)
            for col in range(self._left_table.columnCount()):
                hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
            filtered = self._filtered_source_rows() if self._dev_filter_visible else list(self._source_rows)
            self._write_left_data_rows(filtered)
            self._refresh_dev_section_title()
            self._update_section_filter_buttons_enabled()
        except Exception:
            traceback.print_exc()
            self._show_empty_left_table()

    def _write_staging_table_rows(self, data_rows: list[dict[str, Any]]) -> None:
        spec = self._column_spec or list(_API_DEV_REPLICATE_COLUMN_SPEC)
        self._queue_table.setSortingEnabled(False)
        self._queue_table.setColumnCount(1 + len(spec))
        self._queue_table.setHorizontalHeaderLabels([""] + [s[0] for s in spec])
        hh = self._queue_table.horizontalHeader()
        for col in range(self._queue_table.columnCount()):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
        off = self._queue_data_row_offset()
        total = off + len(data_rows)
        if self._queue_filter_visible and total < 1:
            total = 1
        self._queue_table.setRowCount(total)
        if self._queue_filter_visible:
            for c in range(self._queue_table.columnCount()):
                self._queue_table.takeItem(0, c)
            install_filter_row(
                self._queue_table,
                1 + len(spec),
                on_text_changed=self._schedule_queue_filter_apply,
            )
            w0 = self._queue_table.cellWidget(0, 0)
            if w0 is not None:
                self._queue_table.removeCellWidget(0, 0)
            spacer = QWidget()
            spacer.setFixedSize(40, FILTER_ROW_HEIGHT_PX)
            self._queue_table.setCellWidget(0, 0, spacer)
        for r, row in enumerate(data_rows):
            tr = off + r
            self._queue_table.setItem(tr, 0, self._checkbox_item())
            for col, (_, keys) in enumerate(spec):
                value, key_used = _replicate_dev_value_for_column(row, keys)
                item = QTableWidgetItem(_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self._queue_table.setItem(tr, col + 1, item)
        sync_vertical_header_labels(
            self._queue_table,
            filter_visible=self._queue_filter_visible,
            data_row_count=len(data_rows),
        )
        self._resize_staging_columns(data_rows)
        self._queue_table.setSortingEnabled(not self._queue_filter_visible)
        self._refresh_dev_row_blocked_state()

    def _write_staging_table(self) -> None:
        self._refresh_queue_section_title()
        if not self._staging_rows:
            self._queue_table.setSortingEnabled(False)
            clear_filter_row_widgets(self._queue_table)
            self._queue_filter_btn.blockSignals(True)
            self._queue_filter_btn.setChecked(False)
            self._queue_filter_btn.blockSignals(False)
            self._queue_filter_visible = False
            self._queue_table.setRowCount(0)
            self._queue_table.setColumnCount(0)
            self._update_replicate_enabled()
            self._update_section_filter_buttons_enabled()
            self._refresh_dev_row_blocked_state()
            return
        to_show = self._filtered_queue_rows() if self._queue_filter_visible else list(self._staging_rows)
        self._write_staging_table_rows(to_show)
        self._update_replicate_enabled()
        self._update_section_filter_buttons_enabled()

    def _show_empty_mgmt_catalog(self) -> None:
        self._mgmt_rows = []
        self._mgmt_column_spec = []
        self._mgmt_catalog_table.setSortingEnabled(False)
        clear_filter_row_widgets(self._mgmt_catalog_table)
        self._mgmt_filter_btn.blockSignals(True)
        self._mgmt_filter_btn.setChecked(False)
        self._mgmt_filter_btn.blockSignals(False)
        self._mgmt_filter_visible = False
        self._mgmt_catalog_table.setRowCount(0)
        self._mgmt_catalog_table.setColumnCount(0)
        self._refresh_mgmt_section_title()
        self._update_section_filter_buttons_enabled()
        self._refresh_dev_row_blocked_state()

    def _populate_mgmt_catalog(self, rows: list[dict[str, Any]]) -> None:
        try:
            self._mgmt_rows = [dict(r) for r in rows if isinstance(r, dict)]
            self._mgmt_column_spec = list(_API_COLUMN_SPEC)
            if not self._mgmt_rows:
                self._show_empty_mgmt_catalog()
                return
            filtered = self._filtered_mgmt_rows() if self._mgmt_filter_visible else list(self._mgmt_rows)
            self._write_mgmt_data_rows(filtered)
            self._refresh_mgmt_section_title()
            self._update_section_filter_buttons_enabled()
        except Exception:
            traceback.print_exc()
            self._show_empty_mgmt_catalog()

    def _on_staging_context_menu(self, pos: QPoint) -> None:
        item = self._queue_table.itemAt(pos)
        if item is not None:
            self._queue_table.selectRow(item.row())
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        remove_action = menu.addAction("Remove selected")
        remove_action.setEnabled(self._queue_table.currentRow() >= 0)
        clear_action = menu.addAction("Clear all")
        clear_action.setEnabled(bool(self._staging_rows))
        chosen = menu.exec(self._queue_table.mapToGlobal(pos))
        if chosen == remove_action:
            r = self._queue_table.currentRow()
            off = self._queue_data_row_offset()
            if r < off:
                return
            it1 = self._queue_table.item(r, 1)
            raw = it1.data(Qt.ItemDataRole.UserRole) if it1 is not None else None
            rid = _api_catalog_id(raw) if isinstance(raw, dict) else None
            if rid is None:
                return
            self._staging_rows = [x for x in self._staging_rows if _api_catalog_id(x) != rid]
            self._write_staging_table()
        elif chosen == clear_action:
            self._staging_rows.clear()
            self._queue_filter_btn.blockSignals(True)
            self._queue_filter_btn.setChecked(False)
            self._queue_filter_btn.blockSignals(False)
            self._queue_filter_visible = False
            self._write_staging_table()

    def _token(self) -> str | None:
        profile = get_user_profile()
        t = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(t) if t else None

    def refresh(self) -> None:
        if self._loading:
            self._pending_refresh = True
            return
        self._fetch_and_fill_app_combo()
        tok = self._token()
        self._loading = True
        cancel_auto_hide_message(self, self._message_label)
        self._message_label.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        self._message_label.setText("Loading APIs...")
        self._message_label.setVisible(True)
        self._load_thread = QThread(self)
        self._load_worker = _ApisPairLoadWorker(tok)
        self._load_worker.moveToThread(self._load_thread)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.finished.connect(self._on_apis_loaded)
        self._load_worker.finished.connect(self._load_thread.quit)
        self._load_thread.finished.connect(self._cleanup_load_thread)
        self._load_thread.start()

    @Slot()
    def _on_apis_loaded(
        self,
        success: bool,
        dev_rows: object,
        mgmt_rows: object,
        message: str,
    ) -> None:
        self._loading = False
        if not success:
            self._pending_replicate_success_msg = None
            self._show_message(message or "Failed to load API Dev.", error=True)
            self._show_empty_left_table()
            self._show_empty_mgmt_catalog()
            QTimer.singleShot(0, self._equalize_right_split)
        else:
            show_auto_hiding_message(self, self._message_label, "")
            dev = list(dev_rows) if isinstance(dev_rows, list) else []
            self._populate_left([r for r in dev if isinstance(r, dict)])
            mgmt = list(mgmt_rows) if isinstance(mgmt_rows, list) else []
            self._populate_mgmt_catalog([r for r in mgmt if isinstance(r, dict)])
            pending_ok = self._pending_replicate_success_msg
            if pending_ok:
                self._pending_replicate_success_msg = None
                self._show_message(pending_ok, error=False)
            elif message:
                self._show_message(message, error=False)
            QTimer.singleShot(0, self._equalize_right_split)
            QTimer.singleShot(120, self._equalize_right_split)
        if self._pending_refresh:
            self._pending_refresh = False
            self.refresh()

    def _cleanup_load_thread(self) -> None:
        if self._load_worker is not None:
            self._load_worker.deleteLater()
            self._load_worker = None
        if self._load_thread is not None:
            self._load_thread.deleteLater()
            self._load_thread = None

    def _on_replicate_clicked(self) -> None:
        if not self._staging_rows:
            return
        target_app = self._selected_mgmt_app_id()
        if target_app is None:
            self._show_message("Choose App Id (MGMT) before replicating.", error=True)
            return
        id_list: list[Any] = []
        for row in self._staging_rows:
            rid = _api_catalog_id(row)
            if rid is not None:
                id_list.append(rid)
        if not id_list:
            self._show_message("No API ids found in the selected rows.", error=True)
            return
        tok = self._token()
        if not tok:
            self._show_message("Session expired. Please sign in again.", error=True)
            return
        self._replicate_btn.setEnabled(False)
        self._repl_thread = QThread(self)
        self._repl_worker = _ReplicateWorker(token=tok, app_id=target_app, api_detail_ids=id_list)
        self._repl_worker.moveToThread(self._repl_thread)
        self._repl_thread.started.connect(self._repl_worker.run)
        self._repl_worker.finished.connect(self._on_replicate_finished)
        self._repl_worker.finished.connect(self._repl_thread.quit)
        self._repl_thread.finished.connect(self._cleanup_repl_thread)
        self._repl_thread.start()

    @Slot()
    def _on_replicate_finished(self, result: object) -> None:
        if not isinstance(result, dict):
            self._update_replicate_enabled()
            return
        if result.get("success"):
            self._pending_replicate_success_msg = str(result.get("message") or "Replication completed.")
            self._staging_rows.clear()
            self._write_staging_table()
            self.refresh()
        else:
            err = str(result.get("message") or "Replication failed.")
            self._show_message(err, error=True)
        self._update_replicate_enabled()

    def _cleanup_repl_thread(self) -> None:
        if self._repl_worker is not None:
            self._repl_worker.deleteLater()
            self._repl_worker = None
        if self._repl_thread is not None:
            self._repl_thread.deleteLater()
            self._repl_thread = None

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._reset_replicate_page_for_reload()
        self.refresh()
        QTimer.singleShot(0, self._equalize_right_split)
        QTimer.singleShot(100, self._equalize_right_split)
