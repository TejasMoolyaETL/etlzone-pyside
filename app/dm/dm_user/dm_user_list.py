"""DM: User list page for Data Migration Setup."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QCursor, QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.api import api_delete_dmt_user, api_get_all_dmt_users
from core.app_preferences import format_datetime_display, is_datetime_field
from core.user_context import get_user_profile
from ui.auto_hide_message import show_auto_hiding_message
from ui.blank_display import is_blank_display_value
from ui.data_table import (
    apply_data_table_appearance,
    attach_table_copy_shortcut,
    clear_filter_row_widgets,
    data_row_offset,
    filter_dict_rows_by_column_edits,
    install_filter_row,
    resize_data_table_columns_to_content,
    sync_vertical_header_labels,
)
from ui.form_page_styles import (
    DATA_TABLE_HEADER_FONT_SIZE_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
)
from ui.styles import CONTEXT_MENU_STYLESHEET
from ui.theme import Theme

_USER_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("User Id", ("userId", "id")),
    ("Username", ("username", "userName", "user_name")),
    ("First Name", ("firstName", "first_name")),
    ("Last Name", ("lastName", "last_name")),
    (
        "Status",
        (
            "statusName",
            "statusLabel",
            "status",
            "dm_user_status",
            "dmt_user_status",
            "statusSeq",
            "status_seq",
        ),
    ),
    ("Email", ("email",)),
    ("Mobile", ("mobile", "mobileNumber")),
    ("Created At", ("createdAt", "created_at")),
    ("Created By", ("createdBy", "created_by")),
    ("Modified At", ("modifiedAt", "modified_at", "updatedAt", "updated_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
)


def _user_value_for_column(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key), key
    return None, keys[0]


def _format_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if isinstance(value, dict):
        for k in ("keyValue", "key_value", "name", "label", "displayName"):
            t = str(value.get(k) or "").strip()
            if t:
                return t
        return ""
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    return str(value)


class DmUserListPage(QWidget):
    def __init__(
        self,
        on_create_clicked: Callable[[], None] | None = None,
        on_edit_clicked: Callable[[dict[str, Any], bool], None] | None = None,
        on_copy_app_users_clicked: Callable[[], None] | None = None,
        on_upload_users_clicked: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_create_clicked = on_create_clicked
        self.on_edit_clicked = on_edit_clicked
        self.on_copy_app_users_clicked = on_copy_app_users_clicked
        self.on_upload_users_clicked = on_upload_users_clicked
        self._source_rows: list[dict[str, Any]] = []
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
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        hl.addWidget(QLabel("DM: User"))
        hl.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        hl.addWidget(refresh_btn)
        self._filter_btn = QPushButton("Filters")
        self._filter_btn.setCheckable(True)
        self._filter_btn.setFixedWidth(100)
        self._filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_btn.toggled.connect(self._on_filter_toggle)
        hl.addWidget(self._filter_btn)
        create_btn = QPushButton("Create")
        create_btn.setFixedWidth(100)
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.clicked.connect(lambda: self.on_create_clicked() if self.on_create_clicked else None)
        hl.addWidget(create_btn)
        self._more_btn = QToolButton()
        self._more_btn.setText("☰")
        self._more_btn.setFixedWidth(34)
        self._more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._more_btn.setStyleSheet(
            "QToolButton {"
            f" color: {Theme.PANEL_TEXT_BRIGHT};"
            " font-size: 16px; font-weight: 700; padding-bottom: 2px;"
            " border: none; background: transparent; }"
            f"QToolButton:hover {{ background: {Theme.HEADER_ACCENT_HOVER}; }}"
            f"QToolButton:pressed {{ background: {Theme.HEADER_ACCENT_PRESSED}; }}"
        )
        more_menu = QMenu(self._more_btn)
        more_menu.setStyleSheet(
            "QMenu {"
            " background: #f8fafc; color: #475569;"
            " border: 1px solid #cbd5e1;"
            " border-radius: 0px; padding: 0px; }"
            "QMenu::item {"
            " background: #f8fafc; color: #475569;"
            f" font-size: {DATA_TABLE_HEADER_FONT_SIZE_PX}px; font-weight: 600;"
            " padding: 3px 6px; margin: 0px; border: none;"
            " border-bottom: 2px solid #e2e8f0; border-right: 1px solid #cbd5e1; }"
            "QMenu::item:selected { background: #f8fafc; color: #475569; }"
            "QMenu::item:pressed { background: #f8fafc; color: #475569; }"
        )
        copy_action = QAction("Copy App users", self._more_btn)
        copy_action.triggered.connect(self._on_copy_app_users_clicked)
        more_menu.addAction(copy_action)
        upload_action = QAction("Upload users", self._more_btn)
        upload_action.triggered.connect(self._on_upload_users_clicked)
        more_menu.addAction(upload_action)
        self._more_btn.setMenu(more_menu)
        hl.addWidget(self._more_btn)
        layout.addWidget(header)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(12)
        self._message_label = QLabel()
        self._message_label.setVisible(False)
        cl.addWidget(self._message_label)
        self.table = QTableWidget()
        apply_data_table_appearance(self.table)
        self.table.setSortingEnabled(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        attach_table_copy_shortcut(self.table)
        cl.addWidget(self.table, 1)
        layout.addWidget(content, 1)

    def _data_row_offset(self) -> int:
        return data_row_offset(self._filter_visible)

    def _schedule_filter_apply(self) -> None:
        if self._filter_visible:
            self._filter_apply_timer.start()

    def _filtered_source_rows(self) -> list[dict[str, Any]]:
        return filter_dict_rows_by_column_edits(
            self._source_rows,
            self.table,
            list(_USER_COLUMN_SPEC),
            self._filter_visible,
            _user_value_for_column,
            _format_cell,
        )

    def _write_data_rows(self, rows: list[dict[str, Any]]) -> None:
        off = self._data_row_offset()
        self.table.setSortingEnabled(False)
        total = off + len(rows)
        if self._filter_visible and total < 1:
            total = 1
        self.table.setRowCount(total)
        if self._filter_visible:
            for c in range(self.table.columnCount()):
                self.table.takeItem(0, c)
            install_filter_row(self.table, self.table.columnCount(), on_text_changed=self._schedule_filter_apply)
        for r, row in enumerate(rows):
            tr = off + r
            for col, (_, keys) in enumerate(_USER_COLUMN_SPEC):
                value, key_used = _user_value_for_column(row, keys)
                item = QTableWidgetItem(_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(tr, col, item)
        sync_vertical_header_labels(self.table, filter_visible=self._filter_visible, data_row_count=len(rows))
        resize_data_table_columns_to_content(
            self.table,
            list(_USER_COLUMN_SPEC),
            self._source_rows,
            _user_value_for_column,
            _format_cell,
        )
        self.table.setSortingEnabled(not self._filter_visible)

    def _apply_column_filters_refresh(self) -> None:
        if not self._filter_visible or not self._source_rows:
            return
        self._write_data_rows(self._filtered_source_rows())

    def _on_filter_toggle(self, checked: bool) -> None:
        self._filter_visible = checked
        if not checked:
            self._filter_apply_timer.stop()
            clear_filter_row_widgets(self.table)
        if self._source_rows:
            rows = self._filtered_source_rows() if checked else list(self._source_rows)
            self._write_data_rows(rows)
        else:
            self._show_empty_table()

    def _show_empty_table(self) -> None:
        self._source_rows = []
        self.table.setSortingEnabled(False)
        clear_filter_row_widgets(self.table)
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

    def _get_user_at_row(self, row: int) -> dict[str, Any] | None:
        if row < self._data_row_offset() or row >= self.table.rowCount():
            return None
        item = self.table.item(row, 0)
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        return data if isinstance(data, dict) else None

    def _user_at_pos(self, pos: QPoint) -> dict[str, Any] | None:
        idx = self.table.indexAt(pos)
        if idx.isValid():
            return self._get_user_at_row(idx.row())
        item = self.table.itemAt(pos)
        if item:
            return self._get_user_at_row(item.row())
        return None

    def _on_context_menu(self, pos: QPoint) -> None:
        clicked_item = self.table.itemAt(pos)
        if clicked_item is not None and clicked_item.row() >= self._data_row_offset():
            self.table.setCurrentCell(clicked_item.row(), clicked_item.column())
            self.table.selectRow(clicked_item.row())
        user = self._user_at_pos(pos)
        if user is None and clicked_item is not None and clicked_item.row() >= self._data_row_offset():
            user = self._get_user_at_row(clicked_item.row())
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
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
        elif action == display_action and user is not None and self.on_edit_clicked:
            self.on_edit_clicked(user, False)
        elif action == edit_action and user is not None and self.on_edit_clicked:
            self.on_edit_clicked(user, True)
        elif action == delete_action and user is not None:
            self._handle_delete_user(user)

    def _on_row_double_clicked(self, item: QTableWidgetItem) -> None:
        if item.row() < self._data_row_offset():
            return
        user = self._get_user_at_row(item.row())
        if user is not None and self.on_edit_clicked:
            self.on_edit_clicked(user, False)

    def _handle_delete_user(self, user: dict[str, Any]) -> None:
        uid = user.get("userId") or user.get("id")
        if uid is None:
            show_auto_hiding_message(self, self._message_label, "Cannot delete: User ID is missing.", error=True)
            return
        fn = str(user.get("firstName") or user.get("first_name") or "").strip()
        ln = str(user.get("lastName") or user.get("last_name") or "").strip()
        name = (f"{fn} {ln}".strip() or user.get("userName") or user.get("name") or "this user")
        reply = QMessageBox.question(
            self,
            "Delete User",
            f"Are you sure you want to delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        token = self._token()
        result = api_delete_dmt_user(uid, token=token)
        show_auto_hiding_message(
            self,
            self._message_label,
            str(result.get("message") or ("Deleted." if result.get("success") else "Delete failed.")),
            error=not bool(result.get("success")),
        )
        if result.get("success"):
            self.refresh()

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _load_users(self) -> None:
        result = api_get_all_dmt_users(token=self._token())
        if not result.get("success"):
            self._show_empty_table()
            show_auto_hiding_message(
                self,
                self._message_label,
                str(result.get("message") or "Failed to load users."),
                error=True,
            )
            return
        rows = result.get("data") or []
        self._source_rows = [r for r in rows if isinstance(r, dict)]
        # Keep parity with other list pages: clear stale error banner once data loads.
        show_auto_hiding_message(self, self._message_label, "", error=False)
        self.table.clear()
        self.table.setColumnCount(len(_USER_COLUMN_SPEC))
        self.table.setHorizontalHeaderLabels([h for h, _ in _USER_COLUMN_SPEC])
        rows_to_show = self._filtered_source_rows() if self._filter_visible else list(self._source_rows)
        self._write_data_rows(rows_to_show)

    def _on_copy_app_users_clicked(self) -> None:
        if self.on_copy_app_users_clicked:
            self.on_copy_app_users_clicked()

    def _on_upload_users_clicked(self) -> None:
        if self.on_upload_users_clicked:
            self.on_upload_users_clicked()

    def refresh(self) -> None:
        self._load_users()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._load_users()
