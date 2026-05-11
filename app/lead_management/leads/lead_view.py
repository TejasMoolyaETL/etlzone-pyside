"""Update Lead page."""

from __future__ import annotations

from datetime import date, datetime, time as dtime, timezone
from typing import Any, Callable

from PySide6.QtCore import QDate, QTime, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPalette, QPen, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.user_management.users.user_create import _DatePickerDialog
from core.app_preferences import get_timezone, to_utc_iso
from core.api import api_get_all_contact_persons, api_get_all_lead_companies, api_update_lead
from core.api import (
    api_get_master_key_by_app_id_field_name,
    master_key_row_display_label,
    master_key_row_seq_value,
)
from core.nav_access import collect_allowed_action_names, nav_action_visible
from core.user_context import get_nav_access_steps, get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_api_result_message, show_auto_hiding_message
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    APP_FONT_SIZE_PX,
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_FIELD_SPACING_PX,
    FORM_LABEL_STYLE as LABEL_STYLE,
    INPUT_PLACEHOLDER_COLOR,
    INPUT_PLACEHOLDER_FONT_WEIGHT,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_READONLY_INPUT_STYLE as READONLY_INPUT_STYLE,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    MODAL_FIELD_HEIGHT_PX,
    placeholder_example,
)
from ui.post_save_navigation import schedule_after_success
from ui.theme import Theme
from ui.widgets.required_label import field_caption_label, labeled_field_block

_FORM_FIELDS: tuple[tuple[str, str], ...] = (
    ("companyId", "Company*"),
    ("contactPersonId", "Contact Person*"),
    ("contractType", "Contract Type*"),
    ("projectType", "Project Type"),
    ("role", "Role*"),
    ("source", "Source*"),
    ("leadCommunicationChannel", "Lead Communication Channel*"),
    ("leadStatus", "Lead Status*"),
    ("leadStage", "Lead Stage*"),
    ("nextAction", "Next Action*"),
    ("status", "Status*"),
    ("jobLocation", "Job Location"),
    ("experienceNeeded", "Experience Needed"),
    ("jobDesc", "Job Desc"),
    ("mandatorySkills", "Mandatory Skills"),
    ("optionalSkills", "Optional Skills"),
    ("expectedBilling", "Expected Billing"),
    ("endClientName", "End Client Name"),
    ("intermediateClient1", "Intermediate Client 1"),
    ("intermediateClient2", "Intermediate Client 2"),
    ("intermediateClient3", "Intermediate Client 3"),
    ("intermediateClient4", "Intermediate Client 4"),
    ("currency", "Currency"),
    ("nextFollowUpOn", "Next Follow Up On (YYYY-MM-DD)"),
    ("lastContacted", "Last Contacted (YYYY-MM-DD)"),
    ("estimatedStartDate", "Estimated Start Date (YYYY-MM-DD)"),
    ("estimatedEndDate", "Estimated End Date (YYYY-MM-DD)"),
    ("laptopOwnership", "Laptop Ownership"),
    ("accommodationOwnership", "Accommodation Ownership"),
    ("travelExpenseOwnership", "Travel Expense Ownership"),
    ("perDiemOwnership", "Per Diem Ownership"),
    ("desc", "Description"),
    ("leadRemarks", "Lead Remarks"),
    ("commentAtEtlzone", "Comment At ETLZone"),
)

_INT_FIELDS: frozenset[str] = frozenset({"companyId", "contactPersonId"})

_MASTER_FIELD_BY_LEAD_KEY: dict[str, str] = {
    "contractType": "contract_type",
    "projectType": "project_type",
    "role": "lead_role",
    "source": "lead_source",
    "leadCommunicationChannel": "lead_communication_channel",
    "leadStatus": "lead_status",
    "leadStage": "lead_stage",
    "nextAction": "lead_next_action",
    "status": "lead_status2",
    "laptopOwnership": "laptop_ownership",
    "accommodationOwnership": "accommodation_ownership",
    "travelExpenseOwnership": "travel_expense_ownership",
    "perDiemOwnership": "per_diem_ownership",
}

_REQUIRED_MASTER_KEYS: tuple[str, ...] = (
    "contractType",
    "role",
    "source",
    "leadCommunicationChannel",
    "leadStatus",
    "leadStage",
    "nextAction",
    "status",
)

_GLOBAL_CURRENCY_CODES: tuple[str, ...] = (
    "USD",
    "EUR",
    "GBP",
    "INR",
    "JPY",
    "AUD",
    "CAD",
    "CHF",
    "CNY",
    "SGD",
    "AED",
    "SAR",
    "QAR",
    "KWD",
    "BHD",
    "OMR",
    "MYR",
    "THB",
    "IDR",
    "PHP",
    "KRW",
    "VND",
    "ZAR",
    "EGP",
    "NGN",
    "TRY",
    "RUB",
    "BRL",
    "MXN",
    "NZD",
)


def _qtime_to_12h(initial: QTime) -> tuple[int, int, bool, int]:
    h24, m, s = initial.hour(), initial.minute(), initial.second()
    if h24 == 0:
        return 12, m, False, s
    if h24 < 12:
        return h24, m, False, s
    if h24 == 12:
        return 12, m, True, s
    return h24 - 12, m, True, s


class _TimePickerDialog(QDialog):
    def __init__(self, parent: QWidget | None, initial: QTime) -> None:
        super().__init__(parent)
        self.setWindowTitle("Time")
        self.setModal(True)
        self.setMinimumWidth(300)
        self.setStyleSheet(
            "QDialog { background-color: #ffffff; }"
            "QLabel { color: #1a1a1a; font-size: 13px; }"
        )
        h12, minute, is_pm, self._seconds = _qtime_to_12h(initial)

        self._hour_combo = QComboBox()
        for h in range(1, 13):
            self._hour_combo.addItem(str(h), h)
        self._hour_combo.setCurrentIndex(self._hour_combo.findData(h12))

        self._minute_combo = QComboBox()
        for mm in range(60):
            self._minute_combo.addItem(f"{mm:02d}", mm)
        self._minute_combo.setCurrentIndex(self._minute_combo.findData(minute))
        self._minute_combo.setMaxVisibleItems(10)

        self._ampm_combo = QComboBox()
        self._ampm_combo.addItem("AM")
        self._ampm_combo.addItem("PM")
        self._ampm_combo.setCurrentIndex(1 if is_pm else 0)

        for c in (self._hour_combo, self._minute_combo, self._ampm_combo):
            apply_form_combobox_field(c, height_px=MODAL_FIELD_HEIGHT_PX)
            c.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._hour_combo.setMinimumWidth(56)
        self._minute_combo.setMinimumWidth(56)
        self._ampm_combo.setMinimumWidth(72)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 12)
        outer.setSpacing(14)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        time_row = QHBoxLayout()
        time_row.setSpacing(8)
        time_row.addWidget(self._hour_combo)
        colon = QLabel(":")
        colon.setStyleSheet("color: #1a1a1a; font-size: 15px; font-weight: 600;")
        time_row.addWidget(colon)
        time_row.addWidget(self._minute_combo)
        time_row.addSpacing(4)
        time_row.addWidget(self._ampm_combo)
        time_row.addStretch()
        form.addRow(QLabel("Time:"), time_row)
        outer.addLayout(form)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        ok_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        ok_btn.setDefault(True)
        ok_btn.setAutoDefault(True)
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        outer.addLayout(btn_row)

    def selected_time(self) -> QTime:
        h12 = int(self._hour_combo.currentData())
        m = int(self._minute_combo.currentData())
        is_pm = self._ampm_combo.currentIndex() == 1
        if is_pm:
            h24 = 12 if h12 == 12 else h12 + 12
        else:
            h24 = 0 if h12 == 12 else h12
        return QTime(h24, m, self._seconds)


class _DatePickerDialogWithCurrentDatetime(_DatePickerDialog):
    def __init__(self, initial_date: QDate, parent: QWidget | None = None) -> None:
        super().__init__(initial_date, parent)
        self._use_current_datetime = False
        self._current_dt_checkbox = QCheckBox("Current Datetime")
        self._current_dt_checkbox.setStyleSheet(LABEL_STYLE)
        self._current_dt_checkbox.toggled.connect(self._on_current_datetime_toggled)
        root_layout = self.layout()
        if isinstance(root_layout, QVBoxLayout) and root_layout.count() > 0:
            nav_item = root_layout.itemAt(0)
            nav_layout = nav_item.layout() if nav_item else None
            if isinstance(nav_layout, QHBoxLayout):
                nav_layout.addWidget(self._current_dt_checkbox)

    def _on_current_datetime_toggled(self, checked: bool) -> None:
        if checked:
            self._use_current_datetime = True
            self.accept()

    def use_current_datetime(self) -> bool:
        return self._use_current_datetime


class _DateTimePickerField(QWidget):
    value_changed = Signal()

    def __init__(self, field_height_px: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = datetime.combine(date.today(), dtime(0, 0, 0))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._display = QLineEdit()
        self._display.setReadOnly(True)
        self._display.setCursor(Qt.CursorShape.PointingHandCursor)
        self._display.setFixedHeight(field_height_px)
        self._display.setMinimumWidth(260)
        self._display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._display.setStyleSheet(INPUT_STYLE)
        self._display.mousePressEvent = lambda _e: self._open_datetime_flow()
        layout.addWidget(self._display)
        self._update_display()

    def _open_datetime_flow(self) -> None:
        d = self._value.date()
        date_dlg = _DatePickerDialogWithCurrentDatetime(QDate(d.year, d.month, d.day), self)
        if date_dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if date_dlg.use_current_datetime():
            self._value = datetime.now().replace(microsecond=0)
            self._update_display()
            self.value_changed.emit()
            return
        new_date = date_dlg.selected_date()
        tpart = self._value.time()
        q_init = QTime(tpart.hour, tpart.minute, tpart.second)
        time_dlg = _TimePickerDialog(self, q_init)
        if time_dlg.exec() != QDialog.DialogCode.Accepted:
            return
        qt = time_dlg.selected_time()
        self._value = datetime.combine(new_date, dtime(qt.hour(), qt.minute(), qt.second()))
        self._update_display()
        self.value_changed.emit()

    def _update_display(self) -> None:
        self._display.setText(self._value.strftime("%d %b %Y %I:%M %p"))

    def set_defaults_today_midnight(self) -> None:
        self._value = datetime.combine(date.today(), dtime(0, 0, 0))
        self._update_display()

    def iso_timestamp(self) -> str:
        return self._value.strftime("%Y-%m-%dT%H:%M:%S")

    def set_iso_timestamp(self, value: Any) -> None:
        s = str(value or "").strip()
        if not s:
            self.set_defaults_today_midnight()
            return
        try:
            s_iso = s.replace("Z", "+00:00")
            if len(s_iso) >= 10 and s_iso[10:11] == " ":
                s_iso = s_iso[:10] + "T" + s_iso[11:]
            dt = datetime.fromisoformat(s_iso[:32].rstrip())
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            tz_id = get_timezone()
            target_tz = None
            if tz_id:
                try:
                    from zoneinfo import ZoneInfo

                    target_tz = ZoneInfo(tz_id)
                except Exception:
                    target_tz = None
            dt_local = dt.astimezone(target_tz) if target_tz is not None else dt.astimezone()
            self._value = dt_local.replace(tzinfo=None)
        except ValueError:
            self.set_defaults_today_midnight()
            return
        self._update_display()

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self._display.setEnabled(enabled)


class _JobDescHeightGrip(QWidget):
    """Bottom-right corner grip: drag vertically to resize the job description editor height."""

    def __init__(
        self,
        editor: QPlainTextEdit,
        *,
        min_h: int = 56,
        max_h: int = 420,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._editor = editor
        self._min_h = min_h
        self._max_h = max_h
        self._press_y: float | None = None
        self._height_at_press = 0
        self.setFixedSize(18, 14)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setToolTip("Drag up or down to resize height")

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#94a3b8"))
        pen.setWidthF(1.25)
        p.setPen(pen)
        w, h = self.width(), self.height()
        for i in range(3):
            o = 3 + i * 3
            p.drawLine(w - o, h - 1, w - 1, h - o)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_y = float(event.globalPosition().y())
            self._height_at_press = self._editor.minimumHeight()
            self.grabMouse()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._press_y is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            dy = float(event.globalPosition().y()) - self._press_y
            nh = int(max(self._min_h, min(self._max_h, self._height_at_press + dy)))
            self._editor.setMinimumHeight(nh)
            host = self.parent()
            if isinstance(host, QWidget):
                host.setMinimumHeight(nh)
                host.updateGeometry()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._press_y is not None:
            self._press_y = None
            self.releaseMouse()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class _JobDescEditorWithGrip(QWidget):
    """QPlainTextEdit with a resize grip overlaid on the bottom-right corner."""

    def __init__(self, editor: QPlainTextEdit, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._edit = editor
        editor.setParent(self)
        self._grip = _JobDescHeightGrip(editor, parent=self)
        self._grip.raise_()

    def editor(self) -> QPlainTextEdit:
        return self._edit

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._edit.setGeometry(0, 0, self.width(), self.height())
        g = self._grip
        g.setGeometry(self.width() - g.width(), self.height() - g.height(), g.width(), g.height())
        g.raise_()


class ViewLeadPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._lead: dict[str, Any] = {}
        self._can_edit_action = True
        self._lead_id: Any = None
        self._lead_id_edit: QLineEdit | None = None
        self._field_edits: dict[str, QLineEdit] = {}
        self._job_desc_edit: QPlainTextEdit | None = None
        self._job_desc_default_min_h = 88
        self._jd_style_editing = ""
        self._jd_style_readonly = ""
        self._company_combo: QComboBox | None = None
        self._contact_person_combo: QComboBox | None = None
        self._currency_combo: QComboBox | None = None
        self._master_combo_by_key: dict[str, QComboBox] = {}
        self._datetime_fields: dict[str, _DateTimePickerField] = {}
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
        hl.addWidget(QLabel("Update Lead"))
        hl.addStretch()
        back_btn = QPushButton("Back")
        back_btn.setFixedWidth(100)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self._handle_back)
        hl.addWidget(back_btn)
        layout.addWidget(header)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(12)

        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        card.setMaximumWidth(980)
        card.setStyleSheet(
            f"#profileCard {{ background: {Theme.BG_WHITE}; border: 1px solid {Theme.BORDER_DEFAULT}; "
            "border-radius: 10px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        field_h = MODAL_FIELD_HEIGHT_PX
        field_min_w = 260

        def new_section_grid() -> QGridLayout:
            section_grid = QGridLayout()
            section_grid.setHorizontalSpacing(24)
            section_grid.setVerticalSpacing(10)
            section_grid.setColumnStretch(0, 1)
            section_grid.setColumnStretch(1, 1)
            return section_grid

        scroll_body = QWidget()
        scroll_body.setStyleSheet(f"background-color: {Theme.BG_WHITE};")
        scroll_layout = QVBoxLayout(scroll_body)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(0)

        def horizontal_rule_block() -> QWidget:
            wrap = QWidget()
            lay = QVBoxLayout(wrap)
            lay.setContentsMargins(0, 10, 0, 10)
            lay.setSpacing(0)
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Plain)
            line.setFixedHeight(1)
            line.setStyleSheet(
                f"QFrame {{ background-color: {Theme.BORDER_DEFAULT}; border: none; }}"
            )
            lay.addWidget(line)
            return wrap

        field_by_key = {key: caption for key, caption in _FORM_FIELDS}

        def add_line_field(grid: QGridLayout, key: str, row: int, col: int, col_span: int = 1) -> None:
            if key in ("nextFollowUpOn", "lastContacted", "estimatedStartDate", "estimatedEndDate"):
                picker = _DateTimePickerField(field_h)
                picker.set_defaults_today_midnight()
                self._datetime_fields[key] = picker
                grid.addWidget(
                    labeled_field_block(field_caption_label(field_by_key[key], LABEL_STYLE), picker),
                    row,
                    col,
                    1,
                    col_span,
                )
                return
            if key == "currency":
                combo = QComboBox()
                combo.setMinimumWidth(field_min_w)
                combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                apply_form_combobox_field(combo, height_px=field_h)
                self._currency_combo = combo
                grid.addWidget(
                    labeled_field_block(field_caption_label(field_by_key[key], LABEL_STYLE), combo),
                    row,
                    col,
                    1,
                    col_span,
                )
                return
            if key in ("companyId", "contactPersonId"):
                combo = QComboBox()
                combo.setMinimumWidth(field_min_w)
                combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                apply_form_combobox_field(combo, height_px=field_h)
                if key == "companyId":
                    self._company_combo = combo
                else:
                    self._contact_person_combo = combo
                grid.addWidget(
                    labeled_field_block(field_caption_label(field_by_key[key], LABEL_STYLE), combo),
                    row,
                    col,
                    1,
                    col_span,
                )
                return
            if key in _MASTER_FIELD_BY_LEAD_KEY:
                combo = QComboBox()
                combo.setMinimumWidth(field_min_w)
                combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                apply_form_combobox_field(combo, height_px=field_h)
                self._master_combo_by_key[key] = combo
                grid.addWidget(
                    labeled_field_block(field_caption_label(field_by_key[key], LABEL_STYLE), combo),
                    row,
                    col,
                    1,
                    col_span,
                )
                return
            if key == "jobDesc":
                jd_h0 = self._job_desc_default_min_h
                block = QWidget()
                block.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                v = QVBoxLayout(block)
                v.setContentsMargins(0, 0, 0, 0)
                v.setSpacing(FORM_LABEL_FIELD_SPACING_PX)
                v.addWidget(field_caption_label(field_by_key[key], LABEL_STYLE))
                edit = QPlainTextEdit()
                edit.setPlaceholderText(
                    placeholder_example("Role summary, responsibilities, tech stack, …")
                )
                edit.setMinimumHeight(jd_h0)
                edit.setMinimumWidth(field_min_w)
                edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
                edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                self._jd_style_editing = (
                    f"QPlainTextEdit {{ font-size: {APP_FONT_SIZE_PX}px; padding: 4px 8px; "
                    "border: 1px solid #e2e8f0; border-radius: 4px; background-color: #ffffff; }}"
                    f"QPlainTextEdit::placeholder {{ color: {INPUT_PLACEHOLDER_COLOR}; "
                    f"font-size: {APP_FONT_SIZE_PX}px; font-weight: {INPUT_PLACEHOLDER_FONT_WEIGHT}; }}"
                )
                self._jd_style_readonly = (
                    f"QPlainTextEdit {{ font-size: {APP_FONT_SIZE_PX}px; padding: 4px 8px; "
                    "border: 1px solid #e2e8f0; border-radius: 4px; background-color: #f1f5f9; color: #64748b; }}"
                )
                edit.setStyleSheet(self._jd_style_editing)
                wrap = _JobDescEditorWithGrip(edit)
                wrap.setMinimumHeight(jd_h0)
                wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                v.addWidget(wrap, 1)
                self._job_desc_edit = edit
                grid.addWidget(block, row, col, 1, col_span)
                return
            edit = QLineEdit()
            edit.setFixedHeight(field_h)
            edit.setStyleSheet(INPUT_STYLE)
            edit.setMinimumWidth(field_min_w)
            edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._field_edits[key] = edit
            grid.addWidget(
                labeled_field_block(field_caption_label(field_by_key[key], LABEL_STYLE), edit),
                row,
                col,
                1,
                col_span,
            )

        core_grid = new_section_grid()
        core_row = 0
        lead_id_edit = QLineEdit()
        lead_id_edit.setReadOnly(True)
        lead_id_edit.setFixedHeight(field_h)
        lead_id_edit.setStyleSheet(READONLY_INPUT_STYLE)
        lead_id_edit.setMinimumWidth(field_min_w)
        lead_id_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._lead_id_edit = lead_id_edit
        core_grid.addWidget(
            labeled_field_block(field_caption_label("Lead ID", LABEL_STYLE), lead_id_edit),
            core_row,
            0,
            1,
            1,
        )
        add_line_field(core_grid, "status", core_row, 1)
        core_row += 1
        add_line_field(core_grid, "companyId", core_row, 0)
        add_line_field(core_grid, "contactPersonId", core_row, 1)
        core_row += 1
        core_grid.addWidget(horizontal_rule_block(), core_row, 0, 1, 2)
        core_row += 1
        add_line_field(core_grid, "contractType", core_row, 0)
        add_line_field(core_grid, "projectType", core_row, 1)
        core_row += 1
        for left_key, right_key in (
            ("role", "source"),
            ("leadCommunicationChannel", "leadStatus"),
            ("leadStage", "nextAction"),
        ):
            add_line_field(core_grid, left_key, core_row, 0)
            add_line_field(core_grid, right_key, core_row, 1)
            core_row += 1
        core_grid.addWidget(horizontal_rule_block(), core_row, 0, 1, 2)
        core_row += 1
        add_line_field(core_grid, "jobLocation", core_row, 0)
        add_line_field(core_grid, "experienceNeeded", core_row, 1)
        core_row += 1
        add_line_field(core_grid, "jobDesc", core_row, 0, col_span=2)
        core_row += 1
        add_line_field(core_grid, "mandatorySkills", core_row, 0)
        add_line_field(core_grid, "optionalSkills", core_row, 1)
        core_row += 1
        core_grid.addWidget(horizontal_rule_block(), core_row, 0, 1, 2)
        core_row += 1
        add_line_field(core_grid, "currency", core_row, 0)
        add_line_field(core_grid, "expectedBilling", core_row, 1)
        core_row += 1
        core_grid.addWidget(horizontal_rule_block(), core_row, 0, 1, 2)
        core_row += 1
        add_line_field(core_grid, "estimatedStartDate", core_row, 0)
        add_line_field(core_grid, "estimatedEndDate", core_row, 1)
        core_row += 1
        core_grid.addWidget(horizontal_rule_block(), core_row, 0, 1, 2)
        core_row += 1
        add_line_field(core_grid, "lastContacted", core_row, 0)
        add_line_field(core_grid, "nextFollowUpOn", core_row, 1)
        core_row += 1
        core_grid.addWidget(horizontal_rule_block(), core_row, 0, 1, 2)
        core_row += 1
        scroll_layout.addLayout(core_grid)
        self._field_edits["jobLocation"].setPlaceholderText(placeholder_example("Bangalore, hybrid, or Remote"))
        self._field_edits["experienceNeeded"].setPlaceholderText(placeholder_example("5+ years, lead experience"))
        self._field_edits["mandatorySkills"].setPlaceholderText(placeholder_example("Python, SQL, REST APIs"))
        self._field_edits["optionalSkills"].setPlaceholderText(placeholder_example("Docker, AWS, Kubernetes"))

        own_grid = new_section_grid()
        add_line_field(own_grid, "laptopOwnership", 0, 0)
        add_line_field(own_grid, "accommodationOwnership", 0, 1)
        add_line_field(own_grid, "travelExpenseOwnership", 1, 0)
        add_line_field(own_grid, "perDiemOwnership", 1, 1)
        own_grid.addWidget(horizontal_rule_block(), 2, 0, 1, 2)
        scroll_layout.addLayout(own_grid)

        client_grid = new_section_grid()
        add_line_field(client_grid, "endClientName", 0, 0, col_span=2)
        for row, left_key, right_key in (
            (1, "intermediateClient1", "intermediateClient2"),
            (2, "intermediateClient3", "intermediateClient4"),
        ):
            add_line_field(client_grid, left_key, row, 0)
            add_line_field(client_grid, right_key, row, 1)
        client_grid.addWidget(horizontal_rule_block(), 3, 0, 1, 2)
        self._field_edits["endClientName"].setPlaceholderText(placeholder_example("Shell"))
        self._field_edits["intermediateClient1"].setPlaceholderText(placeholder_example("TCS"))
        self._field_edits["intermediateClient2"].setPlaceholderText(placeholder_example("Infosys"))
        self._field_edits["intermediateClient3"].setPlaceholderText(placeholder_example("Capgemini"))
        self._field_edits["intermediateClient4"].setPlaceholderText(placeholder_example("IBM"))
        self._field_edits["expectedBilling"].setPlaceholderText(placeholder_example("15000"))
        scroll_layout.addLayout(client_grid)

        notes_grid = new_section_grid()
        add_line_field(notes_grid, "desc", 0, 0, col_span=2)
        add_line_field(notes_grid, "leadRemarks", 1, 0, col_span=2)
        add_line_field(notes_grid, "commentAtEtlzone", 2, 0, col_span=2)
        self._field_edits["desc"].setPlaceholderText(placeholder_example("Interview or rate discussion"))
        self._field_edits["leadRemarks"].setPlaceholderText(placeholder_example("Interview discussion ongoing"))
        self._field_edits["commentAtEtlzone"].setPlaceholderText(placeholder_example("Client discussion in progress"))
        scroll_layout.addLayout(notes_grid)

        self._populate_currency_combo()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(scroll_body)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        vp = scroll.viewport()
        vp.setAutoFillBackground(True)
        vpal = vp.palette()
        vpal.setColor(QPalette.ColorRole.Window, QColor(Theme.BG_WHITE))
        vp.setPalette(vpal)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {Theme.BG_WHITE}; border: none; }}"
            f"QScrollArea > QWidget > QWidget {{ background: {Theme.BG_WHITE}; }}"
        )

        self._error_label = QLabel()
        self._error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error_label.setWordWrap(True)
        self._error_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._error_label.setVisible(False)
        card_layout.addWidget(scroll, 1)
        card_layout.addWidget(self._error_label)

        self._back_btn = QPushButton("Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._back_btn.clicked.connect(self._handle_back)
        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setFixedWidth(100)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setStyleSheet(
            FORM_PRIMARY_BUTTON_STYLESHEET
            + " QPushButton:disabled {"
            + " background-color: #e5e7eb;"
            + " color: #6b7280;"
            + " border: 1px solid #cbd5e1;"
            + "}"
        )
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
        display_btns.setStyleSheet("background: transparent; border: none;")
        db = QHBoxLayout(display_btns)
        db.setContentsMargins(0, 0, 0, 0)
        db.setSpacing(12)
        db.setAlignment(Qt.AlignmentFlag.AlignLeft)
        db.addWidget(self._edit_btn)
        db.addWidget(self._back_btn)
        edit_btns = QWidget()
        edit_btns.setStyleSheet("background: transparent; border: none;")
        eb = QHBoxLayout(edit_btns)
        eb.setContentsMargins(0, 0, 0, 0)
        eb.setSpacing(12)
        eb.setAlignment(Qt.AlignmentFlag.AlignLeft)
        eb.addWidget(self._save_btn)
        eb.addWidget(self._cancel_btn)

        self._btn_stack = QStackedWidget()
        self._btn_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self._btn_stack.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._btn_stack.addWidget(display_btns)
        self._btn_stack.addWidget(edit_btns)
        card_layout.addWidget(self._btn_stack, 0, Qt.AlignmentFlag.AlignLeft)

        cl.addWidget(card, 1)
        layout.addWidget(content, 1)
        self._switch_to_view_mode()

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = profile.get("token") or profile.get("accessToken") or profile.get("access_token") or profile.get("jwt")
        return str(token) if token else None

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self._error_label)
        self._error_label.setText("")
        self._error_label.setVisible(False)

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=True, clear_on_user_activity=False)

    @staticmethod
    def _coerce_seq_value(value: Any) -> Any | None:
        if value is None:
            return None
        if isinstance(value, dict):
            seq_val = master_key_row_seq_value(value)
            if seq_val is not None:
                return seq_val
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value == int(value):
            return int(value)
        s = str(value).strip()
        if s.isdigit():
            return int(s)
        return None

    def _master_seq_from_record(self, key: str) -> Any | None:
        seq = self._coerce_seq_value(self._lead.get(key))
        if seq is not None:
            return seq
        for alt in (f"{key}Seq", f"{key}_seq"):
            seq = self._coerce_seq_value(self._lead.get(alt))
            if seq is not None:
                return seq
        return None

    def _set_combo_to_data(self, combo: QComboBox | None, value: Any) -> None:
        if combo is None or value is None:
            return
        idx = combo.findData(value)
        if idx < 0 and isinstance(value, int):
            idx = combo.findData(str(value))
        elif idx < 0:
            s = str(value).strip()
            if s.isdigit():
                idx = combo.findData(int(s))
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _populate_company_combo(self) -> None:
        combo = self._company_combo
        if combo is None:
            return
        result = api_get_all_lead_companies(token=self._token())
        rows = result.get("data") if result.get("success") else []
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Select company…", None)
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cid = row.get("companyId") or row.get("id")
                if cid is None:
                    continue
                name = str(row.get("companyName") or row.get("name") or "").strip()
                label = f"{cid} | {name}" if name else str(cid)
                combo.addItem(label, cid)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _populate_contact_person_combo(self) -> None:
        combo = self._contact_person_combo
        if combo is None:
            return
        result = api_get_all_contact_persons(token=self._token())
        rows = result.get("data") if result.get("success") else []
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Select contact person…", None)
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                contact_id = row.get("contactId") or row.get("contactPersonId") or row.get("id")
                if contact_id is None:
                    continue
                name = str(row.get("name") or row.get("contactPersonName") or "").strip()
                label = f"{contact_id} | {name}" if name else str(contact_id)
                combo.addItem(label, contact_id)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _populate_master_combo(self, lead_key: str, field_name: str) -> None:
        combo = self._master_combo_by_key.get(lead_key)
        if combo is None:
            return
        result = api_get_master_key_by_app_id_field_name(field_name=field_name, token=self._token())
        rows = result.get("data") if result.get("success") else []
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(f"Select {lead_key}…", None)
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                seq_val = master_key_row_seq_value(row)
                if seq_val is None:
                    continue
                label = master_key_row_display_label(row).strip()
                if not label:
                    continue
                combo.addItem(label, seq_val)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _populate_currency_combo(self) -> None:
        combo = self._currency_combo
        if combo is None:
            return
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Select currency…", None)
        for code in _GLOBAL_CURRENCY_CODES:
            combo.addItem(code, code)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _apply_lead_values(self) -> None:
        if self._lead_id_edit is not None:
            self._lead_id_edit.setText(str(self._lead_id or ""))
        for key in (
            "endClientName",
            "intermediateClient1",
            "intermediateClient2",
            "intermediateClient3",
            "intermediateClient4",
            "expectedBilling",
            "jobLocation",
            "experienceNeeded",
            "mandatorySkills",
            "optionalSkills",
            "desc",
            "leadRemarks",
            "commentAtEtlzone",
        ):
            edit = self._field_edits.get(key)
            if edit is None:
                continue
            edit.setText(str(self._lead.get(key) or ""))
        if self._job_desc_edit is not None:
            self._job_desc_edit.setPlainText(str(self._lead.get("jobDesc") or ""))
        self._set_combo_to_data(self._company_combo, self._lead.get("companyId"))
        self._set_combo_to_data(self._contact_person_combo, self._lead.get("contactPersonId"))
        for key in _MASTER_FIELD_BY_LEAD_KEY:
            self._set_combo_to_data(self._master_combo_by_key.get(key), self._master_seq_from_record(key))
        if self._currency_combo is not None:
            self._set_combo_to_data(self._currency_combo, self._lead.get("currency"))
        for key, picker in self._datetime_fields.items():
            picker.set_iso_timestamp(self._lead.get(key))

    def set_lead(self, lead: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        self._lead = dict(lead) if lead else {}
        self._lead_id = self._lead.get("leadId") or self._lead.get("id")
        self._refresh_edit_action_access()
        self._populate_company_combo()
        self._populate_contact_person_combo()
        for lead_key, field_name in _MASTER_FIELD_BY_LEAD_KEY.items():
            self._populate_master_combo(lead_key, field_name)
        self._populate_currency_combo()
        self._apply_lead_values()
        self._clear_error()
        if edit_mode and self._lead and self._can_edit_action:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

    def _refresh_edit_action_access(self) -> None:
        steps = get_nav_access_steps()
        if steps is None:
            self._can_edit_action = True
        else:
            allowed = collect_allowed_action_names(steps)
            self._can_edit_action = nav_action_visible("Leads", "edit", allowed)
        self._edit_btn.setEnabled(self._can_edit_action)
        self._edit_btn.setToolTip("" if self._can_edit_action else "Require Permission.")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_edit_action_access()

    def _handle_back(self) -> None:
        if self.on_back:
            self.on_back()

    def _switch_to_view_mode(self) -> None:
        for edit in self._field_edits.values():
            edit.setReadOnly(True)
            edit.setStyleSheet(READONLY_INPUT_STYLE)
        if self._job_desc_edit is not None:
            self._job_desc_edit.setReadOnly(True)
            if self._jd_style_readonly:
                self._job_desc_edit.setStyleSheet(self._jd_style_readonly)
        if self._company_combo is not None:
            self._company_combo.setEnabled(False)
        if self._contact_person_combo is not None:
            self._contact_person_combo.setEnabled(False)
        if self._currency_combo is not None:
            self._currency_combo.setEnabled(False)
        for combo in self._master_combo_by_key.values():
            combo.setEnabled(False)
        for picker in self._datetime_fields.values():
            picker.setEnabled(False)
        self._btn_stack.setCurrentIndex(0)

    def _handle_edit(self) -> None:
        if not self._can_edit_action:
            self._show_error("Edit disabled: missing step access lead-edit.")
            return
        self._clear_error()
        for edit in self._field_edits.values():
            edit.setReadOnly(False)
            edit.setStyleSheet(INPUT_STYLE)
        if self._job_desc_edit is not None:
            self._job_desc_edit.setReadOnly(False)
            if self._jd_style_editing:
                self._job_desc_edit.setStyleSheet(self._jd_style_editing)
        if self._company_combo is not None:
            self._company_combo.setEnabled(True)
        if self._contact_person_combo is not None:
            self._contact_person_combo.setEnabled(True)
        if self._currency_combo is not None:
            self._currency_combo.setEnabled(True)
        for combo in self._master_combo_by_key.values():
            combo.setEnabled(True)
        for picker in self._datetime_fields.values():
            picker.setEnabled(True)
        self._btn_stack.setCurrentIndex(1)

    def _handle_cancel(self) -> None:
        self._clear_error()
        self._apply_lead_values()
        self._switch_to_view_mode()

    def _payload_from_form(self) -> dict[str, Any] | None:
        if self._company_combo is None or self._company_combo.currentIndex() <= 0:
            self._show_error("Company is required.")
            if self._company_combo is not None:
                self._company_combo.setFocus()
            return None
        company_id = self._company_combo.currentData()
        if company_id is None:
            self._show_error("Company is required.")
            self._company_combo.setFocus()
            return None
        if self._contact_person_combo is None or self._contact_person_combo.currentIndex() <= 0:
            self._show_error("Contact Person is required.")
            if self._contact_person_combo is not None:
                self._contact_person_combo.setFocus()
            return None
        contact_id = self._contact_person_combo.currentData()
        if contact_id is None:
            self._show_error("Contact Person is required.")
            self._contact_person_combo.setFocus()
            return None
        payload: dict[str, Any] = {"companyId": company_id, "contactPersonId": contact_id}
        for key in _REQUIRED_MASTER_KEYS:
            combo = self._master_combo_by_key.get(key)
            if combo is None or combo.currentIndex() <= 0 or combo.currentData() is None:
                caption = dict(_FORM_FIELDS).get(key, key).replace("*", "")
                self._show_error(f"{caption} is required.")
                if combo is not None:
                    combo.setFocus()
                return None
        for key, combo in self._master_combo_by_key.items():
            if combo.currentIndex() > 0 and combo.currentData() is not None:
                payload[key] = combo.currentData()
        if self._currency_combo is not None and self._currency_combo.currentIndex() > 0:
            currency = self._currency_combo.currentData()
            if currency is not None:
                payload["currency"] = currency
        for key, picker in self._datetime_fields.items():
            iso_local = picker.iso_timestamp()
            payload[key] = to_utc_iso(iso_local) or iso_local
        if self._job_desc_edit is not None:
            jd = self._job_desc_edit.toPlainText().strip()
            if jd:
                payload["jobDesc"] = jd
        for key, edit in self._field_edits.items():
            if key in ("companyId", "contactPersonId", "jobDesc"):
                continue
            value = edit.text().strip()
            if not value:
                continue
            if key in _INT_FIELDS:
                if not value.isdigit():
                    self._show_error(f"{key} must be a number.")
                    edit.setFocus()
                    return None
                payload[key] = int(value)
            else:
                payload[key] = value
        return payload

    def _handle_save(self) -> None:
        self._clear_error()
        lead_id = self._lead_id
        if lead_id is None or str(lead_id).strip() == "":
            self._show_error("Lead ID is missing.")
            return
        payload = self._payload_from_form()
        if payload is None:
            return
        result = api_update_lead(lead_id, payload, token=self._token())
        ok = show_api_result_message(
            self,
            self._error_label,
            result,
            error_fallback="Failed to update lead.",
            success_fallback="Lead updated successfully.",
        )
        if ok:
            self._lead.update(payload)
            self._apply_lead_values()
            self._switch_to_view_mode()
            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=lambda: None,
                on_back=self.on_back,
                on_success=self.on_update_success,
            )
