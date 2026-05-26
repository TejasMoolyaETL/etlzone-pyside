"""DMT User Module Assignment list (users + linked modules)."""

from __future__ import annotations

import json
import traceback
from typing import Any, Callable

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.api import (
    api_change_dmt_user_module_status_by_id,
    api_get_all_dmt_users,
    api_get_dmt_user_module_assignments_by_user_id,
    api_remove_dmt_user_module_assignments,
)
from core.nav_access import collect_allowed_action_names, nav_action_visible
from core.user_context import get_nav_access_steps, get_user_profile
from ui.auto_hide_message import show_auto_hiding_message
from ui.data_table import (
    MIN_DATA_COL_WIDTH_PX,
    apply_data_table_appearance,
    attach_table_copy_shortcut,
    clear_filter_row_widgets,
    data_row_offset,
    filter_dict_rows_by_column_edits,
    format_data_table_cell,
    install_filter_row,
    resize_data_table_columns_to_content,
    sync_vertical_header_labels,
)
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    MODAL_FIELD_HEIGHT_PX,
)
from ui.searchable_form_combo import (
    combo_resolved_master_key_seq,
    master_key_invalid_typed_text,
    master_key_seq_for_payload,
    require_master_key_seq_for_payload,
    populate_master_key_by_field_name,
    wire_searchable_master_key_combo,
)
from ui.strict_completer import strict_list_selection_message
from ui.styles import CONTEXT_MENU_STYLESHEET
from ui.widgets.required_label import field_caption_label, labeled_field_block

_ASSIGNMENT_STATUS_FIELD_NAME = "dmt_user_module_status"

# Left: DMT users (subset of fields for split view).
_USER_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("User", ("userId", "id")),
    ("First Name", ("firstName", "first_name")),
    ("Last Name", ("lastName", "last_name")),
    ("Email", ("email",)),
    ("Status", ("status",)),
)

# Right: modules assigned to the selected user.
_MODULE_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Assignment Id",
        (
            "assignmentId",
            "userModuleId",
            "userModuleAssignmentId",
            "dmUserModuleAssignmentId",
            "linkId",
        ),
    ),
    ("Assignment Status", ("assignmentStatus", "assignment_status", "dmt_user_module_status")),
    ("Module Id", ("moduleId", "module_id")),
    ("Module Name", ("moduleName", "name", "module_name")),
    ("Module Status", ("moduleStatus", "status", "statusSeq", "status_seq")),
)


class _UserModuleChangeStatusDialog(QDialog):
    """Pick status (master key seq) for ``api_change_dmt_user_module_status_by_id``."""

    def __init__(self, parent: QWidget | None, *, token: str | None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Change assignment status")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setStyleSheet("QDialog { background: #ffffff; }")
        self._token = token
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(QLabel("Select the new status (status number is sent to the API):"))
        self._status_combo = QComboBox()
        self._status_combo.setMinimumWidth(280)
        apply_form_combobox_field(self._status_combo, height_px=MODAL_FIELD_HEIGHT_PX)
        wire_searchable_master_key_combo(self._status_combo, search_field_label="Status")
        layout.addWidget(
            labeled_field_block(field_caption_label("Status*", LABEL_STYLE), self._status_combo)
        )
        populate_master_key_by_field_name(
            self._status_combo,
            _ASSIGNMENT_STATUS_FIELD_NAME,
            token=token,
            include_placeholder=False,
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_status_seq(self) -> tuple[int | None, str | None]:
        return require_master_key_seq_for_payload(
            self._status_combo, field_caption="Status", strict_phrase="a status"
        )



def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k not in row:
            continue
        val = row[k]
        if val is not None:
            return val
    return None


def _lookup_key_value_label(obj: dict[str, Any]) -> str:
    for kk in ("keyValue", "key_value"):
        v = obj.get(kk)
        if v is not None and not isinstance(v, (dict, list)):
            return str(v)
    return ""


def _format_cell_value(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, dict):
        if "keyValue" in val or "key_value" in val:
            text = _lookup_key_value_label(val)
            if text:
                return text
        try:
            return json.dumps(val, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(val)
    if isinstance(val, list):
        try:
            return json.dumps(val, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(val)
    return str(val)


def _value_pick_tuple(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    for k in keys:
        if k in row and row.get(k) is not None:
            return row.get(k), k
    return _pick(row, keys), keys[0]


def _format_cell_for_filter(
    value: Any, key: str = "", key_candidates: tuple[str, ...] = ()
) -> str:
    return format_data_table_cell(value, key, key_candidates)


class DmtUserModuleAssignmentListPage(QWidget):
    def __init__(
        self,
        on_create_clicked: Callable[[dict[str, Any] | None], None] | None = None,
        on_edit_clicked: Callable[[dict[str, Any], bool], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_create_clicked = on_create_clicked
        self.on_edit_clicked = on_edit_clicked
        self._user_source_rows: list[dict[str, Any]] = []
        self._user_filter_visible = False
        self._user_filter_apply_timer = QTimer(self)
        self._user_filter_apply_timer.setSingleShot(True)
        self._user_filter_apply_timer.setInterval(200)
        self._user_filter_apply_timer.timeout.connect(self._apply_user_column_filters_refresh)
        self._current_user_id: Any = None
        self._save_user_id_for_restore: Any = None
        self._can_create = True
        self._can_display = True
        self._can_edit = True
        self._can_change_status = True
        self._can_delete = True
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
        hl.addWidget(QLabel("DMT: User Module Assignment"))
        hl.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        hl.addWidget(refresh_btn)
        self._user_filter_btn = QPushButton("Filters")
        self._user_filter_btn.setCheckable(True)
        self._user_filter_btn.setFixedWidth(100)
        self._user_filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._user_filter_btn.toggled.connect(self._on_user_filter_toggle)
        hl.addWidget(self._user_filter_btn)
        self._create_btn = QPushButton("Create")
        self._create_btn.setFixedWidth(100)
        self._create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._create_btn.setStyleSheet(
            "QPushButton:disabled {"
            " background-color: #9ca3af;"
            " color: #6b7280;"
            " border: 1px solid #9ca3af;"
            "}"
        )
        self._create_btn.clicked.connect(self._emit_create)
        hl.addWidget(self._create_btn)
        layout.addWidget(header)

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

        self._msg = QLabel()
        self._msg.setWordWrap(True)
        self._msg.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._msg.setVisible(False)
        content_layout.addWidget(self._msg)

        self._user_table = QTableWidget()
        apply_data_table_appearance(self._user_table)
        self._user_table.setSortingEnabled(False)
        self._user_table.setColumnCount(len(_USER_COLUMNS))
        self._user_table.setHorizontalHeaderLabels([h for h, _ in _USER_COLUMNS])
        ch = self._user_table.horizontalHeader()
        ch.setStretchLastSection(False)
        for col in range(len(_USER_COLUMNS)):
            ch.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        ch.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
        self._user_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._user_table.customContextMenuRequested.connect(self._on_user_context_menu)
        self._user_table.itemSelectionChanged.connect(self._on_user_selection_changed)
        attach_table_copy_shortcut(self._user_table)

        right_panel = QWidget()
        right_panel.setMinimumWidth(420)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._modules_table = QTableWidget()
        apply_data_table_appearance(self._modules_table)
        self._modules_table.setColumnCount(len(_MODULE_COLUMNS))
        self._modules_table.setHorizontalHeaderLabels([h for h, _ in _MODULE_COLUMNS])
        rh = self._modules_table.horizontalHeader()
        rh.setStretchLastSection(False)
        for col in range(len(_MODULE_COLUMNS)):
            rh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        rh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
        self._modules_table.setSortingEnabled(False)
        self._modules_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._modules_table.customContextMenuRequested.connect(self._on_module_context_menu)
        self._modules_table.itemDoubleClicked.connect(self._on_module_double_click)
        attach_table_copy_shortcut(self._modules_table)
        right_layout.addWidget(self._modules_table, 1)

        self._modules_msg = QLabel("")
        self._modules_msg.setVisible(False)
        self._modules_msg.setWordWrap(True)
        right_layout.addWidget(self._modules_msg)

        main_split = QSplitter(Qt.Orientation.Horizontal)
        main_split.setChildrenCollapsible(False)
        main_split.setHandleWidth(6)
        main_split.setMinimumHeight(260)
        main_split.addWidget(self._user_table)
        main_split.addWidget(right_panel)
        main_split.setStretchFactor(0, 1)
        main_split.setStretchFactor(1, 1)
        main_split.setSizes([480, 520])
        content_layout.addWidget(main_split, 1)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

    def _emit_create(self) -> None:
        if not self._can_create:
            show_auto_hiding_message(
                self,
                self._msg,
                "Create disabled: missing step access dmt-user-module-assignment-create.",
                error=True,
            )
            return
        if self.on_create_clicked:
            self.on_create_clicked(None)

    def _refresh_action_access(self) -> None:
        steps = get_nav_access_steps()
        if steps is None:
            self._can_create = True
            self._can_display = True
            self._can_edit = True
            self._can_change_status = True
            self._can_delete = True
        else:
            allowed = collect_allowed_action_names(steps)
            lbl = "DMT: User Module Assignment"
            self._can_create = nav_action_visible(lbl, "create", allowed)
            self._can_display = nav_action_visible(lbl, "display", allowed)
            self._can_edit = nav_action_visible(lbl, "edit", allowed)
            self._can_change_status = nav_action_visible(lbl, "change_status", allowed)
            self._can_delete = nav_action_visible(lbl, "delete", allowed)
        self._create_btn.setEnabled(self._can_create)
        self._create_btn.setToolTip("" if self._can_create else "Require Permission.")

    def _token(self) -> str | None:
        p = get_user_profile()
        t = p.get("token") or p.get("accessToken") or p.get("access_token") or p.get("jwt")
        return str(t) if t else None

    def _user_id(self, row: dict[str, Any]) -> Any:
        return row.get("userId") or row.get("id")

    def _user_data_row_offset(self) -> int:
        return data_row_offset(self._user_filter_visible)

    def _selected_user_row_index(self) -> int:
        off = self._user_data_row_offset()
        sm = self._user_table.selectionModel()
        if sm is not None:
            srows = sm.selectedRows(0)
            if srows:
                r = int(srows[0].row())
                if r < off:
                    return -1
                return r
        r = self._user_table.currentRow()
        if r < off:
            return -1
        return r if r >= 0 else -1

    def _user_row_data(self, row_index: int) -> dict[str, Any] | None:
        off = self._user_data_row_offset()
        if row_index < off or row_index >= self._user_table.rowCount():
            return None
        it = self._user_table.item(row_index, 0)
        d = it.data(Qt.ItemDataRole.UserRole) if it else None
        return d if isinstance(d, dict) else None

    def _modules_from_user_row(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        for key in (
            "modules",
            "userModules",
            "user_modules",
            "moduleAssignments",
            "module_assignments",
            "assignments",
        ):
            modules = row.get(key)
            if isinstance(modules, list):
                return [c for c in modules if isinstance(c, dict)]
        return []

    def _load_modules_for_user(self, user_id: Any, embedded: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str, bool]:
        """Return (rows, message, is_error). Loads via GET-by-user-id; falls back to embedded user row data."""
        fetch = api_get_dmt_user_module_assignments_by_user_id(user_id, token=self._token())
        if fetch.get("success"):
            rows = [r for r in (fetch.get("data") or []) if isinstance(r, dict)]
            return rows, "", False
        if embedded:
            return embedded, str(fetch.get("message") or ""), False
        return [], str(fetch.get("message") or "Failed to load module assignments."), True

    def _clear_modules_panel(self, *, message: str = "", error: bool = False) -> None:
        self._current_user_id = None
        self._modules_table.setSortingEnabled(False)
        self._modules_table.setRowCount(0)
        self._modules_table.setSortingEnabled(True)
        self._resize_columns_to_content(self._modules_table)
        if message:
            self._modules_msg.setStyleSheet(FORM_ERROR_LABEL_STYLE if error else "")
            self._modules_msg.setText(message)
            self._modules_msg.setVisible(True)
        else:
            self._modules_msg.setVisible(False)

    def _resize_columns_to_content(self, table: QTableWidget) -> None:
        table.resizeColumnsToContents()
        for col in range(table.columnCount()):
            if table.columnWidth(col) < MIN_DATA_COL_WIDTH_PX:
                table.setColumnWidth(col, MIN_DATA_COL_WIDTH_PX)

    def _schedule_user_filter_apply(self) -> None:
        if self._user_filter_visible:
            self._user_filter_apply_timer.start()

    def _filtered_user_rows(self) -> list[dict[str, Any]]:
        return filter_dict_rows_by_column_edits(
            self._user_source_rows,
            self._user_table,
            list(_USER_COLUMNS),
            self._user_filter_visible,
            _value_pick_tuple,
            _format_cell_for_filter,
        )

    def _write_user_data_rows(self, rows: list[dict[str, Any]]) -> None:
        off = self._user_data_row_offset()
        self._user_table.blockSignals(True)
        self._user_table.setSortingEnabled(False)
        total = off + len(rows)
        if self._user_filter_visible and total < 1:
            total = 1
        self._user_table.setRowCount(total)
        if self._user_filter_visible:
            for c in range(self._user_table.columnCount()):
                self._user_table.takeItem(0, c)
            install_filter_row(
                self._user_table,
                self._user_table.columnCount(),
                on_text_changed=self._schedule_user_filter_apply,
            )
        for r, row in enumerate(rows):
            tr = off + r
            for c, (_, keys) in enumerate(_USER_COLUMNS):
                val, ku = _value_pick_tuple(row, keys)
                it = QTableWidgetItem(format_data_table_cell(val, ku, keys))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 0:
                    it.setData(Qt.ItemDataRole.UserRole, row)
                self._user_table.setItem(tr, c, it)
        sync_vertical_header_labels(
            self._user_table,
            filter_visible=self._user_filter_visible,
            data_row_count=len(rows),
        )
        resize_data_table_columns_to_content(
            self._user_table,
            list(_USER_COLUMNS),
            self._user_source_rows,
            _value_pick_tuple,
            _format_cell_for_filter,
        )
        self._user_table.setSortingEnabled(not self._user_filter_visible)
        self._user_table.blockSignals(False)

    def _apply_user_column_filters_refresh(self) -> None:
        if not self._user_filter_visible or not self._user_source_rows:
            return
        self._write_user_data_rows(self._filtered_user_rows())

    def _on_user_filter_toggle(self, checked: bool) -> None:
        self._user_filter_visible = checked
        if not checked:
            self._user_filter_apply_timer.stop()
            clear_filter_row_widgets(self._user_table)
        if self._user_source_rows:
            rows = self._filtered_user_rows() if checked else list(self._user_source_rows)
            self._write_user_data_rows(rows)
        else:
            self._user_table.setSortingEnabled(False)
            clear_filter_row_widgets(self._user_table)
            self._user_table.setRowCount(0)
            self._user_table.setColumnCount(len(_USER_COLUMNS))
            self._user_table.setHorizontalHeaderLabels([h for h, _ in _USER_COLUMNS])

    def _populate_users(self, rows: list[dict[str, Any]]) -> None:
        self._user_source_rows = rows
        rows_to_show = self._filtered_user_rows() if self._user_filter_visible else list(rows)
        self._write_user_data_rows(rows_to_show)

    def _populate_modules(self, rows: list[dict[str, Any]]) -> None:
        self._modules_table.setSortingEnabled(False)
        self._modules_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, (_, keys) in enumerate(_MODULE_COLUMNS):
                val, ku = _value_pick_tuple(row, keys)
                it = QTableWidgetItem(format_data_table_cell(val, ku, keys))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 0:
                    it.setData(Qt.ItemDataRole.UserRole, row)
                self._modules_table.setItem(r, c, it)
        sync_vertical_header_labels(
            self._modules_table,
            filter_visible=False,
            data_row_count=len(rows),
        )
        self._resize_columns_to_content(self._modules_table)
        self._modules_table.setSortingEnabled(True)

    def _restore_user_selection(self, user_id: Any) -> bool:
        if user_id is None:
            return False
        target = str(user_id)
        off = self._user_data_row_offset()
        for row in range(off, self._user_table.rowCount()):
            data = self._user_row_data(row)
            if not data:
                continue
            cid = self._user_id(data)
            if cid is not None and str(cid) == target:
                self._user_table.setCurrentCell(row, 0)
                self._user_table.selectRow(row)
                return True
        return False

    def refresh(self) -> None:
        self._save_user_id_for_restore = self._current_user_id
        token = self._token()
        result = api_get_all_dmt_users(token=token)
        if not result.get("success"):
            show_auto_hiding_message(
                self, self._msg, str(result.get("message") or "Failed to load users."), error=True
            )
            self._populate_users([])
            self._clear_modules_panel(message="Select a user after users load.")
            self._save_user_id_for_restore = None
            return
        show_auto_hiding_message(self, self._msg, "")
        rows = [r for r in (result.get("data") or []) if isinstance(r, dict)]
        self._populate_users(rows)
        restored = False
        if self._save_user_id_for_restore is not None:
            restored = self._restore_user_selection(self._save_user_id_for_restore)
        self._save_user_id_for_restore = None
        if not rows:
            self._clear_modules_panel(message="No users returned.")
        else:
            if not restored:
                self._user_table.selectRow(self._user_data_row_offset())
            # Always sync right table from the freshly fetched user row data.
            self._on_user_selection_changed()

    def _on_user_selection_changed(self) -> None:
        idx = self._selected_user_row_index()
        if idx < 0:
            self._clear_modules_panel()
            return
        data = self._user_row_data(idx)
        if not data:
            self._clear_modules_panel()
            return
        cid = self._user_id(data)
        if cid is None:
            self._clear_modules_panel(message="Selected user is missing a user id.", error=True)
            return
        self._current_user_id = cid
        embedded = self._modules_from_user_row(data)
        modules, msg, is_error = self._load_modules_for_user(cid, embedded)
        self._populate_modules(modules)
        if is_error:
            show_auto_hiding_message(self, self._msg, msg, error=True)
            self._modules_msg.setStyleSheet(FORM_ERROR_LABEL_STYLE)
            self._modules_msg.setText(msg)
            self._modules_msg.setVisible(True)
        elif not modules:
            self._modules_msg.setStyleSheet("")
            self._modules_msg.setText(msg or "No modules linked to this user.")
            self._modules_msg.setVisible(True)
        else:
            self._modules_msg.setVisible(False)
            show_auto_hiding_message(self, self._msg, "")

    def _module_row_data(self, row: int) -> dict[str, Any] | None:
        if row < 0 or row >= self._modules_table.rowCount():
            return None
        it = self._modules_table.item(row, 0)
        d = it.data(Qt.ItemDataRole.UserRole) if it else None
        return d if isinstance(d, dict) else None

    def _first_module_row_with_assignment(self) -> tuple[int, dict[str, Any]] | None:
        for r in range(self._modules_table.rowCount()):
            row = self._module_row_data(r)
            if row and (
                row.get("assignmentId") is not None
                or row.get("userModuleId") is not None
                or row.get("id") is not None
                or row.get("linkId") is not None
            ):
                return r, row
        return None

    def _assignment_row_id(self, row: dict[str, Any] | None) -> Any:
        if not isinstance(row, dict):
            return None
        for key in (
            "assignmentId",
            "userModuleId",
            "userModuleAssignmentId",
            "dmUserModuleAssignmentId",
            "linkId",
        ):
            val = row.get(key)
            if val is not None:
                return val
        row_id = row.get("id")
        module_id = self._module_id_from_row(row)
        if row_id is not None:
            if module_id is None or str(row_id) != str(module_id):
                return row_id
        return None

    def _module_assignment_actionable(self, module_row: dict[str, Any] | None) -> bool:
        """True when row represents an assigned module (delete needs user + module id)."""
        if not isinstance(module_row, dict):
            return False
        return self._current_user_id is not None and self._module_id_from_row(module_row) is not None

    def _module_id_from_row(self, row: dict[str, Any] | None) -> Any:
        if not isinstance(row, dict):
            return None
        mid = row.get("moduleId")
        if mid is not None:
            return mid
        mod = row.get("module")
        if isinstance(mod, dict):
            return mod.get("moduleId") or mod.get("id")
        return None

    def _status_seq_from_row(self, row: dict[str, Any]) -> Any | None:
        for key in ("assignmentStatus", "assignment_status", "status", "statusSeq", "status_seq"):
            if key not in row:
                continue
            v = row.get(key)
            if v is None:
                continue
            if isinstance(v, dict):
                seq = v.get("seq")
                if seq is None:
                    continue
                if isinstance(seq, int):
                    return seq
                s = str(seq).strip()
                if s.isdigit():
                    return int(s)
                return seq
            if isinstance(v, int):
                return v
            s = str(v).strip()
            if s.isdigit():
                return int(s)
        return None

    def _prefill_for_add(self, user_row: dict[str, Any] | None, module_row: dict[str, Any] | None) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if isinstance(user_row, dict):
            cid = self._user_id(user_row)
            if cid is not None:
                out["userId"] = cid
        _ = module_row
        return out

    def _enrich_module_with_user(self, module_row: dict[str, Any]) -> dict[str, Any]:
        out = dict(module_row)
        idx = self._selected_user_row_index()
        user_row = self._user_row_data(idx) if idx >= 0 else None
        if isinstance(user_row, dict):
            cid = self._user_id(user_row)
            if cid is not None:
                out["userId"] = cid
            out["user"] = user_row
        return out

    def _change_module_assignment_status(self, module_row: dict[str, Any]) -> None:
        if not self._can_change_status:
            show_auto_hiding_message(self, self._msg, "Require Permission.", error=True)
            return
        aid = self._assignment_row_id(module_row)
        if aid is None:
            show_auto_hiding_message(
                self,
                self._msg,
                "Cannot change status: assignment id is missing on this row.",
                error=True,
            )
            return
        dlg = _UserModuleChangeStatusDialog(self, token=self._token())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        status_seq, status_err = dlg.selected_status_seq()
        if status_err:
            show_auto_hiding_message(self, self._msg, status_err, error=True)
            return
        res = api_change_dmt_user_module_status_by_id(aid, status_seq, token=self._token())
        show_auto_hiding_message(
            self, self._msg, str(res.get("message") or ""), error=not bool(res.get("success"))
        )
        if res.get("success"):
            QTimer.singleShot(150, self._on_user_selection_changed)

    def _show_assignment_context_menu(self, module_row: dict[str, Any] | None, global_pos: QPoint) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            CONTEXT_MENU_STYLESHEET
            + " QMenu::item:disabled { background: #9ca3af; color: #6b7280; }"
            + " QMenu::item:disabled:selected, QMenu::item:disabled:hover {"
            + " background: #9ca3af; color: #6b7280; }"
        )
        add = menu.addAction("Add assignment")
        view = menu.addAction("Display assignment")
        change_status = menu.addAction("Change status")
        delete = menu.addAction("Delete assignment")
        actionable = self._module_assignment_actionable(module_row)
        can_change_status = actionable and self._assignment_row_id(module_row) is not None
        add.setEnabled(self._can_create)
        view.setEnabled(
            actionable and self.on_edit_clicked is not None and self._can_display
        )
        change_status.setEnabled(can_change_status and self._can_change_status)
        delete.setEnabled(actionable and self._can_delete)
        act = menu.exec(global_pos)
        if act == add:
            if not self._can_create:
                show_auto_hiding_message(self, self._msg, "Require Permission.", error=True)
                return
            if self.on_create_clicked:
                idx = self._selected_user_row_index()
                user_row = self._user_row_data(idx) if idx >= 0 else None
                self.on_create_clicked(self._prefill_for_add(user_row, module_row))
        elif act == view and module_row and self.on_edit_clicked and actionable:
            if not self._can_display:
                show_auto_hiding_message(self, self._msg, "Require Permission.", error=True)
                return
            self.on_edit_clicked(self._enrich_module_with_user(module_row), False)
        elif act == change_status and module_row and can_change_status:
            self._change_module_assignment_status(module_row)
        elif act == delete and module_row and actionable:
            if not self._can_delete:
                show_auto_hiding_message(self, self._msg, "Require Permission.", error=True)
                return
            user_id = self._current_user_id
            module_id = self._module_id_from_row(module_row)
            if user_id is None or module_id is None:
                show_auto_hiding_message(
                    self, self._msg, "Cannot delete: user or module id is missing.", error=True
                )
                return
            if (
                QMessageBox.question(
                    self,
                    "Delete assignment",
                    "Are you sure you want to delete this assignment?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
            res = api_remove_dmt_user_module_assignments(
                user_id, [module_id], token=self._token()
            )
            show_auto_hiding_message(self, self._msg, str(res.get("message") or ""), error=not bool(res.get("success")))
            if res.get("success"):
                # Optimistic UI update so deleted row disappears immediately.
                kept_rows: list[dict[str, Any]] = []
                for r in range(self._modules_table.rowCount()):
                    row_obj = self._module_row_data(r)
                    if not isinstance(row_obj, dict):
                        continue
                    if self._module_id_from_row(row_obj) == module_id:
                        continue
                    kept_rows.append(row_obj)
                self._populate_modules([r for r in kept_rows if isinstance(r, dict)])
                if not kept_rows:
                    self._modules_msg.setStyleSheet("")
                    self._modules_msg.setText("No modules linked to this user.")
                    self._modules_msg.setVisible(True)
                # Then sync with backend source of truth.
                QTimer.singleShot(150, self.refresh)

    def _on_module_double_click(self, item: QTableWidgetItem) -> None:
        row = self._module_row_data(item.row())
        if not self._can_display:
            show_auto_hiding_message(self, self._msg, "Require Permission.", error=True)
            return
        if row and self.on_edit_clicked and self._module_assignment_actionable(row):
            self.on_edit_clicked(self._enrich_module_with_user(row), False)

    def _on_user_context_menu(self, pos: QPoint) -> None:
        clicked = self._user_table.itemAt(pos)
        if clicked is not None and clicked.row() >= self._user_data_row_offset():
            self._user_table.setCurrentCell(clicked.row(), clicked.column())
            self._user_table.selectRow(clicked.row())
        idx = self._user_table.indexAt(pos)
        user_row: dict[str, Any] | None = None
        if idx.isValid() and idx.row() >= self._user_data_row_offset():
            user_row = self._user_row_data(idx.row())
        if user_row is None and clicked is not None and clicked.row() >= self._user_data_row_offset():
            user_row = self._user_row_data(clicked.row())
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        add = menu.addAction("Add assignment")
        add.setEnabled(self._can_create)
        act = menu.exec(QCursor.pos())
        if act == add:
            if not self._can_create:
                show_auto_hiding_message(self, self._msg, "Require Permission.", error=True)
                return
            if self.on_create_clicked:
                cr = self._modules_table.currentRow()
                selected_module = self._module_row_data(cr) if cr >= 0 else None
                self.on_create_clicked(self._prefill_for_add(user_row, selected_module))

    def _on_module_context_menu(self, pos: QPoint) -> None:
        clicked = self._modules_table.itemAt(pos)
        if clicked is not None:
            self._modules_table.setCurrentCell(clicked.row(), clicked.column())
            self._modules_table.selectRow(clicked.row())
        idx = self._modules_table.indexAt(pos)
        row = self._module_row_data(idx.row()) if idx.isValid() else None
        self._show_assignment_context_menu(row, QCursor.pos())

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        try:
            self._refresh_action_access()
            self.refresh()
        except Exception:
            traceback.print_exc()
