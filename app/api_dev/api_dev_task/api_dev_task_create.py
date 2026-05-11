"""Create API Dev Task page."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QCompleter,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.api import api_create_api_task, api_get_all_api_details
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
    FORM_READONLY_INPUT_STYLE as READONLY_INPUT_STYLE,
    placeholder_auto_filled,
    placeholder_search_select,
)
from ui.post_save_navigation import schedule_after_success
from ui.strict_completer import strict_list_selection_message
from ui.widgets.required_label import field_caption_label, labeled_field_block
from ui.data_table import (
    apply_data_table_appearance,
    attach_table_copy_shortcut,
    clear_filter_row_widgets,
    filter_dict_rows_by_column_edits,
    install_filter_row,
    MIN_DATA_COL_WIDTH_PX,
    sync_vertical_header_labels,
)


class CreateAPIDevTaskPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_create_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._api_completions: list[tuple[str, Any, dict[str, Any]]] = []
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
        title = QLabel("Create API Dev Task")
        header_layout.addWidget(title)
        header_layout.addStretch()
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
        card.setMaximumWidth(700)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        field_h = MODAL_FIELD_HEIGHT_PX

        self.api_id_edit = QLineEdit()
        self.api_id_edit.setReadOnly(True)
        self.api_id_edit.setPlaceholderText(placeholder_auto_filled("API"))
        self.api_id_edit.setStyleSheet(READONLY_INPUT_STYLE)
        self.api_id_edit.setFixedHeight(field_h)
        card_layout.addWidget(
            labeled_field_block(QLabel("API Id:"), self.api_id_edit)
        )

        self.api_search_edit = QLineEdit()
        self.api_search_edit.setPlaceholderText(placeholder_search_select("API Id", "API Name"))
        self.api_search_edit.setStyleSheet(INPUT_STYLE)
        self.api_search_edit.setFixedHeight(field_h)
        self.api_search_edit.installEventFilter(self)
        self.api_search_edit.textChanged.connect(self._on_api_text_changed)
        api_completer = QCompleter(self.api_search_edit)
        api_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        api_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        api_completer.setMaxVisibleItems(12)
        self.api_search_edit.setCompleter(api_completer)
        self.api_choose_btn = QPushButton("Choose")
        self.api_choose_btn.setFixedWidth(100)
        self.api_choose_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.api_choose_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self.api_choose_btn.clicked.connect(self._open_api_picker_dialog)
        api_search_row = QWidget()
        api_search_row_layout = QHBoxLayout(api_search_row)
        api_search_row_layout.setContentsMargins(0, 0, 0, 0)
        api_search_row_layout.setSpacing(8)
        api_search_row_layout.addWidget(self.api_search_edit, 1)
        api_search_row_layout.addWidget(self.api_choose_btn, 0)
        card_layout.addWidget(
            labeled_field_block(field_caption_label("API*", LABEL_STYLE), api_search_row)
        )

        self.summary_edit = QLineEdit()
        self.summary_edit.setPlaceholderText("Short task summary")
        self.summary_edit.setStyleSheet(INPUT_STYLE)
        self.summary_edit.setFixedHeight(field_h)
        card_layout.addWidget(labeled_field_block(field_caption_label("Summary*", LABEL_STYLE), self.summary_edit))

        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("Task description")
        self.desc_edit.setStyleSheet(INPUT_STYLE)
        self.desc_edit.setFixedHeight(field_h)
        card_layout.addWidget(labeled_field_block(field_caption_label("Description*", LABEL_STYLE), self.desc_edit))

        self.status_combo = QComboBox()
        self.status_combo.addItems(["ACTIVE", "INACTIVE", "OPEN", "IN_PROGRESS", "DONE", "BLOCKED"])
        apply_form_combobox_field(self.status_combo, height_px=field_h, min_width=360)
        card_layout.addWidget(labeled_field_block(field_caption_label("Status", LABEL_STYLE), self.status_combo))

        self.error_label = QLabel()
        self.error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self.error_label.setWordWrap(True)
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

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = profile.get("token") or profile.get("accessToken") or profile.get("access_token") or profile.get("jwt")
        return str(token) if token else None

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self.error_label)
        self.error_label.setText("")
        self.error_label.setVisible(False)

    def _setup_api_completer(self) -> None:
        result = api_get_all_api_details(token=self._token())
        rows = result.get("data") if result.get("success") else []
        self._api_completions = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                api_id = row.get("apiId") or row.get("api_id") or row.get("id")
                if api_id is None or str(api_id).strip() == "":
                    continue
                api_name = str(row.get("apiName") or row.get("api_name") or "").strip()
                disp = f"{api_id} | {api_name}" if api_name else f"{api_id}"
                self._api_completions.append((disp, api_id, row))
        self._api_completions.sort(key=lambda x: x[0].lower())
        completer = QCompleter([d for d, _, _ in self._api_completions])
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setMaxVisibleItems(12)

        def on_activated(text: str) -> None:
            self.api_search_edit.setText(text)
            for disp, api_id, _row in self._api_completions:
                if disp == text:
                    self.api_id_edit.setText(str(api_id))
                    break

        completer.activated.connect(on_activated)
        self.api_search_edit.setCompleter(completer)

    def _on_api_text_changed(self, text: str) -> None:
        if not text.strip():
            self.api_id_edit.clear()
            return
        for disp, api_id, _row in self._api_completions:
            if disp == text:
                self.api_id_edit.setText(str(api_id))
                return
        self.api_id_edit.clear()

    def _is_valid_api_selection(self) -> bool:
        text = self.api_search_edit.text().strip()
        if not text:
            return False
        return text in {disp for disp, _, _ in self._api_completions}

    def _resolve_api_id(self) -> int | str | None:
        text = self.api_search_edit.text().strip()
        if not text:
            return None
        for disp, api_id, _row in self._api_completions:
            if disp == text:
                s = str(api_id).strip()
                return int(s) if s.isdigit() else s
        return None

    def _open_api_picker_dialog(self) -> None:
        self._setup_api_completer()
        dlg = QDialog(self)
        dlg.setWindowTitle("Choose API")
        dlg.resize(820, 420)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        filter_toolbar = QHBoxLayout()
        filter_toolbar.setContentsMargins(0, 0, 0, 0)
        filter_toolbar.setSpacing(8)
        filter_toolbar.addStretch()
        filter_btn = QPushButton("Filters")
        filter_btn.setCheckable(True)
        filter_btn.setFixedWidth(100)
        filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        filter_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        filter_toolbar.addWidget(filter_btn)
        lay.addLayout(filter_toolbar)

        table = QTableWidget()
        apply_data_table_appearance(table)
        attach_table_copy_shortcut(table)
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["API Id", "API Method", "API Name", "KeyValue", "Folder"])
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        hh = table.horizontalHeader()
        hh.setStretchLastSection(False)
        for c in range(table.columnCount()):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
        hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
        table.verticalHeader().setVisible(True)
        source_rows: list[dict[str, str]] = []
        api_choice_map: dict[str, tuple[Any, str]] = {}
        for _disp, api_id, row in self._api_completions:
            api_method = str(row.get("apiMethod") or row.get("api_method") or "").strip()
            api_name = str(row.get("apiName") or row.get("api_name") or "").strip()
            api_status_obj = row.get("apiStatusResponse")
            key_value = str(
                (api_status_obj.get("keyValue") if isinstance(api_status_obj, dict) else None)
                or (api_status_obj.get("key_value") if isinstance(api_status_obj, dict) else None)
                or row.get("keyValue")
                or row.get("key_value")
                or row.get("apiStatus")
                or row.get("api_status")
                or ""
            ).strip()
            folder = str(row.get("folder") or "").strip()
            api_id_s = str(api_id)
            source_rows.append(
                {
                    "api_id": api_id_s,
                    "api_method": api_method,
                    "api_name": api_name,
                    "key_value": key_value,
                    "folder": folder,
                }
            )
            api_choice_map[api_id_s] = (api_id, api_name)

        column_spec: list[tuple[str, tuple[str, ...]]] = [
            ("API Id", ("api_id",)),
            ("API Method", ("api_method",)),
            ("API Name", ("api_name",)),
            ("KeyValue", ("key_value",)),
            ("Folder", ("folder",)),
        ]
        filter_visible = False
        filter_apply_timer = QTimer(dlg)
        filter_apply_timer.setSingleShot(True)
        filter_apply_timer.setInterval(200)

        def _value_for_column(row: dict[str, str], keys: tuple[str, ...]) -> tuple[Any, str]:
            for key in keys:
                if key in row:
                    return row[key], key
            return "", keys[0] if keys else ""

        def _format_cell(value: Any, _key: str = "", _keys: tuple[str, ...] = ()) -> str:
            return str(value or "")

        def _render_rows(rows: list[dict[str, str]]) -> None:
            off = 1 if filter_visible else 0
            table.setSortingEnabled(False)
            total = off + len(rows)
            table.setRowCount(total)
            if filter_visible:
                install_filter_row(table, len(column_spec), on_text_changed=_schedule_filter_apply)
                for c in range(table.columnCount()):
                    table.takeItem(0, c)
            for r, row in enumerate(rows):
                tr = off + r
                values = [
                    row["api_id"],
                    row["api_method"],
                    row["api_name"],
                    row["key_value"],
                    row["folder"],
                ]
                for c, v in enumerate(values):
                    item = QTableWidgetItem(v)
                    if c == 0:
                        choice = api_choice_map.get(row["api_id"])
                        if choice is not None:
                            item.setData(Qt.ItemDataRole.UserRole, choice)
                    table.setItem(tr, c, item)
            sync_vertical_header_labels(
                table,
                filter_visible=filter_visible,
                data_row_count=len(rows),
            )
            table.resizeColumnsToContents()
            table.setSortingEnabled(not filter_visible)

        def _filtered_rows() -> list[dict[str, str]]:
            return filter_dict_rows_by_column_edits(
                source_rows,
                table,
                column_spec,
                filter_visible,
                _value_for_column,
                _format_cell,
            )

        def _apply_filters() -> None:
            _render_rows(_filtered_rows())

        def _schedule_filter_apply() -> None:
            if filter_visible:
                filter_apply_timer.start()

        def _toggle_filters(enabled: bool) -> None:
            nonlocal filter_visible
            filter_visible = enabled
            if not enabled:
                filter_apply_timer.stop()
                clear_filter_row_widgets(table)
            _render_rows(_filtered_rows() if enabled else source_rows)

        filter_apply_timer.timeout.connect(_apply_filters)
        filter_btn.toggled.connect(_toggle_filters)
        _render_rows(source_rows)
        def choose_current() -> None:
            row = table.currentRow()
            if row < 0:
                return
            item = table.item(row, 0)
            if item is None:
                return
            data = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(data, tuple) or len(data) != 2:
                return
            api_id, api_name = data
            display = f"{api_id} | {api_name}" if str(api_name).strip() else str(api_id)
            self.api_search_edit.setText(display)
            self.api_id_edit.setText(str(api_id))
            dlg.accept()

        table.itemDoubleClicked.connect(lambda _it: choose_current())
        lay.addWidget(table, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        choose_btn = QPushButton("Choose")
        choose_btn.setFixedWidth(100)
        choose_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        choose_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        choose_btn.clicked.connect(choose_current)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(choose_btn)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)
        dlg.exec()

    def is_dirty(self) -> bool:
        return bool(
            self.api_id_edit.text().strip()
            or self.api_search_edit.text().strip()
            or self.summary_edit.text().strip()
            or self.desc_edit.text().strip()
        )

    def reset_to_default(self) -> None:
        self.api_id_edit.clear()
        self.api_search_edit.clear()
        self.summary_edit.clear()
        self.desc_edit.clear()
        self.status_combo.setCurrentIndex(0)
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
        api_id_raw = self.api_search_edit.text().strip()
        summary = self.summary_edit.text().strip()
        desc = self.desc_edit.text().strip()
        if not api_id_raw:
            self._show_error("API Id is required.")
            return
        if not self._is_valid_api_selection():
            self._show_error(strict_list_selection_message("an API"))
            return
        selected_id = self._resolve_api_id()
        if selected_id is None:
            self._show_error("API Id is invalid. Please select from the list.")
            return
        if not summary:
            self._show_error("Summary is required.")
            return
        if not desc:
            self._show_error("Description is required.")
            return
        api_id: int | str
        sid = str(selected_id).strip()
        api_id = int(sid) if sid.isdigit() else sid
        result = api_create_api_task(
            api_id,
            token=self._token(),
            summary=summary,
            desc=desc,
            status=self.status_combo.currentText().strip(),
        )
        if result.get("success"):
            self._show_success(str(result.get("message") or "API task created successfully."))
            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
        else:
            self._show_error(str(result.get("message") or "Failed to create API task."))

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._setup_api_completer()

    def eventFilter(self, obj, event) -> bool:
        if obj == self.api_search_edit and event.type() == QEvent.Type.FocusIn:
            self._setup_api_completer()
        return super().eventFilter(obj, event)
