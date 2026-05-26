"""Comment panel for selected DMT Object Tracker row (Lead list–style table + dialogs)."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QShowEvent, QTextDocument
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.lead_management.leads.lead_create import _DateTimePickerField
from core.api import (
    api_add_object_tracker_comment,
    api_delete_object_tracker_comment_by_id,
    api_get_all_dmt_users,
    api_get_object_tracker_comments_by_object_id,
    api_update_object_tracker_comment_by_id,
)
from core.app_preferences import format_field_display_value, to_utc_iso
from core.nav_access import collect_allowed_action_names, nav_action_visible
from core.user_context import get_nav_access_steps, get_user_profile
from ui.auto_hide_message import show_auto_hiding_message
from ui.data_table import (
    apply_data_table_appearance,
    attach_table_copy_shortcut,
    clear_filter_row_widgets,
    data_row_offset,
    filter_dict_rows_by_column_edits,
    render_dict_rows_table,
    saved_filter_texts,
)
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET,
    MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET,
    MODAL_FIELD_HEIGHT_PX,
    MODAL_FIELD_LABEL_STYLE,
)
from ui.styles import CONTEXT_MENU_STYLESHEET

_OBJECT_TRACKER_COMMENT_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Comment By", ("commentByUsername", "commentBy", "username")),
    ("Comment On Date", ("commentOnDate", "createdAt")),
    ("Comment", ("comment", "commentText")),
    ("Status", ("status",)),
    ("Created At", ("createdAt",)),
    ("Created By", ("createdBy",)),
    ("Modified At", ("modifiedAt",)),
    ("Modified By", ("modifiedBy",)),
)

_COMMENT_BTN_STYLE = (
    "QPushButton {"
    " font-size: 10px;"
    " font-weight: 600;"
    " border: 1px solid #cbd5e1;"
    " border-radius: 4px;"
    " background: #ffffff;"
    " color: #334155;"
    " padding: 0 8px;"
    "}"
    "QPushButton:hover:enabled { background: #f8fafc; border-color: #94a3b8; }"
    "QPushButton:pressed:enabled { background: #f1f5f9; border-color: #64748b; }"
    "QPushButton:disabled {"
    " background: #e5e7eb;"
    " color: #9ca3af;"
    " border: 1px solid #d1d5db;"
    "}"
    "QPushButton:disabled:hover, QPushButton:disabled:pressed {"
    " background: #e5e7eb;"
    " color: #9ca3af;"
    " border: 1px solid #d1d5db;"
    "}"
)


def _value_for_column(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    return None


def _value_for_comment_column(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    value = _value_for_column(row, keys)
    return value, keys[0] if keys else ""


def _object_tracker_comment_status_display(value: Any) -> str:
    """Backend ``status`` may be ``{ category, keyValue, seq }``; show ``keyValue`` for the table."""
    if isinstance(value, dict):
        kv = value.get("keyValue")
        if kv is not None and str(kv).strip():
            return str(kv).strip()
        cat = value.get("category")
        if cat is not None and str(cat).strip():
            return str(cat).strip()
        seq = value.get("seq")
        if seq is not None and str(seq).strip():
            return str(seq).strip()
        return ""
    if value is None:
        return ""
    return format_field_display_value(value, "status", ("status",))


def _plain_comment_preview(value: Any, *, max_len: int = 2000) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    low = s.lower()
    if "<!doctype" in low or "<html" in low or "qrichtext" in low or ("<p" in low and "</p>" in low):
        doc = QTextDocument()
        doc.setHtml(s)
        s = (doc.toPlainText() or "").strip()
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def _display_cell(value: Any, key: str, key_candidates: tuple[str, ...]) -> str:
    keys = (key, *key_candidates) if key_candidates else (key,)
    if key == "status" or "status" in keys:
        return _object_tracker_comment_status_display(value)
    if "comment" in keys or key in ("comment", "commentText"):
        return _plain_comment_preview(value)
    return format_field_display_value(value, key, key_candidates)


def _tracker_id_from_record(rec: dict[str, Any] | None) -> str:
    if not isinstance(rec, dict):
        return ""
    for k in ("objectTrackerId", "trackerId", "id"):
        v = rec.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _comment_id_from_row(row: dict[str, Any]) -> Any:
    return row.get("commentId") or row.get("id")


def _auth_token() -> str | None:
    profile = get_user_profile()
    token = (
        profile.get("token")
        or profile.get("accessToken")
        or profile.get("access_token")
        or profile.get("jwt")
        or profile.get("id_token")
    )
    text = str(token or "").strip()
    return text if text else None


def _dmt_user_row_username(row: dict[str, Any]) -> str:
    """Pick a login-style string from a DMT user row for ``commentByUsername``."""
    for k in ("userName", "username", "loginId", "login_id", "email"):
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


class _ObjectTrackerCommentDialog(QDialog):
    """Add / view–edit object tracker comment (mirrors Lead comment dialog layout)."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        title: str,
        object_tracker_id: str = "",
        initial: dict[str, Any] | None = None,
        view_edit_mode: bool = False,
        allow_comment_edit: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setStyleSheet("QDialog { background: #ffffff; }")
        self._view_edit_mode = bool(view_edit_mode)
        self._allow_comment_edit = bool(allow_comment_edit)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        self._msg = QLabel()
        self._msg.setWordWrap(True)
        self._msg.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._msg.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._msg.setVisible(False)
        lay.addWidget(self._msg)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._by_combo = QComboBox()
        self._date_edit = _DateTimePickerField(MODAL_FIELD_HEIGHT_PX)
        self._comment_edit = QPlainTextEdit()
        apply_form_combobox_field(self._by_combo, height_px=MODAL_FIELD_HEIGHT_PX)
        self._comment_edit.setStyleSheet(
            "QPlainTextEdit { font-size: 10px; padding: 4px 8px; border: 1px solid #e2e8f0; border-radius: 4px; background: #ffffff; }"
        )
        self._comment_edit.setMinimumHeight(140)
        self._comment_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        by_lbl = QLabel("Comment By Username:")
        date_lbl = QLabel("Comment On Date:")
        c_lbl = QLabel("Comment:")
        by_lbl.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        date_lbl.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        c_lbl.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        form.addRow(by_lbl, self._by_combo)
        form.addRow(date_lbl, self._date_edit)
        form.addRow(c_lbl, self._comment_edit)
        lay.addLayout(form)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #cbd5e1; border: none; max-height: 1px;")
        lay.addWidget(sep)

        ok_btn = QPushButton("Save")
        ok_btn.setFixedWidth(100)
        ok_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        ok_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)
        cancel_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

        src = initial or {}
        self._populate_comment_by_combo()
        self._set_comment_by_value(
            str(src.get("commentByUsername") or src.get("commentBy") or src.get("username") or "")
        )
        raw_comment_on_date = src.get("commentOnDate") or src.get("createdAt") or ""
        if str(raw_comment_on_date or "").strip():
            self._date_edit.set_iso_timestamp(raw_comment_on_date)
        else:
            self._date_edit.set_defaults_today_midnight()
        raw_comment = str(src.get("comment") or src.get("commentText") or "")
        self._comment_edit.setPlainText(_plain_comment_preview(raw_comment, max_len=100_000))

        if self._view_edit_mode:
            self._set_read_only(True)
        else:
            self._set_read_only(False)

        self._back_btn = QPushButton("Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)
        self._back_btn.clicked.connect(self.reject)
        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setFixedWidth(100)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)
        self._edit_btn.clicked.connect(lambda: self._set_read_only(False))
        if self._view_edit_mode and not self._allow_comment_edit:
            self._edit_btn.setVisible(False)

        display_btns = QWidget()
        db = QHBoxLayout(display_btns)
        db.setContentsMargins(0, 0, 0, 0)
        db.setSpacing(12)
        db.setAlignment(Qt.AlignmentFlag.AlignLeft)
        db.addWidget(self._edit_btn)
        db.addWidget(self._back_btn)
        db.addStretch(1)

        edit_btns = QWidget()
        eb = QHBoxLayout(edit_btns)
        eb.setContentsMargins(0, 0, 0, 0)
        eb.setSpacing(12)
        eb.setAlignment(Qt.AlignmentFlag.AlignLeft)
        eb.addWidget(ok_btn)
        eb.addWidget(cancel_btn)
        eb.addStretch(1)

        self._btn_stack = QStackedWidget()
        self._btn_stack.setFrameShape(QFrame.Shape.NoFrame)
        self._btn_stack.setStyleSheet("QStackedWidget { border: none; background: transparent; }")
        self._btn_stack.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._btn_stack.addWidget(display_btns)
        self._btn_stack.addWidget(edit_btns)
        if self._view_edit_mode:
            self._btn_stack.setCurrentIndex(0)
        else:
            self._btn_stack.setCurrentIndex(1)
        lay.addWidget(self._btn_stack)

    def add_payload(self) -> dict[str, Any]:
        """Fields for create API (plain comment + username + date)."""
        iso_local = self._date_edit.iso_timestamp()
        return {
            "commentByUsername": str(self._by_combo.currentData() or self._by_combo.currentText() or "").strip(),
            "commentOnDate": (to_utc_iso(iso_local) or iso_local or "")[:10],
            "comment": self._comment_edit.toPlainText().strip(),
        }

    def update_comment_text(self) -> str:
        """Body for update-by-id API (comment text only)."""
        return self._comment_edit.toPlainText().strip()

    def _set_read_only(self, read_only: bool) -> None:
        self._by_combo.setEnabled(not read_only)
        self._date_edit.setEnabled(not read_only)
        self._comment_edit.setReadOnly(read_only)
        self._comment_edit.setStyleSheet(
            (
                "QPlainTextEdit { font-size: 10px; padding: 4px 8px; border: 1px solid #e2e8f0; border-radius: 4px; "
                "background: #f1f5f9; color: #64748b; }"
            )
            if read_only
            else "QPlainTextEdit { font-size: 10px; padding: 4px 8px; border: 1px solid #e2e8f0; border-radius: 4px; background: #ffffff; }"
        )
        if hasattr(self, "_btn_stack"):
            self._btn_stack.setCurrentIndex(0 if read_only else 1)

    def _populate_comment_by_combo(self) -> None:
        self._by_combo.blockSignals(True)
        self._by_combo.clear()
        self._by_combo.addItem("Select username…", "")
        self._msg.setVisible(False)
        collected: set[str] = set()
        result = api_get_all_dmt_users(token=_auth_token())
        rows = result.get("data") if isinstance(result.get("data"), list) else []
        if result.get("success") and isinstance(rows, list):
            names: list[str] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                u = _dmt_user_row_username(row)
                if u and u not in collected:
                    collected.add(u)
                    names.append(u)
            for u in sorted(names, key=lambda s: s.lower()):
                self._by_combo.addItem(u, u)
        else:
            self._msg.setText(str(result.get("message") or "Could not load DMT user list."))
            self._msg.setVisible(True)
        profile = get_user_profile()
        uname = str(
            profile.get("username") or profile.get("userName") or profile.get("user_name") or ""
        ).strip()
        if uname and uname not in collected:
            self._by_combo.addItem(uname, uname)
            collected.add(uname)
        self._by_combo.setCurrentIndex(0)
        self._by_combo.blockSignals(False)

    def _set_comment_by_value(self, value: str) -> None:
        target = str(value or "").strip()
        if not target:
            return
        idx = self._by_combo.findData(target)
        if idx < 0:
            idx = self._by_combo.findText(target)
        if idx < 0:
            self._by_combo.addItem(target, target)
            idx = self._by_combo.findData(target)
        if idx >= 0:
            self._by_combo.setCurrentIndex(idx)


class ObjectTrackerCommentPanel(QWidget):
    """Lead-style comments: message strip, Add/Update/Delete, table."""

    def __init__(self, vp: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vp = vp
        self._comment_rows: list[dict[str, Any]] = []
        self._comment_filter_visible = False
        self._comment_filter_timer = QTimer(self)
        self._comment_filter_timer.setSingleShot(True)
        self._comment_filter_timer.setInterval(200)
        self._comment_filter_timer.timeout.connect(self._refresh_comment_table_view)
        self._can_comment_create = True
        self._can_comment_display = True
        self._can_comment_edit = True
        self._can_comment_delete = True
        self._build_ui()
        reg = getattr(vp, "register_comment_context_listener", None)
        if callable(reg):
            reg(self._on_tracker_context_changed)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._comment_message_label = QLabel()
        self._comment_message_label.setVisible(False)
        layout.addWidget(self._comment_message_label)
        layout.addSpacing(2)

        comment_actions_row = QHBoxLayout()
        comment_actions_row.setContentsMargins(0, 0, 0, 0)
        comment_actions_row.setSpacing(6)
        _comment_btn_h = 20
        _comment_btn_w = 62
        self._comment_add_btn = QPushButton("Add")
        self._comment_add_btn.setFixedSize(_comment_btn_w, _comment_btn_h)
        self._comment_add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._comment_add_btn.setStyleSheet(_COMMENT_BTN_STYLE)
        self._comment_add_btn.clicked.connect(self._on_add_comment_clicked)
        self._comment_update_btn = QPushButton("Update")
        self._comment_update_btn.setFixedSize(_comment_btn_w, _comment_btn_h)
        self._comment_update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._comment_update_btn.setStyleSheet(_COMMENT_BTN_STYLE)
        self._comment_update_btn.clicked.connect(self._on_update_comment_clicked)
        self._comment_delete_btn = QPushButton("Delete")
        self._comment_delete_btn.setFixedSize(_comment_btn_w, _comment_btn_h)
        self._comment_delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._comment_delete_btn.setStyleSheet(_COMMENT_BTN_STYLE)
        self._comment_delete_btn.clicked.connect(self._on_delete_comment_clicked)
        comment_actions_row.addStretch()
        self._comment_filters_btn = QPushButton("Filters")
        self._comment_filters_btn.setCheckable(True)
        self._comment_filters_btn.setFixedSize(62, _comment_btn_h)
        self._comment_filters_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._comment_filters_btn.setStyleSheet(_COMMENT_BTN_STYLE)
        self._comment_filters_btn.toggled.connect(self._on_comment_filters_toggled)
        comment_actions_row.addWidget(self._comment_filters_btn)
        comment_actions_row.addWidget(self._comment_add_btn)
        comment_actions_row.addWidget(self._comment_update_btn)
        comment_actions_row.addWidget(self._comment_delete_btn)
        layout.addLayout(comment_actions_row)

        self._comment_table = QTableWidget()
        apply_data_table_appearance(self._comment_table)
        self._comment_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._comment_table.customContextMenuRequested.connect(self._on_comment_context_menu)
        self._comment_table.itemDoubleClicked.connect(self._on_comment_double_clicked)
        attach_table_copy_shortcut(self._comment_table)
        layout.addWidget(self._comment_table, 1)

        self._refresh_comment_access()

    def _on_tracker_context_changed(self) -> None:
        self._refresh_comments_for_selected_tracker(show_message=False)

    def _refresh_comment_access(self) -> None:
        steps = get_nav_access_steps()
        lbl = "DMT - Object List Tracker"
        if steps is None:
            self._can_comment_create = True
            self._can_comment_display = True
            self._can_comment_edit = True
            self._can_comment_delete = True
        else:
            allowed = collect_allowed_action_names(steps)
            self._can_comment_create = nav_action_visible(lbl, "comment_create", allowed)
            self._can_comment_display = nav_action_visible(lbl, "comment_display", allowed)
            self._can_comment_edit = nav_action_visible(lbl, "comment_edit", allowed)
            self._can_comment_delete = nav_action_visible(lbl, "comment_delete", allowed)
        self._comment_add_btn.setEnabled(self._can_comment_create)
        self._comment_add_btn.setToolTip("" if self._can_comment_create else "Require Permission.")
        can_view_or_edit = self._can_comment_display or self._can_comment_edit
        self._comment_update_btn.setEnabled(can_view_or_edit)
        self._comment_update_btn.setToolTip("" if can_view_or_edit else "Require Permission.")
        self._comment_delete_btn.setEnabled(self._can_comment_delete)
        self._comment_delete_btn.setToolTip("" if self._can_comment_delete else "Require Permission.")

    def _selected_tracker_id(self) -> str:
        row = self._vp.get_selected_row() if self._vp is not None else None
        return _tracker_id_from_record(row if isinstance(row, dict) else None)

    def _comment_data_row_offset(self) -> int:
        return data_row_offset(self._comment_filter_visible)

    def _on_comment_filters_toggled(self, checked: bool) -> None:
        self._comment_filter_visible = checked
        if not checked:
            clear_filter_row_widgets(self._comment_table)
        self._refresh_comment_table_view()

    def _schedule_comment_filter_apply(self) -> None:
        if self._comment_filter_visible:
            self._comment_filter_timer.start()

    def _filtered_comment_rows(self) -> list[dict[str, Any]]:
        rows = list(self._comment_rows)
        if not self._comment_filter_visible:
            return rows
        return filter_dict_rows_by_column_edits(
            rows,
            self._comment_table,
            list(_OBJECT_TRACKER_COMMENT_COLUMNS),
            True,
            _value_for_comment_column,
            _display_cell,
        )

    def _refresh_comment_table_view(self) -> None:
        saved = saved_filter_texts(self._comment_table) if self._comment_filter_visible else None
        render_dict_rows_table(
            self._comment_table,
            self._filtered_comment_rows(),
            list(_OBJECT_TRACKER_COMMENT_COLUMNS),
            filter_visible=self._comment_filter_visible,
            value_for_column=_value_for_comment_column,
            format_cell=_display_cell,
            on_filter_text_changed=self._schedule_comment_filter_apply,
            saved_filter_texts_list=saved,
            user_role_column=0,
        )

    def _render_comment_table(self) -> None:
        self._refresh_comment_table_view()

    def _refresh_comments_for_selected_tracker(self, *, show_message: bool) -> None:
        self._refresh_comment_access()
        tid = self._selected_tracker_id()
        if not tid:
            self._comment_rows = []
            self._render_comment_table()
            if show_message:
                show_auto_hiding_message(
                    self,
                    self._comment_message_label,
                    "Select an object tracker row to load comments.",
                    error=True,
                )
            return
        result = api_get_object_tracker_comments_by_object_id(tid, token=_auth_token())
        if not result.get("success"):
            self._comment_rows = []
            self._render_comment_table()
            show_auto_hiding_message(
                self,
                self._comment_message_label,
                str(result.get("message") or "Failed to load comments."),
                error=True,
            )
            return
        self._comment_rows = [r for r in (result.get("comments") or []) if isinstance(r, dict)]
        self._render_comment_table()
        if show_message:
            show_auto_hiding_message(
                self,
                self._comment_message_label,
                str(result.get("message") or "Comments loaded."),
                error=False,
            )

    def _comment_at_table_row(self, table_row: int) -> dict[str, Any] | None:
        if table_row < self._comment_data_row_offset():
            return None
        item = self._comment_table.item(table_row, 0)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _comment_at_pos(self, pos: QPoint) -> dict[str, Any] | None:
        idx = self._comment_table.indexAt(pos)
        if idx.isValid():
            return self._comment_at_table_row(idx.row())
        item = self._comment_table.itemAt(pos)
        if item:
            return self._comment_at_table_row(item.row())
        return None

    def _on_comment_double_clicked(self, _item: QTableWidgetItem) -> None:
        self._on_update_comment_clicked()

    def _on_comment_context_menu(self, pos: QPoint) -> None:
        tid = self._selected_tracker_id()
        selected = self._comment_at_pos(pos)
        menu = QMenu(self)
        menu.setStyleSheet(
            CONTEXT_MENU_STYLESHEET
            + " QMenu::item:disabled { background: #9ca3af; color: #6b7280; }"
            + " QMenu::item:disabled:selected, QMenu::item:disabled:hover {"
            + " background: #9ca3af; color: #6b7280; }"
        )
        add_action = menu.addAction("Add Comment")
        update_action = menu.addAction("Update Comment")
        delete_action = menu.addAction("Delete Comment")
        add_action.setEnabled(bool(tid) and self._can_comment_create)
        can_view = self._can_comment_display or self._can_comment_edit
        update_action.setEnabled(selected is not None and can_view)
        delete_action.setEnabled(selected is not None and self._can_comment_delete)
        action = menu.exec(QCursor.pos())
        if action == add_action:
            self._on_add_comment_clicked()
        elif action == update_action:
            if selected is not None:
                row = self._comment_table.indexAt(pos).row()
                if row >= 0:
                    self._comment_table.selectRow(row)
            self._on_update_comment_clicked()
        elif action == delete_action:
            if selected is not None:
                row = self._comment_table.indexAt(pos).row()
                if row >= 0:
                    self._comment_table.selectRow(row)
            self._on_delete_comment_clicked()

    def _on_add_comment_clicked(self) -> None:
        if not self._can_comment_create:
            show_auto_hiding_message(self, self._comment_message_label, "Require Permission.", error=True)
            return
        tid = self._selected_tracker_id()
        if not tid:
            show_auto_hiding_message(self, self._comment_message_label, "Select an object tracker row first.", error=True)
            return
        dlg = _ObjectTrackerCommentDialog(
            self,
            title="Add Comment",
            object_tracker_id=str(tid),
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        body = dlg.add_payload()
        if not body.get("comment"):
            show_auto_hiding_message(self, self._comment_message_label, "Comment is required.", error=True)
            return
        result = api_add_object_tracker_comment(
            tid,
            body["comment"],
            token=_auth_token(),
            comment_by_username=body.get("commentByUsername") or None,
            comment_on_date=body.get("commentOnDate") or None,
        )
        show_auto_hiding_message(
            self,
            self._comment_message_label,
            str(result.get("message") or ("Comment added." if result.get("success") else "Add comment failed.")),
            error=not bool(result.get("success")),
        )
        if result.get("success"):
            self._refresh_comments_for_selected_tracker(show_message=False)

    def _on_update_comment_clicked(self) -> None:
        if not (self._can_comment_display or self._can_comment_edit):
            show_auto_hiding_message(self, self._comment_message_label, "Require Permission.", error=True)
            return
        row = self._comment_table.currentRow()
        data = self._comment_at_table_row(row)
        if not data:
            show_auto_hiding_message(self, self._comment_message_label, "Select a comment row to update.", error=True)
            return
        comment_id = _comment_id_from_row(data)
        if comment_id is None or str(comment_id).strip() == "":
            show_auto_hiding_message(self, self._comment_message_label, "Selected comment has no comment ID.", error=True)
            return
        dlg = _ObjectTrackerCommentDialog(
            self,
            title="Object Tracker Comment",
            object_tracker_id=self._selected_tracker_id(),
            initial=data,
            view_edit_mode=True,
            allow_comment_edit=self._can_comment_edit,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if not self._can_comment_edit:
            return
        text = dlg.update_comment_text()
        if not text:
            show_auto_hiding_message(self, self._comment_message_label, "Comment is required.", error=True)
            return
        result = api_update_object_tracker_comment_by_id(comment_id, text, token=_auth_token())
        show_auto_hiding_message(
            self,
            self._comment_message_label,
            str(result.get("message") or ("Comment updated." if result.get("success") else "Update comment failed.")),
            error=not bool(result.get("success")),
        )
        if result.get("success"):
            self._refresh_comments_for_selected_tracker(show_message=False)

    def _on_delete_comment_clicked(self) -> None:
        if not self._can_comment_delete:
            show_auto_hiding_message(self, self._comment_message_label, "Require Permission.", error=True)
            return
        row = self._comment_table.currentRow()
        data = self._comment_at_table_row(row)
        if not data:
            show_auto_hiding_message(self, self._comment_message_label, "Select a comment row to delete.", error=True)
            return
        comment_id = _comment_id_from_row(data)
        if comment_id is None or str(comment_id).strip() == "":
            show_auto_hiding_message(self, self._comment_message_label, "Selected comment has no comment ID.", error=True)
            return
        reply = QMessageBox.question(
            self,
            "Delete Comment",
            f"Are you sure you want to delete comment '{comment_id}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = api_delete_object_tracker_comment_by_id(comment_id, token=_auth_token())
        show_auto_hiding_message(
            self,
            self._comment_message_label,
            str(result.get("message") or ("Comment deleted." if result.get("success") else "Delete comment failed.")),
            error=not bool(result.get("success")),
        )
        if result.get("success"):
            self._refresh_comments_for_selected_tracker(show_message=False)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_comments_for_selected_tracker(show_message=False)
