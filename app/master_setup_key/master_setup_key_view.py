"""View / edit Master Setup Key page (PUT category query param)."""

from __future__ import annotations

import json
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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

from core.api import api_update_master_setup_key_entry
from core.app_preferences import format_datetime_display, is_datetime_field
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.blank_display import is_blank_display_value
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
from ui.widgets.required_label import field_caption_label, labeled_field_block

_COL1 = (
    ("Id", ("id",)),
    ("Category*", ("category",)),
)
_COL2 = (
    ("Created By", ("createdBy", "created_by")),
    ("Created On", ("createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified On", ("modifiedAt", "modified_at")),
)
_ALL = _COL1 + _COL2
_READONLY = frozenset(
    {"id", "createdBy", "created_by", "createdAt", "created_at", "modifiedBy", "modified_by", "modifiedAt", "modified_at"}
)


def _get(rec: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in rec:
            return rec[k]
    return None


def _fmt(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if isinstance(value, (list, dict)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    return str(value)


def _category_edit_text(rec: dict[str, Any]) -> str:
    """Single-line value for the category editor (list → comma-separated)."""
    v = _get(rec, ("category",))
    if isinstance(v, list):
        return ", ".join(str(x).strip() for x in v if str(x).strip())
    return str(v or "").strip()


class ViewMasterSetupKeyPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._record: dict[str, Any] = {}
        self._field_edits: dict[str, QLineEdit] = {}
        self._snapshot_category: str = ""
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
        hl.addWidget(QLabel("Master Setup Key Details"))
        hl.addStretch()
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll_content = QWidget()
        scroll_content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
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
            edit = QLineEdit()
            edit.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
            edit.setMinimumWidth(240)
            edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            ro = canonical in _READONLY
            edit.setReadOnly(ro)
            edit.setStyleSheet(READONLY_INPUT_STYLE if ro else INPUT_STYLE)
            if canonical == "category":
                edit.setPlaceholderText("Category name…")
            self._field_edits[canonical] = edit
            grid.addWidget(labeled_field_block(field_caption_label(label_text, LABEL_STYLE), edit), idx, col)

        for idx, (label_text, keys) in enumerate(_COL1):
            add_field(0, idx, label_text, keys)
        for idx, (label_text, keys) in enumerate(_COL2):
            add_field(1, idx, label_text, keys)

        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setFixedWidth(100)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._edit_btn.clicked.connect(self._handle_edit)

        self._back_btn = QPushButton("Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._back_btn.clicked.connect(self._handle_back)

        self._save_btn = QPushButton("Save")
        self._save_btn.setFixedWidth(100)
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._save_btn.clicked.connect(self._handle_save)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedWidth(100)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._cancel_btn.clicked.connect(self._handle_cancel)

        view_row = QWidget()
        view_row.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        view_row.setStyleSheet("background: transparent;")
        vlay = QHBoxLayout(view_row)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(12)
        vlay.addWidget(self._edit_btn)
        vlay.addWidget(self._back_btn)

        edit_row = QWidget()
        edit_row.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        edit_row.setStyleSheet("background: transparent;")
        elay = QHBoxLayout(edit_row)
        elay.setContentsMargins(0, 0, 0, 0)
        elay.setSpacing(12)
        elay.addWidget(self._save_btn)
        elay.addWidget(self._cancel_btn)

        self._btn_stack = QStackedWidget()
        self._btn_stack.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._btn_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self._btn_stack.addWidget(view_row)
        self._btn_stack.addWidget(edit_row)

        self._error_label = QLabel()
        self._error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)

        btn_row = max(len(_COL1), len(_COL2))
        grid.addWidget(self._error_label, btn_row, 0, 1, 2)
        grid.addWidget(
            self._btn_stack,
            btn_row + 1,
            0,
            1,
            2,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )

        card_layout.addLayout(grid)
        content_layout.addWidget(card)
        content_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)
        self._switch_to_view_mode()

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = profile.get("token") or profile.get("accessToken") or profile.get("access_token") or profile.get("jwt")
        return str(token) if token else None

    def set_record(self, record: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        self._record = dict(record) if record else {}
        self._snapshot_category = _category_edit_text(self._record)
        self._refresh_values()
        if edit_mode and self._record:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

    def _refresh_values(self) -> None:
        for _label, keys in _ALL:
            canonical = keys[0]
            ed = self._field_edits.get(canonical)
            if not ed:
                continue
            if canonical == "category":
                ed.setText(self._snapshot_category)
                continue
            value = _get(self._record, keys)
            ed.setText(_fmt(value, keys[0], keys))

    def _handle_back(self) -> None:
        if self.on_back:
            self.on_back()

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self._error_label)
        self._error_label.setText("")
        self._error_label.setVisible(False)

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=False)

    def _handle_edit(self) -> None:
        self._clear_error()
        cat_ed = self._field_edits.get("category")
        if cat_ed:
            cat_ed.setReadOnly(False)
            cat_ed.setStyleSheet(INPUT_STYLE)
        self._btn_stack.setCurrentIndex(1)

    def _switch_to_view_mode(self) -> None:
        cat_ed = self._field_edits.get("category")
        if cat_ed:
            cat_ed.setReadOnly(True)
            cat_ed.setStyleSheet(READONLY_INPUT_STYLE)
        self._btn_stack.setCurrentIndex(0)

    def is_edit_mode(self) -> bool:
        return self._btn_stack.currentIndex() == 1

    def _has_unsaved_changes(self) -> bool:
        cat_ed = self._field_edits.get("category")
        if not cat_ed:
            return False
        return cat_ed.text().strip() != self._snapshot_category.strip()

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

    def _handle_save(self) -> None:
        self._clear_error()
        if not self._has_unsaved_changes():
            navigate_after_no_changes(
                show_non_error_message=self._show_success,
                clear_message=self._clear_error,
                on_back=self.on_back,
            )
            return
        cat_ed = self._field_edits.get("category")
        new_cat = (cat_ed.text().strip() if cat_ed else "")
        if not new_cat:
            self._show_error("Category is required.")
            return
        rid = self._record.get("id")
        if rid is None:
            self._show_error("ID is missing.")
            return
        result = api_update_master_setup_key_entry(rid, category=new_cat, token=self._token())
        if not result.get("success"):
            self._show_error(str(result.get("message") or "Update failed."))
            return
        self._record["category"] = new_cat
        self._snapshot_category = new_cat
        self._show_success(str(result.get("message") or "Updated successfully."))
        schedule_after_success(
            delay_ms=800,
            clear_error=self._clear_error,
            on_back=self.on_back,
            on_success=self.on_update_success,
        )
