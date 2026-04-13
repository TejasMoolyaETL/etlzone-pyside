"""App Id list — GET get-all-app-id; create/update/delete with description body (same UX as API: List)."""

from __future__ import annotations

import json
import traceback
from typing import Any

from PySide6.QtCore import QObject, QPoint, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QCursor, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.user_management.users.user_create import INPUT_STYLE
from app.user_management.users.user_view import READONLY_INPUT_STYLE
from app.user_management.user_timepass.user_role_ui_helpers import _add_view_user_form_row
from core.api import (
    api_create_app_id,
    api_delete_app_id_by_id,
    api_get_all_app_id,
    api_update_app_id_by_id,
)
from core.app_preferences import format_datetime_display, is_datetime_field
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.blank_display import is_blank_display_value
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET,
    MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET,
    MODAL_FIELD_HEIGHT_PX,
    MODAL_FIELD_LABEL_STYLE,
    placeholder_example,
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
from ui.post_save_navigation import NO_CHANGES_MESSAGE
from ui.styles import CONTEXT_MENU_STYLESHEET

_HIDDEN_KEYS = frozenset({"password", "token", "accessToken", "access_token", "jwt"})

_APP_ID_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("App Id", ("appId", "app_id", "id")),
    ("Description", ("description", "Description")),
    ("Created By", ("createdBy", "created_by")),
    ("Created At", ("createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified At", ("modifiedAt", "modified_at", "updatedAt", "updated_at")),
)


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


def _row_app_id(row: dict[str, Any]) -> Any:
    return row.get("appId") or row.get("app_id") or row.get("id")


def _row_description(row: dict[str, Any]) -> str:
    for k in ("description", "Description"):
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _display_field(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    value, key_used = _value_for_column(row, keys)
    return _format_cell(value, key_used, keys)


class _AppIdsLoadWorker(QObject):
    finished = Signal(bool, object, str)

    def __init__(self, token: str | None) -> None:
        super().__init__()
        self._token = token

    @Slot()
    def run(self) -> None:
        result = api_get_all_app_id(token=self._token)
        if not result.get("success"):
            self.finished.emit(False, [], str(result.get("message", "Failed to load app ids.")))
            return
        raw = result.get("data") or []
        rows = [r for r in raw if isinstance(r, dict)]
        self.finished.emit(True, rows, "")


class _CreateAppIdDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, *, token: str | None = None) -> None:
        super().__init__(parent)
        self._token = token
        self._creation_success_message = "Created successfully."
        self.setWindowTitle("Create App Id")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setStyleSheet("QDialog { background: #ffffff; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.msg = QLabel()
        self.msg.setWordWrap(True)
        self.msg.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self.msg.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.msg.setVisible(False)
        layout.addWidget(self.msg)

        form_opts = {
            "contents_margins": (0, 0, 0, 0),
            "h_spacing": 12,
            "v_spacing": 8,
            "label_align": Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        }

        def _make_form() -> QFormLayout:
            f = QFormLayout()
            f.setContentsMargins(*form_opts["contents_margins"])
            f.setHorizontalSpacing(form_opts["h_spacing"])
            f.setVerticalSpacing(form_opts["v_spacing"])
            f.setLabelAlignment(form_opts["label_align"])
            return f

        fh = MODAL_FIELD_HEIGHT_PX
        form = _make_form()

        self.description_edit = QLineEdit()
        self.description_edit.setPlaceholderText(placeholder_example("USER"))
        self.description_edit.setStyleSheet(INPUT_STYLE)
        self.description_edit.setFixedHeight(fh)
        self.description_edit.setMinimumWidth(360)
        self.description_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_view_user_form_row(form, "Description*", self.description_edit)

        layout.addLayout(form)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #cbd5e1; border: none; max-height: 1px;")
        layout.addWidget(sep)

        save_btn = QPushButton("Save")
        save_btn.setFixedWidth(100)
        save_btn.setDefault(True)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)
        save_btn.clicked.connect(self._submit)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)
        cancel_btn.clicked.connect(self.reject)

        btn_row = QWidget()
        btn_row.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        br = QHBoxLayout(btn_row)
        br.setContentsMargins(0, 0, 0, 0)
        br.setSpacing(12)
        br.setAlignment(Qt.AlignmentFlag.AlignLeft)
        br.addWidget(save_btn)
        br.addWidget(cancel_btn)
        br.addStretch(1)
        layout.addWidget(btn_row)

    def _clear_msg(self) -> None:
        self.msg.clear()
        self.msg.setVisible(False)

    def _show_err(self, text: str) -> None:
        self.msg.setText(text)
        self.msg.setVisible(bool(text))

    def _submit(self) -> None:
        self._clear_msg()
        desc = self.description_edit.text().strip()
        if not desc:
            self._show_err("Description is required.")
            self.description_edit.setFocus()
            return
        if not self._token or not str(self._token).strip():
            self._show_err("Session expired. Please log in again.")
            return
        result = api_create_app_id(description=desc, token=self._token)
        if result.get("success"):
            self._creation_success_message = str(result.get("message") or "Created successfully.")
            self.accept()
            return
        self._show_err(str(result.get("message") or "Failed to create."))

    def creation_success_message(self) -> str:
        return self._creation_success_message

    def values(self) -> dict[str, str]:
        return {"description": self.description_edit.text().strip()}


class _EditAppIdDialog(QDialog):
    def __init__(self, parent: QWidget | None, row: dict[str, Any]) -> None:
        super().__init__(parent)
        self._app_id = _row_app_id(row)
        self.success_message = "App id updated."
        self._orig_description = _row_description(row)

        self.setWindowTitle("App Id Detail")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setStyleSheet("QDialog { background: #ffffff; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.msg = QLabel()
        self.msg.setWordWrap(True)
        self.msg.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self.msg.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.msg.setVisible(False)
        layout.addWidget(self.msg)

        form_opts = {
            "contents_margins": (0, 0, 0, 0),
            "h_spacing": 12,
            "v_spacing": 8,
            "label_align": Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        }

        def _make_form() -> QFormLayout:
            f = QFormLayout()
            f.setContentsMargins(*form_opts["contents_margins"])
            f.setHorizontalSpacing(form_opts["h_spacing"])
            f.setVerticalSpacing(form_opts["v_spacing"])
            f.setLabelAlignment(form_opts["label_align"])
            return f

        fh = MODAL_FIELD_HEIGHT_PX

        def _ro_audit_line(text: str) -> QLineEdit:
            e = QLineEdit(text)
            e.setReadOnly(True)
            e.setFixedHeight(fh)
            e.setMinimumWidth(360)
            e.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            e.setStyleSheet(READONLY_INPUT_STYLE)
            return e

        top_form = _make_form()
        id_edit = QLineEdit(str(self._app_id) if self._app_id is not None else "")
        id_edit.setReadOnly(True)
        id_edit.setFixedHeight(fh)
        id_edit.setMinimumWidth(360)
        id_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        id_edit.setStyleSheet(READONLY_INPUT_STYLE)
        _add_view_user_form_row(top_form, "App Id", id_edit)
        _add_view_user_form_row(
            top_form, "Created By", _ro_audit_line(_display_field(row, ("createdBy", "created_by")))
        )
        _add_view_user_form_row(
            top_form, "Created At", _ro_audit_line(_display_field(row, ("createdAt", "created_at")))
        )
        _add_view_user_form_row(
            top_form, "Modified By", _ro_audit_line(_display_field(row, ("modifiedBy", "modified_by")))
        )
        _add_view_user_form_row(
            top_form,
            "Modified At",
            _ro_audit_line(_display_field(row, ("modifiedAt", "modified_at", "updatedAt", "updated_at"))),
        )
        layout.addLayout(top_form)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #cbd5e1; border: none; max-height: 1px;")
        layout.addWidget(sep)

        bottom_form = _make_form()
        self.description_edit = QLineEdit()
        self.description_edit.setText(self._orig_description)
        self.description_edit.setPlaceholderText(placeholder_example("USER"))
        self.description_edit.setFixedHeight(fh)
        self.description_edit.setMinimumWidth(360)
        self.description_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_view_user_form_row(bottom_form, "Description*", self.description_edit)
        layout.addLayout(bottom_form)

        back_btn = QPushButton("Back")
        back_btn.setFixedWidth(100)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)
        back_btn.clicked.connect(self.reject)

        edit_btn = QPushButton("Edit")
        edit_btn.setFixedWidth(100)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)
        edit_btn.clicked.connect(self._enter_edit_mode)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)
        cancel_btn.clicked.connect(self._handle_cancel)

        save_btn = QPushButton("Save")
        save_btn.setFixedWidth(100)
        save_btn.setDefault(True)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)
        save_btn.clicked.connect(self._handle_save)

        display_btns = QWidget()
        dbl = QHBoxLayout(display_btns)
        dbl.setContentsMargins(0, 0, 0, 0)
        dbl.setSpacing(12)
        dbl.addWidget(edit_btn)
        dbl.addWidget(back_btn)

        edit_btns = QWidget()
        ebl = QHBoxLayout(edit_btns)
        ebl.setContentsMargins(0, 0, 0, 0)
        ebl.setSpacing(12)
        ebl.addWidget(save_btn)
        ebl.addWidget(cancel_btn)

        self._btn_stack = QStackedWidget()
        self._btn_stack.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._btn_stack.addWidget(display_btns)
        self._btn_stack.addWidget(edit_btns)

        btn_wrap = QWidget()
        bwl = QHBoxLayout(btn_wrap)
        bwl.setContentsMargins(0, 0, 0, 0)
        bwl.setSpacing(12)
        bwl.addWidget(self._btn_stack)
        bwl.addStretch(1)
        layout.addWidget(btn_wrap)

        self._editing = False
        self._snap_description = ""
        self._enter_view_mode()

    def _restore_editable_from_original(self) -> None:
        self.description_edit.setText(self._orig_description)

    def _enter_view_mode(self) -> None:
        self._editing = False
        self.msg.clear()
        self.msg.setVisible(False)
        self.description_edit.setEnabled(False)
        self.description_edit.setStyleSheet(READONLY_INPUT_STYLE)
        self._btn_stack.setCurrentIndex(0)

    def _enter_edit_mode(self) -> None:
        self.msg.clear()
        self.msg.setVisible(False)
        self._editing = True
        self.description_edit.setEnabled(True)
        self.description_edit.setStyleSheet(INPUT_STYLE)
        self._snap_description = self.description_edit.text()
        self._btn_stack.setCurrentIndex(1)

    def _has_unsaved_changes(self) -> bool:
        if not self._editing:
            return False
        return self.description_edit.text() != self._snap_description

    def _handle_cancel(self) -> None:
        if not self._has_unsaved_changes():
            self._restore_editable_from_original()
            self._enter_view_mode()
            return
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Discard and leave edit mode?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Discard:
            self._restore_editable_from_original()
            self._enter_view_mode()

    def _handle_save(self) -> None:
        self.msg.clear()
        self.msg.setVisible(False)
        if self._app_id is None:
            self.msg.setText("Missing app id.")
            self.msg.setVisible(True)
            return
        if not self._has_unsaved_changes():
            self.success_message = NO_CHANGES_MESSAGE
            self.accept()
            return
        desc = self.description_edit.text().strip()
        if not desc:
            self.msg.setText("Description is required.")
            self.msg.setVisible(True)
            self.description_edit.setFocus()
            return
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        if not token:
            self.msg.setText("Session expired.")
            self.msg.setVisible(True)
            return
        result = api_update_app_id_by_id(self._app_id, description=desc, token=token)
        if not result.get("success"):
            self.msg.setText(result.get("message", "Update failed."))
            self.msg.setVisible(True)
            return
        self.success_message = result.get("message", "App id updated.")
        self.accept()

    def values(self) -> dict[str, str]:
        return {"description": self.description_edit.text().strip()}


class ApiAppIdListPage(QWidget):
    """API Management → API: App Id."""

    def __init__(self) -> None:
        super().__init__()
        self._loading = False
        self._pending_refresh = False
        self._load_thread: QThread | None = None
        self._load_worker: _AppIdsLoadWorker | None = None
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
        title = QLabel("API: App Id")
        header_layout.addWidget(title)
        header_layout.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        header_layout.addWidget(refresh_btn)
        self._filter_toggle = QPushButton("Filters")
        self._filter_toggle.setCheckable(True)
        self._filter_toggle.setFixedWidth(100)
        self._filter_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_toggle.toggled.connect(self._on_filter_toggle)
        header_layout.addWidget(self._filter_toggle)
        add_btn = QPushButton("Create")
        add_btn.setFixedWidth(100)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._show_add_dialog)
        header_layout.addWidget(add_btn)
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
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        self.table.itemDoubleClicked.connect(self._on_table_row_double_clicked)
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
            _value_for_column,
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
        for r, row in enumerate(data_rows):
            tr = off + r
            for col, (_, keys) in enumerate(self._column_spec):
                value, key_used = _value_for_column(row, keys)
                item = QTableWidgetItem(_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, row)
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
            _value_for_column,
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

    def _show_empty_table(self) -> None:
        self._source_rows = []
        self._column_spec = []
        self.table.setSortingEnabled(False)
        clear_filter_row_widgets(self.table)
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

    def _populate_table(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            self._show_empty_table()
            return
        try:
            self._source_rows = [dict(r) for r in rows if isinstance(r, dict)]
            self._column_spec = list(_APP_ID_COLUMN_SPEC)
            self.table.setSortingEnabled(False)
            headers = [spec[0] for spec in self._column_spec]
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

    def refresh(self) -> None:
        if self._loading:
            self._pending_refresh = True
            return
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        self._loading = True
        cancel_auto_hide_message(self, self._message_label)
        self._message_label.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        self._message_label.setText("Loading app ids...")
        self._message_label.setVisible(True)
        self._load_thread = QThread(self)
        self._load_worker = _AppIdsLoadWorker(token)
        self._load_worker.moveToThread(self._load_thread)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.finished.connect(self._on_loaded)
        self._load_worker.finished.connect(self._load_thread.quit)
        self._load_thread.finished.connect(self._cleanup_loader)
        self._load_thread.start()

    @Slot()
    def _on_loaded(self, success: bool, rows: object, message: str) -> None:
        self._loading = False
        if not success:
            self._show_message(message or "Failed to load app ids.", error=True)
            self._show_empty_table()
        else:
            show_auto_hiding_message(self, self._message_label, "")
            data = list(rows) if isinstance(rows, list) else []
            self._populate_table([r for r in data if isinstance(r, dict)])
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

    def _get_token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _show_message(self, text: str, *, error: bool) -> None:
        show_auto_hiding_message(self, self._message_label, text, error=error)

    def _has_data_row_selection(self) -> bool:
        for it in self.table.selectedItems():
            if self._is_data_table_row(it.row()):
                return True
        return False

    def _selected_row(self) -> dict[str, Any] | None:
        items = self.table.selectedItems()
        if not items:
            return None
        r = items[0].row()
        if not self._is_data_table_row(r):
            return None
        item = self.table.item(r, 0)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _on_table_context_menu(self, pos: QPoint) -> None:
        clicked_item = self.table.itemAt(pos)
        if clicked_item is not None and self._is_data_table_row(clicked_item.row()):
            self.table.setCurrentCell(clicked_item.row(), clicked_item.column())
            self.table.selectRow(clicked_item.row())
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        add_action = menu.addAction("Add App Id")
        edit_action = menu.addAction("Edit Selected App Id")
        remove_action = menu.addAction("Remove Selected App Id")
        has_selected_row = self._has_data_row_selection() or (
            clicked_item is not None and self._is_data_table_row(clicked_item.row())
        )
        edit_action.setEnabled(has_selected_row)
        remove_action.setEnabled(has_selected_row)
        action = menu.exec(QCursor.pos())
        if action == add_action:
            self._show_add_dialog()
        elif action == remove_action:
            self._remove_selected()
        elif action == edit_action:
            self._edit_selected()

    def _on_table_row_double_clicked(self, item: QTableWidgetItem) -> None:
        if not self._is_data_table_row(item.row()):
            return
        row_item = self.table.item(item.row(), 0)
        if row_item is None:
            return
        rec = row_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(rec, dict):
            return
        if _row_app_id(rec) is None:
            return
        self._run_edit_dialog(rec)

    def _run_edit_dialog(self, row: dict[str, Any]) -> None:
        dlg = _EditAppIdDialog(self, row)
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        self._show_message(dlg.success_message, error=False)
        self.refresh()

    def _edit_selected(self) -> None:
        rec = self._selected_row()
        if not rec:
            self._show_message("Select a row to edit.", error=True)
            return
        if _row_app_id(rec) is None:
            self._show_message("Cannot edit: missing app id.", error=True)
            return
        self._run_edit_dialog(rec)

    def _remove_selected(self) -> None:
        rec = self._selected_row()
        if not rec:
            self._show_message("Select a row to remove.", error=True)
            return
        app_id = _row_app_id(rec)
        if app_id is None:
            self._show_message("Cannot remove: missing app id.", error=True)
            return
        reply = QMessageBox.question(
            self,
            "Remove App Id",
            "Remove this app id?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        token = self._get_token()
        if not token:
            self._show_message("Session expired. Please log in again.", error=True)
            return
        result = api_delete_app_id_by_id(app_id, token=token)
        if result.get("success"):
            self._show_message(result.get("message", "Removed."), error=False)
            self.refresh()
            return
        self._show_message(result.get("message", "Failed to remove."), error=True)

    def _show_add_dialog(self) -> None:
        token = self._get_token()
        if not token:
            self._show_message("Session expired. Please log in again.", error=True)
            return
        dlg = _CreateAppIdDialog(self, token=token)
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        self._show_message(dlg.creation_success_message(), error=False)
        self.refresh()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh()
