"""View / edit API Dev Task page."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.api import api_update_api_task_by_id
from core.app_preferences import format_field_display_value
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_READONLY_INPUT_STYLE as READONLY_INPUT_STYLE,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
)
from ui.post_save_navigation import navigate_after_no_changes, schedule_after_success
from ui.searchable_form_combo import wire_searchable_labeled_rows_combo
from ui.widgets.required_label import field_caption_label, labeled_field_block

_COL1 = (
    ("Task Id", ("taskId", "id")),
    ("API Id", ("apiId", "api_id")),
    ("Summary*", ("summary",)),
    ("Description*", ("desc", "description")),
    ("Status", ("status",)),
)
_COL2 = (
    ("Created By", ("createdBy", "created_by")),
    ("Created At", ("createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified At", ("modifiedAt", "modified_at", "updatedAt", "updated_at")),
)
_FIELDS = _COL1 + _COL2
_READONLY = frozenset(
    {
        "taskId",
        "id",
        "apiId",
        "api_id",
        "createdBy",
        "created_by",
        "createdAt",
        "created_at",
        "modifiedBy",
        "modified_by",
        "modifiedAt",
        "modified_at",
        "updatedAt",
        "updated_at",
    }
)


def _value(rec: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in rec:
            return rec.get(k)
    return None


def _display_value(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    return format_field_display_value(value, key, key_candidates)


def _task_id(rec: dict[str, Any]) -> int | str | None:
    return rec.get("taskId") or rec.get("id")


class ViewAPIDevTaskPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._task: dict[str, Any] = {}
        self._edits: dict[str, QWidget] = {}
        self._editable: list[str] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QWidget()
        header.setStyleSheet(FORM_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        hl.addWidget(QLabel("API Dev Task"))
        hl.addStretch()
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        card = QWidget()
        card.setObjectName("profileCard")
        card.setMinimumWidth(520)
        card.setMaximumWidth(860)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        def add_field(col: int, idx: int, label_text: str, keys: tuple[str, ...]) -> None:
            canonical = keys[0]
            if canonical not in _READONLY:
                self._editable.append(canonical)
            label_widget = field_caption_label(label_text, LABEL_STYLE)
            if canonical == "status":
                w = QComboBox()
                apply_form_combobox_field(w, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX, min_width=240)
                _task_statuses = ("ACTIVE", "INACTIVE", "OPEN", "IN_PROGRESS", "DONE", "BLOCKED")
                wire_searchable_labeled_rows_combo(
                    w,
                    rows=[(s, s) for s in _task_statuses],
                    search_field_label="Status",
                    default_display_text="ACTIVE",
                )
                w.setEnabled(False)
                self._edits[canonical] = w
            else:
                w = QLineEdit()
                w.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
                w.setMinimumWidth(240)
                w.setReadOnly(True)
                w.setStyleSheet(READONLY_INPUT_STYLE)
                self._edits[canonical] = w
            grid.addWidget(labeled_field_block(label_widget, w), idx, col)

        for i, (lt, keys) in enumerate(_COL1):
            add_field(0, i, lt, keys)
        for i, (lt, keys) in enumerate(_COL2):
            add_field(1, i, lt, keys)

        self._back_btn = QPushButton("Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._back_btn.clicked.connect(self._handle_back)

        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setFixedWidth(100)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._edit_btn.clicked.connect(self._handle_edit)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedWidth(100)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._cancel_btn.clicked.connect(self._handle_cancel)

        self._save_btn = QPushButton("Save")
        self._save_btn.setFixedWidth(100)
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._save_btn.clicked.connect(self._handle_save)

        display_btns = QWidget()
        dbl = QHBoxLayout(display_btns)
        dbl.setContentsMargins(0, 0, 0, 0)
        dbl.setSpacing(12)
        dbl.addWidget(self._edit_btn)
        dbl.addWidget(self._back_btn)

        edit_btns = QWidget()
        ebl = QHBoxLayout(edit_btns)
        ebl.setContentsMargins(0, 0, 0, 0)
        ebl.setSpacing(12)
        ebl.addWidget(self._save_btn)
        ebl.addWidget(self._cancel_btn)

        self._btn_stack = QStackedWidget()
        self._btn_stack.addWidget(display_btns)
        self._btn_stack.addWidget(edit_btns)

        self._error_label = QLabel()
        self._error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)

        btn_row = max(len(_COL1), len(_COL2))
        grid.addWidget(self._error_label, btn_row, 0, 1, 2)
        grid.addWidget(self._btn_stack, btn_row + 1, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
        card_layout.addLayout(grid)
        content_layout.addWidget(card)
        content_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)
        self._switch_to_view_mode()

    def set_task(self, task: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        self._task = dict(task) if task else {}
        self._refresh_values()
        if edit_mode and self._task:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

    def _refresh_values(self) -> None:
        for _lt, keys in _FIELDS:
            canonical = keys[0]
            val = _value(self._task, keys)
            w = self._edits.get(canonical)
            if isinstance(w, QLineEdit):
                w.setText(_display_value(val, canonical, keys))
            elif isinstance(w, QComboBox):
                txt = _display_value(val, canonical, keys)
                if txt and w.findText(txt) < 0:
                    w.addItem(txt, txt)
                w.setCurrentText(txt or "ACTIVE")

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = profile.get("token") or profile.get("accessToken") or profile.get("access_token") or profile.get("jwt")
        return str(token) if token else None

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self._error_label)
        self._error_label.setText("")
        self._error_label.setVisible(False)

    def _edit_value(self, key: str) -> str:
        w = self._edits.get(key)
        if isinstance(w, QLineEdit):
            return w.text().strip()
        if isinstance(w, QComboBox):
            return w.currentText().strip()
        return ""

    def _switch_to_view_mode(self) -> None:
        for key in self._editable:
            w = self._edits.get(key)
            if isinstance(w, QLineEdit):
                w.setReadOnly(True)
                w.setStyleSheet(READONLY_INPUT_STYLE)
            elif isinstance(w, QComboBox):
                w.setEnabled(False)
        self._btn_stack.setCurrentIndex(0)

    def _handle_back(self) -> None:
        if self.on_back:
            self.on_back()

    def _handle_edit(self) -> None:
        self._clear_error()
        for key in self._editable:
            w = self._edits.get(key)
            if isinstance(w, QLineEdit):
                w.setReadOnly(False)
                w.setStyleSheet(INPUT_STYLE)
            elif isinstance(w, QComboBox):
                w.setEnabled(True)
        self._btn_stack.setCurrentIndex(1)

    def _has_unsaved_changes(self) -> bool:
        for _lt, keys in _FIELDS:
            canonical = keys[0]
            if canonical in _READONLY:
                continue
            current = self._edit_value(canonical)
            original = _display_value(_value(self._task, keys), canonical, keys).strip()
            if current != original:
                return True
        return False

    def _handle_cancel(self) -> None:
        if not self._has_unsaved_changes():
            self._clear_error()
            self._refresh_values()
            self._switch_to_view_mode()
            return
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Discard and leave?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Discard:
            self._clear_error()
            self._refresh_values()
            self._switch_to_view_mode()

    def is_edit_mode(self) -> bool:
        return self._btn_stack.currentIndex() == 1

    def _handle_save(self) -> None:
        task_id = _task_id(self._task)
        if task_id is None:
            self._show_error("Task ID is missing.")
            return
        summary = self._edit_value("summary")
        desc = self._edit_value("desc")
        status = self._edit_value("status")
        if not summary:
            self._show_error("Summary is required.")
            return
        if not desc:
            self._show_error("Description is required.")
            return
        result = api_update_api_task_by_id(
            task_id,
            token=self._token(),
            summary=summary,
            desc=desc,
            status=status,
        )
        if not result.get("success"):
            self._show_error(str(result.get("message") or "Failed to update API task."))
            return
        self._task.update({"summary": summary, "desc": desc, "status": status})
        self._refresh_values()
        self._switch_to_view_mode()
        self._show_success(str(result.get("message") or "API task updated successfully."))
        schedule_after_success(
            delay_ms=600,
            clear_error=self._clear_error,
            reset=lambda: None,
            on_back=self.on_back,
            on_success=self.on_update_success,
        )
