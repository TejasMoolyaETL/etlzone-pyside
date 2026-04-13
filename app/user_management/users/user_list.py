"""Users list - fetches /api/user/all and displays users in a table."""

from __future__ import annotations

import json
import traceback
from typing import Any, Callable

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QCursor, QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.api import api_delete_user, api_get_all_users
from core.app_preferences import format_datetime_display, is_datetime_field
from ui.blank_display import is_blank_display_value
from core.user_context import get_user_profile
from ui.auto_hide_message import show_auto_hiding_message
from ui.form_page_styles import (
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
)
from ui.data_table import (
    apply_data_table_appearance,
    attach_table_copy_shortcut,
    clear_filter_row_widgets,
    data_row_offset,
    filter_dict_rows_by_column_edits,
    install_filter_row,
    MIN_DATA_COL_WIDTH_PX,
    resize_data_table_columns_to_content,
    sync_vertical_header_labels,
)
from ui.styles import CONTEXT_MENU_STYLESHEET

# Keys to hide from table
_HIDDEN_KEYS = frozenset({"password", "token", "accessToken", "access_token", "jwt"})

# Logical columns in order: (header_name, possible API keys)
_COLUMN_SPEC = (
    ("User Id", ("id", "userId", "user_id")),
    ("Username", ("username", "userName", "user_name")),
    ("Role", ("defaultRole", "default_role", "userRole", "role", "roles")),
    ("Firstname", ("firstName", "first_name")),
    ("Lastname", ("lastName", "last_name", "name")),
    ("Email", ("email",)),
    ("Mobile", ("mobileNumber", "mobile_number")),
    ("Status", ("userStatus", "status")),
    ("Timezone", ("timezone", "timeZone", "tz", "userTimezone", "user_time_zone")),
    ("Org", ("organizationName", "organization_name", "orgName", "org_name", "organization")),
    ("BU", ("buName", "bu_name", "businessUnitName", "business_unit_name", "businessUnit", "bu")),
    ("Dept", ("deptName", "dept_name", "departmentName", "department_name", "department", "dept")),
    ("Position", ("positionName", "position_name", "position")),
    ("Created By", ("createdBy", "created_by")),
    ("Created At", ("createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified At", ("modifiedAt", "modified_at", "updatedAt", "updated_at")),
)

# For _ordered_keys: flat list of all keys in display order
_COLUMN_ORDER = tuple(
    key for _, keys in _COLUMN_SPEC for key in keys
)


def _flatten_user(user: dict[str, Any]) -> dict[str, Any]:
    """Return user dict with hidden keys removed."""
    return {k: v for k, v in user.items() if k not in _HIDDEN_KEYS}


def _ordered_keys(user: dict[str, Any]) -> list[str]:
    """Column order: preferred first, then remaining alphabetically."""
    ordered = [k for k in _COLUMN_ORDER if k in user]
    remaining = sorted(k for k in user if k not in _COLUMN_ORDER)
    return ordered + remaining


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


def _position_name(value: Any) -> Any:
    """Return a printable position name from nested/flat API value."""
    if isinstance(value, dict):
        for k in ("positionName", "position_name", "name"):
            v = value.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return None
    return value


def _organization_name(value: Any) -> Any:
    """Return a printable organization name from nested/flat API value."""
    if isinstance(value, dict):
        for k in ("orgName", "organizationName", "organization_name", "name"):
            v = value.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return None
    return value


def _bu_name(value: Any) -> Any:
    """Return a printable BU name from nested/flat API value."""
    if isinstance(value, dict):
        for k in ("buName", "bu_name", "businessUnitName", "business_unit_name", "name"):
            v = value.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return None
    return value


def _dept_name(value: Any) -> Any:
    """Return a printable department name from nested/flat API value."""
    if isinstance(value, dict):
        for k in ("deptName", "dept_name", "departmentName", "department_name", "name"):
            v = value.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return None
    return value


def _role_name(value: Any) -> Any:
    """Return a printable role name from direct/nested API value."""
    if isinstance(value, dict):
        for k in ("roleName", "role_name", "name", "role", "defaultRole"):
            v = value.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return None
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            return _role_name(first)
        if first is not None and str(first).strip():
            return str(first).strip()
        return None
    return value


def _status_name(value: Any) -> Any:
    """Normalize backend status tokens for consistent UI labels."""
    if value is None:
        return value
    s = str(value).strip().upper()
    if s == "DEACTIVE":
        return "INACTIVE"
    return value


def _resolve_user_column_value(
    user: dict[str, Any], keys: tuple[str, ...], *, flat: dict[str, Any] | None = None
) -> tuple[Any, str]:
    """Raw value + format key for one column — must match table cells and filter matching."""
    f = flat if flat is not None else _flatten_user(user)
    key = keys[0]
    value = f.get(key)
    if value is None:
        for alt in keys[1:]:
            value = f.get(alt)
            if value is not None:
                key = alt
                break
    if keys == ("userStatus", "status"):
        value = _status_name(value)
    elif keys == ("roleStatusDisplay", "role_status_display"):
        value = _status_name(value)
    elif keys == (
        "defaultRole",
        "default_role",
        "userRole",
        "role",
        "roles",
    ):
        value = _role_name(value)
    elif keys == (
        "positionName",
        "position_name",
        "position",
    ):
        value = _position_name(value)
    elif keys == (
        "organizationName",
        "organization_name",
        "orgName",
        "org_name",
        "organization",
    ):
        value = _organization_name(value)
    elif keys == (
        "buName",
        "bu_name",
        "businessUnitName",
        "business_unit_name",
        "businessUnit",
        "bu",
    ):
        value = _bu_name(value)
    elif keys == (
        "deptName",
        "dept_name",
        "departmentName",
        "department_name",
        "department",
        "dept",
    ):
        value = _dept_name(value)
    return (value, key)


def _value_for_user_column(user: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    return _resolve_user_column_value(user, keys)


class UsersPage(QWidget):
    """Page that fetches and displays all users in a table."""

    def __init__(
        self,
        on_create_clicked: Callable[[], None] | None = None,
        on_edit_clicked: Callable[[dict[str, Any], bool], None] | None = None,
        *,
        page_title: str = "Users",
        show_create_button: bool = True,
        on_row_activate: Callable[[dict[str, Any]], None] | None = None,
        row_action_text: str = "Reset password",
        custom_column_spec: tuple[tuple[str, tuple[str, ...]], ...] | None = None,
        row_actions: list[tuple[str, Callable[[dict[str, Any]], None]]] | None = None,
    ) -> None:
        super().__init__()
        self.on_create_clicked = on_create_clicked
        self.on_edit_clicked = on_edit_clicked
        self._page_title = page_title
        self._show_create_button = show_create_button
        self.on_row_activate = on_row_activate
        self._row_action_text = row_action_text
        self._custom_column_spec = custom_column_spec
        self._row_actions = row_actions or []
        self._source_rows: list[dict[str, Any]] = []
        self._column_spec: list[tuple[str, tuple[str, ...]]] = []
        self._filter_visible = False
        self._filter_apply_timer = QTimer(self)
        self._filter_apply_timer.setSingleShot(True)
        self._filter_apply_timer.setInterval(200)
        self._filter_apply_timer.timeout.connect(self._apply_column_filters_refresh)
        self._build_ui()

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
        title = QLabel(self._page_title)
        header_layout.addWidget(title)
        header_layout.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._load_users)
        header_layout.addWidget(refresh_btn)

        self._filter_btn = QPushButton("Filters")
        self._filter_btn.setCheckable(True)
        self._filter_btn.setChecked(False)
        self._filter_btn.setFixedWidth(100)
        self._filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_btn.setToolTip("Toggle per-column filters on the user list")
        self._filter_btn.toggled.connect(self._on_filter_toggle)
        header_layout.addWidget(self._filter_btn)

        if self._show_create_button:
            create_btn = QPushButton("Create")
            create_btn.setFixedWidth(100)
            create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            create_btn.clicked.connect(
                lambda: self.on_create_clicked() if self.on_create_clicked else None
            )
            header_layout.addWidget(create_btn)

        layout.addWidget(header)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        self._message_label = QLabel()
        self._message_label.setWordWrap(True)
        self._message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._message_label.setVisible(False)
        content_layout.addWidget(self._message_label)

        self.table = QTableWidget()
        apply_data_table_appearance(self.table)
        self.table.setSortingEnabled(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        attach_table_copy_shortcut(self.table)
        content_layout.addWidget(self.table, 1)

        layout.addWidget(content)

    def _data_row_offset(self) -> int:
        return data_row_offset(self._filter_visible)

    def _is_data_table_row(self, table_row: int) -> bool:
        return table_row >= self._data_row_offset()

    def _schedule_filter_apply(self) -> None:
        if self._filter_visible:
            self._filter_apply_timer.start()

    def _filtered_source_rows(self) -> list[dict[str, Any]]:
        return filter_dict_rows_by_column_edits(
            self._source_rows,
            self.table,
            self._column_spec,
            self._filter_visible,
            _value_for_user_column,
            _format_cell,
        )

    def _write_data_rows(self, data_rows: list[dict[str, Any]]) -> None:
        off = self._data_row_offset()
        self.table.setSortingEnabled(False)
        total = off + len(data_rows)
        if self._filter_visible and total < 1:
            total = 1
        self.table.setRowCount(total)
        if self._filter_visible:
            for c in range(self.table.columnCount()):
                self.table.takeItem(0, c)
            install_filter_row(
                self.table,
                len(self._column_spec),
                on_text_changed=self._schedule_filter_apply,
            )
        for r, user in enumerate(data_rows):
            tr = off + r
            flat = _flatten_user(user)
            for col, (_, keys) in enumerate(self._column_spec):
                value, key_used = _resolve_user_column_value(user, keys, flat=flat)
                kc = keys
                item = QTableWidgetItem(_format_cell(value, key_used, kc))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, user)
                self.table.setItem(tr, col, item)
        sync_vertical_header_labels(
            self.table,
            filter_visible=self._filter_visible,
            data_row_count=len(data_rows),
        )
        resize_data_table_columns_to_content(
            self.table,
            self._column_spec,
            self._source_rows,
            _value_for_user_column,
            _format_cell,
        )
        self.table.setSortingEnabled(not self._filter_visible)

    def _apply_column_filters_refresh(self) -> None:
        if not self._filter_visible or not self._column_spec or not self._source_rows:
            return
        try:
            filtered = self._filtered_source_rows()
            self._write_data_rows(filtered)
        except Exception:
            traceback.print_exc()

    def _on_filter_toggle(self, checked: bool) -> None:
        self._filter_visible = checked
        if not checked:
            self._filter_apply_timer.stop()
            clear_filter_row_widgets(self.table)
        if self._column_spec and self._source_rows:
            try:
                to_show = self._filtered_source_rows() if checked else list(self._source_rows)
                self._write_data_rows(to_show)
            except Exception:
                traceback.print_exc()
        elif not self._source_rows:
            self._show_empty_table()

    def _get_user_at_row(self, row: int) -> dict[str, Any] | None:
        if row < 0 or row >= self.table.rowCount():
            return None
        if not self._is_data_table_row(row):
            return None
        first_cell = self.table.item(row, 0)
        user = first_cell.data(Qt.ItemDataRole.UserRole) if first_cell else None
        return user if isinstance(user, dict) else None

    def _user_at_pos(self, pos: QPoint) -> dict[str, Any] | None:
        vp = self.table.viewport()

        def _from_viewport(vp_point: QPoint) -> dict[str, Any] | None:
            idx = self.table.indexAt(vp_point)
            if idx.isValid():
                return self._get_user_at_row(idx.row())
            item = self.table.itemAt(vp_point)
            if item:
                return self._get_user_at_row(item.row())
            return None

        user = _from_viewport(pos)
        if user is not None:
            return user
        return _from_viewport(vp.mapFrom(self.table, pos))

    def _on_context_menu(self, pos: QPoint) -> None:
        clicked = self.table.itemAt(pos)
        if clicked is not None and self._is_data_table_row(clicked.row()):
            self.table.setCurrentCell(clicked.row(), clicked.column())
            self.table.selectRow(clicked.row())
        user = self._user_at_pos(pos)
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        if self._row_actions:
            actions: list[tuple[QAction, Callable[[dict[str, Any]], None]]] = []
            for label, callback in self._row_actions:
                act = menu.addAction(label)
                act.setEnabled(user is not None)
                actions.append((act, callback))
            action = menu.exec(QCursor.pos())
            if user is not None:
                for act, callback in actions:
                    if action == act:
                        callback(user)
                        break
            return
        if self.on_row_activate:
            row_action = menu.addAction(self._row_action_text)
            row_action.setEnabled(user is not None)
            action = menu.exec(QCursor.pos())
            if action == row_action and user is not None:
                self.on_row_activate(user)
            return

        add_action = menu.addAction("Add User")
        display_action = menu.addAction("Display User")
        edit_action = menu.addAction("Edit User")
        delete_action = menu.addAction("Delete User")
        display_action.setEnabled(user is not None and self.on_edit_clicked is not None)
        edit_action.setEnabled(user is not None and self.on_edit_clicked is not None)
        delete_action.setEnabled(user is not None)
        action = menu.exec(QCursor.pos())
        if action == add_action and self.on_create_clicked:
            self.on_create_clicked()
        elif action == display_action and self.on_edit_clicked:
            self.on_edit_clicked(user, False)
        elif action == edit_action and self.on_edit_clicked:
            self.on_edit_clicked(user, True)
        elif action == delete_action:
            self._handle_delete_user(user)

    def _on_row_double_clicked(self, item: QTableWidgetItem) -> None:
        if not self._is_data_table_row(item.row()):
            return
        user = self._get_user_at_row(item.row())
        if not user:
            return
        if self._row_actions:
            self._row_actions[0][1](user)
            return
        if self.on_row_activate:
            self.on_row_activate(user)
            return
        if self.on_edit_clicked:
            self.on_edit_clicked(user, False)

    def _handle_delete_user(self, user: dict[str, Any]) -> None:
        user_id = user.get("id") or user.get("userId") or user.get("user_id")
        if user_id is None:
            show_auto_hiding_message(
                self, self._message_label, "Cannot delete: User ID is missing.", error=True
            )
            return
        username = user.get("username") or user.get("userName") or user.get("user_name") or "this user"
        reply = QMessageBox.question(
            self,
            "Delete User",
            f"Are you sure you want to delete '{username}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_delete_user(user_id, token=token)
        if result.get("success"):
            show_auto_hiding_message(
                self,
                self._message_label,
                result.get("message", "User deleted successfully."),
                error=False,
            )
            QTimer.singleShot(800, self._load_users)
        else:
            show_auto_hiding_message(
                self,
                self._message_label,
                result.get("message", "Failed to delete user."),
                error=True,
            )

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._load_users()

    def refresh(self) -> None:
        """Reload users from API (call after create/update/delete)."""
        self._load_users()

    def _load_users(self) -> None:
        """Call API and populate table."""
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        result = api_get_all_users(token=token)

        if not result.get("success"):
            show_auto_hiding_message(
                self,
                self._message_label,
                result.get("message", "Failed to load users."),
                error=True,
            )
            self._show_empty_table()
            return
        show_auto_hiding_message(self, self._message_label, "")
        data = result.get("data") or []
        self._populate_table(data)

    def _show_empty_table(self) -> None:
        """Show empty table with no columns."""
        self._source_rows = []
        self._column_spec = []
        self.table.setSortingEnabled(False)
        clear_filter_row_widgets(self.table)
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

    def _populate_table(self, users: list[dict[str, Any]]) -> None:
        """Populate table from list of user dicts."""
        if not users:
            self._show_empty_table()
            return
        try:
            self._source_rows = [dict(u) for u in users if isinstance(u, dict)]
            active_column_spec = self._custom_column_spec or _COLUMN_SPEC
            self._column_spec = list(active_column_spec)
            headers = [spec[0] for spec in self._column_spec]
            self.table.setSortingEnabled(False)
            self.table.setColumnCount(len(self._column_spec))
            self.table.setHorizontalHeaderLabels(headers)
            hh = self.table.horizontalHeader()
            hh.setStretchLastSection(False)
            for col in range(self.table.columnCount()):
                hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
            filtered = self._filtered_source_rows() if self._filter_visible else list(self._source_rows)
            self._write_data_rows(filtered)
        except Exception:
            traceback.print_exc()
            self._show_empty_table()
