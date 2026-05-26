"""DM User Project Mapping: left all users, right users assigned to selected project."""

from __future__ import annotations

import json
import traceback
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QHideEvent, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
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
    api_assign_dm_users_to_project,
    api_change_dm_user_project_status_by_ids,
    api_delete_dm_user_projects_by_ids,
    api_get_all_dm_projects,
    api_get_all_dmt_users,
    api_get_dm_users_by_project_id,
    api_get_master_key_by_app_id_field_name,
    master_key_row_display_label,
    master_key_row_seq_value,
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

_USER_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("User Id", ("userId", "user_id", "id")),
    ("Username", ("username", "userName", "user_name")),
    ("First Name", ("firstName", "first_name")),
    ("Last Name", ("lastName", "last_name")),
    ("Email", ("email",)),
    ("Mobile", ("mobile", "mobileNumber", "mobile_number")),
    ("Created By", ("createdBy", "created_by")),
    ("Created At", ("createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified At", ("modifiedAt", "modified_at", "updatedAt", "updated_at")),
)

_PROJECT_USER_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("User Id", ("userId", "user_id")),
    ("Mapping Id", ("id", "mappingId", "mapping_id", "userProjectId", "user_project_id")),
    ("Username", ("username", "userName", "user_name", "name")),
    ("Email", ("email",)),
    ("Status", ("status", "statusName", "statusLabel", "status_seq", "statusSeq")),
    ("User Type", ("userType", "user_type", "userTypeName", "user_type_name")),
)

_DM_USER_PROJECT_STATUS_FIELD = "dm_user_module_status"
_DM_USER_TYPE_FIELD = "dm_user_type"


def _normalize_project_user_row(row: dict[str, Any]) -> dict[str, Any]:
    """Copy nested user id onto top level when missing."""
    out = dict(row)
    for k in ("userId", "user_id"):
        v = out.get(k)
        if v is not None and str(v).strip() != "":
            return out
    for nest_key in ("user", "userDetail", "userDetails", "detail", "userInfo", "dmUser"):
        sub = out.get(nest_key)
        if not isinstance(sub, dict):
            continue
        for k in ("userId", "user_id", "id"):
            v = sub.get(k)
            if v is not None and str(v).strip() != "":
                out.setdefault("userId", v)
                return out
    return out


def _load_master_key_rows(field_name: str, token: str | None) -> list[dict[str, Any]]:
    result = api_get_master_key_by_app_id_field_name(field_name=field_name, token=token)
    if not result.get("success"):
        return []
    return [r for r in (result.get("data") or []) if isinstance(r, dict)]


def _populate_master_combo(combo: QComboBox, rows: list[dict[str, Any]]) -> None:
    combo.clear()
    for row in rows:
        label = master_key_row_display_label(row)
        seq = master_key_row_seq_value(row)
        if seq is None:
            continue
        combo.addItem(label, seq)


def _user_id_from_row(row: dict[str, Any]) -> Any:
    for key in ("userId", "user_id", "id"):
        v = row.get(key)
        if v is not None and str(v).strip() != "":
            return v
    for nest_key in ("user", "userDetail", "userDetails", "detail", "userInfo", "dmUser"):
        sub = row.get(nest_key)
        if isinstance(sub, dict):
            for key in ("userId", "user_id", "id"):
                v = sub.get(key)
                if v is not None and str(v).strip() != "":
                    return v
    return None


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


class _DmUserProjectLoadWorker(QObject):
    finished = Signal(bool, object, object, str)

    def __init__(self, token: str | None) -> None:
        super().__init__()
        self._token = token

    @Slot()
    def run(self) -> None:
        projects_result = api_get_all_dm_projects(token=self._token)
        if not projects_result.get("success"):
            self.finished.emit(
                False, [], [], str(projects_result.get("message") or "Failed to load projects.")
            )
            return
        users_result = api_get_all_dmt_users(token=self._token)
        if not users_result.get("success"):
            self.finished.emit(
                False, [], [], str(users_result.get("message") or "Failed to load users.")
            )
            return
        projects = [r for r in (projects_result.get("data") or []) if isinstance(r, dict)]
        users = [u for u in (users_result.get("data") or []) if isinstance(u, dict)]
        self.finished.emit(True, projects, users, "")


class _AssignUserProjectDialog(QDialog):
    """Modal: choose status and user type (master config) before assign."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        count: int,
        status_rows: list[dict[str, Any]],
        user_type_rows: list[dict[str, Any]],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Assign users")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setStyleSheet("QDialog { background: #ffffff; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        intro = QLabel(f"Assign {count} user(s) to this project. Choose status and user type:")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        status_lbl = QLabel("Status")
        status_lbl.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        layout.addWidget(status_lbl)
        self._status_combo = QComboBox()
        apply_form_combobox_field(self._status_combo, height_px=MODAL_FIELD_HEIGHT_PX)
        _populate_master_combo(self._status_combo, status_rows)
        layout.addWidget(self._status_combo)

        type_lbl = QLabel("User type")
        type_lbl.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        layout.addWidget(type_lbl)
        self._user_type_combo = QComboBox()
        apply_form_combobox_field(self._user_type_combo, height_px=MODAL_FIELD_HEIGHT_PX)
        _populate_master_combo(self._user_type_combo, user_type_rows)
        layout.addWidget(self._user_type_combo)

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

    def selected_status(self) -> Any:
        return self._status_combo.currentData()

    def selected_user_type(self) -> Any:
        return self._user_type_combo.currentData()


class _UserProjectStatusDialog(QDialog):
    """Modal: choose status (master config seq) for change-status-by-id."""

    def __init__(self, parent: QWidget | None, *, count: int, status_rows: list[dict[str, Any]]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Change status")
        self.setModal(True)
        self.setMinimumWidth(360)
        self.setStyleSheet("QDialog { background: #ffffff; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        intro = QLabel(f"Choose status for {count} selected mapping(s):")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._status_combo = QComboBox()
        apply_form_combobox_field(self._status_combo, height_px=MODAL_FIELD_HEIGHT_PX)
        _populate_master_combo(self._status_combo, status_rows)
        layout.addWidget(self._status_combo)

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

    def selected_status(self) -> Any:
        return self._status_combo.currentData()


class DmUserProjectMappingPage(QWidget):
    """Project-driven user assignment (DM user–project mapping)."""

    def __init__(self) -> None:
        super().__init__()
        self._loading = False
        self._pending_refresh = False
        self._projects: list[dict[str, Any]] = []
        self._users: list[dict[str, Any]] = []
        self._load_thread: QThread | None = None
        self._load_worker: _DmUserProjectLoadWorker | None = None
        self._load_generation = 0
        self._active_load_generation = 0
        self._user_column_spec: list[tuple[str, tuple[str, ...]]] = []
        self._filter_visible = False
        self._left_assignment_filter_mode = "all"
        self._project_user_filter_visible = False
        self._current_project_id: Any = None
        self._left_checkbox_col = 0
        self._right_checkbox_col = 0
        self._assigned_user_keys_for_project: set[tuple[str, str]] = set()
        self._assigned_user_ids_for_project: set[str] = set()
        self._project_user_rows: list[dict[str, Any]] = []
        self._filter_apply_timer = QTimer(self)
        self._filter_apply_timer.setSingleShot(True)
        self._filter_apply_timer.setInterval(200)
        self._filter_apply_timer.timeout.connect(self._apply_user_column_filters_refresh)
        self._project_user_filter_apply_timer = QTimer(self)
        self._project_user_filter_apply_timer.setSingleShot(True)
        self._project_user_filter_apply_timer.setInterval(200)
        self._project_user_filter_apply_timer.timeout.connect(self._apply_project_user_column_filters_refresh)
        self._build_ui()

    def _lhs_user_identity(self, row: dict[str, Any]) -> tuple[str, str]:
        username = str(row.get("username") or row.get("userName") or row.get("user_name") or "").strip().lower()
        email = str(row.get("email") or "").strip().lower()
        return (username, email)

    def _rhs_user_identity(self, row: dict[str, Any]) -> tuple[str, str]:
        username = str(row.get("username") or row.get("userName") or row.get("user_name") or row.get("name") or "").strip().lower()
        email = str(row.get("email") or "").strip().lower()
        return (username, email)

    def _mapping_id_from_project_user_row(self, row: dict[str, Any]) -> Any:
        return (
            row.get("id")
            or row.get("mappingId")
            or row.get("mapping_id")
            or row.get("userProjectId")
            or row.get("user_project_id")
        )

    def _style_assigned_lhs_row(self, table_row: int) -> None:
        """Muted row styling for users already assigned to the selected project."""
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
        title = QLabel("DM: User Project Mapping")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self._filter_btn = QPushButton("Filters")
        self._filter_btn.setCheckable(True)
        self._filter_btn.setChecked(False)
        self._filter_btn.setFixedWidth(100)
        self._filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_btn.toggled.connect(self._on_user_filter_toggled)
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

        self._project_combo = QComboBox()
        apply_form_combobox_field(self._project_combo, height_px=MODAL_FIELD_HEIGHT_PX, min_width=180)
        self._project_combo.setFixedWidth(220)
        self._project_combo.currentIndexChanged.connect(self._on_project_changed)

        self._assign_selected_btn = QPushButton("Assign")
        self._assign_selected_btn.setFixedWidth(88)
        self._assign_selected_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._assign_selected_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._assign_selected_btn.setEnabled(False)
        self._assign_selected_btn.clicked.connect(self._assign_selected_users_to_project)

        self._remove_assign_btn = QPushButton("Remove")
        self._remove_assign_btn.setFixedWidth(88)
        self._remove_assign_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._remove_assign_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove_assign_btn.setEnabled(False)
        self._remove_assign_btn.clicked.connect(self._remove_selected_assignments)

        self._change_status_btn = QPushButton("Change status")
        self._change_status_btn.setFixedWidth(130)
        self._change_status_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._change_status_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._change_status_btn.setEnabled(False)
        self._change_status_btn.clicked.connect(self._change_status_selected_mappings)

        self._project_user_filter_btn = QPushButton("Filters")
        self._project_user_filter_btn.setCheckable(True)
        self._project_user_filter_btn.setChecked(False)
        self._project_user_filter_btn.setFixedWidth(88)
        self._project_user_filter_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._project_user_filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._project_user_filter_btn.setEnabled(False)
        self._project_user_filter_btn.toggled.connect(self._on_project_user_filter_toggled)

        role_top_row = QWidget()
        role_top_row_lay = QHBoxLayout(role_top_row)
        role_top_row_lay.setContentsMargins(0, 0, 0, 0)
        role_top_row_lay.setSpacing(8)
        role_top_row_lay.addWidget(self._project_combo)
        role_top_row_lay.addWidget(self._project_user_filter_btn)
        role_top_row_lay.addStretch(1)
        right_layout.addSpacing(8)
        right_layout.addWidget(role_top_row)

        self._project_users_table = QTableWidget()
        apply_data_table_appearance(self._project_users_table)
        cols = list(_PROJECT_USER_COLUMNS)
        self._project_users_table.setColumnCount(len(cols))
        self._project_users_table.setHorizontalHeaderLabels([h for h, _ in cols])
        hh = self._project_users_table.horizontalHeader()
        hh.setStretchLastSection(False)
        for col in range(len(cols)):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
        self._project_users_table.setSortingEnabled(True)
        attach_table_copy_shortcut(self._project_users_table)
        self._project_users_table.itemChanged.connect(self._on_right_table_item_changed)
        self._project_users_table.itemClicked.connect(self._on_right_table_item_clicked)
        right_layout.addWidget(self._project_users_table, 1)

        role_bottom_btn_row = QWidget()
        role_bottom_btn_row.setStyleSheet("margin-bottom: 6px;")
        role_bottom_btn_lay = QHBoxLayout(role_bottom_btn_row)
        role_bottom_btn_lay.setContentsMargins(0, 0, 0, 0)
        role_bottom_btn_lay.setSpacing(8)
        role_bottom_btn_lay.addWidget(self._assign_selected_btn)
        role_bottom_btn_lay.addWidget(self._remove_assign_btn)
        role_bottom_btn_lay.addWidget(self._change_status_btn)
        role_bottom_btn_lay.addStretch(1)
        right_layout.addWidget(role_bottom_btn_row)

        self._projects_msg = QLabel("")
        self._projects_msg.setWordWrap(True)
        self._projects_msg.setVisible(False)
        self._projects_msg.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        right_layout.addWidget(self._projects_msg)

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

    def _clear_projects_feedback(self) -> None:
        self._projects_msg.clear()
        self._projects_msg.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        self._projects_msg.setVisible(False)

    def _set_projects_feedback(self, text: str, *, error: bool = False) -> None:
        self._projects_msg.setStyleSheet(FORM_ERROR_LABEL_STYLE if error else MODAL_FIELD_LABEL_STYLE)
        self._projects_msg.setText(text)
        self._projects_msg.setVisible(True)

    def _user_data_row_offset(self) -> int:
        return data_row_offset(self._filter_visible)

    def _schedule_user_filter_apply(self) -> None:
        if self._filter_visible:
            self._filter_apply_timer.start()

    def _filtered_user_source_rows(self) -> list[dict[str, Any]]:
        source_rows = list(self._users)
        if self._left_assignment_filter_mode == "assigned" and self._current_project_id is not None:
            source_rows = [
                row for row in source_rows
                if self._lhs_user_identity(row) in self._assigned_user_keys_for_project
            ]
        elif self._left_assignment_filter_mode == "unassigned" and self._current_project_id is not None:
            source_rows = [
                row for row in source_rows
                if self._lhs_user_identity(row) not in self._assigned_user_keys_for_project
            ]
        if not self._filter_visible or not self._user_column_spec:
            return source_rows
        filtered_rows = list(source_rows)
        col_offset = 1 if self._current_project_id is not None else 0
        for col, (_, keys) in enumerate(self._user_column_spec):
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

    def _write_user_data_rows(self, data_rows: list[dict[str, Any]]) -> None:
        off = self._user_data_row_offset()
        self.table.setSortingEnabled(False)
        total = off + len(data_rows)
        if self._filter_visible and total < 1:
            total = 1
        self.table.setRowCount(total)
        if self._filter_visible:
            for c in range(self.table.columnCount()):
                self.table.takeItem(0, c)
            install_filter_row(self.table, self.table.columnCount(), on_text_changed=self._schedule_user_filter_apply)
            if self._current_project_id is not None:
                self.table.removeCellWidget(0, self._left_checkbox_col)
        for r, row in enumerate(data_rows):
            tr = off + r
            uid = _user_id_from_row(row)
            is_assigned_for_project = False
            if self._current_project_id is not None:
                if uid is not None and str(uid).strip() in self._assigned_user_ids_for_project:
                    is_assigned_for_project = True
                elif self._lhs_user_identity(row) in self._assigned_user_keys_for_project:
                    is_assigned_for_project = True
            if self._current_project_id is not None:
                check_item = QTableWidgetItem("")
                check_flags = Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable
                if not is_assigned_for_project:
                    check_flags |= Qt.ItemFlag.ItemIsEnabled
                check_item.setFlags(check_flags)
                check_item.setCheckState(Qt.CheckState.Unchecked)
                check_item.setData(Qt.ItemDataRole.UserRole, row)
                if is_assigned_for_project:
                    check_item.setData(Qt.ItemDataRole.ToolTipRole, "Already assigned to selected project.")
                self.table.setItem(tr, self._left_checkbox_col, check_item)
            for col_idx, (_, keys) in enumerate(self._user_column_spec):
                value, key_used = _value_for_column(row, keys)
                item = QTableWidgetItem(_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if is_assigned_for_project:
                    item.setFlags((item.flags() & ~Qt.ItemFlag.ItemIsEditable) & ~Qt.ItemFlag.ItemIsEnabled)
                    item.setData(Qt.ItemDataRole.ToolTipRole, "Already assigned to selected project.")
                item.setData(Qt.ItemDataRole.UserRole, row)
                target_col = col_idx + 1 if self._current_project_id is not None else col_idx
                self.table.setItem(tr, target_col, item)
            if is_assigned_for_project:
                self._style_assigned_lhs_row(tr)
        sync_vertical_header_labels(self.table, filter_visible=self._filter_visible, data_row_count=len(data_rows))
        if self._current_project_id is None:
            spec_for_resize: list[tuple[str, tuple[str, ...]]] = list(self._user_column_spec)
        else:
            spec_for_resize = [("Select", ("__select__",)), *self._user_column_spec]
        resize_data_table_columns_to_content(
            self.table,
            spec_for_resize,
            self._users,
            _value_for_column,
            _format_cell,
        )
        self.table.setSortingEnabled(not self._filter_visible)

    def _apply_user_column_filters_refresh(self) -> None:
        if not self._filter_visible or not self._user_column_spec or not self._users:
            return
        try:
            self._write_user_data_rows(self._filtered_user_source_rows())
        except Exception:
            traceback.print_exc()

    def _project_user_data_row_offset(self) -> int:
        return data_row_offset(self._project_user_filter_visible)

    def _schedule_project_user_filter_apply(self) -> None:
        if self._project_user_filter_visible:
            self._project_user_filter_apply_timer.start()

    def _filtered_project_user_rows(self) -> list[dict[str, Any]]:
        role_col_spec = [("Select", ("__select__",)), *list(_PROJECT_USER_COLUMNS)]
        return filter_dict_rows_by_column_edits(
            self._project_user_rows,
            self._project_users_table,
            role_col_spec,
            self._project_user_filter_visible,
            _value_for_column,
            _format_cell,
        )

    def _write_project_user_rows(self, rows: list[dict[str, Any]]) -> None:
        cols = list(_PROJECT_USER_COLUMNS)
        off = self._project_user_data_row_offset()
        self._project_users_table.blockSignals(True)
        self._project_users_table.setSortingEnabled(False)
        self._project_users_table.setColumnCount(1 + len(cols))
        self._project_users_table.setHorizontalHeaderLabels(["Select"] + [h for h, _ in cols])
        r_hh = self._project_users_table.horizontalHeader()
        r_hh.setStretchLastSection(False)
        for col in range(1 + len(cols)):
            r_hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        r_hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
        total = off + len(rows)
        if self._project_user_filter_visible and total < 1:
            total = 1
        self._project_users_table.setRowCount(total)
        if self._project_user_filter_visible:
            for c in range(self._project_users_table.columnCount()):
                self._project_users_table.takeItem(0, c)
            install_filter_row(
                self._project_users_table,
                self._project_users_table.columnCount(),
                on_text_changed=self._schedule_project_user_filter_apply,
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
            self._project_users_table.setItem(tr, self._right_checkbox_col, check_item)
            for c_idx, (_, keys) in enumerate(cols):
                val, key_used = _value_for_column(row, keys)
                item = QTableWidgetItem(_format_cell(val, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self._project_users_table.setItem(tr, c_idx + 1, item)
        sync_vertical_header_labels(
            self._project_users_table,
            filter_visible=self._project_user_filter_visible,
            data_row_count=len(rows),
        )
        spec_resize = [("Select", ("__select__",)), *cols]
        resize_data_table_columns_to_content(
            self._project_users_table,
            spec_resize,
            self._project_user_rows,
            _value_for_column,
            _format_cell,
        )
        self._project_users_table.setSortingEnabled(not self._project_user_filter_visible)
        self._project_users_table.blockSignals(False)
        self._update_assign_button_state()

    def _apply_project_user_column_filters_refresh(self) -> None:
        if not self._project_user_filter_visible or not self._project_user_rows:
            return
        self._write_project_user_rows(self._filtered_project_user_rows())

    def _on_project_user_filter_toggled(self, checked: bool) -> None:
        self._project_user_filter_visible = checked
        if not checked:
            self._project_user_filter_apply_timer.stop()
            clear_filter_row_widgets(self._project_users_table)
        if self._current_project_id is None:
            return
        self._write_project_user_rows(
            self._filtered_project_user_rows() if checked else list(self._project_user_rows)
        )

    def _on_user_filter_toggled(self, checked: bool) -> None:
        self._filter_visible = checked
        if not checked:
            self._filter_apply_timer.stop()
            clear_filter_row_widgets(self.table)
        if self._user_column_spec and self._users:
            self._write_user_data_rows(self._filtered_user_source_rows())

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
        if self._user_column_spec and self._users:
            self._write_user_data_rows(self._filtered_user_source_rows())

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
        if self._user_column_spec and self._users:
            self._write_user_data_rows(self._filtered_user_source_rows())

    def _populate_left_table(self, rows: list[dict[str, Any]]) -> None:
        self._users = [dict(r) for r in rows if isinstance(r, dict)]
        if not self._users:
            self._user_column_spec = []
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return
        self._user_column_spec = list(_USER_COLUMNS)
        self.table.setSortingEnabled(False)
        if self._current_project_id is not None:
            self.table.setColumnCount(len(self._user_column_spec) + 1)
            self.table.setHorizontalHeaderLabels(["Select"] + [col for col, _ in self._user_column_spec])
        else:
            self.table.setColumnCount(len(self._user_column_spec))
            self.table.setHorizontalHeaderLabels([col for col, _ in self._user_column_spec])
        hh = self.table.horizontalHeader()
        hh.setStretchLastSection(False)
        for col in range(self.table.columnCount()):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
        self._write_user_data_rows(self._filtered_user_source_rows())

    def _populate_projects(self, projects: list[dict[str, Any]]) -> None:
        self._projects = [dict(r) for r in projects if isinstance(r, dict)]
        self._project_combo.blockSignals(True)
        self._project_combo.clear()
        self._project_combo.addItem("Select Project")
        for row in self._projects:
            pid = row.get("projectId") or row.get("project_id") or row.get("id")
            if pid is None:
                continue
            name = str(row.get("projectName") or row.get("project_name") or row.get("name") or "").strip()
            label = f"{pid} | {name}" if name else str(pid)
            self._project_combo.addItem(label, pid)
        self._project_combo.blockSignals(False)
        self._project_combo.setCurrentIndex(0)
        self._current_project_id = None
        # Refresh may repopulate roles without emitting indexChanged(0->0),
        # so reset both filter toggles explicitly here.
        self._filter_btn.setChecked(False)
        self._filter_btn.setEnabled(True)
        self._left_assignment_filter_mode = "all"
        self._assigned_only_btn.setChecked(False)
        self._assigned_only_btn.setEnabled(False)
        self._unassigned_only_btn.setChecked(False)
        self._unassigned_only_btn.setEnabled(False)
        self._project_user_filter_btn.setChecked(False)
        self._project_user_filter_btn.setEnabled(False)
        self._project_users_table.setRowCount(0)
        self._reset_project_users_table_columns_plain()
        self._clear_projects_feedback()

    def _reset_project_users_table_columns_plain(self) -> None:
        """Assignments table without checkbox column (no project / empty / error)."""
        cols = list(_PROJECT_USER_COLUMNS)
        self._project_users_table.setColumnCount(len(cols))
        self._project_users_table.setHorizontalHeaderLabels([h for h, _ in cols])
        hh = self._project_users_table.horizontalHeader()
        hh.setStretchLastSection(False)
        for col in range(len(cols)):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)

    def _on_project_changed(self, index: int) -> None:
        if index <= 0:
            self._current_project_id = None
            self._assigned_user_keys_for_project.clear()
            self._assigned_user_ids_for_project.clear()
            self._project_user_rows = []
            self._left_assignment_filter_mode = "all"
            self._assigned_only_btn.setChecked(False)
            self._assigned_only_btn.setEnabled(False)
            self._unassigned_only_btn.setChecked(False)
            self._unassigned_only_btn.setEnabled(False)
            self._project_user_filter_btn.setChecked(False)
            self._project_user_filter_btn.setEnabled(False)
            self._project_users_table.setRowCount(0)
            self._reset_project_users_table_columns_plain()
            self._clear_projects_feedback()
            self._filter_btn.setEnabled(True)
            self._populate_left_table(self._users)
            self._update_assign_button_state()
            return
        self._current_project_id = self._project_combo.currentData()
        self._left_assignment_filter_mode = "all"
        self._assigned_only_btn.setChecked(False)
        self._assigned_only_btn.setEnabled(True)
        self._unassigned_only_btn.setChecked(False)
        self._unassigned_only_btn.setEnabled(True)
        self._project_user_filter_btn.setEnabled(True)
        self._filter_btn.setEnabled(True)
        self._populate_left_table(self._users)
        self._update_assign_button_state()
        self._load_project_users()

    def _selected_left_user_ids(self) -> list[Any]:
        if self._current_project_id is None:
            return []
        out: list[Any] = []
        off = self._user_data_row_offset()
        for row in range(off, self.table.rowCount()):
            item = self.table.item(row, self._left_checkbox_col)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(data, dict):
                continue
            user_id = data.get("userId") or data.get("user_id") or data.get("id")
            if user_id is not None:
                out.append(user_id)
        return out

    def _on_left_table_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == self._left_checkbox_col:
            self._update_assign_button_state()

    def _checked_mapping_ids_for_remove(self) -> list[Any]:
        out: list[Any] = []
        if self._current_project_id is None:
            return out
        if self._project_users_table.columnCount() <= self._right_checkbox_col:
            return out
        off = self._project_user_data_row_offset()
        for row in range(off, self._project_users_table.rowCount()):
            item = self._project_users_table.item(row, self._right_checkbox_col)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(data, dict):
                continue
            mid = self._mapping_id_from_project_user_row(data)
            if mid is not None and str(mid).strip() != "":
                out.append(mid)
        return list(dict.fromkeys(out))

    def _checked_mapping_ids_for_status(self) -> list[Any]:
        out: list[Any] = []
        if self._current_project_id is None:
            return out
        if self._project_users_table.columnCount() <= self._right_checkbox_col:
            return out
        off = self._project_user_data_row_offset()
        for row in range(off, self._project_users_table.rowCount()):
            item = self._project_users_table.item(row, self._right_checkbox_col)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            data = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(data, dict):
                continue
            mid = self._mapping_id_from_project_user_row(data)
            if mid is not None and str(mid).strip() != "":
                out.append(mid)
        return list(dict.fromkeys(out))

    def _on_right_table_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == self._right_checkbox_col:
            self._update_assign_button_state()

    def _on_right_table_item_clicked(self, _item: QTableWidgetItem) -> None:
        self._update_assign_button_state()

    def _update_assign_button_state(self) -> None:
        can_assign = self._current_project_id is not None and bool(self._selected_left_user_ids())
        self._assign_selected_btn.setEnabled(can_assign)
        self._assign_selected_btn.setCursor(
            Qt.CursorShape.PointingHandCursor if can_assign else Qt.CursorShape.ArrowCursor
        )
        can_remove = self._current_project_id is not None and bool(
            self._checked_mapping_ids_for_remove()
        )
        self._remove_assign_btn.setEnabled(can_remove)
        self._remove_assign_btn.setCursor(
            Qt.CursorShape.PointingHandCursor if can_remove else Qt.CursorShape.ArrowCursor
        )
        can_deactivate = self._current_project_id is not None and bool(
            self._checked_mapping_ids_for_status()
        )
        self._change_status_btn.setEnabled(can_deactivate)
        self._change_status_btn.setCursor(
            Qt.CursorShape.PointingHandCursor if can_deactivate else Qt.CursorShape.ArrowCursor
        )

    def _remove_selected_assignments(self) -> None:
        if self._current_project_id is None:
            self._set_projects_feedback("Select a project first.", error=True)
            return
        assignment_ids = self._checked_mapping_ids_for_remove()
        if not assignment_ids:
            self._set_projects_feedback(
                "Check one or more rows with a Mapping Id to remove.",
                error=True,
            )
            return
        token = self._get_token()
        if not token:
            self._set_projects_feedback("Session expired. Please log in again.", error=True)
            return
        n = len(assignment_ids)
        reply = QMessageBox.question(
            self,
            "Remove users",
            f"Remove {n} user mapping(s) from this project?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = api_delete_dm_user_projects_by_ids(
            mapping_ids=assignment_ids,
            token=token,
        )
        if not result.get("success"):
            self._set_projects_feedback(
                str(result.get("message") or "Failed to remove users from project."),
                error=True,
            )
            self._load_project_users()
            return
        self._set_projects_feedback(str(result.get("message") or "User(s) removed from project."), error=False)
        self._load_project_users()

    def _change_status_selected_mappings(self) -> None:
        if self._current_project_id is None:
            self._set_projects_feedback("Select a project first.", error=True)
            return
        mapping_ids = self._checked_mapping_ids_for_status()
        if not mapping_ids:
            self._set_projects_feedback(
                "Check one or more rows with a Mapping Id to change status.",
                error=True,
            )
            return
        token = self._get_token()
        if not token:
            self._set_projects_feedback("Session expired. Please log in again.", error=True)
            return
        status_rows = _load_master_key_rows(_DM_USER_PROJECT_STATUS_FIELD, token)
        if not status_rows:
            self._set_projects_feedback(
                f"Failed to load status options ({_DM_USER_PROJECT_STATUS_FIELD}).",
                error=True,
            )
            return
        dlg = _UserProjectStatusDialog(self, count=len(mapping_ids), status_rows=status_rows)
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        status = dlg.selected_status()
        if status is None:
            self._set_projects_feedback("Select a status.", error=True)
            return
        result = api_change_dm_user_project_status_by_ids(
            mapping_ids=mapping_ids,
            status=status,
            token=token,
        )
        if not result.get("success"):
            self._set_projects_feedback(
                str(result.get("message") or "Failed to update mapping status."),
                error=True,
            )
            self._load_project_users()
            return
        self._set_projects_feedback(
            str(result.get("message") or "Mapping status updated."),
            error=False,
        )
        self._load_project_users()

    def _assign_selected_users_to_project(self) -> None:
        if self._current_project_id is None:
            self._set_projects_feedback("Select a project first.", error=True)
            return
        selected_user_ids = self._selected_left_user_ids()
        if not selected_user_ids:
            self._set_projects_feedback("Select at least one user on the left table.", error=True)
            return
        token = self._get_token()
        if not token:
            self._set_projects_feedback("Session expired. Please log in again.", error=True)
            return
        status_rows = _load_master_key_rows(_DM_USER_PROJECT_STATUS_FIELD, token)
        user_type_rows = _load_master_key_rows(_DM_USER_TYPE_FIELD, token)
        if not status_rows:
            self._set_projects_feedback(
                f"Failed to load status options ({_DM_USER_PROJECT_STATUS_FIELD}).",
                error=True,
            )
            return
        if not user_type_rows:
            self._set_projects_feedback(
                f"Failed to load user type options ({_DM_USER_TYPE_FIELD}).",
                error=True,
            )
            return
        dlg = _AssignUserProjectDialog(
            self,
            count=len(selected_user_ids),
            status_rows=status_rows,
            user_type_rows=user_type_rows,
        )
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        status = dlg.selected_status()
        user_type = dlg.selected_user_type()
        if status is None or user_type is None:
            self._set_projects_feedback("Select status and user type.", error=True)
            return
        result = api_assign_dm_users_to_project(
            project_id=self._current_project_id,
            user_ids=selected_user_ids,
            status=status,
            user_type=user_type,
            token=token,
        )
        if not result.get("success"):
            self._set_projects_feedback(str(result.get("message") or "Failed to assign users."), error=True)
            return
        self._set_projects_feedback(str(result.get("message") or "Users assigned successfully."), error=False)
        self._load_project_users()

    def _load_project_users(self) -> None:
        if self._current_project_id is None:
            return
        self._set_projects_feedback("Loading project users...", error=False)
        self._project_user_rows = []
        self._reset_project_users_table_columns_plain()
        self._project_users_table.setSortingEnabled(False)
        self._project_users_table.setRowCount(0)
        result = api_get_dm_users_by_project_id(self._current_project_id, token=self._get_token())
        if not result.get("success"):
            self._set_projects_feedback(
                str(result.get("message") or "Failed to load project users."),
                error=True,
            )
            self._update_assign_button_state()
            return
        rows = [r for r in (result.get("data") or []) if isinstance(r, dict)]
        if not rows:
            self._assigned_user_keys_for_project.clear()
            self._assigned_user_ids_for_project.clear()
            self._set_projects_feedback("No users assigned to selected project.", error=False)
            self._project_users_table.setSortingEnabled(True)
            self._populate_left_table(self._users)
            self._update_assign_button_state()
            return
        self._assigned_user_keys_for_project = {
            self._rhs_user_identity(r) for r in rows if isinstance(r, dict)
        }
        self._assigned_user_ids_for_project = set()
        for r in rows:
            if not isinstance(r, dict):
                continue
            uid = _user_id_from_row(_normalize_project_user_row(dict(r)))
            if uid is not None and str(uid).strip() != "":
                self._assigned_user_ids_for_project.add(str(uid).strip())
        self._project_user_rows = [_normalize_project_user_row(dict(r)) for r in rows if isinstance(r, dict)]
        self._populate_left_table(self._users)
        self._clear_projects_feedback()
        self._write_project_user_rows(
            self._filtered_project_user_rows()
            if self._project_user_filter_visible
            else list(self._project_user_rows)
        )
        self._update_assign_button_state()

    def _stop_load_thread(self) -> None:
        """Quit and wait for the background loader so QThread is not destroyed while running."""
        worker = self._load_worker
        thread = self._load_thread
        self._load_worker = None
        self._load_thread = None
        if worker is not None:
            try:
                worker.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            worker.deleteLater()
        if thread is not None:
            if thread.isRunning():
                thread.quit()
                thread.wait(5000)
            try:
                thread.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            thread.deleteLater()

    def refresh(self) -> None:
        if self._loading:
            self._pending_refresh = True
            return
        self._stop_load_thread()
        self._loading = True
        self._load_generation += 1
        self._active_load_generation = self._load_generation
        cancel_auto_hide_message(self, self.message_label)
        self.message_label.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        self.message_label.setText("Loading projects and users...")
        self.message_label.setVisible(True)
        self._load_thread = QThread(self)
        self._load_worker = _DmUserProjectLoadWorker(self._get_token())
        self._load_worker.moveToThread(self._load_thread)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.finished.connect(self._on_loaded)
        self._load_worker.finished.connect(self._load_thread.quit)
        self._load_thread.finished.connect(self._cleanup_loader)
        self._load_thread.start()

    @Slot()
    def _on_loaded(self, success: bool, projects_obj: object, users_obj: object, message: str) -> None:
        if self._active_load_generation != self._load_generation:
            return
        self._loading = False
        if not success:
            show_auto_hiding_message(self, self.message_label, message or "Failed to load data.", error=True)
            self._populate_projects([])
            self._populate_left_table([])
        else:
            projects = list(projects_obj) if isinstance(projects_obj, list) else []
            users = list(users_obj) if isinstance(users_obj, list) else []
            self._populate_projects(projects)
            self._populate_left_table(users)
            show_auto_hiding_message(self, self.message_label, "")
        if self._pending_refresh:
            self._pending_refresh = False
            self.refresh()

    def _cleanup_loader(self) -> None:
        thread = self._load_thread
        worker = self._load_worker
        self._load_worker = None
        self._load_thread = None
        if worker is not None:
            worker.deleteLater()
        if thread is not None:
            if thread.isRunning():
                thread.quit()
                thread.wait(5000)
            thread.deleteLater()

    def hideEvent(self, event: QHideEvent) -> None:
        self._pending_refresh = False
        self._loading = False
        self._load_generation += 1
        self._stop_load_thread()
        super().hideEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh()
