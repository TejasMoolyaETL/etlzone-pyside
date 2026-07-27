"""ETL: Connections — 25/75 master–detail list and connection editor."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QPoint, Qt, QThread, QTimer, Slot
from PySide6.QtGui import QCursor, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.etl.connections.add_connection_dialog import AddConnectionDialog, build_connection_payload
from app.etl.connections.connection_async import (
    CONNECTION_FEEDBACK_PENDING_STYLE,
    ConnectionApiWorker,
)
from core.api import (
    api_delete_connection,
    api_get_all_connections,
    api_save_connection,
    api_test_connection,
    api_update_connection,
)
from core.etl_connection_context import get_etl_connection_context
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.data_table import (
    apply_data_table_appearance,
    attach_table_copy_shortcut,
    clear_filter_row_widgets,
    data_row_offset,
    filter_dict_rows_by_column_edits,
    format_data_table_cell,
    render_dict_rows_table,
    saved_filter_texts,
)
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE,
    FORM_LABEL_STYLE,
    FORM_PAGE_FONT_SIZE_PX,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_READONLY_INPUT_STYLE,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    placeholder_example,
)
from ui.styles import CONTEXT_MENU_STYLESHEET
from ui.theme import Theme
from ui.widgets.required_label import field_caption_label, labeled_field_block

_CONNECTION_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Connection Name", ("connectionName",)),
    ("Connection ID", ("connectionId", "connectionID", "connection_id", "id")),
)

# Shown in view mode only; API payloads use the stored password from the selected row.
_PASSWORD_MASK = "********"

# Match DM: Company view — primary Edit with muted disabled chrome.
_EDIT_BTN_STYLESHEET = (
    FORM_PRIMARY_BUTTON_STYLESHEET
    + " QPushButton:disabled {"
    + " background-color: #e5e7eb;"
    + " color: #6b7280;"
    + " border: 1px solid #cbd5e1;"
    + "}"
)

# Match DM: Company list — Create button disabled state on navy header.
_HEADER_CREATE_DISABLED_STYLESHEET = (
    "QPushButton:disabled {"
    " background-color: #9ca3af;"
    " color: #6b7280;"
    " border: 1px solid #9ca3af;"
    "}"
)


def _value_for_column(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    for key in keys:
        if key in row and row.get(key) is not None:
            return (row.get(key), key)
    return (None, keys[0] if keys else "")


def _connection_id(conn: dict[str, Any] | None) -> int | str | None:
    if not conn:
        return None
    for key in ("connectionId", "connectionID", "connection_id", "id"):
        value = conn.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _connection_numeric_field_text(conn: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = conn.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


class ConnectionsPageWidget(QWidget):
    """25% connection list · 75% detail panel (empty until a row is selected)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        hl.addWidget(QLabel("ETL: Connections"))
        hl.addStretch()
        self.connections_filters_btn = QPushButton("Filters")
        self.connections_filters_btn.setCheckable(True)
        self.connections_filters_btn.setFixedWidth(100)
        self.connections_filters_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setFixedWidth(100)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_connection_btn = QPushButton("Create")
        self.add_connection_btn.setFixedWidth(100)
        self.add_connection_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_connection_btn.setStyleSheet(_HEADER_CREATE_DISABLED_STYLESHEET)
        hl.addWidget(self.connections_filters_btn)
        hl.addWidget(self.refresh_btn)
        hl.addWidget(self.add_connection_btn)
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )

        content = QWidget()
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        content.setMinimumHeight(320)
        content.setMinimumWidth(560)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setVisible(False)
        content_layout.addWidget(self.message_label)

        self.connections_table = QTableWidget()
        apply_data_table_appearance(self.connections_table)
        self.connections_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.connections_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.connections_table.setSortingEnabled(True)
        attach_table_copy_shortcut(self.connections_table)

        right_wrap = QWidget()
        right_layout = QVBoxLayout(right_wrap)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.detail_stack = QStackedWidget()

        empty_page = QWidget()
        empty_layout = QVBoxLayout(empty_page)
        empty_layout.setContentsMargins(24, 48, 24, 48)
        self.empty_hint = QLabel("Select a connection from the list to view details.")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setStyleSheet(
            f"color: {Theme.TEXT_SECONDARY}; font-size: {FORM_PAGE_FONT_SIZE_PX + 1}px;"
        )
        empty_layout.addStretch()
        empty_layout.addWidget(self.empty_hint)
        empty_layout.addStretch()
        self.detail_stack.addWidget(empty_page)

        details_page = QWidget()
        details_outer = QVBoxLayout(details_page)
        details_outer.setContentsMargins(0, 0, 0, 0)
        details_outer.setSpacing(0)

        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        detail_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        detail_scroll_content = QWidget()
        detail_scroll_content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        detail_scroll_layout = QVBoxLayout(detail_scroll_content)
        detail_scroll_layout.setContentsMargins(0, 0, 0, 0)
        detail_scroll_layout.setSpacing(0)

        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        card.setMinimumWidth(600)
        card.setMaximumWidth(840)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 12px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 12)
        card_layout.setSpacing(10)

        field_h = FORM_SINGLELINE_FIELD_HEIGHT_PX

        conn_grid = QGridLayout()
        conn_grid.setHorizontalSpacing(24)
        conn_grid.setVerticalSpacing(10)
        conn_grid.setColumnStretch(0, 1)

        def _line_field() -> QLineEdit:
            w = QLineEdit()
            w.setReadOnly(True)
            w.setFixedHeight(field_h)
            w.setMinimumWidth(440)
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            w.setStyleSheet(FORM_READONLY_INPUT_STYLE)
            return w

        self.conn_id_value = _line_field()
        conn_grid.addWidget(
            labeled_field_block(
                field_caption_label("Connection ID", FORM_LABEL_STYLE),
                self.conn_id_value,
            ),
            0,
            0,
        )
        self.conn_name_value = _line_field()
        conn_grid.addWidget(
            labeled_field_block(
                field_caption_label("Connection Name", FORM_LABEL_STYLE),
                self.conn_name_value,
            ),
            1,
            0,
        )
        self.db_type_value = QComboBox()
        self.db_type_value.addItems(["ORACLE", "MYSQL", "POSTGRES", "SQLSERVER"])
        apply_form_combobox_field(self.db_type_value, height_px=field_h, min_width=440)
        self.db_type_value.setEnabled(False)
        conn_grid.addWidget(
            labeled_field_block(
                field_caption_label("Db Type*", FORM_LABEL_STYLE),
                self.db_type_value,
            ),
            2,
            0,
        )
        self.host_value = _line_field()
        conn_grid.addWidget(
            labeled_field_block(
                field_caption_label("Host*", FORM_LABEL_STYLE),
                self.host_value,
            ),
            3,
            0,
        )
        self.port_value = _line_field()
        conn_grid.addWidget(
            labeled_field_block(field_caption_label("Port", FORM_LABEL_STYLE), self.port_value),
            4,
            0,
        )
        self.database_value = _line_field()
        conn_grid.addWidget(
            labeled_field_block(
                field_caption_label("Database / Service*", FORM_LABEL_STYLE),
                self.database_value,
            ),
            5,
            0,
        )
        self.username_value = _line_field()
        conn_grid.addWidget(
            labeled_field_block(
                field_caption_label("Username*", FORM_LABEL_STYLE),
                self.username_value,
            ),
            6,
            0,
        )
        self.password_value = _line_field()
        self.password_value.setEchoMode(QLineEdit.EchoMode.Password)
        conn_grid.addWidget(
            labeled_field_block(
                field_caption_label("Password*", FORM_LABEL_STYLE),
                self.password_value,
            ),
            7,
            0,
        )
        self.fetch_size_value = _line_field()
        conn_grid.addWidget(
            labeled_field_block(
                field_caption_label("Fetch Size", FORM_LABEL_STYLE),
                self.fetch_size_value,
            ),
            8,
            0,
        )
        self.chunk_size_value = _line_field()
        conn_grid.addWidget(
            labeled_field_block(
                field_caption_label("Chunk Size", FORM_LABEL_STYLE),
                self.chunk_size_value,
            ),
            9,
            0,
        )

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setFixedWidth(100)
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.setStyleSheet(_EDIT_BTN_STYLESHEET)
        self.edit_btn.setEnabled(False)
        self.test_btn = QPushButton("Test")
        self.test_btn.setFixedWidth(100)
        self.test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self.test_btn.setEnabled(False)
        self.save_btn = QPushButton("Save")
        self.save_btn.setFixedWidth(100)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedWidth(100)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self.back_btn = QPushButton("Back")
        self.back_btn.setFixedWidth(100)
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self.back_btn.setEnabled(False)

        view_btns = QWidget()
        view_btns.setStyleSheet("background: transparent;")
        view_btns.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        vb = QHBoxLayout(view_btns)
        vb.setContentsMargins(0, 0, 0, 0)
        vb.setSpacing(12)
        vb.setAlignment(Qt.AlignmentFlag.AlignLeft)
        vb.addWidget(self.edit_btn)
        vb.addWidget(self.back_btn)

        edit_btns = QWidget()
        edit_btns.setStyleSheet("background: transparent;")
        edit_btns.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        eb = QHBoxLayout(edit_btns)
        eb.setContentsMargins(0, 0, 0, 0)
        eb.setSpacing(12)
        eb.setAlignment(Qt.AlignmentFlag.AlignLeft)
        eb.addWidget(self.save_btn)
        eb.addWidget(self.cancel_btn)

        self._detail_btn_stack = QStackedWidget()
        self._detail_btn_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self._detail_btn_stack.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._detail_btn_stack.addWidget(view_btns)
        self._detail_btn_stack.addWidget(edit_btns)

        action_btns = QWidget()
        action_btns.setStyleSheet("background: transparent;")
        action_btns.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        ab = QHBoxLayout(action_btns)
        ab.setContentsMargins(0, 0, 0, 0)
        ab.setSpacing(12)
        ab.setAlignment(Qt.AlignmentFlag.AlignLeft)
        ab.addWidget(self.test_btn)
        ab.addWidget(self._detail_btn_stack)

        self.detail_status_label = QLabel()
        self.detail_status_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self.detail_status_label.setWordWrap(True)
        self.detail_status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.detail_status_label.setVisible(False)

        btn_row = 10
        conn_grid.addWidget(self.detail_status_label, btn_row, 0)
        conn_grid.addWidget(
            action_btns,
            btn_row + 1,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        conn_grid.setRowMinimumHeight(btn_row + 1, 52)

        card_layout.addLayout(conn_grid)
        detail_scroll_layout.addWidget(
            card,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        detail_scroll_layout.addStretch()
        detail_scroll.setWidget(detail_scroll_content)
        details_outer.addWidget(detail_scroll, 1)
        self.detail_stack.addWidget(details_page)

        right_layout.addWidget(self.detail_stack, 1)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(6)
        split.setMinimumHeight(320)
        split.addWidget(self.connections_table)
        split.addWidget(right_wrap)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        split.setSizes([250, 750])
        content_layout.addWidget(split, 1)

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def show_empty_detail(self) -> None:
        self.detail_stack.setCurrentIndex(0)
        self.edit_btn.setEnabled(False)
        self.test_btn.setEnabled(False)
        self.back_btn.setEnabled(False)
        self.show_view_buttons()

    def show_detail_panel(self) -> None:
        self.detail_stack.setCurrentIndex(1)
        self.edit_btn.setEnabled(True)
        self.test_btn.setEnabled(True)
        self.back_btn.setEnabled(True)

    def show_view_buttons(self) -> None:
        self._detail_btn_stack.setCurrentIndex(0)

    def show_edit_buttons(self) -> None:
        self._detail_btn_stack.setCurrentIndex(1)


class EtlConnectionsPage(QWidget):
    """Connections screen with API wiring."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._ui = ConnectionsPageWidget()
        layout.addWidget(self._ui)

        self._ctx = get_etl_connection_context()
        self._connections: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self._editing = False
        self._restore_connection_name: str | None = None
        self._connections_filter_visible = False
        self._connections_filter_timer = QTimer(self)
        self._connections_filter_timer.setSingleShot(True)
        self._connections_filter_timer.setInterval(200)
        self._detail_async_busy = False
        self._detail_api_thread: QThread | None = None
        self._detail_api_worker: ConnectionApiWorker | None = None

        self._ui.add_connection_btn.clicked.connect(self._open_add_dialog)
        self._ui.refresh_btn.clicked.connect(self.refresh)
        self._ui.connections_filters_btn.toggled.connect(self._on_connections_filters_toggled)
        self._connections_filter_timer.timeout.connect(self._refresh_connections_table)
        self._ui.connections_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._ui.connections_table.customContextMenuRequested.connect(
            self._on_connections_context_menu
        )
        self._ui.connections_table.itemSelectionChanged.connect(self._on_selection_changed)
        self._ui.edit_btn.clicked.connect(self._on_edit_clicked)
        self._ui.back_btn.clicked.connect(self._on_back_clicked)
        self._ui.cancel_btn.clicked.connect(self._on_cancel_clicked)
        self._ui.test_btn.clicked.connect(self._on_test_clicked)
        self._ui.save_btn.clicked.connect(self._on_save_clicked)

        self._ui.show_empty_detail()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh()

    def refresh(self) -> None:
        if self._current:
            self._restore_connection_name = str(self._current.get("connectionName") or "").strip()
        token = self._token()
        result = api_get_all_connections(token)
        if not result.get("success"):
            self._connections = []
            self._ctx.set_connections([])
            self._populate_table()
            self._show_page_message(str(result.get("message") or "Failed to load connections."), error=True)
            return
        self._connections = list(result.get("data") or [])
        self._ctx.set_connections(self._connections)
        self._populate_table()
        show_auto_hiding_message(self, self._ui.message_label, "", error=False)

    def _token(self) -> str | None:
        profile = get_user_profile() or {}
        return profile.get("token") or profile.get("accessToken")

    def _show_page_message(self, text: str, *, error: bool) -> None:
        show_auto_hiding_message(self, self._ui.message_label, text, error=error)

    def _schedule_connections_filter_apply(self) -> None:
        if self._connections_filter_visible:
            self._connections_filter_timer.start()

    def _on_connections_filters_toggled(self, checked: bool) -> None:
        self._connections_filter_visible = checked
        if not checked:
            clear_filter_row_widgets(self._ui.connections_table)
        self._refresh_connections_table()

    def _connections_filtered_rows(self) -> list[dict[str, Any]]:
        rows = list(self._connections)
        if not self._connections_filter_visible:
            return rows
        return filter_dict_rows_by_column_edits(
            rows,
            self._ui.connections_table,
            list(_CONNECTION_COLUMNS),
            True,
            _value_for_column,
            format_data_table_cell,
        )

    def _refresh_connections_table(self) -> None:
        saved = (
            saved_filter_texts(self._ui.connections_table)
            if self._connections_filter_visible
            else None
        )
        render_dict_rows_table(
            self._ui.connections_table,
            self._connections_filtered_rows(),
            list(_CONNECTION_COLUMNS),
            filter_visible=self._connections_filter_visible,
            value_for_column=_value_for_column,
            format_cell=format_data_table_cell,
            on_filter_text_changed=self._schedule_connections_filter_apply,
            saved_filter_texts_list=saved,
        )

    def _populate_table(self) -> None:
        self._refresh_connections_table()
        table = self._ui.connections_table

        restored = False
        if self._restore_connection_name:
            restored = self._select_connection_by_name(self._restore_connection_name)
            self._restore_connection_name = None

        if not restored:
            table.clearSelection()
            self._current = None
            self._editing = False
            self._ui.show_empty_detail()

    def _select_connection_by_name(self, name: str) -> bool:
        target = (name or "").strip().lower()
        if not target:
            return False
        table = self._ui.connections_table
        offset = data_row_offset(self._connections_filter_visible)
        for row in range(offset, table.rowCount()):
            item = table.item(row, 0)
            if item is None:
                continue
            conn = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(conn, dict):
                continue
            conn_name = str(conn.get("connectionName") or "").strip().lower()
            if conn_name == target:
                table.selectRow(row)
                return True
        return False

    def _selected_connection(self) -> dict[str, Any] | None:
        row = self._selected_table_row()
        if row < 0:
            return None
        item = self._ui.connections_table.item(row, 0)
        if item is None:
            return None
        conn = item.data(Qt.ItemDataRole.UserRole)
        return conn if isinstance(conn, dict) else None

    def _selected_table_row(self) -> int:
        sm = self._ui.connections_table.selectionModel()
        if sm is not None:
            rows = sm.selectedRows()
            if rows:
                return int(rows[0].row())
        return self._ui.connections_table.currentRow()

    def _on_selection_changed(self) -> None:
        conn = self._selected_connection()
        if conn is None:
            self._current = None
            self._ctx.select_connection(None)
            self._editing = False
            self._ui.show_empty_detail()
            self._clear_detail_status()
            return

        self._current = conn
        self._ctx.select_connection(conn)
        self._editing = False
        self._ui.show_view_buttons()
        self._set_details_editable(False)
        self._set_connection_details(conn)
        self._ui.show_detail_panel()
        self._clear_detail_status()

    def _connection_at_pos(self, pos: QPoint) -> dict[str, Any] | None:
        table = self._ui.connections_table
        idx = table.indexAt(pos)
        if idx.isValid():
            item = table.item(idx.row(), 0)
            if item is not None:
                conn = item.data(Qt.ItemDataRole.UserRole)
                return conn if isinstance(conn, dict) else None
        clicked = table.itemAt(pos)
        if clicked is not None:
            item = table.item(clicked.row(), 0)
            if item is not None:
                conn = item.data(Qt.ItemDataRole.UserRole)
                return conn if isinstance(conn, dict) else None
        return None

    def _on_connections_context_menu(self, pos: QPoint) -> None:
        table = self._ui.connections_table
        clicked_item = table.itemAt(pos)
        if clicked_item is not None:
            table.setCurrentCell(clicked_item.row(), clicked_item.column())
            table.selectRow(clicked_item.row())
        conn = self._connection_at_pos(pos) or self._selected_connection()
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        create_action = menu.addAction("Create Connection")
        delete_action = menu.addAction("Delete Connection")
        delete_action.setEnabled(conn is not None)
        action = menu.exec(QCursor.pos())
        if action == create_action:
            self._open_add_dialog()
        elif action == delete_action and conn is not None:
            self._handle_delete_connection(conn)

    def _handle_delete_connection(self, conn: dict[str, Any]) -> None:
        conn_id = _connection_id(conn)
        if conn_id is None:
            self._show_page_message("Cannot delete: connection ID is missing.", error=True)
            return
        name = str(conn.get("connectionName") or "this connection").strip() or "this connection"
        reply = QMessageBox.question(
            self,
            "Delete Connection",
            f"Are you sure you want to delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = api_delete_connection(conn_id, token=self._token())
        if result.get("success"):
            if self._current and _connection_id(self._current) == conn_id:
                self._current = None
                self._editing = False
                self._ui.show_empty_detail()
            self._show_page_message(str(result.get("message") or "Connection deleted."), error=False)
            QTimer.singleShot(700, self.refresh)
        else:
            self._show_page_message(
                str(result.get("message") or "Failed to delete connection."),
                error=True,
            )

    def _open_add_dialog(self) -> None:
        dlg = AddConnectionDialog(
            self,
            on_test=lambda p: api_test_connection(p, token=self._token()),
            on_save=lambda p: api_save_connection(p, token=self._token()),
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._show_page_message(dlg.success_message, error=False)
            self.refresh()

    def _apply_field_style(
        self, field: QLineEdit, *, editable: bool, placeholder: str = ""
    ) -> None:
        field.setReadOnly(not editable)
        field.setStyleSheet(FORM_INPUT_STYLE if editable else FORM_READONLY_INPUT_STYLE)
        field.setPlaceholderText(placeholder_example(placeholder) if editable and placeholder else "")

    def _set_connection_details(self, conn: dict[str, Any]) -> None:
        conn_id = _connection_id(conn)
        self._ui.conn_id_value.setText("" if conn_id is None else str(conn_id))
        self._ui.conn_name_value.setText(str(conn.get("connectionName") or ""))
        db = str(conn.get("dbType") or "")
        idx = self._ui.db_type_value.findText(db)
        if idx >= 0:
            self._ui.db_type_value.setCurrentIndex(idx)
        elif db:
            self._ui.db_type_value.setCurrentText(db)
        self._ui.host_value.setText(str(conn.get("host") or ""))
        port = conn.get("port")
        self._ui.port_value.setText("" if port is None else str(port))
        self._ui.database_value.setText(str(conn.get("databaseName") or ""))
        user = conn.get("dbUserName") or conn.get("username") or ""
        self._ui.username_value.setText(str(user))
        pwd = str(conn.get("dbPassword") or conn.get("password") or "")
        if self._editing:
            self._ui.password_value.setText(pwd)
        else:
            self._ui.password_value.setText(_PASSWORD_MASK if pwd else "")
        self._ui.fetch_size_value.setText(
            _connection_numeric_field_text(conn, "fetchSize", "fetch_size")
        )
        self._ui.chunk_size_value.setText(
            _connection_numeric_field_text(conn, "chunkSize", "chunk_size", "chunkSIze")
        )

    def _set_details_editable(self, editable: bool) -> None:
        self._apply_field_style(
            self._ui.conn_name_value, editable=editable, placeholder="my connection"
        )
        self._ui.db_type_value.setEnabled(editable)
        self._apply_field_style(self._ui.host_value, editable=editable, placeholder="localhost")
        self._apply_field_style(self._ui.port_value, editable=editable, placeholder="1521")
        self._apply_field_style(
            self._ui.database_value, editable=editable, placeholder="ORCL or mydb"
        )
        self._apply_field_style(self._ui.username_value, editable=editable, placeholder="dbuser")
        self._apply_field_style(self._ui.password_value, editable=editable, placeholder="password")
        self._apply_field_style(
            self._ui.fetch_size_value, editable=editable, placeholder="2000"
        )
        self._apply_field_style(
            self._ui.chunk_size_value, editable=editable, placeholder="2000"
        )
        if self._current and editable:
            pwd = str(self._current.get("dbPassword") or self._current.get("password") or "")
            self._ui.password_value.setText(pwd)
        elif self._current:
            pwd = str(self._current.get("dbPassword") or self._current.get("password") or "")
            self._ui.password_value.setText(_PASSWORD_MASK if pwd else "")

    def _on_edit_clicked(self) -> None:
        if self._detail_async_busy:
            return
        if not self._current:
            return
        self._editing = True
        self._set_details_editable(True)
        self._ui.show_edit_buttons()
        self._clear_detail_status()

    def _on_cancel_clicked(self) -> None:
        if self._detail_async_busy:
            return
        if not self._current:
            return
        self._editing = False
        self._set_details_editable(False)
        self._set_connection_details(self._current)
        self._ui.show_view_buttons()
        self._clear_detail_status()

    def _on_back_clicked(self) -> None:
        if self._detail_async_busy:
            return
        self._editing = False
        self._current = None
        self._ui.connections_table.clearSelection()
        self._ui.show_empty_detail()
        self._clear_detail_status()

    def _stored_password(self, conn: dict[str, Any] | None = None) -> str:
        rec = conn if conn is not None else self._current
        if not rec:
            return ""
        return str(rec.get("dbPassword") or rec.get("password") or "").strip()

    def _password_for_api(self) -> str:
        """Plain password for the API; UI may show ``_PASSWORD_MASK`` in view mode."""
        typed = self._ui.password_value.text().strip()
        if self._editing:
            if typed == _PASSWORD_MASK:
                return self._stored_password()
            return typed
        if typed and typed != _PASSWORD_MASK:
            return typed
        return self._stored_password()

    def _build_update_payload(self) -> dict[str, Any]:
        return build_connection_payload(
            connection_name=self._ui.conn_name_value.text(),
            db_type=self._ui.db_type_value.currentText(),
            host=self._ui.host_value.text(),
            port_text=self._ui.port_value.text(),
            database_name=self._ui.database_value.text(),
            username=self._ui.username_value.text(),
            password=self._password_for_api(),
            fetch_size_text=self._ui.fetch_size_value.text(),
            chunk_size_text=self._ui.chunk_size_value.text(),
        )

    def _clear_detail_status(self) -> None:
        cancel_auto_hide_message(self, self._ui.detail_status_label)
        self._ui.detail_status_label.clear()
        self._ui.detail_status_label.setVisible(False)

    def _set_detail_status(self, message: str, *, is_error: bool = False) -> None:
        if not message:
            self._clear_detail_status()
            return
        if is_error:
            self._ui.detail_status_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
            self._ui.detail_status_label.setText(message)
            self._ui.detail_status_label.setVisible(True)
        else:
            show_auto_hiding_message(self, self._ui.detail_status_label, message, error=False)
            self._ui.detail_status_label.setVisible(True)

    def _detail_editable_fields(self) -> tuple[QWidget, ...]:
        return (
            self._ui.conn_name_value,
            self._ui.db_type_value,
            self._ui.host_value,
            self._ui.port_value,
            self._ui.database_value,
            self._ui.username_value,
            self._ui.password_value,
            self._ui.fetch_size_value,
            self._ui.chunk_size_value,
        )

    def _set_detail_pending(self, text: str) -> None:
        cancel_auto_hide_message(self, self._ui.detail_status_label)
        self._ui.detail_status_label.setStyleSheet(CONNECTION_FEEDBACK_PENDING_STYLE)
        self._ui.detail_status_label.setText(text)
        self._ui.detail_status_label.setVisible(True)

    def _set_detail_async_busy(self, busy: bool) -> None:
        self._detail_async_busy = busy
        has_conn = self._current is not None
        self._ui.test_btn.setEnabled(has_conn and not busy)
        self._ui.edit_btn.setEnabled(has_conn and not self._editing and not busy)
        self._ui.back_btn.setEnabled(has_conn and not busy)
        if self._editing:
            self._ui.save_btn.setEnabled(not busy)
            self._ui.cancel_btn.setEnabled(not busy)
            for field in self._detail_editable_fields():
                field.setEnabled(not busy)
        elif busy:
            self._ui.save_btn.setEnabled(False)
            self._ui.cancel_btn.setEnabled(False)

    def _detail_api_thread_running(self) -> bool:
        return self._detail_api_thread is not None and self._detail_api_thread.isRunning()

    def _start_detail_async(
        self,
        *,
        on_call: Callable[[dict[str, Any]], dict[str, Any]],
        pending_text: str,
        fail_prefix: str,
        finished_handler: Callable[[object], None],
    ) -> None:
        if self._detail_async_busy:
            return
        self._set_detail_async_busy(True)
        self._set_detail_pending(pending_text)

        payload = self._build_update_payload()
        self._detail_api_thread = QThread(self)
        self._detail_api_worker = ConnectionApiWorker(payload, on_call, fail_prefix=fail_prefix)
        self._detail_api_worker.moveToThread(self._detail_api_thread)
        self._detail_api_thread.started.connect(self._detail_api_worker.run)
        self._detail_api_worker.finished.connect(finished_handler)
        self._detail_api_worker.finished.connect(self._detail_api_thread.quit)
        self._detail_api_thread.finished.connect(self._cleanup_detail_api_thread)
        self._detail_api_thread.start()

    def _cleanup_detail_api_thread(self) -> None:
        if self._detail_api_worker is not None:
            self._detail_api_worker.deleteLater()
            self._detail_api_worker = None
        if self._detail_api_thread is not None:
            self._detail_api_thread.deleteLater()
            self._detail_api_thread = None

    def _on_test_clicked(self) -> None:
        self._clear_detail_status()
        if self._detail_async_busy:
            return
        if not self._current:
            self._set_detail_status("Select a connection first.", is_error=True)
            return
        self._start_detail_async(
            on_call=lambda p: api_test_connection(p, token=self._token()),
            pending_text="Testing…",
            fail_prefix="Test failed",
            finished_handler=self._on_detail_test_finished,
        )

    @Slot(object)
    def _on_detail_test_finished(self, result: object) -> None:
        self._set_detail_async_busy(False)
        if not isinstance(result, dict):
            self._set_detail_status("Test failed.", is_error=True)
            return
        if result.get("success"):
            self._set_detail_status(
                str(result.get("message") or "Connection successful."),
                is_error=False,
            )
        else:
            self._set_detail_status(str(result.get("message") or "Test failed."), is_error=True)

    def _on_save_clicked(self) -> None:
        self._clear_detail_status()
        if self._detail_async_busy:
            return
        if not self._current:
            self._set_detail_status("Select a connection first.", is_error=True)
            return
        conn_id = _connection_id(self._current)
        if conn_id is None:
            self._set_detail_status("Cannot update: connection ID is missing.", is_error=True)
            return
        if not self._ui.conn_name_value.text().strip():
            self._set_detail_status("Connection name is required.", is_error=True)
            return

        def _update(payload: dict[str, Any]) -> dict[str, Any]:
            return api_update_connection(conn_id, payload, token=self._token())

        self._start_detail_async(
            on_call=_update,
            pending_text="Saving…",
            fail_prefix="Save failed",
            finished_handler=self._on_detail_save_finished,
        )

    @Slot(object)
    def _on_detail_save_finished(self, result: object) -> None:
        self._set_detail_async_busy(False)
        if not isinstance(result, dict):
            self._set_detail_status("Failed to save.", is_error=True)
            return
        if not result.get("success"):
            self._set_detail_status(str(result.get("message") or "Failed to save."), is_error=True)
            return
        self._set_detail_status(str(result.get("message") or "Connection saved."), is_error=False)
        payload = self._build_update_payload()
        merged = {**self._current, **payload}
        merged["dbUserName"] = payload.get("username")
        merged["dbPassword"] = payload.get("password")
        self._current = merged
        self._editing = False
        self._set_details_editable(False)
        self._set_connection_details(self._current)
        self._ui.show_view_buttons()
        self.refresh()
