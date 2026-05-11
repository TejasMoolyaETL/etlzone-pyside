"""Create Master Setup Key page (POST category array)."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.api import api_create_master_setup_key_entry
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
)
from ui.post_save_navigation import schedule_after_success


class CreateMasterSetupKeyPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_create_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._category_edit = QLineEdit()
        self._category_list = QListWidget()
        self._remove_btn: QPushButton | None = None
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
        hl.addWidget(QLabel("Create Master Setup Key"))
        hl.addStretch()
        back_btn = QPushButton("Back")
        back_btn.setFixedWidth(100)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self._handle_back)
        hl.addWidget(back_btn)
        layout.addWidget(header)

        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        card.setMaximumWidth(440)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 12px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)

        self._category_edit.setPlaceholderText("Category name…")
        self._category_edit.setStyleSheet(INPUT_STYLE)
        self._category_edit.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
        self._category_edit.setMinimumWidth(200)
        self._category_edit.returnPressed.connect(self._add_category)

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        add_row.addWidget(self._category_edit, 1)
        add_btn = QPushButton("+")
        add_btn.setFixedWidth(44)
        add_btn.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setToolTip("Add category to the list")
        add_btn.clicked.connect(self._add_category)
        add_row.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        card_layout.addLayout(add_row)

        list_lbl = QLabel("Categories to create")
        list_lbl.setStyleSheet(LABEL_STYLE)
        card_layout.addWidget(list_lbl)
        self._category_list.setMinimumHeight(120)
        self._category_list.setMaximumHeight(200)
        self._category_list.setAlternatingRowColors(True)
        self._category_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        card_layout.addWidget(self._category_list)

        remove_row = QHBoxLayout()
        self._remove_btn = QPushButton("Remove selected")
        self._remove_btn.setFixedWidth(140)
        self._remove_btn.setEnabled(False)
        self._remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove_btn.clicked.connect(self._remove_selected)
        remove_row.addWidget(self._remove_btn)
        remove_row.addStretch()
        card_layout.addLayout(remove_row)

        self._error_label = QLabel()
        self._error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        card_layout.addWidget(self._error_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        create_btn = QPushButton("Create")
        create_btn.setFixedWidth(100)
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        create_btn.clicked.connect(self._handle_create)
        btn_row.addWidget(create_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        cancel_btn.clicked.connect(self._handle_back)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        card_layout.addLayout(btn_row)

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card, 0)
        outer.addStretch()
        layout.addLayout(outer)

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = profile.get("token") or profile.get("accessToken") or profile.get("access_token") or profile.get("jwt")
        return str(token) if token else None

    def _sync_remove_button(self) -> None:
        if self._remove_btn is not None:
            self._remove_btn.setEnabled(self._category_list.count() > 0)

    def _list_categories(self) -> list[str]:
        out: list[str] = []
        for i in range(self._category_list.count()):
            it = self._category_list.item(i)
            if it is not None:
                t = it.text().strip()
                if t:
                    out.append(t)
        return out

    def _add_category(self) -> None:
        text = self._category_edit.text().strip()
        if not text:
            self._show_error("Enter a category before adding.")
            return
        existing_lower = {self._category_list.item(i).text().strip().lower() for i in range(self._category_list.count())}
        if text.lower() in existing_lower:
            self._show_error("That category is already in the list.")
            return
        self._clear_error()
        self._category_list.addItem(QListWidgetItem(text))
        self._category_edit.clear()
        self._category_edit.setFocus()
        self._sync_remove_button()

    def _remove_selected(self) -> None:
        if not self._remove_btn or not self._remove_btn.isEnabled():
            return
        row = self._category_list.currentRow()
        if row < 0:
            self._show_error("Select a row to remove.")
            return
        self._clear_error()
        self._category_list.takeItem(row)
        self._sync_remove_button()

    def is_dirty(self) -> bool:
        if self._category_edit.text().strip():
            return True
        return self._category_list.count() > 0

    def reset_to_default(self) -> None:
        self._category_edit.clear()
        self._category_list.clear()
        self._sync_remove_button()
        self._clear_error()

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self._error_label)
        self._error_label.setText("")
        self._error_label.setVisible(False)

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=False)

    def _handle_back(self) -> None:
        if not self.is_dirty():
            if self.on_back:
                self.on_back()
            return
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Discard and leave?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Discard:
            self.reset_to_default()
            if self.on_back:
                self.on_back()

    def _handle_create(self) -> None:
        self._clear_error()
        categories = self._list_categories()
        if not categories:
            self._show_error("Add at least one category to the list before creating.")
            return
        result = api_create_master_setup_key_entry(categories, token=self._token())
        if result.get("success"):
            self._show_success(str(result.get("message") or "Created successfully."))
            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
        else:
            self._show_error(str(result.get("message") or "Create failed."))
