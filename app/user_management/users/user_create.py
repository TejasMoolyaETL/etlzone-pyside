"""Create User page - form to add a new user.

Layout and styling match View Profile page exactly.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Callable

from PySide6.QtCore import QPoint, QDate, Qt, QRegularExpression, Signal, QTimer
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCalendarWidget,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtCore import QStringListModel

from core.api import api_create_user, api_get_all_depts, api_get_all_orgs, api_get_all_positions
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    DIALOG_BUTTON_BOX_STYLESHEET,
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_FIELD_SPACING_PX,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_FONT_SIZE_PX,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LINEEDIT_PLACEHOLDER_SUBSTYLE,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_READONLY_INPUT_STYLE as READONLY_INPUT_STYLE,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    placeholder_auto_filled,
    placeholder_search_select,
)
from ui.post_save_navigation import schedule_after_success
from ui.strict_completer import strict_list_selection_message
from ui.styles import CONTEXT_MENU_STYLESHEET
from ui.widgets.password_edit import PasswordLineEdit
from ui.widgets.required_label import field_caption_label
from core.validators import COUNTRY_CODES, validate_mobile

_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# PasswordLineEdit wrapper: FORM_INPUT_STYLE contains QLineEdit::placeholder, which breaks
# PasswordLineEdit.setStyleSheet's wrapping (border ends up outside any selector). Shell + inner padding matches other rows.
_CREATE_USER_PASSWORD_SHELL = (
    "border: 1px solid #e2e8f0; border-radius: 4px; background-color: #ffffff;"
)

_ROLES = ("USER", "PADMIN", "SADMIN")

_MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


# Modern date picker calendar stylesheet
_CALENDAR_STYLE = f"""
    QCalendarWidget {{
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
    }}
    QCalendarWidget QWidget#qt_calendar_navigationbar {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #f8fafc, stop:1 #f1f5f9);
        border-bottom: 1px solid #e2e8f0;
        border-radius: 8px 8px 0 0;
        min-height: 36px;
    }}
    QCalendarWidget QToolButton {{
        background: transparent;
        color: #0f172a;
        font-size: {FORM_PAGE_FONT_SIZE_PX}px;
        font-weight: 600;
        border: none;
        min-width: 32px;
        min-height: 32px;
        border-radius: 6px;
    }}
    QCalendarWidget QToolButton:hover {{
        background-color: #e2e8f0;
    }}
    QCalendarWidget QToolButton::menu-indicator {{
        image: none;
    }}
    QCalendarWidget QAbstractItemView {{
        background-color: #ffffff;
        selection-background-color: #6366f1;
        selection-color: #ffffff;
        font-size: {FORM_PAGE_FONT_SIZE_PX}px;
        font-weight: 500;
    }}
    QCalendarWidget QAbstractItemView:enabled {{
        color: #0f172a;
    }}
    QCalendarWidget QAbstractItemView:disabled {{
        color: #94a3b8;
    }}
"""


class _SimpleDropdown(QFrame):
    """Simple custom dropdown: button + QMenu list."""

    selectionChanged = Signal(int, object)

    def __init__(
        self,
        items: list[tuple[str, object]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("border: 1px solid #e2e8f0; border-radius: 4px; background: #fff;")
        self._items = items
        self._current_index = 0
        self._block_signals = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._btn = QPushButton()
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setStyleSheet(
            f"QPushButton {{ padding: 2px 8px; border: none; border-radius: 3px; "
            f"background: transparent; font-size: {FORM_PAGE_FONT_SIZE_PX}px; font-weight: 400; color: #0f172a; text-align: left; }}"
            "QPushButton:hover { background: #f8fafc; }"
        )
        self._btn.clicked.connect(self._show_menu)
        layout.addWidget(self._btn)
        self._update_text()

    def _update_text(self) -> None:
        if 0 <= self._current_index < len(self._items):
            self._btn.setText(self._items[self._current_index][0])

    def _show_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        for i, (text, _) in enumerate(self._items):
            action = menu.addAction(text)
            action.triggered.connect(lambda checked, idx=i: self._on_picked(idx))
        menu.popup(self._btn.mapToGlobal(QPoint(0, self._btn.height())))

    def _on_picked(self, index: int) -> None:
        if 0 <= index < len(self._items):
            self._current_index = index
            self._update_text()
            if not self._block_signals:
                self.selectionChanged.emit(index, self._items[index][1])

    def setCurrentIndex(self, index: int) -> None:
        if 0 <= index < len(self._items):
            self._current_index = index
            self._update_text()

    def currentIndex(self) -> int:
        return self._current_index

    def currentData(self) -> object:
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index][1]
        return None

    def blockSignals(self, block: bool) -> bool:
        prev = self._block_signals
        self._block_signals = block
        return prev

    def findData(self, value: object) -> int:
        for i, (_, data) in enumerate(self._items):
            if data == value:
                return i
        return -1

    def setMinimumWidth(self, w: int) -> None:
        super().setMinimumWidth(w)
        self._btn.setMinimumWidth(w)

    def setMinimumHeight(self, h: int) -> None:
        super().setMinimumHeight(h)
        self._btn.setMinimumHeight(h)


class _DatePickerDialog(QDialog):
    """Modern date picker dialog with prominent month/year selection."""

    def __init__(self, initial_date: QDate, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(DIALOG_BUTTON_BOX_STYLESHEET)
        self.setWindowTitle("Select Date")
        self.setModal(True)
        self._selected_date = initial_date.toPython()

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Month & Year - simple custom dropdowns
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(12)

        month_items = [(name, i) for i, name in enumerate(_MONTH_NAMES, 1)]
        self._month_combo = _SimpleDropdown(month_items)
        self._month_combo.setMinimumWidth(100)
        self._month_combo.setMinimumHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
        self._month_combo.selectionChanged.connect(lambda _i, _d: self._on_month_year_changed())
        nav_layout.addWidget(self._month_combo)

        year_items = [(str(y), y) for y in range(2020, 2036)]
        self._year_combo = _SimpleDropdown(year_items)
        self._year_combo.setMinimumWidth(70)
        self._year_combo.setMinimumHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
        self._year_combo.selectionChanged.connect(lambda _i, _d: self._on_month_year_changed())
        nav_layout.addWidget(self._year_combo)

        nav_layout.addStretch()
        layout.addLayout(nav_layout)

        # Calendar (no nav bar - we use our own month/year at top)
        self._calendar = QCalendarWidget()
        self._calendar.setNavigationBarVisible(False)
        self._calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self._calendar.setStyleSheet(_CALENDAR_STYLE)
        self._calendar.setMinimumSize(320, 280)
        self._calendar.clicked.connect(self._on_date_clicked)
        layout.addWidget(self._calendar)

        # Buttons (OK to confirm, Cancel to dismiss)
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self._apply_date(self._selected_date)

    def _apply_date(self, d: date) -> None:
        self._selected_date = d
        self._month_combo.blockSignals(True)
        self._year_combo.blockSignals(True)
        self._month_combo.setCurrentIndex(d.month - 1)
        idx = self._year_combo.findData(d.year)
        if idx >= 0:
            self._year_combo.setCurrentIndex(idx)
        self._month_combo.blockSignals(False)
        self._year_combo.blockSignals(False)
        self._calendar.setSelectedDate(QDate(d.year, d.month, d.day))
        self._calendar.setCurrentPage(d.year, d.month)

    def _on_month_year_changed(self) -> None:
        month = self._month_combo.currentData() or self._month_combo.currentIndex() + 1
        year = self._year_combo.currentData()
        if year is None:
            try:
                year = int(self._year_combo.currentText())
            except (ValueError, TypeError):
                year = date.today().year
        day = min(self._selected_date.day, 28)
        try:
            self._selected_date = date(year, month, day)
        except ValueError:
            self._selected_date = date(year, month, 1)
        self._calendar.setCurrentPage(year, month)
        self._calendar.setSelectedDate(QDate(self._selected_date.year, self._selected_date.month, self._selected_date.day))

    def _on_date_clicked(self, qdate: QDate) -> None:
        self._selected_date = qdate.toPython()
        self.accept()  # Close and apply immediately on date click

    def selected_date(self) -> date:
        return self._selected_date


_DATEPICKER_EDIT_STYLE = (
    f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; padding: 4px 8px; border: 1px solid #e2e8f0; "
    "border-radius: 4px; min-width: 140px;"
    + LINEEDIT_PLACEHOLDER_SUBSTYLE
)
_DATEPICKER_EDIT_ENABLED = f"{_DATEPICKER_EDIT_STYLE} background-color: #ffffff; color: #0f172a;"
_DATEPICKER_EDIT_DISABLED = f"{_DATEPICKER_EDIT_STYLE} background-color: #f1f5f9; color: #64748b;"


class _DatePickerEdit(QWidget):
    """Date picker that opens a modern dialog with prominent month/year selection."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._date = date.today()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._display = QLineEdit()
        self._display.setReadOnly(True)
        self._display.setCursor(Qt.CursorShape.PointingHandCursor)
        self._display.setStyleSheet(_DATEPICKER_EDIT_ENABLED)
        self._display.mousePressEvent = lambda e: self._open_picker(e)
        layout.addWidget(self._display)

        self._update_display()

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self._display.setStyleSheet(
            _DATEPICKER_EDIT_ENABLED if enabled else _DATEPICKER_EDIT_DISABLED
        )

    def _update_display(self) -> None:
        self._display.setText(self._date.strftime("%d %b %Y"))

    def _open_picker(self, event: object = None) -> None:
        dlg = _DatePickerDialog(QDate(self._date.year, self._date.month, self._date.day), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._date = dlg.selected_date()
            self._update_display()

    def date(self) -> date:
        return self._date

    def setDate(self, qdate: QDate) -> None:
        self._date = qdate.toPython()
        self._update_display()


class CreateUserPage(QWidget):
    """Page with form to create a new user. Layout matches View Profile page."""

    def __init__(self, on_back: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.on_back = on_back
        self._org_items: list[tuple[str, str]] = []
        self._dept_items: list[tuple[str, str]] = []
        self._position_items: list[tuple[str, str]] = []
        self._ref_loaded = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(FORM_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        header_layout.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        title = QLabel("Create User")
        header_layout.addWidget(title)
        header_layout.addStretch()
        back_btn = QPushButton("Back")
        back_btn.setFixedWidth(100)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self.request_back)
        header_layout.addWidget(back_btn)
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
        card.setMaximumWidth(920)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        fields_grid = QGridLayout()
        fields_grid.setHorizontalSpacing(24)
        fields_grid.setVerticalSpacing(0)
        fields_grid.setColumnStretch(0, 1)
        fields_grid.setColumnStretch(1, 1)
        field_h = FORM_SINGLELINE_FIELD_HEIGHT_PX

        def _make_col() -> QVBoxLayout:
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(10)
            return col

        def _add_field_group(col: QVBoxLayout, label: QLabel, field: QWidget) -> None:
            """Label above control with shared tight caption-to-field spacing."""
            group = QVBoxLayout()
            group.setContentsMargins(0, 0, 0, 0)
            group.setSpacing(FORM_LABEL_FIELD_SPACING_PX)
            label.setMinimumWidth(0)
            label.setMaximumWidth(16777215)
            group.addWidget(label)
            group.addWidget(field)
            wrap = QWidget()
            wrap.setLayout(group)
            col.addWidget(wrap)

        left_col = _make_col()
        right_col = _make_col()

        # Left column
        label_username = QLabel("Username:")
        label_username.setStyleSheet(LABEL_STYLE)
        self.username_edit = QLineEdit()
        self.username_edit.setReadOnly(True)
        self.username_edit.setPlaceholderText("(Generated by backend)")
        self.username_edit.setStyleSheet(READONLY_INPUT_STYLE)
        self.username_edit.setFixedHeight(field_h)
        self.username_edit.setMinimumWidth(240)
        self.username_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_field_group(left_col, label_username, self.username_edit)

        label_email = field_caption_label("Email", LABEL_STYLE, required=True)
        self.email_edit = QLineEdit()
        self.email_edit.setStyleSheet(INPUT_STYLE)
        self.email_edit.setFixedHeight(field_h)
        self.email_edit.setMinimumWidth(240)
        self.email_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.email_edit.textChanged.connect(
            lambda text: self._update_email_style(self.email_edit, text)
        )
        _add_field_group(left_col, label_email, self.email_edit)

        label_password = field_caption_label("Password", LABEL_STYLE, required=True)
        self.password_edit = PasswordLineEdit(use_default_style=False)
        self.password_edit.setStyleSheet(_CREATE_USER_PASSWORD_SHELL)
        self.password_edit.set_inner_padding("2px 8px", font_size_px=FORM_PAGE_FONT_SIZE_PX)
        self.password_edit.setFixedHeight(field_h)
        self.password_edit.setMinimumWidth(240)
        self.password_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_field_group(left_col, label_password, self.password_edit)

        label_first = field_caption_label("First Name", LABEL_STYLE, required=True)
        self.first_name_edit = QLineEdit()
        self.first_name_edit.setStyleSheet(INPUT_STYLE)
        self.first_name_edit.setFixedHeight(field_h)
        self.first_name_edit.setMinimumWidth(240)
        self.first_name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_field_group(left_col, label_first, self.first_name_edit)

        label_last = field_caption_label("Last Name", LABEL_STYLE, required=True)
        self.last_name_edit = QLineEdit()
        self.last_name_edit.setStyleSheet(INPUT_STYLE)
        self.last_name_edit.setFixedHeight(field_h)
        self.last_name_edit.setMinimumWidth(240)
        self.last_name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_field_group(left_col, label_last, self.last_name_edit)

        # Right column
        label_org = QLabel("Org Name:")
        label_org.setStyleSheet(LABEL_STYLE)
        self.org_name_edit = QLineEdit()
        self.org_name_edit.setPlaceholderText(placeholder_search_select("Org Id", "Org Name"))
        self.org_name_edit.setStyleSheet(INPUT_STYLE)
        self.org_name_edit.setFixedHeight(field_h)
        self.org_name_edit.setMinimumWidth(240)
        self.org_name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.org_name_edit.textEdited.connect(lambda _t: self.org_id_edit.clear())
        self.org_name_completer = QCompleter(self.org_name_edit)
        self.org_name_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.org_name_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.org_name_completer.setMaxVisibleItems(12)
        self.org_name_edit.setCompleter(self.org_name_completer)
        self.org_name_completer.activated.connect(self._on_org_selected)
        _add_field_group(right_col, label_org, self.org_name_edit)

        label_org_id = QLabel("Org Id:")
        label_org_id.setStyleSheet(LABEL_STYLE)
        self.org_id_edit = QLineEdit()
        self.org_id_edit.setReadOnly(True)
        self.org_id_edit.setPlaceholderText(placeholder_auto_filled("Org Name"))
        self.org_id_edit.setStyleSheet(READONLY_INPUT_STYLE)
        self.org_id_edit.setFixedHeight(field_h)
        self.org_id_edit.setMinimumWidth(240)
        self.org_id_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_field_group(right_col, label_org_id, self.org_id_edit)

        label_dept = QLabel("Dept Name:")
        label_dept.setStyleSheet(LABEL_STYLE)
        self.dept_name_edit = QLineEdit()
        self.dept_name_edit.setPlaceholderText(placeholder_search_select("Dept Id", "Dept Name"))
        self.dept_name_edit.setStyleSheet(INPUT_STYLE)
        self.dept_name_edit.setFixedHeight(field_h)
        self.dept_name_edit.setMinimumWidth(240)
        self.dept_name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.dept_name_edit.textEdited.connect(lambda _t: self.dept_id_value_edit.clear())
        self.dept_id_completer = QCompleter(self.dept_name_edit)
        self.dept_id_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.dept_id_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.dept_id_completer.setMaxVisibleItems(12)
        self.dept_name_edit.setCompleter(self.dept_id_completer)
        self.dept_id_completer.activated.connect(self._on_dept_selected)
        _add_field_group(right_col, label_dept, self.dept_name_edit)

        label_dept_id = QLabel("Dept Id:")
        label_dept_id.setStyleSheet(LABEL_STYLE)
        self.dept_id_value_edit = QLineEdit()
        self.dept_id_value_edit.setReadOnly(True)
        self.dept_id_value_edit.setPlaceholderText(placeholder_auto_filled("Dept Name"))
        self.dept_id_value_edit.setStyleSheet(READONLY_INPUT_STYLE)
        self.dept_id_value_edit.setFixedHeight(field_h)
        self.dept_id_value_edit.setMinimumWidth(240)
        self.dept_id_value_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_field_group(right_col, label_dept_id, self.dept_id_value_edit)

        label_position = QLabel("Position Name:")
        label_position.setStyleSheet(LABEL_STYLE)
        self.position_name_edit = QLineEdit()
        self.position_name_edit.setPlaceholderText(placeholder_search_select("Position Id", "Position Name"))
        self.position_name_edit.setStyleSheet(INPUT_STYLE)
        self.position_name_edit.setFixedHeight(field_h)
        self.position_name_edit.setMinimumWidth(240)
        self.position_name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.position_name_edit.textEdited.connect(lambda _t: self.position_id_value_edit.clear())
        self.position_id_completer = QCompleter(self.position_name_edit)
        self.position_id_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.position_id_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.position_id_completer.setMaxVisibleItems(12)
        self.position_name_edit.setCompleter(self.position_id_completer)
        self.position_id_completer.activated.connect(self._on_position_selected)
        _add_field_group(right_col, label_position, self.position_name_edit)

        label_position_id = QLabel("Position Id:")
        label_position_id.setStyleSheet(LABEL_STYLE)
        self.position_id_value_edit = QLineEdit()
        self.position_id_value_edit.setReadOnly(True)
        self.position_id_value_edit.setPlaceholderText(placeholder_auto_filled("Position Name"))
        self.position_id_value_edit.setStyleSheet(READONLY_INPUT_STYLE)
        self.position_id_value_edit.setFixedHeight(field_h)
        self.position_id_value_edit.setMinimumWidth(240)
        self.position_id_value_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_field_group(right_col, label_position_id, self.position_id_value_edit)

        label_mobile = field_caption_label("Mobile", LABEL_STYLE, required=True)
        mobile_container = QWidget()
        mobile_container.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
        mobile_row = QHBoxLayout(mobile_container)
        mobile_row.setContentsMargins(0, 0, 0, 0)
        mobile_row.setSpacing(10)
        self.mobile_country = QComboBox()
        for code, country in COUNTRY_CODES:
            self.mobile_country.addItem(f"{country} ({code})", code)
        apply_form_combobox_field(self.mobile_country, height_px=field_h, min_width=120)
        self.mobile_number = QLineEdit()
        self.mobile_number.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"^\d*$"))
        )
        self.mobile_number.setStyleSheet(INPUT_STYLE)
        self.mobile_number.setFixedHeight(field_h)
        self.mobile_number.setMinimumWidth(120)
        self.mobile_number.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.mobile_country.currentIndexChanged.connect(self._update_mobile_style)
        self.mobile_number.textChanged.connect(self._update_mobile_style)
        mobile_row.addWidget(self.mobile_country)
        mobile_row.addWidget(self.mobile_number, 1)
        _add_field_group(left_col, label_mobile, mobile_container)

        label_status = QLabel("Status:")
        label_status.setStyleSheet(LABEL_STYLE)
        self.status_combo = QComboBox()
        self.status_combo.addItems(["ACTIVE", "INACTIVE"])
        apply_form_combobox_field(self.status_combo, height_px=field_h, min_width=140)
        self.status_combo.currentIndexChanged.connect(self._on_status_changed)
        _add_field_group(left_col, label_status, self.status_combo)

        left_widget = QWidget()
        left_widget.setLayout(left_col)
        left_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        right_widget = QWidget()
        right_widget.setLayout(right_col)
        right_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        fields_grid.addWidget(left_widget, 0, 0, alignment=Qt.AlignmentFlag.AlignTop)
        fields_grid.addWidget(right_widget, 0, 1, alignment=Qt.AlignmentFlag.AlignTop)
        card_layout.addLayout(fields_grid)

        # Error message (inline, above buttons)
        self._error_label = QLabel()
        self._error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error_label.setWordWrap(True)
        self._error_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._error_label.setVisible(False)
        card_layout.addWidget(self._error_label)

        # Create / Cancel row (same button metrics and QSS as user_view Save/Cancel)
        bottom_btn_row = QHBoxLayout()
        bottom_btn_row.setSpacing(12)

        create_btn = QPushButton("Create User")
        create_btn.setMinimumWidth(100)
        create_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        create_btn.clicked.connect(self._handle_create)
        bottom_btn_row.addWidget(create_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        cancel_btn.clicked.connect(self.request_back)
        bottom_btn_row.addWidget(cancel_btn)
        bottom_btn_row.addStretch()

        bottom_btn_wrap = QWidget()
        bottom_btn_wrap.setMinimumHeight(52)
        bottom_btn_wrap.setLayout(bottom_btn_row)
        card_layout.addWidget(bottom_btn_wrap)

        content_layout.addWidget(card)
        content_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

    def _set_error(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=True)

    def _set_success(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=False)

    def _get_default_values(self) -> dict:
        """Return snapshot of default form values."""
        return {
            "email": "",
            "password": "",
            "first_name": "",
            "last_name": "",
            "org_name": "",
            "org_id": "",
            "dept_name": "",
            "dept_id": "",
            "position_name": "",
            "position_id": "",
            "mobile_country_index": 0,
            "mobile_number": "",
            "status": "ACTIVE",
        }

    def is_dirty(self) -> bool:
        """True if any field differs from default."""
        d = self._get_default_values()
        if self.email_edit.text().strip() != d["email"]:
            return True
        if self.password_edit.text() != d["password"]:
            return True
        if self.first_name_edit.text().strip() != d["first_name"]:
            return True
        if self.last_name_edit.text().strip() != d["last_name"]:
            return True
        if self.org_name_edit.text().strip() != d["org_name"]:
            return True
        if self.org_id_edit.text().strip() != d["org_id"]:
            return True
        if self.dept_name_edit.text().strip() != d["dept_name"]:
            return True
        if self.dept_id_value_edit.text().strip() != d["dept_id"]:
            return True
        if self.position_name_edit.text().strip() != d["position_name"]:
            return True
        if self.position_id_value_edit.text().strip() != d["position_id"]:
            return True
        if self.mobile_country.currentIndex() != d["mobile_country_index"]:
            return True
        if self.mobile_number.text().strip() != d["mobile_number"]:
            return True
        if self.status_combo.currentText() != d["status"]:
            return True
        return False

    def reset_to_default(self, clear_message: bool = True) -> None:
        """Reset all fields to default values."""
        self.email_edit.clear()
        self.password_edit.clear()
        self.first_name_edit.clear()
        self.last_name_edit.clear()
        self.org_name_edit.clear()
        self.org_id_edit.clear()
        self.dept_name_edit.clear()
        self.dept_id_value_edit.clear()
        self.position_name_edit.clear()
        self.position_id_value_edit.clear()
        self.mobile_country.blockSignals(True)
        self.mobile_country.setCurrentIndex(0)
        self.mobile_country.blockSignals(False)
        self.mobile_number.clear()
        self.status_combo.setCurrentText("ACTIVE")
        if clear_message:
            self._clear_message()

    def _clear_message(self) -> None:
        cancel_auto_hide_message(self, self._error_label)
        self._error_label.setText("")
        self._error_label.setVisible(False)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._clear_message()
        self._ensure_reference_data_loaded()

    def request_back(self) -> None:
        """Navigate back, showing confirmation if form has unsaved changes."""
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

    def _on_status_changed(self, index: int) -> None:
        # No validity dates in create-user; keep handler for future use.
        return None

    def _ensure_reference_data_loaded(self) -> None:
        if self._ref_loaded:
            return
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        orgs = api_get_all_orgs(token=token)
        depts = api_get_all_depts(token=token)
        positions = api_get_all_positions(token=token)

        self._org_items = self._extract_id_name_items(
            orgs.get("data") or [],
            id_keys=("orgId", "org_id", "organizationId", "id"),
            name_keys=("orgName", "org_name", "organizationName", "name"),
        )
        self._dept_items = self._extract_id_name_items(
            depts.get("data") or [],
            id_keys=("deptId", "dept_id", "departmentId", "id"),
            name_keys=("deptName", "dept_name", "departmentName", "name"),
        )
        self._position_items = self._extract_id_name_items(
            positions.get("data") or [],
            id_keys=("positionId", "position_id", "id"),
            name_keys=("positionName", "position_name", "name"),
        )

        self.org_name_completer.setModel(QStringListModel(self._format_items(self._org_items)))
        self.dept_id_completer.setModel(QStringListModel(self._format_items(self._dept_items)))
        self.position_id_completer.setModel(QStringListModel(self._format_items(self._position_items)))

        self._ref_loaded = True

    def _extract_id_name_items(
        self,
        rows: list[dict],
        *,
        id_keys: tuple[str, ...],
        name_keys: tuple[str, ...],
    ) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            _id = None
            _name = None
            for k in id_keys:
                v = row.get(k)
                if v is not None and str(v).strip():
                    _id = str(v).strip()
                    break
            for k in name_keys:
                v = row.get(k)
                if v is not None and str(v).strip():
                    _name = str(v).strip()
                    break
            if _id:
                items.append((_id, _name or ""))
        return items

    def _format_items(self, items: list[tuple[str, str]]) -> list[str]:
        out: list[str] = []
        for _id, name in items:
            out.append(f"{_id} | {name}" if name else _id)
        return out

    def _parse_selected_id(self, text: str) -> str:
        return (text or "").split("|", 1)[0].strip()

    def _on_org_selected(self, text: str) -> None:
        selected_id = self._parse_selected_id(text)
        self.org_id_edit.setText(selected_id)
        # Keep display text in "id | name" form from completer selection.
        self.org_name_edit.setText(text)

    def _on_dept_selected(self, text: str) -> None:
        self.dept_name_edit.setText(text)
        self.dept_id_value_edit.setText(self._parse_selected_id(text))

    def _on_position_selected(self, text: str) -> None:
        self.position_name_edit.setText(text)
        self.position_id_value_edit.setText(self._parse_selected_id(text))

    def _update_email_style(self, widget: QLineEdit, text: str) -> None:
        """Update email field border color based on validity (like View Profile)."""
        base = f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; padding: 4px 8px; border-radius: 4px;"
        if not text.strip():
            widget.setStyleSheet(f"{base} border: 1px solid #e2e8f0; background-color: #ffffff;")
        elif _EMAIL_REGEX.match(text.strip()):
            widget.setStyleSheet(f"{base} border: 1px solid #22c55e; background-color: #ffffff;")
        else:
            widget.setStyleSheet(f"{base} border: 1px solid #ef4444; background-color: #ffffff;")

    def _update_mobile_style(self) -> None:
        """Update mobile number field border color based on validity (like View Profile)."""
        base = f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; padding: 4px 8px; border-radius: 4px; background-color: #ffffff;"
        number = self.mobile_number.text().strip()
        country_code = self.mobile_country.currentData() or "+91"
        if not number:
            self.mobile_number.setStyleSheet(f"{base} border: 1px solid #e2e8f0;")
        else:
            valid, _ = validate_mobile(country_code, number)
            color = "#22c55e" if valid else "#ef4444"
            self.mobile_number.setStyleSheet(f"{base} border: 1px solid {color};")

    def _handle_create(self) -> None:
        email = self.email_edit.text().strip()
        password = self.password_edit.text()
        first_name = self.first_name_edit.text().strip()
        last_name = self.last_name_edit.text().strip()
        mobile_raw = self.mobile_number.text().strip()
        country_code = self.mobile_country.currentData() or "+91"
        mobile_number = f"{country_code}{mobile_raw}"
        status = self.status_combo.currentText()

        self._set_error("")

        if not email:
            self._set_error("Email is required.")
            self.email_edit.setFocus()
            return
        if not _EMAIL_REGEX.match(email):
            self._set_error("Please enter a valid email address.")
            self.email_edit.setFocus()
            return
        if not password:
            self._set_error("Password is required.")
            self.password_edit.setFocus()
            return
        if len(password) < 6:
            self._set_error("Password must be at least 6 characters.")
            self.password_edit.setFocus()
            return
        if not first_name:
            self._set_error("First name is required.")
            self.first_name_edit.setFocus()
            return
        if not last_name:
            self._set_error("Last name is required.")
            self.last_name_edit.setFocus()
            return
        if not mobile_raw:
            self._set_error("Mobile number is required.")
            self.mobile_number.setFocus()
            return

        valid, msg = validate_mobile(country_code, mobile_raw)
        if not valid:
            self._set_error(msg)
            self.mobile_number.setFocus()
            return

        # Org/Dept/Position are optional; any non-empty value must exactly match a list line.
        org_text = self.org_name_edit.text().strip()
        if org_text:
            if org_text not in set(self._format_items(self._org_items)):
                self._set_error(strict_list_selection_message("an organization"))
                self.org_name_edit.setFocus()
                return
            org_id = self._parse_selected_id(org_text)
        else:
            org_id = None

        dept_text = self.dept_name_edit.text().strip()
        if dept_text:
            if dept_text not in set(self._format_items(self._dept_items)):
                self._set_error(strict_list_selection_message("a department"))
                self.dept_name_edit.setFocus()
                return
            dept_id = self._parse_selected_id(dept_text)
        else:
            dept_id = None

        pos_text = self.position_name_edit.text().strip()
        if pos_text:
            if pos_text not in set(self._format_items(self._position_items)):
                self._set_error(strict_list_selection_message("a position"))
                self.position_name_edit.setFocus()
                return
            position_id = self._parse_selected_id(pos_text)
        else:
            position_id = None

        self.org_id_edit.setText(org_id or "")
        self.dept_id_value_edit.setText(dept_id or "")
        self.position_id_value_edit.setText(position_id or "")

        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        result = api_create_user(
            email=email,
            password=password,
            firstName=first_name,
            lastName=last_name,
            mobileNumber=mobile_number,
            status=status,
            orgId=int(org_id) if org_id and str(org_id).isdigit() else org_id,
            deptId=int(dept_id) if dept_id and str(dept_id).isdigit() else dept_id,
            positionId=int(position_id) if position_id and str(position_id).isdigit() else position_id,
            token=token,
        )

        if not result.get("success"):
            self._set_error(result.get("message", "Failed to create user."))
            return

        self._set_success(result.get("message", "User created successfully."))
        schedule_after_success(
            delay_ms=800,
            clear_error=self._clear_message,
            reset=lambda: self.reset_to_default(clear_message=False),
            on_back=self.on_back,
            on_success=None,
        )
