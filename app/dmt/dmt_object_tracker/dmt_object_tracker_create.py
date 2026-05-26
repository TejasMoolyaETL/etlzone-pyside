"""Create Object List Tracker record page."""

from __future__ import annotations

from datetime import date, datetime, time as dtime, timezone
from typing import Any, Callable

from PySide6.QtCore import QDate, QObject, QThread, QTime, Qt, Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.user_management.users.user_create import _DatePickerDialog
from core.app_preferences import get_timezone, to_utc_iso
from core.api import (
    api_create_object_tracker,
    api_get_all_modules,
    api_get_all_objects,
    master_key_row_seq_value,
)
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    MODAL_FIELD_HEIGHT_PX,
    placeholder_example,
)
from ui.post_save_navigation import schedule_after_success
from ui.searchable_form_combo import (
    combo_resolved_master_key_seq,
    master_key_invalid_typed_text,
    master_key_seq_for_payload,
    require_master_key_seq_for_payload,
    populate_master_key_by_field_name,
    reset_searchable_combo,
    wire_searchable_master_key_combo,
)
from ui.strict_completer import strict_list_selection_message
from ui.widgets.required_label import field_caption_label, labeled_field_block


_FIELD_STATUS = "dmt_object_list_tracker_status"
_FIELD_BUSINESS_OBJECT_TYPE = "dmt_business_object_type"
_FIELD_SCOPE = "dmt_scope"
_FIELD_LOAD_APPROACH = "dmt_load_approach"
_FIELD_UPLOAD_TOOL = "dmt_upload_tool"
_FIELD_CUSTOMIZATION_STATUS = "dmt_customization_status"
_FIELD_BUILD_STATUS = "dmt_buildStatus"
_FIELD_FUNCTIONAL_UNIT_TESTING_STATUS = "dmt_functionalUnitTestingStatus"
_FIELD_BUSINESS_UNIT_TESTING_STATUS = "dmt_businessUnitTestingStatus"


def _seq_from_record(rec: dict[str, Any], *keys: str) -> Any | None:
    for key in keys:
        v = rec.get(key)
        if v is None:
            continue
        if isinstance(v, dict):
            seq = master_key_row_seq_value(v)
            if seq is not None:
                return seq
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, float) and v == int(v):
            return int(v)
        s = str(v).strip()
        if s.isdigit():
            return int(s)
    return None


def _ids_equal(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return False
    sa, sb = str(a).strip(), str(b).strip()
    if sa == sb:
        return True
    try:
        return int(sa) == int(sb)
    except ValueError:
        return False


def _comments_payload_string(text: str) -> str:
    """API expects ``comments`` as a single string (not a list of lines)."""
    return (text or "").strip()


def _qtime_to_12h(initial: QTime) -> tuple[int, int, bool, int]:
    """Return (hour_1_12, minute, is_pm, second) for combo initialization."""
    h24, m, s = initial.hour(), initial.minute(), initial.second()
    if h24 == 0:
        return 12, m, False, s
    if h24 < 12:
        return h24, m, False, s
    if h24 == 12:
        return 12, m, True, s
    return h24 - 12, m, True, s


class _ReferenceDataWorker(QObject):
    finished = Signal(dict)

    def __init__(self, token: str | None) -> None:
        super().__init__()
        self._token = token

    def run(self) -> None:
        try:
            modules_result = api_get_all_modules(token=self._token)
            objects_result = api_get_all_objects(token=self._token)
            self.finished.emit({"modules": modules_result, "objects": objects_result, "exception": None})
        except Exception as exc:
            self.finished.emit({"exception": str(exc)})


class _TimePickerDialog(QDialog):
    """Second step after date pick — hour / minute / AM-PM combo pickers."""

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
    """Date picker variant with a quick 'Current Datetime' action."""

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
    """Click → same calendar as Valid from; after date OK → time dialog; API gets full ``datetime``."""

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
        self._value = datetime.combine(
            new_date,
            dtime(qt.hour(), qt.minute(), qt.second()),
        )
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


class CreateDmtObjectTrackerPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_create_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._all_object_rows: list[dict[str, Any]] = []
        self._ref_loaded = False
        self._loading_refs = False
        self._ref_thread: QThread | None = None
        self._ref_worker: _ReferenceDataWorker | None = None
        self._completion_dates_user_touched = False
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
        title = QLabel("Create Object List Tracker")
        header_layout.addWidget(title)
        header_layout.addStretch()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedWidth(100)
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self._refresh_reference_combos)
        header_layout.addWidget(self._refresh_btn)
        back_btn = QPushButton("Back")
        back_btn.setFixedWidth(100)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self._handle_back)
        header_layout.addWidget(back_btn)
        layout.addWidget(header)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        card.setMaximumWidth(980)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        field_h = MODAL_FIELD_HEIGHT_PX
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        self.module_combo = QComboBox()
        self.module_combo.addItem("— Select module —", None)
        apply_form_combobox_field(self.module_combo, height_px=field_h, min_width=280)

        self.object_combo = QComboBox()
        self.object_combo.addItem("— Select object —", None)
        apply_form_combobox_field(self.object_combo, height_px=field_h, min_width=280)
        self.object_combo.setEnabled(False)
        self.object_combo.setToolTip("Select a module first.")
        self.module_combo.currentIndexChanged.connect(self._on_module_selection_changed)

        self._field_edits: dict[str, QLineEdit] = {}

        def add_text_field(key: str, label: str, col: int, row: int, placeholder: str) -> None:
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            edit.setStyleSheet(INPUT_STYLE)
            edit.setFixedHeight(field_h)
            edit.setMinimumWidth(260)
            edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._field_edits[key] = edit
            grid.addWidget(labeled_field_block(field_caption_label(label, LABEL_STYLE), edit), row, col)

        def add_separator(row: int) -> None:
            wrap = QWidget()
            wrap_layout = QVBoxLayout(wrap)
            wrap_layout.setContentsMargins(0, 8, 0, 8)
            wrap_layout.setSpacing(0)
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Plain)
            line.setFixedHeight(1)
            line.setStyleSheet("background-color: #e5e7eb; border: none;")
            wrap_layout.addWidget(line)
            grid.addWidget(wrap, row, 0, 1, 3)

        grid.addWidget(
            labeled_field_block(field_caption_label("Module*", LABEL_STYLE), self.module_combo), 0, 0
        )
        grid.addWidget(
            labeled_field_block(field_caption_label("Object*", LABEL_STYLE), self.object_combo), 0, 1
        )

        self.business_object_type_combo = QComboBox()
        apply_form_combobox_field(
            self.business_object_type_combo, height_px=field_h, min_width=260
        )
        wire_searchable_master_key_combo(
            self.business_object_type_combo, search_field_label="Business object type"
        )
        grid.addWidget(
            labeled_field_block(
                field_caption_label("Business Object Type*", LABEL_STYLE),
                self.business_object_type_combo,
            ),
            0,
            2,
        )
        add_text_field("tcode", "TCode", 0, 1, placeholder_example("VA01"))
        self.status_combo = QComboBox()
        apply_form_combobox_field(self.status_combo, height_px=field_h, min_width=260)
        wire_searchable_master_key_combo(self.status_combo, search_field_label="Status")
        grid.addWidget(
            labeled_field_block(field_caption_label("Status*", LABEL_STYLE), self.status_combo),
            1,
            1,
            1,
            2,
        )

        add_separator(2)
        self.scope_combo = QComboBox()
        apply_form_combobox_field(self.scope_combo, height_px=field_h, min_width=260)
        wire_searchable_master_key_combo(self.scope_combo, search_field_label="Scope")
        grid.addWidget(
            labeled_field_block(field_caption_label("Scope*", LABEL_STYLE), self.scope_combo),
            3,
            0,
        )

        self.load_approach_combo = QComboBox()
        apply_form_combobox_field(self.load_approach_combo, height_px=field_h, min_width=260)
        wire_searchable_master_key_combo(
            self.load_approach_combo, search_field_label="Load approach"
        )
        grid.addWidget(
            labeled_field_block(field_caption_label("Load Approach*", LABEL_STYLE), self.load_approach_combo),
            3,
            1,
        )

        self.upload_tool_combo = QComboBox()
        apply_form_combobox_field(self.upload_tool_combo, height_px=field_h, min_width=260)
        wire_searchable_master_key_combo(self.upload_tool_combo, search_field_label="Upload tool")
        grid.addWidget(
            labeled_field_block(field_caption_label("Upload Tool*", LABEL_STYLE), self.upload_tool_combo),
            3,
            2,
        )

        self.customization_status_combo = QComboBox()
        apply_form_combobox_field(
            self.customization_status_combo, height_px=field_h, min_width=260
        )
        wire_searchable_master_key_combo(
            self.customization_status_combo, search_field_label="Customization status"
        )
        grid.addWidget(
            labeled_field_block(
                field_caption_label("Customization Status*", LABEL_STYLE),
                self.customization_status_combo,
            ),
            4,
            0,
        )
        add_text_field("estimatedProdCount", "Estimated Prod Count", 1, 4, placeholder_example("100"))
        add_text_field("dmcProgramName", "DMC Program Name", 2, 4, placeholder_example("Data Migration"))

        add_separator(5)
        self.build_status_combo = QComboBox()
        apply_form_combobox_field(self.build_status_combo, height_px=field_h, min_width=260)
        wire_searchable_master_key_combo(self.build_status_combo, search_field_label="Build status")
        grid.addWidget(
            labeled_field_block(field_caption_label("Build Status*", LABEL_STYLE), self.build_status_combo),
            6,
            0,
        )
        self.build_completion_datetime = _DateTimePickerField(field_h)
        self.build_completion_datetime.set_defaults_today_midnight()
        self.build_completion_datetime.value_changed.connect(self._on_completion_date_changed)
        grid.addWidget(
            labeled_field_block(
                field_caption_label("Build Completion Date & time", LABEL_STYLE),
                self.build_completion_datetime,
            ),
            7,
            0,
        )

        self.functional_unit_testing_status_combo = QComboBox()
        apply_form_combobox_field(
            self.functional_unit_testing_status_combo, height_px=field_h, min_width=260
        )
        wire_searchable_master_key_combo(
            self.functional_unit_testing_status_combo,
            search_field_label="Functional unit testing status",
        )
        grid.addWidget(
            labeled_field_block(
                field_caption_label("Functional Unit Testing Status*", LABEL_STYLE),
                self.functional_unit_testing_status_combo,
            ),
            6,
            1,
        )
        self.functional_unit_testing_completion_datetime = _DateTimePickerField(field_h)
        self.functional_unit_testing_completion_datetime.set_defaults_today_midnight()
        self.functional_unit_testing_completion_datetime.value_changed.connect(
            self._on_completion_date_changed
        )
        grid.addWidget(
            labeled_field_block(
                field_caption_label("Functional Unit Testing Completion Date & time", LABEL_STYLE),
                self.functional_unit_testing_completion_datetime,
            ),
            7,
            1,
        )

        self.business_unit_testing_status_combo = QComboBox()
        apply_form_combobox_field(
            self.business_unit_testing_status_combo, height_px=field_h, min_width=260
        )
        wire_searchable_master_key_combo(
            self.business_unit_testing_status_combo,
            search_field_label="Business unit testing status",
        )
        grid.addWidget(
            labeled_field_block(
                field_caption_label("Business Unit Testing Status*", LABEL_STYLE),
                self.business_unit_testing_status_combo,
            ),
            6,
            2,
        )
        self.business_unit_testing_completion_datetime = _DateTimePickerField(field_h)
        self.business_unit_testing_completion_datetime.set_defaults_today_midnight()
        self.business_unit_testing_completion_datetime.value_changed.connect(
            self._on_completion_date_changed
        )
        grid.addWidget(
            labeled_field_block(
                field_caption_label("Business Unit Testing Completion Date & time", LABEL_STYLE),
                self.business_unit_testing_completion_datetime,
            ),
            7,
            2,
        )

        add_separator(8)
        add_text_field("functionalSPOC", "Functional SPOC", 0, 9, placeholder_example("Ali"))

        self.uploaded_to_sharepoint_combo = QComboBox()
        self.uploaded_to_sharepoint_combo.addItem("Yes", True)
        self.uploaded_to_sharepoint_combo.addItem("No", False)
        apply_form_combobox_field(
            self.uploaded_to_sharepoint_combo, height_px=field_h, min_width=160
        )
        self.uploaded_to_sharepoint_combo.setCurrentIndex(1)
        grid.addWidget(
            labeled_field_block(
                field_caption_label("Uploaded to SharePoint*", LABEL_STYLE),
                self.uploaded_to_sharepoint_combo,
            ),
            9,
            1,
        )
        self._comments_edit = QPlainTextEdit()
        self._comments_edit.setPlaceholderText(placeholder_example("One line per comment"))
        self._comments_edit.setStyleSheet(INPUT_STYLE)
        self._comments_edit.setMinimumHeight(72)
        self._comments_edit.setMaximumHeight(140)
        self._comments_edit.setMinimumWidth(260)
        self._comments_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._comments_edit.setTabChangesFocus(True)
        grid.addWidget(
            labeled_field_block(field_caption_label("Comments", LABEL_STYLE), self._comments_edit),
            10,
            0,
            1,
            3,
        )

        card_layout.addLayout(grid)

        card_layout.addSpacing(12)
        self.error_label = QLabel()
        self.error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self.error_label.setWordWrap(True)
        self.error_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.error_label.setVisible(False)
        card_layout.addWidget(self.error_label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        create_btn = QPushButton("Create")
        create_btn.setFixedWidth(100)
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        create_btn.clicked.connect(self._handle_create)
        btn_layout.addWidget(create_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        cancel_btn.clicked.connect(self._handle_back)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        card_layout.addLayout(btn_layout)

        content_layout.addWidget(card)
        content_layout.addStretch()
        layout.addWidget(content)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._load_reference_combos(force=True)

    def _on_completion_date_changed(self) -> None:
        self._completion_dates_user_touched = True

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _refresh_reference_combos(self) -> None:
        self._load_reference_combos(force=True)

    def _set_reference_loading_state(self, loading: bool) -> None:
        self._loading_refs = loading
        self._refresh_btn.setEnabled(not loading)
        self.module_combo.setEnabled(not loading)
        self.object_combo.setEnabled(False if loading else self.module_combo.currentData() is not None)
        for c in self._master_key_combos():
            c.setEnabled(not loading)
        self._refresh_btn.setText("Refresh")

    def _load_reference_combos(self, *, force: bool = False) -> None:
        if self._ref_thread is not None:
            return
        if self._ref_loaded and not force:
            return
        self._clear_error()
        self._set_reference_loading_state(True)
        self.module_combo.blockSignals(True)
        self.object_combo.blockSignals(True)
        self.module_combo.clear()
        self.object_combo.clear()
        self.module_combo.addItem("Loading modules...", None)
        self.object_combo.addItem("Loading objects...", None)
        self.module_combo.blockSignals(False)
        self.object_combo.blockSignals(False)

        self._ref_thread = QThread(self)
        self._ref_worker = _ReferenceDataWorker(self._token())
        self._ref_worker.moveToThread(self._ref_thread)
        self._ref_thread.started.connect(self._ref_worker.run)
        self._ref_worker.finished.connect(self._on_reference_data_loaded)
        self._ref_worker.finished.connect(self._ref_thread.quit)
        self._ref_thread.finished.connect(self._on_reference_worker_finished)
        self._ref_thread.start()

    def _on_reference_data_loaded(self, payload: dict[str, Any]) -> None:
        if payload.get("exception"):
            self._show_error(
                f"Failed to load reference data: {payload.get('exception')}",
                clear_on_user_activity=False,
            )
            return

        modules_result = payload.get("modules") or {}
        objects_result = payload.get("objects") or {}

        self.module_combo.blockSignals(True)
        self.object_combo.blockSignals(True)
        self.module_combo.clear()
        self.object_combo.clear()
        self.module_combo.addItem("— Select module —", None)
        self.object_combo.addItem("— Select object —", None)

        if modules_result.get("success"):
            for row in modules_result.get("data") or []:
                if not isinstance(row, dict):
                    continue
                module_id = row.get("moduleId") or row.get("id")
                if module_id is None:
                    continue
                name = str(row.get("moduleName") or row.get("name") or module_id)
                self.module_combo.addItem(name, module_id)

        self._all_object_rows = []
        if objects_result.get("success"):
            self._all_object_rows = [
                r for r in (objects_result.get("data") or []) if isinstance(r, dict)
            ]

        if not modules_result.get("success"):
            self._show_error(
                str(modules_result.get("message") or "Failed to load modules."),
                clear_on_user_activity=False,
            )
        elif not objects_result.get("success"):
            self._show_error(
                str(objects_result.get("message") or "Failed to load objects."),
                clear_on_user_activity=False,
            )

        self.module_combo.setCurrentIndex(0)
        self.object_combo.setCurrentIndex(0)
        self.module_combo.blockSignals(False)
        self.object_combo.blockSignals(False)
        self._on_module_selection_changed()

        if modules_result.get("success") and objects_result.get("success"):
            self._ref_loaded = True
            self._populate_tracker_master_field_combos()

    def _populate_tracker_master_field_combos(self) -> None:
        tk = self._token()
        specs: tuple[tuple[QComboBox, str], ...] = (
            (self.status_combo, _FIELD_STATUS),
            (self.business_object_type_combo, _FIELD_BUSINESS_OBJECT_TYPE),
            (self.scope_combo, _FIELD_SCOPE),
            (self.load_approach_combo, _FIELD_LOAD_APPROACH),
            (self.upload_tool_combo, _FIELD_UPLOAD_TOOL),
            (self.customization_status_combo, _FIELD_CUSTOMIZATION_STATUS),
            (self.build_status_combo, _FIELD_BUILD_STATUS),
            (self.functional_unit_testing_status_combo, _FIELD_FUNCTIONAL_UNIT_TESTING_STATUS),
            (self.business_unit_testing_status_combo, _FIELD_BUSINESS_UNIT_TESTING_STATUS),
        )
        for combo, field_name in specs:
            populate_master_key_by_field_name(
                combo,
                field_name,
                token=tk,
                include_placeholder=False,
            )

    def _on_reference_worker_finished(self) -> None:
        self._set_reference_loading_state(False)
        if self._ref_worker is not None:
            self._ref_worker.deleteLater()
        if self._ref_thread is not None:
            self._ref_thread.deleteLater()
        self._ref_worker = None
        self._ref_thread = None

    def _repopulate_object_combo_for_module(self) -> None:
        self.object_combo.clear()
        self.object_combo.addItem("— Select object —", None)
        module_id = self.module_combo.currentData()
        if module_id is None:
            return
        for row in self._all_object_rows:
            object_id = row.get("objectId") or row.get("id")
            if object_id is None:
                continue
            row_module_id = row.get("moduleId") or row.get("module_id")
            if row_module_id is None or not _ids_equal(row_module_id, module_id):
                continue
            name = str(row.get("objectName") or row.get("name") or object_id)
            self.object_combo.addItem(name, object_id)

    def _on_module_selection_changed(self, *_unused: int) -> None:
        has_module = self.module_combo.currentData() is not None
        self.object_combo.blockSignals(True)
        if has_module:
            self._repopulate_object_combo_for_module()
        else:
            self.object_combo.clear()
            self.object_combo.addItem("— Select object —", None)
        self.object_combo.setCurrentIndex(0)
        self.object_combo.blockSignals(False)
        self.object_combo.setEnabled(has_module)
        if not has_module:
            self.object_combo.setToolTip("Select a module first.")
        elif self.object_combo.count() <= 1:
            self.object_combo.setToolTip("No objects for this module.")
        else:
            self.object_combo.setToolTip("")

    def _show_error(self, message: str, *, clear_on_user_activity: bool = True) -> None:
        show_auto_hiding_message(
            self,
            self.error_label,
            message,
            error=True,
            clear_on_user_activity=clear_on_user_activity,
        )

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self.error_label)
        self.error_label.setText("")
        self.error_label.setVisible(False)

    def _parse_optional_int(self, key: str) -> int | None:
        text = self._field_edits[key].text().strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None

    def _required_int(self, key: str, message: str) -> int | None:
        value = self._parse_optional_int(key)
        if value is None:
            # Sticky: setFocus() triggers focusChanged, which would clear the message immediately.
            self._show_error(message, clear_on_user_activity=False)
            self._field_edits[key].setFocus()
            return None
        return value

    def _build_payload(self) -> dict[str, Any] | None:
        module_id = self.module_combo.currentData()
        if module_id is None:
            self._show_error("Please select a module.")
            return None
        object_id = self.object_combo.currentData()
        if object_id is None:
            self._show_error("Please select an object.")
            return None

        master_fields: tuple[tuple[str, QComboBox, str, str], ...] = (
            ("status", self.status_combo, "Status", "a status"),
            ("businessObjectType", self.business_object_type_combo, "Business object type", "a business object type"),
            ("scope", self.scope_combo, "Scope", "a scope"),
            ("loadApproach", self.load_approach_combo, "Load approach", "a load approach"),
            ("uploadTool", self.upload_tool_combo, "Upload tool", "an upload tool"),
            ("customizationStatus", self.customization_status_combo, "Customization status", "a customization status"),
            ("buildStatus", self.build_status_combo, "Build status", "a build status"),
            (
                "functionalUnitTestingStatus",
                self.functional_unit_testing_status_combo,
                "Functional unit testing status",
                "a functional unit testing status",
            ),
            (
                "businessUnitTestingStatus",
                self.business_unit_testing_status_combo,
                "Business unit testing status",
                "a business unit testing status",
            ),
        )
        master_values: dict[str, int] = {}
        for payload_key, combo, caption, phrase in master_fields:
            seq, err = require_master_key_seq_for_payload(
                combo, field_caption=caption, strict_phrase=phrase
            )
            if err:
                self._show_error(err, clear_on_user_activity=False)
                combo.setFocus()
                return None
            master_values[payload_key] = seq

        payload: dict[str, Any] = {
            "moduleId": int(module_id) if str(module_id).strip().isdigit() else module_id,
            "objectId": int(object_id) if str(object_id).strip().isdigit() else object_id,
            "uploadedToSharePoint": bool(self.uploaded_to_sharepoint_combo.currentData()),
            **master_values,
        }

        tcode = self._field_edits["tcode"].text().strip()
        if tcode:
            payload["tcode"] = tcode

        for key, dt_field in (
            ("buildCompletionDate", self.build_completion_datetime),
            (
                "functionalUnitTestingCompletionDate",
                self.functional_unit_testing_completion_datetime,
            ),
            (
                "businessUnitTestingCompletionDate",
                self.business_unit_testing_completion_datetime,
            ),
        ):
            iso_local = dt_field.iso_timestamp()
            payload[key] = to_utc_iso(iso_local) or iso_local

        for key in ("functionalSPOC", "dmcProgramName"):
            val = self._field_edits[key].text().strip()
            if val:
                payload[key] = val

        payload["comments"] = _comments_payload_string(self._comments_edit.toPlainText())

        est_count = self._parse_optional_int("estimatedProdCount")
        if est_count is not None:
            payload["estimatedProdCount"] = est_count
        return payload

    def _master_key_combos(self) -> tuple[QComboBox, ...]:
        return (
            self.status_combo,
            self.business_object_type_combo,
            self.scope_combo,
            self.load_approach_combo,
            self.upload_tool_combo,
            self.customization_status_combo,
            self.build_status_combo,
            self.functional_unit_testing_status_combo,
            self.business_unit_testing_status_combo,
        )

    def is_dirty(self) -> bool:
        if self.module_combo.currentData() is not None or self.object_combo.currentData() is not None:
            return True
        if any(
            (s := combo_resolved_master_key_seq(c)) is not None and str(s).strip() != ""
            for c in self._master_key_combos()
        ):
            return True
        if self._completion_dates_user_touched:
            return True
        if bool(self.uploaded_to_sharepoint_combo.currentData()):
            return True
        if self._comments_edit.toPlainText().strip():
            return True
        return any(edit.text().strip() for edit in self._field_edits.values())

    def reset_to_default(self) -> None:
        for edit in self._field_edits.values():
            edit.clear()
        self._comments_edit.clear()
        self.uploaded_to_sharepoint_combo.setCurrentIndex(1)
        self.module_combo.setCurrentIndex(0)
        self.object_combo.setCurrentIndex(0)
        for c in self._master_key_combos():
            reset_searchable_combo(c)
        self.build_completion_datetime.set_defaults_today_midnight()
        self.functional_unit_testing_completion_datetime.set_defaults_today_midnight()
        self.business_unit_testing_completion_datetime.set_defaults_today_midnight()
        self._completion_dates_user_touched = False
        self._on_module_selection_changed()
        self._clear_error()

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
        payload = self._build_payload()
        if payload is None:
            return
        result = api_create_object_tracker(payload, token=self._token())
        if result.get("success"):
            self._show_success(str(result.get("message") or "Object tracker record created successfully."))
            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
        else:
            self._show_error(str(result.get("message") or "Failed to create object tracker record."))
