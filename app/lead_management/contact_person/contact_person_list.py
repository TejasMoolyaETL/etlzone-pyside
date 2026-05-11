"""Lead Contact Person list page."""

from __future__ import annotations

import ast
import json
import re
import traceback
from typing import Any, Callable

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.api import api_delete_contact_person, api_get_all_contact_persons
from core.app_preferences import format_datetime_display, is_datetime_field
from core.nav_access import collect_allowed_action_names, nav_action_visible
from core.user_context import get_nav_access_steps, get_user_profile
from ui.auto_hide_message import show_auto_hiding_message
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
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
)
from ui.styles import CONTEXT_MENU_STYLESHEET

# Header label, then tuple of JSON keys to try (first present wins). Matches lead-mgmt get-all response.
_LOOKUP_STYLE_KEYS: frozenset[str] = frozenset(
    {
        "city",
        "citySeq",
        "country",
        "countrySeq",
        "state",
        "stateSeq",
        "position",
        "positionSeq",
        "position_seq",
        "lead_contact_person_position",
        "designation",
        "status",
        "statusSeq",
        "status_seq",
        "lead_contact_person_status",
    }
)

# Columns that may carry master-setup objects (dict, [dict], or JSON string). Used to avoid mis-parsing other fields.
_MASTER_VALUE_COLUMN_KEYS: frozenset[str] = frozenset().union(
    *(
        keys
        for _, keys in (
            ("Position", ("position", "lead_contact_person_position", "designation", "positionSeq", "position_seq")),
            ("City", ("city", "citySeq")),
            ("State", ("state", "stateSeq")),
            ("Country", ("country", "countrySeq")),
            ("Status", ("status", "lead_contact_person_status", "statusSeq", "status_seq")),
        )
    ),
)

_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Contact Id", ("contactId", "id", "contactPersonId", "contact_person_id")),
    ("Name", ("name", "contactPersonName")),
    ("Email", ("email", "email1")),
    ("Mobile", ("mobile", "contactNo")),
    ("Position", ("position", "lead_contact_person_position", "designation", "positionSeq", "position_seq")),
    ("City", ("city", "citySeq")),
    ("State", ("state", "stateSeq")),
    ("Country", ("country", "countrySeq")),
    ("Status", ("status", "lead_contact_person_status", "statusSeq", "status_seq")),
    ("Hierarchy", ("hierarchy",)),
    ("URL", ("url",)),
    ("Created at", ("createdAt", "created_at")),
    ("Created by", ("createdBy", "created_by")),
    ("Modified at", ("modifiedAt", "modified_at")),
    ("Modified by", ("modifiedBy", "modified_by")),
)


def _is_master_lookup_shaped(val: Any) -> bool:
    if not isinstance(val, dict):
        return False
    if val.get("keyValue") is not None or val.get("key_value") is not None:
        return True
    inner = val.get("data") if isinstance(val.get("data"), dict) else None
    if inner is not None and (inner.get("keyValue") is not None or inner.get("key_value") is not None):
        return True
    return False


def _value_for_column(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    """Prefer a nested master object (dict with ``keyValue``) over a bare *Seq integer."""
    first_scalar: tuple[Any, str] | None = None
    for k in keys:
        if k not in row:
            continue
        val = row[k]
        if val is None:
            continue
        if _is_master_lookup_shaped(val):
            return val, k
        if first_scalar is None:
            first_scalar = (val, k)
    if first_scalar is not None:
        return first_scalar
    return None, keys[0]


def _lookup_style_display(obj: dict[str, Any]) -> str:
    for kk in ("keyValue", "key_value"):
        v = obj.get(kk)
        if v is not None and not isinstance(v, (dict, list)):
            return str(v)
    inner = obj.get("data") if isinstance(obj.get("data"), dict) else None
    if inner is not None:
        for kk in ("keyValue", "key_value"):
            v = inner.get(kk)
            if v is not None and not isinstance(v, (dict, list)):
                return str(v)
    for kk in ("name", "category"):
        v = obj.get(kk)
        if v is not None and not isinstance(v, (dict, list)):
            return str(v)
    return ""


def _unwrap_master_value(value: Any) -> dict[str, Any] | None:
    """Normalize dict / single-element list / JSON or Python-literal string to a master row dict."""
    if isinstance(value, dict):
        if _is_master_lookup_shaped(value):
            inner = value.get("data")
            return inner if isinstance(inner, dict) else value
        return None
    if isinstance(value, list) and len(value) == 1:
        return _unwrap_master_value(value[0])
    if isinstance(value, str):
        s = value.strip()
        if len(s) < 2:
            return None
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                parsed = ast.literal_eval(s)
            except (ValueError, SyntaxError):
                try:
                    parsed = json.loads(s)
                except (ValueError, TypeError):
                    parsed = None
            if parsed is not None:
                return _unwrap_master_value(parsed)
        return None
    return None


def _coerce_master_cell_text(value: Any) -> str | None:
    row = _unwrap_master_value(value)
    if row is None:
        return None
    text = _lookup_style_display(row)
    return text if text else None


def _format_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if value is None:
        return ""
    # Prevent false datetime formatting for identifiers like ``contactId``.
    id_like = tuple((key_candidates or (key,)))
    if any(str(k or "").strip().lower().endswith("id") for k in id_like):
        return str(value)
    # Master columns first: keys like ``lead_contact_person_position`` falsely match ``is_datetime_field`` ("on" in "person").
    if _MASTER_VALUE_COLUMN_KEYS.intersection(key_candidates):
        coerced = _coerce_master_cell_text(value)
        if coerced is not None:
            return coerced
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, dict):
        # Master-config / lookup objects (e.g. position) expose ``keyValue``; show that in grid cells.
        if key in _LOOKUP_STYLE_KEYS or "keyValue" in value or "key_value" in value:
            text = _lookup_style_display(value)
            return text if text else str(value)
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)
    if isinstance(value, str) and key in _LOOKUP_STYLE_KEYS:
        s = value.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                parsed = ast.literal_eval(s)
            except (ValueError, SyntaxError):
                try:
                    parsed = json.loads(s)
                except (ValueError, TypeError):
                    parsed = None
            if isinstance(parsed, dict):
                text = _lookup_style_display(parsed)
                return text if text else str(parsed)
        m = re.search(r"""['"]keyValue['"]\s*:\s*['"]([^'"]+)['"]""", s)
        if m:
            return m.group(1)
    if isinstance(value, list):
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


class ContactPersonListPage(QWidget):
    def __init__(
        self,
        on_create_clicked: Callable[[], None] | None = None,
        on_edit_clicked: Callable[[dict[str, Any], bool], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_create_clicked = on_create_clicked
        self.on_edit_clicked = on_edit_clicked
        self._source_rows: list[dict[str, Any]] = []
        self._filter_visible = False
        self._filter_apply_timer = QTimer(self)
        self._filter_apply_timer.setSingleShot(True)
        self._filter_apply_timer.setInterval(200)
        self._filter_apply_timer.timeout.connect(self._apply_column_filters_refresh)
        self._can_create = True
        self._can_display = True
        self._can_edit = True
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
        hl.addWidget(QLabel("Lead: Contact Person"))
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
        self._msg = QLabel()
        self._msg.setVisible(False)
        self.table = QTableWidget()
        apply_data_table_appearance(self.table)
        self.table.setSortingEnabled(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.itemDoubleClicked.connect(self._on_double_click)
        attach_table_copy_shortcut(self.table)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(self._msg)
        bl.addWidget(self.table, 1)
        layout.addWidget(body, 1)

    def _emit_create(self) -> None:
        if not self._can_create:
            show_auto_hiding_message(
                self,
                self._msg,
                "Create disabled: missing step access lead-contact-person-create.",
                error=True,
            )
            return
        if self.on_create_clicked:
            self.on_create_clicked()

    def _refresh_action_access(self) -> None:
        steps = get_nav_access_steps()
        if steps is None:
            self._can_create = True
            self._can_display = True
            self._can_edit = True
            self._can_delete = True
        else:
            allowed = collect_allowed_action_names(steps)
            self._can_create = nav_action_visible("Lead: Contact Person", "create", allowed)
            self._can_display = nav_action_visible("Lead: Contact Person", "display", allowed)
            self._can_edit = nav_action_visible("Lead: Contact Person", "edit", allowed)
            self._can_delete = nav_action_visible("Lead: Contact Person", "delete", allowed)
        self._create_btn.setEnabled(self._can_create)
        self._create_btn.setToolTip("" if self._can_create else "Require Permission.")

    def _data_row_offset(self) -> int:
        return data_row_offset(self._filter_visible)

    def _schedule_filter_apply(self) -> None:
        if self._filter_visible:
            self._filter_apply_timer.start()

    def _filtered_source_rows(self) -> list[dict[str, Any]]:
        return filter_dict_rows_by_column_edits(
            self._source_rows,
            self.table,
            list(_COLUMNS),
            self._filter_visible,
            _value_for_column,
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
            for c, (_, keys) in enumerate(_COLUMNS):
                raw, key_used = _value_for_column(row, keys)
                text = _format_cell(raw, key_used, keys)
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(tr, c, item)
        sync_vertical_header_labels(self.table, filter_visible=self._filter_visible, data_row_count=len(rows))
        resize_data_table_columns_to_content(
            self.table,
            list(_COLUMNS),
            self._source_rows,
            _value_for_column,
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

    def _token(self) -> str | None:
        p = get_user_profile()
        t = p.get("token") or p.get("accessToken") or p.get("access_token") or p.get("jwt")
        return str(t) if t else None

    def refresh(self) -> None:
        result = api_get_all_contact_persons(token=self._token())
        if not result.get("success"):
            show_auto_hiding_message(self, self._msg, str(result.get("message") or "Failed to load contact persons."), error=True)
            self._show_empty_table()
            return
        rows = result.get("data") or []
        self._source_rows = [r for r in rows if isinstance(r, dict)]
        self.table.clear()
        self.table.setColumnCount(len(_COLUMNS))
        self.table.setHorizontalHeaderLabels([h for h, _ in _COLUMNS])
        rows_to_show = self._filtered_source_rows() if self._filter_visible else list(self._source_rows)
        self._write_data_rows(rows_to_show)

    def _get_contact_at_row(self, row: int) -> dict[str, Any] | None:
        if row < self._data_row_offset() or row >= self.table.rowCount():
            return None
        it = self.table.item(row, 0)
        data = it.data(Qt.ItemDataRole.UserRole) if it else None
        return data if isinstance(data, dict) else None

    def _contact_at_pos(self, pos: QPoint) -> dict[str, Any] | None:
        idx = self.table.indexAt(pos)
        if idx.isValid():
            return self._get_contact_at_row(idx.row())
        item = self.table.itemAt(pos)
        if item:
            return self._get_contact_at_row(item.row())
        return None

    def _on_double_click(self, item: QTableWidgetItem) -> None:
        if item.row() < self._data_row_offset():
            return
        row = self._get_contact_at_row(item.row())
        if not self._can_display:
            show_auto_hiding_message(self, self._msg, "Require Permission.", error=True)
            return
        if row and self.on_edit_clicked:
            self.on_edit_clicked(row, False)

    def _on_context_menu(self, pos: QPoint) -> None:
        clicked_item = self.table.itemAt(pos)
        if clicked_item is not None and clicked_item.row() >= self._data_row_offset():
            self.table.setCurrentCell(clicked_item.row(), clicked_item.column())
            self.table.selectRow(clicked_item.row())
        row = self._contact_at_pos(pos)
        if row is None and clicked_item is not None and clicked_item.row() >= self._data_row_offset():
            row = self._get_contact_at_row(clicked_item.row())
        menu = QMenu(self)
        menu.setStyleSheet(
            CONTEXT_MENU_STYLESHEET
            + " QMenu::item:disabled { background: #9ca3af; color: #6b7280; }"
            + " QMenu::item:disabled:selected, QMenu::item:disabled:hover {"
            + " background: #9ca3af; color: #6b7280; }"
        )
        add = menu.addAction("Add Contact Person")
        view = menu.addAction("Display Contact Person")
        edit = menu.addAction("Edit Contact Person")
        delete = menu.addAction("Delete Contact Person")
        add.setEnabled(self._can_create)
        has_row = row is not None
        view.setEnabled(has_row and self.on_edit_clicked is not None and self._can_display)
        edit.setEnabled(has_row and self.on_edit_clicked is not None and self._can_edit)
        delete.setEnabled(has_row and self._can_delete)
        act = menu.exec(QCursor.pos())
        if act == add:
            self._emit_create()
        elif act == view and row and self.on_edit_clicked:
            if not self._can_display:
                show_auto_hiding_message(self, self._msg, "Require Permission.", error=True)
                return
            self.on_edit_clicked(row, False)
        elif act == edit and row and self.on_edit_clicked:
            if not self._can_edit:
                show_auto_hiding_message(self, self._msg, "Require Permission.", error=True)
                return
            self.on_edit_clicked(row, True)
        elif act == delete and row:
            if not self._can_delete:
                show_auto_hiding_message(self, self._msg, "Require Permission.", error=True)
                return
            pid = row.get("contactId") or row.get("contactPersonId") or row.get("id")
            if pid is None:
                return
            if QMessageBox.question(
                self,
                "Delete Contact Person",
                "Are you sure you want to delete this contact person?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
            res = api_delete_contact_person(pid, token=self._token())
            show_auto_hiding_message(self, self._msg, str(res.get("message") or ""), error=not bool(res.get("success")))
            if res.get("success"):
                self.refresh()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        try:
            self._refresh_action_access()
            self.refresh()
        except Exception:
            traceback.print_exc()
