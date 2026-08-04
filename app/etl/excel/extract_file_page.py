"""ETL: Excel — Extract File (pick session + sheet, then execute import)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.api import (
    api_execute_import_sheet,
    api_get_all_import_session_ids,
    api_get_import_sheets_by_uuid,
)
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_combobox_style import apply_form_combobox_field, install_combo_popup_below_field
from ui.form_page_styles import (
    APP_FONT_SIZE_PX,
    FORM_ERROR_LABEL_STYLE,
    FORM_LABEL_STYLE,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
)
from ui.theme import Theme
from ui.widgets.required_label import field_caption_label, labeled_field_block

_HEADER_BTN_STYLESHEET = (
    f"QPushButton {{ background: {Theme.HEADER_ACCENT}; color: {Theme.PANEL_TEXT_BRIGHT}; border: none; "
    "border-radius: 6px; padding: 5px 16px; font-size: 12px; font-weight: 500; }"
    f"QPushButton:hover:!disabled {{ background: {Theme.HEADER_ACCENT_HOVER}; }}"
    f"QPushButton:pressed:!disabled {{ background: {Theme.HEADER_ACCENT_PRESSED}; }}"
    f"QPushButton:disabled {{ background: #1e293b; color: {Theme.TEXT_SECONDARY}; }}"
)

_CARD_STYLE = f"""
    QFrame#extractCard {{
        background: {Theme.BG_WHITE};
        border: 1px solid {Theme.BORDER_DEFAULT};
        border-radius: 10px;
    }}
    QLabel#extractCardTitle {{
        color: {Theme.TEXT_PRIMARY};
        font-size: 15px;
        font-weight: 700;
        background: transparent;
        border: none;
    }}
    QLabel#extractCardHint {{
        color: {Theme.TEXT_SECONDARY};
        font-size: 11px;
        background: transparent;
        border: none;
    }}
"""


class ExtractFilePage(QWidget):
    """Extract File: choose session + sheet, then execute the import."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loaded_once = False
        self._executing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        hl.addWidget(QLabel("Excel: Extract File"))
        hl.addStretch()
        self.extract_btn = QPushButton("Extract")
        self.extract_btn.setFixedWidth(110)
        self.extract_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.extract_btn.setStyleSheet(_HEADER_BTN_STYLESHEET)
        self.extract_btn.clicked.connect(self._handle_extract)
        hl.addWidget(self.extract_btn)
        root.addWidget(header)

        body = QWidget()
        body.setStyleSheet(f"background: {Theme.BG_PAGE_ALT};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 24)
        body_layout.setSpacing(14)
        body_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        form = QFrame()
        form.setObjectName("extractCard")
        form.setStyleSheet(_CARD_STYLE)
        form.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        form.setMaximumWidth(760)
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(20, 16, 20, 18)
        form_layout.setSpacing(10)

        card_title = QLabel("Extract a mapped sheet")
        card_title.setObjectName("extractCardTitle")
        form_layout.addWidget(card_title)
        card_hint = QLabel(
            "Select an import session to load its sheets, then click Extract to run the execute API."
        )
        card_hint.setObjectName("extractCardHint")
        card_hint.setWordWrap(True)
        form_layout.addWidget(card_hint)
        form_layout.addSpacing(4)

        field_w = 520

        session_lbl = field_caption_label("Session ID*", FORM_LABEL_STYLE)
        self.session_combo = QComboBox()
        self.session_combo.setPlaceholderText("Select session name")
        apply_form_combobox_field(
            self.session_combo,
            height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX,
            min_width=field_w,
        )
        install_combo_popup_below_field(self.session_combo)
        self.session_combo.setCurrentIndex(-1)
        self.session_combo.currentIndexChanged.connect(self._on_session_changed)
        form_layout.addWidget(labeled_field_block(session_lbl, self.session_combo))

        sheet_lbl = field_caption_label("Sheet*", FORM_LABEL_STYLE)
        self.sheet_combo = QComboBox()
        self.sheet_combo.setPlaceholderText("Select sheet")
        apply_form_combobox_field(
            self.sheet_combo,
            height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX,
            min_width=field_w,
        )
        install_combo_popup_below_field(self.sheet_combo)
        self.sheet_combo.setCurrentIndex(-1)
        form_layout.addWidget(labeled_field_block(sheet_lbl, self.sheet_combo))

        options_lbl = field_caption_label("Options*", FORM_LABEL_STYLE)
        options_row = QWidget()
        options_layout = QHBoxLayout(options_row)
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.setSpacing(18)
        self.drop_and_create_radio = QRadioButton("Drop and Create")
        self.delete_radio = QRadioButton("Delete")
        self._operation_group = QButtonGroup(self)
        self._operation_group.setExclusive(True)
        self._operation_group.addButton(self.drop_and_create_radio)
        self._operation_group.addButton(self.delete_radio)
        for rb in (self.drop_and_create_radio, self.delete_radio):
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            rb.setStyleSheet(
                f"QRadioButton {{ color: {Theme.TEXT_PRIMARY}; font-size: {APP_FONT_SIZE_PX}px; "
                f"font-weight: 500; spacing: 8px; }}"
            )
            options_layout.addWidget(rb)
        self.drop_and_create_radio.setChecked(True)
        options_layout.addStretch(1)
        form_layout.addWidget(labeled_field_block(options_lbl, options_row))

        self.message_label = QLabel()
        self.message_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.message_label.setVisible(False)
        form_layout.addWidget(self.message_label)

        body_layout.addWidget(form)
        body_layout.addStretch(1)
        root.addWidget(body, 1)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._loaded_once:
            self._loaded_once = True
            self._load_lists()

    def go_to_nav_item(self, item_name: str) -> None:
        _ = item_name
        self._load_lists()

    def selected_session_id(self) -> str:
        return str(self.session_combo.currentData() or "").strip()

    def selected_sheet_id(self) -> int | str | None:
        data = self.sheet_combo.currentData()
        if isinstance(data, dict):
            return data.get("sheetId")
        return data

    def selected_operation(self) -> str | None:
        if self.drop_and_create_radio.isChecked():
            return "DROP_CREATE"
        if self.delete_radio.isChecked():
            return "DELETE"
        return None

    def _token(self) -> str | None:
        profile = get_user_profile() or {}
        return profile.get("token") or profile.get("accessToken")

    def _clear_message(self) -> None:
        cancel_auto_hide_message(self, self.message_label)
        self.message_label.setText("")
        self.message_label.setVisible(False)

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self.message_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self.message_label, message, error=False)

    def _sheet_label(self, row: dict[str, Any]) -> str:
        sheet_name = str(row.get("sheetName") or "").strip()
        sheet_id = row.get("sheetId")
        if sheet_name and sheet_id is not None and str(sheet_id).strip() != "":
            return f"{sheet_name} (ID: {sheet_id})"
        if sheet_name:
            return sheet_name
        if sheet_id is not None and str(sheet_id).strip() != "":
            return f"Sheet ID: {sheet_id}"
        return "Unnamed sheet"

    def _load_lists(self) -> None:
        previous_session = self.selected_session_id()
        previous_sheet = self.selected_sheet_id()

        self.extract_btn.setEnabled(False)
        try:
            sessions_result = api_get_all_import_session_ids(self._token())
        finally:
            self.extract_btn.setEnabled(True)

        self.session_combo.blockSignals(True)
        self.session_combo.clear()
        sessions = sessions_result.get("data") if sessions_result.get("success") else []
        if not isinstance(sessions, list):
            sessions = []
        session_restore = -1
        for row in sessions:
            if not isinstance(row, dict):
                continue
            sid = str(row.get("sessionId") or "").strip()
            name = str(row.get("sessionName") or "").strip()
            if not name and not sid:
                continue
            self.session_combo.addItem(name or sid, sid)
            if previous_session and sid == previous_session:
                session_restore = self.session_combo.count() - 1
        self.session_combo.setCurrentIndex(session_restore)
        self.session_combo.blockSignals(False)

        if not sessions_result.get("success"):
            self._clear_sheets()
            self._show_error(str(sessions_result.get("message") or "Failed to load sessions."))
            return

        if self.selected_session_id():
            self._load_sheets_for_session(self.selected_session_id(), prefer_sheet_id=previous_sheet)
        else:
            self._clear_sheets()

    def _clear_sheets(self) -> None:
        self.sheet_combo.blockSignals(True)
        self.sheet_combo.clear()
        self.sheet_combo.setCurrentIndex(-1)
        self.sheet_combo.blockSignals(False)

    def _on_session_changed(self, _index: int = -1) -> None:
        session_id = self.selected_session_id()
        if not session_id:
            self._clear_sheets()
            return
        self._load_sheets_for_session(session_id)

    def _load_sheets_for_session(
        self,
        session_id: str,
        *,
        prefer_sheet_id: int | str | None = None,
    ) -> None:
        self.extract_btn.setEnabled(False)
        try:
            result = api_get_import_sheets_by_uuid(session_id, token=self._token())
        finally:
            self.extract_btn.setEnabled(True)

        self.sheet_combo.blockSignals(True)
        self.sheet_combo.clear()
        sheets = result.get("data") if result.get("success") else []
        if not isinstance(sheets, list):
            sheets = []
        sheet_restore = -1
        for row in sheets:
            if not isinstance(row, dict):
                continue
            sheet_id = row.get("sheetId")
            if sheet_id is None or str(sheet_id).strip() == "":
                continue
            self.sheet_combo.addItem(self._sheet_label(row), row)
            if prefer_sheet_id is not None and str(sheet_id) == str(prefer_sheet_id):
                sheet_restore = self.sheet_combo.count() - 1
        self.sheet_combo.setCurrentIndex(sheet_restore)
        self.sheet_combo.blockSignals(False)

        if not result.get("success"):
            self._show_error(str(result.get("message") or "Failed to load sheets for session."))
            return
        if self.sheet_combo.count() == 0:
            self._show_error("No sheets found for the selected session.")
            return
        self._clear_message()

    def _handle_extract(self) -> None:
        if self._executing:
            return
        session_id = self.selected_session_id()
        sheet_id = self.selected_sheet_id()
        operation = self.selected_operation()
        if not session_id:
            self._show_error("Select a session before running Extract.")
            return
        if sheet_id is None or str(sheet_id).strip() == "":
            self._show_error("Select a sheet before running Extract.")
            return
        if not operation:
            self._show_error("Select Drop and Create or Delete before running Extract.")
            return

        self._clear_message()
        self._executing = True
        self.extract_btn.setEnabled(False)
        try:
            result = api_execute_import_sheet(
                session_id,
                sheet_id,
                operation=operation,
                token=self._token(),
            )
        finally:
            self._executing = False
            self.extract_btn.setEnabled(True)

        if not result.get("success"):
            self._show_error(str(result.get("message") or "Extract failed."))
            return
        self._show_success(str(result.get("message") or "Extract completed."))
