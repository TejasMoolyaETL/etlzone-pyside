"""ETL: Excel — Import State (name + source type)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.api import api_create_import
from core.user_context import get_user_profile
from ui.auto_hide_message import show_auto_hiding_message
from ui.form_combobox_style import apply_form_combobox_field, install_combo_popup_below_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE,
    FORM_LABEL_STYLE,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
)
from ui.widgets.required_label import field_caption_label, labeled_field_block
from ui.theme import Theme

# Display label → API ``sourceType``
_SOURCE_TYPE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Excel", "EXCEL"),
    ("CSV", "CSV"),
    ("JSON", "JSON"),
)

_HEADER_IMPORT_DISABLED_STYLESHEET = (
    f"QPushButton {{ background: {Theme.HEADER_ACCENT}; color: {Theme.PANEL_TEXT_BRIGHT}; border: none; "
    "border-radius: 6px; padding: 5px 16px; font-size: 12px; font-weight: 500; }"
    f"QPushButton:hover:!disabled {{ background: {Theme.HEADER_ACCENT_HOVER}; }}"
    f"QPushButton:pressed:!disabled {{ background: {Theme.HEADER_ACCENT_PRESSED}; }}"
    f"QPushButton:disabled {{ background: #1e293b; color: {Theme.TEXT_SECONDARY}; }}"
)

_IMPORT_CARD_STYLESHEET = f"""
    QFrame#importCard {{
        background: {Theme.BG_WHITE};
        border: 1px solid {Theme.BORDER_DEFAULT};
        border-radius: 10px;
    }}
    QLabel#importCardTitle {{
        color: {Theme.TEXT_PRIMARY};
        font-size: 16px;
        font-weight: 700;
        background: transparent;
        border: none;
    }}
    QLabel#importCardHint {{
        color: {Theme.TEXT_SECONDARY};
        font-size: 11px;
        background: transparent;
        border: none;
    }}
"""


class ExcelPage(QWidget):
    """Import State form: name, type (Excel / CSV / JSON), and Import action."""

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
        hl.addWidget(QLabel("Excel: Import State"))
        hl.addStretch()
        self.import_btn = QPushButton("Import")
        self.import_btn.setFixedWidth(100)
        self.import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_btn.setStyleSheet(_HEADER_IMPORT_DISABLED_STYLESHEET)
        self.import_btn.clicked.connect(self._handle_import)
        hl.addWidget(self.import_btn)
        root.addWidget(header)

        body = QWidget()
        body.setStyleSheet(f"background: {Theme.BG_PAGE_ALT};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 24)
        body_layout.setSpacing(14)
        body_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        form = QFrame()
        form.setObjectName("importCard")
        form.setStyleSheet(_IMPORT_CARD_STYLESHEET)
        form.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        form.setMaximumWidth(640)
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(22, 18, 22, 22)
        form_layout.setSpacing(12)

        card_title = QLabel("Create an import session")
        card_title.setObjectName("importCardTitle")
        form_layout.addWidget(card_title)
        card_hint = QLabel(
            "Name the import and select its source format. You can upload and analyze the file next."
        )
        card_hint.setObjectName("importCardHint")
        card_hint.setWordWrap(True)
        form_layout.addWidget(card_hint)
        form_layout.addSpacing(4)

        field_w = 520

        name_lbl = field_caption_label("Name*", FORM_LABEL_STYLE)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("File name…")
        self.name_edit.setStyleSheet(FORM_INPUT_STYLE)
        self.name_edit.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
        self.name_edit.setMinimumWidth(field_w)
        self.name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form_layout.addWidget(labeled_field_block(name_lbl, self.name_edit))

        type_lbl = field_caption_label("Type*", FORM_LABEL_STYLE)
        self.type_combo = QComboBox()
        self.type_combo.setPlaceholderText("Select file type")
        for label, api_value in _SOURCE_TYPE_OPTIONS:
            self.type_combo.addItem(label, api_value)
        self.type_combo.setCurrentIndex(-1)
        self.type_combo.setMaxVisibleItems(len(_SOURCE_TYPE_OPTIONS))
        apply_form_combobox_field(
            self.type_combo,
            height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX,
            min_width=field_w,
        )
        install_combo_popup_below_field(self.type_combo)
        form_layout.addWidget(labeled_field_block(type_lbl, self.type_combo))

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
        body_layout.addStretch()
        root.addWidget(body, 1)

    def go_to_nav_item(self, item_name: str) -> None:
        """Keep dashboard navigation hook; Import State is the only section."""
        _ = item_name

    def _selected_source_type(self) -> str:
        return str(self.type_combo.currentData() or "").strip().upper()

    def _reset_type_selection(self) -> None:
        self.type_combo.setCurrentIndex(-1)

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self.message_label, message, error=False)

    def _handle_import(self) -> None:
        name = self.name_edit.text().strip()
        source_type = self._selected_source_type()
        if not name or not source_type:
            return

        self.import_btn.setEnabled(False)
        try:
            result = api_create_import(name, source_type, token=self._token())
        finally:
            self.import_btn.setEnabled(True)

        if result.get("success"):
            self._show_success(str(result.get("message") or "Import created."))
            self.name_edit.clear()
            self._reset_type_selection()
