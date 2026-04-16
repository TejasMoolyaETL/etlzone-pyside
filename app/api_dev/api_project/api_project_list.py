"""API Project list — same layout and behavior as API Management → API: List."""

from __future__ import annotations

import json
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QPoint, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QCursor, QShowEvent
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

from core.api import api_delete_project, api_get_all_projects
from core.app_preferences import format_datetime_display, is_datetime_field
from core.nav_access import collect_allowed_action_names, nav_action_visible
from core.user_context import get_nav_access_steps, get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.blank_display import is_blank_display_value
from ui.form_page_styles import (
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    MODAL_FIELD_LABEL_STYLE,
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

_HIDDEN_KEYS = frozenset({"password", "token", "accessToken", "access_token", "jwt"})

# apiDetails[] from get-all-api-projects — not shown here (use API: Details for per-API rows).
_OMITTED_FROM_PROJECT_TABLE_KEYS = frozenset({"apiDetails", "api_details"})


def _row_for_project_table(row: dict[str, Any]) -> dict[str, Any]:
    """Shallow copy without nested list payloads; keeps table cells and row payloads lean."""
    return {k: v for k, v in row.items() if k not in _OMITTED_FROM_PROJECT_TABLE_KEYS}

_PROJECT_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Project Id (Internal)", ("projectid", "projectId", "project_id")),
    ("Project Name", ("projectName", "project_name")),
    ("Project Desc", ("projectDesc", "project_desc", "projectDescription")),
    ("Project Owner User Id", ("projectOwnerUserld", "projectOwnerUserId", "project_owner_user_id")),
    ("Project Status", ("projectStatus", "project_status")),
    ("Project Server", ("projectServer", "project_server")),
    ("Project Port", ("projectPort", "project_port")),
    ("Created By", ("createdBy", "created_by", "CreatedBy")),
    ("Created At", ("createdAt", "created_at", "CreatedAt", "createDate", "creationDate", "dateCreated")),
    ("Modified By", ("modifiedBy", "modified_by", "ModifiedBy")),
    ("Modified At", ("modifiedAt", "modified_at", "ModifiedAt", "updatedAt", "updated_at", "modifyDate", "dateModified")),
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


def _project_id(row: dict[str, Any]) -> Any:
    return row.get("projectId") or row.get("projectid") or row.get("project_id")


class _ProjectsLoadWorker(QObject):
    finished = Signal(bool, object, str)

    def __init__(self, token: str | None) -> None:
        super().__init__()
        self._token = token

    @Slot()
    def run(self) -> None:
        result = api_get_all_projects(token=self._token)
        if not result.get("success"):
            self.finished.emit(False, [], str(result.get("message", "Failed to load projects.")))
            return
        raw = result.get("data") or []
        rows = [r for r in raw if isinstance(r, dict)]
        self.finished.emit(True, rows, "")


class APIProjectsPage(QWidget):
    """Operational project list (API → API: Projects) — matches API: List UX."""

    def __init__(
        self,
        on_create_clicked: Callable[[], None] | None = None,
        on_edit_clicked: Callable[[dict[str, Any], bool], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_create_clicked = on_create_clicked
        self.on_edit_clicked = on_edit_clicked
        self._loading = False
        self._pending_refresh = False
        self._load_thread: QThread | None = None
        self._load_worker: _ProjectsLoadWorker | None = None
        self._source_rows: list[dict[str, Any]] = []
        self._column_spec: list[tuple[str, tuple[str, ...]]] = []
        self._filter_visible = False
        self._filter_apply_timer = QTimer(self)
        self._filter_apply_timer.setSingleShot(True)
        self._filter_apply_timer.setInterval(200)
        self._filter_apply_timer.timeout.connect(self._apply_column_filters_refresh)
        self._can_create_project = True
        self._can_display_project = True
        self._can_edit_project = True
        self._can_delete_project = True
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
        title = QLabel("API: Projects")
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
        self._create_btn.clicked.connect(self._emit_add)
        header_layout.addWidget(self._create_btn)
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

    def _emit_add(self) -> None:
        if not self._can_create_project:
            self._show_message(
                "Create disabled: missing step access api-dev-projects-create.",
                error=True,
            )
            return
        if self.on_create_clicked:
            self.on_create_clicked()

    def _refresh_action_access(self) -> None:
        steps = get_nav_access_steps()
        if steps is None:
            # SADMIN / unrestricted mode.
            self._can_create_project = True
            self._can_display_project = True
            self._can_edit_project = True
            self._can_delete_project = True
        else:
            allowed_actions = collect_allowed_action_names(steps)
            self._can_create_project = nav_action_visible(
                "API: Projects", "create", allowed_actions
            )
            self._can_display_project = nav_action_visible(
                "API: Projects", "display", allowed_actions
            )
            self._can_edit_project = nav_action_visible(
                "API: Projects", "edit", allowed_actions
            )
            self._can_delete_project = nav_action_visible(
                "API: Projects", "delete", allowed_actions
            )
        self._create_btn.setEnabled(self._can_create_project)
        self._create_btn.setToolTip(
            "" if self._can_create_project else "Require Permission."
        )

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
        for r, slim in enumerate(data_rows):
            tr = off + r
            for col, (_, keys) in enumerate(self._column_spec):
                value, key_used = _value_for_column(slim, keys)
                item = QTableWidgetItem(_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, slim)
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
            self._source_rows = [_row_for_project_table(dict(r)) for r in rows if isinstance(r, dict)]
            self._column_spec = list(_PROJECT_COLUMN_SPEC)
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
            self._show_message("Failed to display project rows.", error=True)
            self._show_empty_table()

    def refresh(self) -> None:
        if self._loading:
            self._pending_refresh = True
            return
        token = self._get_token()
        self._loading = True
        cancel_auto_hide_message(self, self._message_label)
        self._message_label.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        self._message_label.setText("Loading projects...")
        self._message_label.setVisible(True)
        self._load_thread = QThread(self)
        self._load_worker = _ProjectsLoadWorker(token)
        self._load_worker.moveToThread(self._load_thread)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.finished.connect(self._on_projects_loaded)
        self._load_worker.finished.connect(self._load_thread.quit)
        self._load_thread.finished.connect(self._cleanup_loader)
        self._load_thread.start()

    @Slot()
    def _on_projects_loaded(self, success: bool, rows: object, message: str) -> None:
        self._loading = False
        try:
            if not success:
                self._show_message(message or "Failed to load projects.", error=True)
                self._show_empty_table()
            else:
                show_auto_hiding_message(self, self._message_label, "")
                data = list(rows) if isinstance(rows, list) else []
                self._populate_table([r for r in data if isinstance(r, dict)])
        except Exception:
            traceback.print_exc()
            self._show_message("Failed to display projects.", error=True)
            self._show_empty_table()
        finally:
            if self._pending_refresh:
                self._pending_refresh = False
                try:
                    self.refresh()
                except Exception:
                    traceback.print_exc()

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

    def _selected_project_row(self) -> dict[str, Any] | None:
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
        menu.setStyleSheet(
            CONTEXT_MENU_STYLESHEET
            + " QMenu::item:disabled { background: #9ca3af; color: #6b7280; }"
            + " QMenu::item:disabled:selected, QMenu::item:disabled:hover {"
            + " background: #9ca3af; color: #6b7280; }"
        )
        add_action = menu.addAction("Add Project")
        display_action = menu.addAction("Display Selected Project")
        edit_action = menu.addAction("Edit Selected Project")
        remove_action = menu.addAction("Remove Selected Project")
        add_action.setEnabled(self._can_create_project)
        has_selected = self._has_data_row_selection() or (
            clicked_item is not None and self._is_data_table_row(clicked_item.row())
        )
        display_action.setEnabled(
            has_selected and self.on_edit_clicked is not None and self._can_display_project
        )
        edit_action.setEnabled(
            has_selected and self.on_edit_clicked is not None and self._can_edit_project
        )
        remove_action.setEnabled(has_selected and self._can_delete_project)
        action = menu.exec(QCursor.pos())
        if action == add_action:
            self._emit_add()
        elif action == display_action:
            self._display_selected_project()
        elif action == edit_action:
            self._edit_selected_project()
        elif action == remove_action:
            self._remove_selected_project()

    def _on_table_row_double_clicked(self, item: QTableWidgetItem) -> None:
        if not self._is_data_table_row(item.row()):
            return
        row_item = self.table.item(item.row(), 0)
        if row_item is None:
            return
        rec = row_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(rec, dict):
            return
        if not self._can_display_project:
            self._show_message("Require Permission.", error=True)
            return
        if self.on_edit_clicked:
            self.on_edit_clicked(rec, False)

    def _display_selected_project(self) -> None:
        if not self._can_display_project:
            self._show_message("Require Permission.", error=True)
            return
        rec = self._selected_project_row()
        if not rec:
            self._show_message("Select a project to display.", error=True)
            return
        if self.on_edit_clicked:
            self.on_edit_clicked(rec, False)

    def _edit_selected_project(self) -> None:
        if not self._can_edit_project:
            self._show_message("Require Permission.", error=True)
            return
        rec = self._selected_project_row()
        if not rec:
            self._show_message("Select a project to edit.", error=True)
            return
        if _project_id(rec) is None:
            self._show_message("Cannot edit: missing project id.", error=True)
            return
        if self.on_edit_clicked:
            self.on_edit_clicked(rec, True)

    def _remove_selected_project(self) -> None:
        if not self._can_delete_project:
            self._show_message("Require Permission.", error=True)
            return
        rec = self._selected_project_row()
        if not rec:
            self._show_message("Select a project to remove.", error=True)
            return
        pid = _project_id(rec)
        if pid is None:
            self._show_message("Cannot remove: missing project id.", error=True)
            return
        name = (
            rec.get("projectName")
            or rec.get("project_name")
            or "this project"
        )
        reply = QMessageBox.question(
            self,
            "Remove Project",
            f"Remove '{name}' from the list?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        token = self._get_token()
        if not token:
            self._show_message("Session expired. Please log in again.", error=True)
            return
        result = api_delete_project(pid, token=token)
        if result.get("success"):
            self._show_message(result.get("message", "Project removed."), error=False)
            self.refresh()
            return
        self._show_message(result.get("message", "Failed to remove project."), error=True)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        try:
            self._refresh_action_access()
            self.refresh()
        except Exception:
            traceback.print_exc()
