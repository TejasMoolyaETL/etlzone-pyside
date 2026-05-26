"""Role-API Assignment page: left all APIs, right APIs assigned to selected role."""

from __future__ import annotations

import json
import traceback
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QShowEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QRadioButton,
    QScrollArea,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.api import (
    api_change_status_multiple_api_by_role_id,
    api_get_all_apis,
    api_get_all_roles,
    api_get_api_access_by_role_id,
    api_grant_multiple_api_access,
    api_remove_multiple_api_by_role_id,
)
from core.app_preferences import format_datetime_display, is_datetime_field
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.blank_display import is_blank_display_value
from ui.data_table import (
    MIN_DATA_COL_WIDTH_PX,
    apply_data_table_appearance,
    attach_table_copy_shortcut,
    clear_filter_row_widgets,
    data_row_offset,
    filter_dict_rows_by_column_edits,
    install_filter_row,
    resize_data_table_columns_to_content,
    sync_vertical_header_labels,
)
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    MODAL_FIELD_HEIGHT_PX,
    MODAL_FIELD_LABEL_STYLE,
)
from ui.theme import Theme

_HIDDEN_KEYS = frozenset({"password", "token", "accessToken", "access_token", "jwt"})

_API_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("API Id", ("apiId", "api_id", "id")),
    ("Name", ("apiName", "api_name", "name", "title")),
    ("Method", ("httpMethod", "http_method", "method", "verb")),
    ("Endpoint", ("apiEndpoint", "api_endpoint", "endpoint", "path", "urlPath", "url_path", "url", "uri")),
    ("App Id", ("appId", "app_id", "appIdVal", "app_id_val")),
    ("App Desc", ("appDesc", "app_desc", "appDescription", "app_description", "description", "desc")),
    ("Created By", ("createdBy", "created_by")),
    ("Created At", ("createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified At", ("modifiedAt", "modified_at", "updatedAt", "updated_at")),
)

_ROLE_API_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("API Id", ("apiId", "api_id")),
    ("API Assign Id", ("apiAssignId", "api_assign_id", "assignId", "assign_id")),
    ("API Name", ("apiName", "api_name", "name", "title")),
    (
        "API Endpoint",
        (
            "apiEndPoint",
            "apiEndpoint",
            "api_endpoint",
            "endpoint",
            "path",
            "urlPath",
            "url_path",
            "url",
            "uri",
        ),
    ),
    ("Status", ("status",)),
)


def _normalize_role_api_row(row: dict[str, Any]) -> dict[str, Any]:
    """Copy nested API id onto top level when missing so the API Id column can resolve."""
    out = dict(row)
    for k in ("apiId", "api_id"):
        v = out.get(k)
        if v is not None and str(v).strip() != "":
            return out
    for nest_key in ("api", "apiDetail", "apiDetails", "detail", "apiInfo"):
        sub = out.get(nest_key)
        if not isinstance(sub, dict):
            continue
        for k in ("apiId", "api_id", "id"):
            v = sub.get(k)
            if v is not None and str(v).strip() != "":
                out.setdefault("apiId", v)
                return out
    return out


def _flatten_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k not in _HIDDEN_KEYS}


def _value_for_column(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    flat = _flatten_row(row)
    for key in keys:
        if key in flat:
            return (flat[key], key)
    return (None, keys[0] if keys else "")


def _format_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


class _LoadWorker(QObject):
    finished = Signal(bool, object, object, str)

    def __init__(self, token: str | None) -> None:
        super().__init__()
        self._token = token

    @Slot()
    def run(self) -> None:
        roles_result = api_get_all_roles(token=self._token)
        if not roles_result.get("success"):
            self.finished.emit(False, [], [], str(roles_result.get("message", "Failed to load roles.")))
            return
        apis_result = api_get_all_apis(token=self._token)
        if not apis_result.get("success"):
            self.finished.emit(False, [], [], str(apis_result.get("message", "Failed to load APIs.")))
            return
        roles = [r for r in (roles_result.get("data") or []) if isinstance(r, dict)]
        apis = [a for a in (apis_result.get("data") or []) if isinstance(a, dict)]
        self.finished.emit(True, roles, apis, "")


class _RoleApiAccessStatusDialog(QDialog):
    """Modal: choose ACTIVE or INACTIVE for change-status-multiple-api-by-role-id."""

    def __init__(self, parent: QWidget | None, *, count: int) -> None:
        super().__init__(parent)
        self.setWindowTitle("ACTIVE / INACTIVE")
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setStyleSheet("QDialog { background: #ffffff; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        intro = QLabel(f"Choose status for {count} selected API(s) for this role:")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._radio_active = QRadioButton("ACTIVE")
        self._radio_inactive = QRadioButton("INACTIVE")
        self._radio_active.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self._radio_active)
        grp.addButton(self._radio_inactive)
        layout.addWidget(self._radio_active)
        layout.addWidget(self._radio_inactive)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        submit = QPushButton("Submit")
        submit.setFixedWidth(100)
        submit.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        submit.setCursor(Qt.CursorShape.PointingHandCursor)
        submit.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.setFixedWidth(100)
        cancel.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(submit)
        btn_row.addWidget(cancel)
        layout.addLayout(btn_row)

    def selected_status(self) -> str:
        """Return API status: ACTIVE or INACTIVE."""
        if self._radio_inactive.isChecked():
            return "INACTIVE"
        return "ACTIVE"


class RoleApiAssignmentPage(QWidget):
    """Role-driven assignment view. Does not change API: API-Role Assignment behavior."""

    def __init__(self) -> None:
        super().__init__()
        self._loading = False
        self._pending_refresh = False
        self._roles: list[dict[str, Any]] = []
        self._apis: list[dict[str, Any]] = []
        self._load_thread: QThread | None = None
        self._load_worker: _LoadWorker | None = None
        self._api_column_spec: list[tuple[str, tuple[str, ...]]] = []
        self._filter_visible = False
        self._left_assignment_filter_mode = "all"
        self._role_filter_visible = False
        self._current_role_id: Any = None
        self._left_checkbox_col = 0
        self._right_checkbox_col = 0
        self._assigned_api_keys_for_role: set[tuple[str, str]] = set()
        self._role_api_rows: list[dict[str, Any]] = []
        self._filter_apply_timer = QTimer(self)
        self._filter_apply_timer.setSingleShot(True)
        self._filter_apply_timer.setInterval(200)
        self._filter_apply_timer.timeout.connect(self._apply_api_column_filters_refresh)
        self._role_filter_apply_timer = QTimer(self)
        self._role_filter_apply_timer.setSingleShot(True)
        self._role_filter_apply_timer.setInterval(200)
        self._role_filter_apply_timer.timeout.connect(self._apply_role_api_column_filters_refresh)
        self._build_ui()

    def _lhs_api_identity(self, row: dict[str, Any]) -> tuple[str, str]:
        name = str(row.get("apiName") or row.get("api_name") or row.get("name") or "").strip().lower()
        endpoint = str(
            row.get("apiEndpoint")
            or row.get("api_endpoint")
            or row.get("endpoint")
            or row.get("path")
            or ""
        ).strip().lower()
        return (name, endpoint)

    def _rhs_api_identity(self, row: dict[str, Any]) -> tuple[str, str]:
        name = str(row.get("apiName") or row.get("api_name") or row.get("name") or "").strip().lower()
        endpoint = str(
            row.get("apiEndPoint")
            or row.get("apiEndpoint")
            or row.get("api_endpoint")
            or row.get("endpoint")
            or row.get("path")
            or ""
        ).strip().lower()
        return (name, endpoint)

    def _api_id_from_role_api_row(self, row: dict[str, Any]) -> Any:
        """Resolve API id for remove/grant; role-API payloads often omit flat apiId."""
        for key in ("apiId", "api_id", "apiID"):
            v = row.get(key)
            if v is not None and str(v).strip() != "":
                return v
        for nest_key in ("api", "apiDetail", "apiDetails", "detail", "apiInfo"):
            sub = row.get(nest_key)
            if isinstance(sub, dict):
                for key in ("apiId", "api_id", "apiID", "id"):
                    v = sub.get(key)
                    if v is not None and str(v).strip() != "":
                        return v
        v = row.get("id")
        if v is not None and str(v).strip() != "":
            return v
        ident = self._rhs_api_identity(row)
        if ident != ("", ""):
            for api_row in self._apis:
                if self._lhs_api_identity(api_row) == ident:
                    return (
                        api_row.get("apiId")
                        or api_row.get("api_id")
                        or api_row.get("id")
                    )
        return None

    def _assign_id_from_role_api_row(self, row: dict[str, Any]) -> Any:
        return (
            row.get("apiAssignId")
            or row.get("api_assign_id")
            or row.get("assignId")
            or row.get("assign_id")
        )

    def _style_assigned_lhs_row(self, table_row: int) -> None:
        """Muted row styling for APIs already assigned to the selected role."""
        fg = QBrush(QColor(Theme.TEXT_SECONDARY))
        bg = QBrush(QColor(Theme.BG_ACTIVITY))
        for col in range(self.table.columnCount()):
            it = self.table.item(table_row, col)
            if it is None:
                continue
            it.setForeground(fg)
            it.setBackground(bg)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        header_layout.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        title = QLabel("API: Role-API Assignment")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self._filter_btn = QPushButton("Filters")
        self._filter_btn.setCheckable(True)
        self._filter_btn.setChecked(False)
        self._filter_btn.setFixedWidth(100)
        self._filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_btn.toggled.connect(self._on_api_filter_toggled)
        header_layout.addWidget(self._filter_btn)

        self._assigned_only_btn = QPushButton("Assigned Only")
        self._assigned_only_btn.setCheckable(True)
        self._assigned_only_btn.setChecked(False)
        self._assigned_only_btn.setFixedWidth(120)
        self._assigned_only_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._assigned_only_btn.setEnabled(False)
        self._assigned_only_btn.toggled.connect(self._on_assigned_only_toggled)
        header_layout.addWidget(self._assigned_only_btn)

        self._unassigned_only_btn = QPushButton("Unassigned Only")
        self._unassigned_only_btn.setCheckable(True)
        self._unassigned_only_btn.setChecked(False)
        self._unassigned_only_btn.setFixedWidth(128)
        self._unassigned_only_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._unassigned_only_btn.setEnabled(False)
        self._unassigned_only_btn.toggled.connect(self._on_unassigned_only_toggled)
        header_layout.addWidget(self._unassigned_only_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        header_layout.addWidget(refresh_btn)
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )

        content = QWidget()
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setVisible(False)
        content_layout.addWidget(self.message_label)

        self.table = QTableWidget()
        apply_data_table_appearance(self.table)
        # Only style disabled checkboxes (already-assigned rows); enabled uses default Fusion.
        self.table.setStyleSheet(
            self.table.styleSheet()
            + (
                f"QTableWidget::indicator:unchecked:disabled {{ background: {Theme.BG_PAGE_ALT}; "
                f"border: 1px solid {Theme.BORDER_INPUT}; border-radius: 2px; }}"
                f"QTableWidget::indicator:checked:disabled {{ background: {Theme.BG_PAGE_ALT}; "
                f"border: 1px solid {Theme.BORDER_INPUT}; border-radius: 2px; }}"
            )
        )
        self.table.setSortingEnabled(False)
        self.table.setMinimumWidth(620)
        self.table.itemChanged.connect(self._on_left_table_item_changed)
        attach_table_copy_shortcut(self.table)

        right_panel = QWidget()
        right_panel.setMinimumWidth(340)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._role_combo = QComboBox()
        apply_form_combobox_field(self._role_combo, height_px=MODAL_FIELD_HEIGHT_PX, min_width=180)
        self._role_combo.setFixedWidth(220)
        self._role_combo.currentIndexChanged.connect(self._on_role_changed)

        self._assign_selected_btn = QPushButton("Assign")
        self._assign_selected_btn.setFixedWidth(88)
        self._assign_selected_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._assign_selected_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._assign_selected_btn.setEnabled(False)
        self._assign_selected_btn.clicked.connect(self._assign_selected_apis_to_role)

        self._remove_assign_btn = QPushButton("Remove")
        self._remove_assign_btn.setFixedWidth(88)
        self._remove_assign_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._remove_assign_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove_assign_btn.setEnabled(False)
        self._remove_assign_btn.clicked.connect(self._remove_selected_assignments)

        self._deactivate_assign_btn = QPushButton("ACTIVE/INACTIVE")
        self._deactivate_assign_btn.setFixedWidth(130)
        self._deactivate_assign_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._deactivate_assign_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._deactivate_assign_btn.setEnabled(False)
        self._deactivate_assign_btn.clicked.connect(self._deactivate_selected_assignments)

        self._role_filter_btn = QPushButton("Filters")
        self._role_filter_btn.setCheckable(True)
        self._role_filter_btn.setChecked(False)
        self._role_filter_btn.setFixedWidth(88)
        self._role_filter_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._role_filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._role_filter_btn.setEnabled(False)
        self._role_filter_btn.toggled.connect(self._on_role_filter_toggled)

        role_top_row = QWidget()
        role_top_row_lay = QHBoxLayout(role_top_row)
        role_top_row_lay.setContentsMargins(0, 0, 0, 0)
        role_top_row_lay.setSpacing(8)
        role_top_row_lay.addWidget(self._role_combo)
        role_top_row_lay.addWidget(self._role_filter_btn)
        role_top_row_lay.addStretch(1)
        right_layout.addSpacing(8)
        right_layout.addWidget(role_top_row)

        self._role_apis_table = QTableWidget()
        apply_data_table_appearance(self._role_apis_table)
        cols = list(_ROLE_API_COLUMNS)
        self._role_apis_table.setColumnCount(len(cols))
        self._role_apis_table.setHorizontalHeaderLabels([h for h, _ in cols])
        hh = self._role_apis_table.horizontalHeader()
        hh.setStretchLastSection(False)
        for col in range(len(cols)):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
        self._role_apis_table.setSortingEnabled(True)
        attach_table_copy_shortcut(self._role_apis_table)
        self._role_apis_table.itemChanged.connect(self._on_right_table_item_changed)
        self._role_apis_table.itemClicked.connect(self._on_right_table_item_clicked)
        right_layout.addWidget(self._role_apis_table, 1)

        role_bottom_btn_row = QWidget()
        role_bottom_btn_row.setStyleSheet("margin-bottom: 6px;")
        role_bottom_btn_lay = QHBoxLayout(role_bottom_btn_row)
        role_bottom_btn_lay.setContentsMargins(0, 0, 0, 0)
        role_bottom_btn_lay.setSpacing(8)
        role_bottom_btn_lay.addWidget(self._assign_selected_btn)
        role_bottom_btn_lay.addWidget(self._remove_assign_btn)
        role_bottom_btn_lay.addWidget(self._deactivate_assign_btn)
        role_bottom_btn_lay.addStretch(1)
        right_layout.addWidget(role_bottom_btn_row)

        self._roles_msg = QLabel("")
        self._roles_msg.setWordWrap(True)
        self._roles_msg.setVisible(False)
        self._roles_msg.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        right_layout.addWidget(self._roles_msg)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(6)
        split.addWidget(self.table)
        split.addWidget(right_panel)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([650, 430])
        content_layout.addWidget(split, 1)
        self._update_assign_button_state()

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

    def _get_token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _clear_roles_feedback(self) -> None:
        self._roles_msg.clear()
        self._roles_msg.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        self._roles_msg.setVisible(False)

    def _set_roles_feedback(self, text: str, *, error: bool = False) -> None:
        self._roles_msg.setStyleSheet(FORM_ERROR_LABEL_STYLE if error else MODAL_FIELD_LABEL_STYLE)
        self._roles_msg.setText(text)
        self._roles_msg.setVisible(True)

    def _api_data_row_offset(self) -> int:
        return data_row_offset(self._filter_visible)

    def _schedule_api_filter_apply(self) -> None:
        if self._filter_visible:
            self._filter_apply_timer.start()

    def _filtered_api_source_rows(self) -> list[dict[str, Any]]:
        source_rows = list(self._apis)
        if self._left_assignment_filter_mode == "assigned" and self._current_role_id is not None:
            source_rows = [
                row for row in source_rows
                if self._lhs_api_identity(row) in self._assigned_api_keys_for_role
            ]
        elif self._left_assignment_filter_mode == "unassigned" and self._current_role_id is not None:
            source_rows = [
                row for row in source_rows
                if self._lhs_api_identity(row) not in self._assigned_api_keys_for_role
            ]
        if not self._filter_visible or not self._api_column_spec:
            return source_rows
        filtered_rows = list(source_rows)
        col_offset = 1 if self._current_role_id is not None else 0
        for col, (_, keys) in enumerate(self._api_column_spec):
            w = self.table.cellWidget(0, col + col_offset)
            if w is None:
                continue
            q = str(getattr(w, "text", lambda: "")()).strip().lower()
            if not q:
                continue
            filtered_rows = [
                r
                for r in filtered_rows
                if q in _format_cell(*_value_for_column(r, keys), keys).lower()
            ]
        return filtered_rows

    def _write_api_data_rows(self, data_rows: list[dict[str, Any]]) -> None:
        off = self._api_data_row_offset()
        self.table.setSortingEnabled(False)
        total = off + len(data_rows)
        if self._filter_visible and total < 1:
            total = 1
        self.table.setRowCount(total)
        if self._filter_visible:
            for c in range(self.table.columnCount()):
                self.table.takeItem(0, c)
            install_filter_row(self.table, self.table.columnCount(), on_text_changed=self._schedule_api_filter_apply)
            if self._current_role_id is not None:
                self.table.removeCellWidget(0, self._left_checkbox_col)
        for r, row in enumerate(data_rows):
            tr = off + r
            is_assigned_for_role = (
                self._current_role_id is not None
                and self._lhs_api_identity(row) in self._assigned_api_keys_for_role
            )
            if self._current_role_id is not None:
                check_item = QTableWidgetItem("")
                check_flags = Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable
                if not is_assigned_for_role:
                    check_flags |= Qt.ItemFlag.ItemIsEnabled
                check_item.setFlags(check_flags)
                check_item.setCheckState(Qt.CheckState.Unchecked)
                check_item.setData(Qt.ItemDataRole.UserRole, row)
                if is_assigned_for_role:
                    check_item.setData(Qt.ItemDataRole.ToolTipRole, "Already assigned to selected role.")
                self.table.setItem(tr, self._left_checkbox_col, check_item)
            for col_idx, (_, keys) in enumerate(self._api_column_spec):
                value, key_used = _value_for_column(row, keys)
                item = QTableWidgetItem(_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if is_assigned_for_role:
                    item.setFlags((item.flags() & ~Qt.ItemFlag.ItemIsEditable) & ~Qt.ItemFlag.ItemIsEnabled)
                    item.setData(Qt.ItemDataRole.ToolTipRole, "Already assigned to selected role.")
                item.setData(Qt.ItemDataRole.UserRole, row)
                target_col = col_idx + 1 if self._current_role_id is not None else col_idx
                self.table.setItem(tr, target_col, item)
            if is_assigned_for_role:
                self._style_assigned_lhs_row(tr)
        sync_vertical_header_labels(self.table, filter_visible=self._filter_visible, data_row_count=len(data_rows))
        if self._current_role_id is None:
            spec_for_resize: list[tuple[str, tuple[str, ...]]] = list(self._api_column_spec)
        else:
            spec_for_resize = [("Select", ("__select__",)), *self._api_column_spec]
        resize_data_table_columns_to_content(
            self.table,
            spec_for_resize,
            self._apis,
            _value_for_column,
            _format_cell,
        )
        self.table.setSortingEnabled(not self._filter_visible)

    def _apply_api_column_filters_refresh(self) -> None:
        if not self._filter_visible or not self._api_column_spec or not self._apis:
            return
        try:
            self._write_api_data_rows(self._filtered_api_source_rows())
        except Exception:
            traceback.print_exc()

    def _role_api_data_row_offset(self) -> int:
        return data_row_offset(self._role_filter_visible)

    def _schedule_role_api_filter_apply(self) -> None:
        if self._role_filter_visible:
            self._role_filter_apply_timer.start()

    def _filtered_role_api_rows(self) -> list[dict[str, Any]]:
        role_col_spec = [("Select", ("__select__",)), *list(_ROLE_API_COLUMNS)]
        return filter_dict_rows_by_column_edits(
            self._role_api_rows,
            self._role_apis_table,
            role_col_spec,
            self._role_filter_visible,
            _value_for_column,
            _format_cell,
        )

    def _write_role_api_rows(self, rows: list[dict[str, Any]]) -> None:
        cols = list(_ROLE_API_COLUMNS)
        off = self._role_api_data_row_offset()
        self._role_apis_table.blockSignals(True)
        self._role_apis_table.setSortingEnabled(False)
        self._role_apis_table.setColumnCount(1 + len(cols))
        self._role_apis_table.setHorizontalHeaderLabels(["Select"] + [h for h, _ in cols])
        r_hh = self._role_apis_table.horizontalHeader()
        r_hh.setStretchLastSection(False)
        for col in range(1 + len(cols)):
            r_hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        r_hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
        total = off + len(rows)
        if self._role_filter_visible and total < 1:
            total = 1
        self._role_apis_table.setRowCount(total)
        if self._role_filter_visible:
            for c in range(self._role_apis_table.columnCount()):
                self._role_apis_table.takeItem(0, c)
            install_filter_row(
                self._role_apis_table,
                self._role_apis_table.columnCount(),
                on_text_changed=self._schedule_role_api_filter_apply,
            )
        for r_idx, row in enumerate(rows):
            tr = off + r_idx
            check_item = QTableWidgetItem("")
            check_item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEnabled
            )
            check_item.setCheckState(Qt.CheckState.Unchecked)
            check_item.setData(Qt.ItemDataRole.UserRole, row)
            self._role_apis_table.setItem(tr, self._right_checkbox_col, check_item)
            for c_idx, (_, keys) in enumerate(cols):
                val, key_used = _value_for_column(row, keys)
                item = QTableWidgetItem(_format_cell(val, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self._role_apis_table.setItem(tr, c_idx + 1, item)
        sync_vertical_header_labels(
            self._role_apis_table,
            filter_visible=self._role_filter_visible,
            data_row_count=len(rows),
        )
        spec_resize = [("Select", ("__select__",)), *cols]
        resize_data_table_columns_to_content(
            self._role_apis_table,
            spec_resize,
            self._role_api_rows,
            _value_for_column,
            _format_cell,
        )
        self._role_apis_table.setSortingEnabled(not self._role_filter_visible)
        self._role_apis_table.blockSignals(False)
        self._update_assign_button_state()

    def _apply_role_api_column_filters_refresh(self) -> None:
        if not self._role_filter_visible or not self._role_api_rows:
            return
        self._write_role_api_rows(self._filtered_role_api_rows())

    def _on_role_filter_toggled(self, checked: bool) -> None:
        self._role_filter_visible = checked
        if not checked:
            self._role_filter_apply_timer.stop()
            clear_filter_row_widgets(self._role_apis_table)
        if self._current_role_id is None:
            return
        self._write_role_api_rows(
            self._filtered_role_api_rows() if checked else list(self._role_api_rows)
        )

    def _on_api_filter_toggled(self, checked: bool) -> None:
        self._filter_visible = checked
        if not checked:
            self._filter_apply_timer.stop()
            clear_filter_row_widgets(self.table)
        if self._api_column_spec and self._apis:
            self._write_api_data_rows(self._filtered_api_source_rows())

    def _on_assigned_only_toggled(self, checked: bool) -> None:
        if checked and self._unassigned_only_btn.isChecked():
            self._unassigned_only_btn.blockSignals(True)
            self._unassigned_only_btn.setChecked(False)
            self._unassigned_only_btn.blockSignals(False)
        self._left_assignment_filter_mode = "assigned" if checked else "all"
        if self._unassigned_only_btn.isChecked():
            self._left_assignment_filter_mode = "unassigned"
        if self._left_assignment_filter_mode == "all":
            self._assigned_only_btn.blockSignals(True)
            self._assigned_only_btn.setChecked(False)
            self._assigned_only_btn.blockSignals(False)
        if self._api_column_spec and self._apis:
            self._write_api_data_rows(self._filtered_api_source_rows())

    def _on_unassigned_only_toggled(self, checked: bool) -> None:
        if checked and self._assigned_only_btn.isChecked():
            self._assigned_only_btn.blockSignals(True)
            self._assigned_only_btn.setChecked(False)
            self._assigned_only_btn.blockSignals(False)
        self._left_assignment_filter_mode = "unassigned" if checked else "all"
        if self._assigned_only_btn.isChecked():
            self._left_assignment_filter_mode = "assigned"
        if self._left_assignment_filter_mode == "all":
            self._unassigned_only_btn.blockSignals(True)
            self._unassigned_only_btn.setChecked(False)
            self._unassigned_only_btn.blockSignals(False)
        if self._api_column_spec and self._apis:
            self._write_api_data_rows(self._filtered_api_source_rows())

    def _populate_left_table(self, rows: list[dict[str, Any]]) -> None:
        self._apis = [dict(r) for r in rows if isinstance(r, dict)]
        if not self._apis:
            self._api_column_spec = []
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return
        self._api_column_spec = list(_API_COLUMNS)
        self.table.setSortingEnabled(False)
        if self._current_role_id is not None:
            self.table.setColumnCount(len(self._api_column_spec) + 1)
            self.table.setHorizontalHeaderLabels(["Select"] + [col for col, _ in self._api_column_spec])
        else:
            self.table.setColumnCount(len(self._api_column_spec))
            self.table.setHorizontalHeaderLabels([col for col, _ in self._api_column_spec])
        hh = self.table.horizontalHeader()
        hh.setStretchLastSection(False)
        for col in range(self.table.columnCount()):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
        self._write_api_data_rows(self._filtered_api_source_rows())

    def _populate_roles(self, roles: list[dict[str, Any]]) -> None:
        self._roles = [dict(r) for r in roles if isinstance(r, dict)]
        self._role_combo.blockSignals(True)
        self._role_combo.clear()
        self._role_combo.addItem("Select Role")
        for row in self._roles:
            rid = row.get("roleId") or row.get("role_id") or row.get("id")
            if rid is None:
                continue
            name = str(row.get("roleName") or row.get("role_name") or row.get("name") or "").strip()
            label = f"{rid} | {name}" if name else str(rid)
            self._role_combo.addItem(label, rid)
        self._role_combo.blockSignals(False)
        self._role_combo.setCurrentIndex(0)
        self._current_role_id = None
        # Refresh may repopulate roles without emitting indexChanged(0->0),
        # so reset both filter toggles explicitly here.
        self._filter_btn.setChecked(False)
        self._filter_btn.setEnabled(True)
        self._left_assignment_filter_mode = "all"
        self._assigned_only_btn.setChecked(False)
        self._assigned_only_btn.setEnabled(False)
        self._unassigned_only_btn.setChecked(False)
        self._unassigned_only_btn.setEnabled(False)
        self._role_filter_btn.setChecked(False)
        self._role_filter_btn.setEnabled(False)
        self._role_apis_table.setRowCount(0)
        self._reset_role_apis_table_columns_plain()
        self._clear_roles_feedback()

    def _reset_role_apis_table_columns_plain(self) -> None:
        """Assignments table without checkbox column (no role / empty / error)."""
        cols = list(_ROLE_API_COLUMNS)
        self._role_apis_table.setColumnCount(len(cols))
        self._role_apis_table.setHorizontalHeaderLabels([h for h, _ in cols])
        hh = self._role_apis_table.horizontalHeader()
        hh.setStretchLastSection(False)
        for col in range(len(cols)):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)

    def _on_role_changed(self, index: int) -> None:
        if index <= 0:
            self._current_role_id = None
            self._assigned_api_keys_for_role.clear()
            self._role_api_rows = []
            self._left_assignment_filter_mode = "all"
            self._assigned_only_btn.setChecked(False)
            self._assigned_only_btn.setEnabled(False)
            self._unassigned_only_btn.setChecked(False)
            self._unassigned_only_btn.setEnabled(False)
            self._role_filter_btn.setChecked(False)
            self._role_filter_btn.setEnabled(False)
            self._role_apis_table.setRowCount(0)
            self._reset_role_apis_table_columns_plain()
            self._clear_roles_feedback()
            self._filter_btn.setEnabled(True)
            self._populate_left_table(self._apis)
            self._update_assign_button_state()
            return
        self._current_role_id = self._role_combo.currentData()
        self._left_assignment_filter_mode = "all"
        self._assigned_only_btn.setChecked(False)
        self._assigned_only_btn.setEnabled(True)
        self._unassigned_only_btn.setChecked(False)
        self._unassigned_only_btn.setEnabled(True)
        self._role_filter_btn.setEnabled(True)
        self._filter_btn.setEnabled(True)
        self._populate_left_table(self._apis)
        self._update_assign_button_state()
        self._load_role_apis()

    def _selected_left_api_ids(self) -> list[Any]:
        if self._current_role_id is None:
            return []
        out: list[Any] = []
        off = self._api_data_row_offset()
        for row in range(off, self.table.rowCount()):
            item = self.table.item(row, self._left_checkbox_col)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(data, dict):
                continue
            api_id = data.get("apiId") or data.get("api_id") or data.get("id")
            if api_id is not None:
                out.append(api_id)
        return out

    def _on_left_table_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == self._left_checkbox_col:
            self._update_assign_button_state()

    def _checked_assignment_ids_for_role_remove(self) -> list[Any]:
        out: list[Any] = []
        if self._current_role_id is None:
            return out
        if self._role_apis_table.columnCount() <= self._right_checkbox_col:
            return out
        off = self._role_api_data_row_offset()
        for row in range(off, self._role_apis_table.rowCount()):
            item = self._role_apis_table.item(row, self._right_checkbox_col)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(data, dict):
                continue
            aid = self._assign_id_from_role_api_row(data)
            if aid is not None and str(aid).strip() != "":
                out.append(aid)
        return list(dict.fromkeys(out))

    def _checked_api_ids_for_role_deactivate(self) -> list[Any]:
        out: list[Any] = []
        if self._current_role_id is None:
            return out
        if self._role_apis_table.columnCount() <= self._right_checkbox_col:
            return out
        off = self._role_api_data_row_offset()
        for row in range(off, self._role_apis_table.rowCount()):
            item = self._role_apis_table.item(row, self._right_checkbox_col)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(data, dict):
                continue
            api_id = self._api_id_from_role_api_row(data)
            if api_id is not None and str(api_id).strip() != "":
                out.append(api_id)
        return list(dict.fromkeys(out))

    def _on_right_table_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == self._right_checkbox_col:
            self._update_assign_button_state()

    def _on_right_table_item_clicked(self, _item: QTableWidgetItem) -> None:
        self._update_assign_button_state()

    def _update_assign_button_state(self) -> None:
        can_assign = self._current_role_id is not None and bool(self._selected_left_api_ids())
        self._assign_selected_btn.setEnabled(can_assign)
        self._assign_selected_btn.setCursor(
            Qt.CursorShape.PointingHandCursor if can_assign else Qt.CursorShape.ArrowCursor
        )
        can_remove = self._current_role_id is not None and bool(
            self._checked_assignment_ids_for_role_remove()
        )
        self._remove_assign_btn.setEnabled(can_remove)
        self._remove_assign_btn.setCursor(
            Qt.CursorShape.PointingHandCursor if can_remove else Qt.CursorShape.ArrowCursor
        )
        can_deactivate = self._current_role_id is not None and bool(
            self._checked_api_ids_for_role_deactivate()
        )
        self._deactivate_assign_btn.setEnabled(can_deactivate)
        self._deactivate_assign_btn.setCursor(
            Qt.CursorShape.PointingHandCursor if can_deactivate else Qt.CursorShape.ArrowCursor
        )

    def _remove_selected_assignments(self) -> None:
        if self._current_role_id is None:
            self._set_roles_feedback("Select a role first.", error=True)
            return
        assignment_ids = self._checked_assignment_ids_for_role_remove()
        if not assignment_ids:
            self._set_roles_feedback(
                "Check one or more rows with an API Assign Id to remove.",
                error=True,
            )
            return
        token = self._get_token()
        if not token:
            self._set_roles_feedback("Session expired. Please log in again.", error=True)
            return
        n = len(assignment_ids)
        reply = QMessageBox.question(
            self,
            "Remove APIs",
            f"Remove {n} API assignment(s) from this role?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = api_remove_multiple_api_by_role_id(
            role_id=self._current_role_id,
            assignment_ids=assignment_ids,
            token=token,
        )
        if not result.get("success"):
            self._set_roles_feedback(
                str(result.get("message") or "Failed to remove APIs from role."),
                error=True,
            )
            self._load_role_apis()
            return
        self._set_roles_feedback(str(result.get("message") or "API(s) removed from role."), error=False)
        self._load_role_apis()

    def _deactivate_selected_assignments(self) -> None:
        if self._current_role_id is None:
            self._set_roles_feedback("Select a role first.", error=True)
            return
        api_ids = self._checked_api_ids_for_role_deactivate()
        if not api_ids:
            self._set_roles_feedback(
                "Check one or more rows with a resolvable API id to change status.",
                error=True,
            )
            return
        token = self._get_token()
        if not token:
            self._set_roles_feedback("Session expired. Please log in again.", error=True)
            return
        dlg = _RoleApiAccessStatusDialog(self, count=len(api_ids))
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        status = dlg.selected_status()
        result = api_change_status_multiple_api_by_role_id(
            role_id=self._current_role_id,
            api_ids=api_ids,
            status=status,
            token=token,
        )
        if not result.get("success"):
            self._set_roles_feedback(
                str(result.get("message") or "Failed to update API access status for role."),
                error=True,
            )
            self._load_role_apis()
            return
        self._set_roles_feedback(
            str(result.get("message") or "API access status updated."),
            error=False,
        )
        self._load_role_apis()

    def _assign_selected_apis_to_role(self) -> None:
        if self._current_role_id is None:
            self._set_roles_feedback("Select a role first.", error=True)
            return
        selected_api_ids = self._selected_left_api_ids()
        if not selected_api_ids:
            self._set_roles_feedback("Select at least one API on the left table.", error=True)
            return
        token = self._get_token()
        if not token:
            self._set_roles_feedback("Session expired. Please log in again.", error=True)
            return
        result = api_grant_multiple_api_access(
            role_id=self._current_role_id,
            api_ids=selected_api_ids,
            token=token,
        )
        if not result.get("success"):
            self._set_roles_feedback(str(result.get("message") or "Failed to assign APIs."), error=True)
            return
        self._set_roles_feedback(str(result.get("message") or "APIs assigned successfully."), error=False)
        self._load_role_apis()

    def _load_role_apis(self) -> None:
        if self._current_role_id is None:
            return
        self._set_roles_feedback("Loading role APIs...", error=False)
        self._role_api_rows = []
        self._reset_role_apis_table_columns_plain()
        self._role_apis_table.setSortingEnabled(False)
        self._role_apis_table.setRowCount(0)
        result = api_get_api_access_by_role_id(self._current_role_id, token=self._get_token())
        if not result.get("success"):
            self._set_roles_feedback(
                str(result.get("message") or "Failed to load role APIs."),
                error=True,
            )
            self._update_assign_button_state()
            return
        rows = [r for r in (result.get("data") or []) if isinstance(r, dict)]
        if not rows:
            self._assigned_api_keys_for_role.clear()
            self._set_roles_feedback("No APIs assigned to selected role.", error=False)
            self._role_apis_table.setSortingEnabled(True)
            self._populate_left_table(self._apis)
            self._update_assign_button_state()
            return
        self._assigned_api_keys_for_role = {
            self._rhs_api_identity(r) for r in rows if isinstance(r, dict)
        }
        self._role_api_rows = [_normalize_role_api_row(dict(r)) for r in rows if isinstance(r, dict)]
        self._populate_left_table(self._apis)
        self._clear_roles_feedback()
        self._write_role_api_rows(
            self._filtered_role_api_rows()
            if self._role_filter_visible
            else list(self._role_api_rows)
        )
        self._update_assign_button_state()

    def refresh(self) -> None:
        if self._loading:
            self._pending_refresh = True
            return
        self._loading = True
        cancel_auto_hide_message(self, self.message_label)
        self.message_label.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        self.message_label.setText("Loading roles and APIs...")
        self.message_label.setVisible(True)
        self._load_thread = QThread(self)
        self._load_worker = _LoadWorker(self._get_token())
        self._load_worker.moveToThread(self._load_thread)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.finished.connect(self._on_loaded)
        self._load_worker.finished.connect(self._load_thread.quit)
        self._load_thread.finished.connect(self._cleanup_loader)
        self._load_thread.start()

    @Slot()
    def _on_loaded(self, success: bool, roles_obj: object, apis_obj: object, message: str) -> None:
        self._loading = False
        if not success:
            show_auto_hiding_message(self, self.message_label, message or "Failed to load data.", error=True)
            self._populate_roles([])
            self._populate_left_table([])
        else:
            roles = list(roles_obj) if isinstance(roles_obj, list) else []
            apis = list(apis_obj) if isinstance(apis_obj, list) else []
            self._populate_roles(roles)
            self._populate_left_table(apis)
            show_auto_hiding_message(self, self.message_label, "")
        if self._pending_refresh:
            self._pending_refresh = False
            self.refresh()

    def _cleanup_loader(self) -> None:
        if self._load_worker is not None:
            self._load_worker.deleteLater()
            self._load_worker = None
        if self._load_thread is not None:
            self._load_thread.deleteLater()
            self._load_thread = None

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh()
