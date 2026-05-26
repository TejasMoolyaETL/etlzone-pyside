"""ETL: Job Logs — summary and execution timeline with optional auto-refresh."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QHideEvent, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from core.api import api_get_all_etl_jobs
from core.user_context import get_user_profile
from ui.auto_hide_message import show_auto_hiding_message
from core.app_preferences import format_datetime_display
from ui.data_table import (
    apply_data_table_appearance,
    attach_table_copy_shortcut,
    clear_filter_row_widgets,
    filter_dict_rows_by_column_edits,
    format_data_table_cell,
    render_dict_rows_table,
    saved_filter_texts,
)
from ui.form_page_styles import (
    FORM_PAGE_FONT_SIZE_PX,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    LIST_PAGE_HEADER_TITLE_FONT_PX,
)


class _JobLogsFetchWorker(QObject):
    finished = Signal(object, str)

    def __init__(self, token: str | None) -> None:
        super().__init__()
        self._token = token

    @Slot()
    def run(self) -> None:
        result = api_get_all_etl_jobs(self._token)
        if result.get("success"):
            self.finished.emit(result.get("data") or {}, "")
        else:
            self.finished.emit({}, str(result.get("message") or "Failed to load job logs."))


def _timeline_row_value(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    for key in keys:
        if key in row:
            return row.get(key), key
    return None, keys[0] if keys else ""


def _timeline_format_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if value is None or value == "":
        return "--"
    return format_data_table_cell(value, key, key_candidates)


class JobLogsPageWidget(QWidget):
    """Job logs summary + timeline table."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._timeline_rows: list[dict[str, Any]] = []
        self._timeline_cols_spec: list[tuple[str, tuple[str, ...]]] = []
        self._timeline_filter_visible = False
        self._timeline_filter_timer = QTimer(self)
        self._timeline_filter_timer.setSingleShot(True)
        self._timeline_filter_timer.setInterval(200)
        self._timeline_filter_timer.timeout.connect(self._refresh_timeline_table)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        title = QLabel("ETL: Job Logs")
        title.setStyleSheet(f"font-size: {LIST_PAGE_HEADER_TITLE_FONT_PX}px; font-weight: 600; color: #ffffff;")
        hl.addWidget(title)
        hl.addStretch()
        root.addWidget(header)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(10)

        controls_card = QFrame()
        controls_card.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }"
        )
        controls_layout = QVBoxLayout(controls_card)
        controls_layout.setContentsMargins(14, 12, 14, 12)
        controls_layout.setSpacing(10)

        controls_row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self.auto_refresh_checkbox = QCheckBox("Auto refresh (3s)")
        self.auto_refresh_checkbox.setChecked(True)
        self.auto_refresh_checkbox.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px;")
        controls_row.addWidget(self.refresh_btn)
        controls_row.addWidget(self.auto_refresh_checkbox)
        controls_row.addStretch()
        controls_layout.addLayout(controls_row)

        summary_grid = QGridLayout()
        summary_grid.setHorizontalSpacing(24)
        summary_grid.setVerticalSpacing(6)
        label_style = f"font-size: {FORM_PAGE_FONT_SIZE_PX}px;"
        self.summary_total_jobs = QLabel("Total jobs: --")
        self.summary_running = QLabel("Running: --")
        self.summary_completed = QLabel("Completed: --")
        self.summary_failed = QLabel("Failed: --")
        self.summary_total_tables = QLabel("Total tables: --")
        self.summary_processed_tables = QLabel("Processed tables: --")
        for lbl in (
            self.summary_total_jobs,
            self.summary_running,
            self.summary_completed,
            self.summary_failed,
            self.summary_total_tables,
            self.summary_processed_tables,
        ):
            lbl.setStyleSheet(label_style)
        summary_grid.addWidget(self.summary_total_jobs, 0, 0)
        summary_grid.addWidget(self.summary_running, 0, 1)
        summary_grid.addWidget(self.summary_completed, 1, 0)
        summary_grid.addWidget(self.summary_failed, 1, 1)
        summary_grid.addWidget(self.summary_total_tables, 2, 0)
        summary_grid.addWidget(self.summary_processed_tables, 2, 1)
        controls_layout.addLayout(summary_grid)
        content_layout.addWidget(controls_card)

        timeline_card = QFrame()
        timeline_card.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }"
        )
        timeline_layout = QVBoxLayout(timeline_card)
        timeline_layout.setContentsMargins(14, 12, 14, 12)
        timeline_hdr_row = QHBoxLayout()
        timeline_hdr = QLabel("Execution timeline (sequence wise)")
        timeline_hdr.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; font-weight: 600;")
        timeline_hdr_row.addWidget(timeline_hdr)
        timeline_hdr_row.addStretch()
        self.timeline_filters_btn = QPushButton("Filters")
        self.timeline_filters_btn.setCheckable(True)
        self.timeline_filters_btn.setFixedWidth(80)
        self.timeline_filters_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        timeline_hdr_row.addWidget(self.timeline_filters_btn)
        timeline_layout.addLayout(timeline_hdr_row)

        self.timeline_table = QTableWidget(0, 0)
        apply_data_table_appearance(
            self.timeline_table,
            read_only=True,
            stretch_last_section=False,
            hide_vertical_header=True,
        )
        attach_table_copy_shortcut(self.timeline_table)
        self.timeline_filters_btn.toggled.connect(self._on_timeline_filters_toggled)
        timeline_layout.addWidget(self.timeline_table, 1)
        content_layout.addWidget(timeline_card, 1)

        self.page_status_label = QLabel("")
        self.page_status_label.setWordWrap(True)
        content_layout.addWidget(self.page_status_label)

        root.addWidget(content, 1)

    def render_all_reports(self, payload: Any) -> None:
        jobs = self._extract_rows(payload, ("job", "jobs"))
        logs = self._extract_rows(payload, ("tables", "logs", "steps"))
        self._set_summary(jobs)

        timeline_rows = self._collect_timeline_rows(payload)
        if not timeline_rows:
            timeline_rows = logs if logs else jobs
        timeline_rows = sorted(timeline_rows, key=self._timeline_sort_key)
        self._render_timeline_table(timeline_rows)

    def _extract_rows(self, payload: Any, preferred_keys: tuple[str, ...]) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if not isinstance(payload, dict):
            return []
        for key in preferred_keys:
            value = payload.get(key)
            if isinstance(value, list):
                rows = [row for row in value if isinstance(row, dict)]
                if rows:
                    return rows
            if isinstance(value, dict):
                return [value]
        return []

    def _collect_timeline_rows(self, payload: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not isinstance(payload, dict):
            return rows
        for source, value in payload.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        row = dict(item)
                        row["_source"] = source
                        rows.append(row)
            elif isinstance(value, dict):
                row = dict(value)
                row["_source"] = source
                rows.append(row)
        return rows

    def _set_summary(self, jobs: list[dict[str, Any]]) -> None:
        total_jobs = len(jobs)
        running = completed = failed = 0
        total_tables = processed_tables = 0
        for job in jobs:
            status = str(job.get("status", "")).upper()
            if status in ("RUNNING", "QUEUED"):
                running += 1
            elif status == "COMPLETED":
                completed += 1
            elif status in ("FAILED", "ERROR"):
                failed += 1
            total_tables += self._safe_int(job.get("totalTables"))
            processed_tables += self._safe_int(job.get("processedTables"))

        self.summary_total_jobs.setText(f"Total jobs: {total_jobs}")
        self.summary_running.setText(f"Running: {running}")
        self.summary_completed.setText(f"Completed: {completed}")
        self.summary_failed.setText(f"Failed: {failed}")
        self.summary_total_tables.setText(f"Total tables: {total_tables}")
        self.summary_processed_tables.setText(f"Processed tables: {processed_tables}")

    def _timeline_sort_key(self, row: dict[str, Any]) -> tuple[Any, ...]:
        stage = self._infer_stage(row)
        stage_order = {"SCAN": 1, "IMPORT": 2, "JOB": 3, "TABLE": 4, "OTHER": 5}
        timestamp = self._pick_time(row)
        sequence = self._pick_sequence(row)
        seq_num = self._safe_int(sequence) if sequence not in ("", "-") else 10**9
        return (str(timestamp), stage_order.get(stage, 99), seq_num, str(row.get("id", "")))

    def _build_timeline_display_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        display: list[dict[str, Any]] = []
        for r_index, row in enumerate(rows, start=1):
            display.append(
                {
                    "order": r_index,
                    "stage": self._infer_stage(row),
                    "event": self._infer_event(row),
                    "status": self._pick_status(row),
                    "time": self._pick_time(row),
                    "source": row.get("_source", "--"),
                    **{k: v for k, v in row.items() if not str(k).startswith("_")},
                }
            )
        return display

    def _on_timeline_filters_toggled(self, checked: bool) -> None:
        self._timeline_filter_visible = checked
        if not checked:
            clear_filter_row_widgets(self.timeline_table)
        self._refresh_timeline_table()

    def _derive_timeline_column_spec(self, rows: list[dict[str, Any]]) -> list[tuple[str, tuple[str, ...]]]:
        columns = ["order", "stage", "event", "status", "time", "source"]
        for row in rows:
            for key in row.keys():
                if str(key).startswith("_"):
                    continue
                if key not in columns:
                    columns.append(key)
        return [(c.upper(), (c,)) for c in columns]

    def _refresh_timeline_table(self) -> None:
        table = self.timeline_table
        if not self._timeline_rows:
            table.setColumnCount(0)
            table.setRowCount(0)
            return
        display_rows = self._build_timeline_display_rows(self._timeline_rows)
        filtered = list(display_rows)
        if self._timeline_filter_visible:
            filtered = filter_dict_rows_by_column_edits(
                display_rows,
                table,
                self._timeline_cols_spec,
                True,
                _timeline_row_value,
                _timeline_format_cell,
            )
        saved = saved_filter_texts(table) if self._timeline_filter_visible else None
        render_dict_rows_table(
            table,
            filtered,
            self._timeline_cols_spec,
            filter_visible=self._timeline_filter_visible,
            value_for_column=_timeline_row_value,
            format_cell=_timeline_format_cell,
            on_filter_text_changed=self._schedule_timeline_filter_apply,
            saved_filter_texts_list=saved,
        )

    def _schedule_timeline_filter_apply(self) -> None:
        if self._timeline_filter_visible:
            self._timeline_filter_timer.start()

    def _render_timeline_table(self, rows: list[dict[str, Any]]) -> None:
        self._timeline_rows = list(rows)
        self._timeline_cols_spec = self._derive_timeline_column_spec(rows)
        self._refresh_timeline_table()

    def _infer_stage(self, row: dict[str, Any]) -> str:
        text = " ".join(str(v) for v in row.values()).lower()
        source = str(row.get("_source", "")).lower()
        combo = f"{source} {text}"
        if "scan" in combo:
            return "SCAN"
        if "import" in combo:
            return "IMPORT"
        if "job" in combo:
            return "JOB"
        if "table" in combo:
            return "TABLE"
        return "OTHER"

    def _infer_event(self, row: dict[str, Any]) -> str:
        for key in ("event", "action", "stepName", "msg", "message"):
            if row.get(key) not in (None, ""):
                return str(row.get(key))
        stage = self._infer_stage(row)
        status = self._pick_status(row)
        if stage == "SCAN":
            return f"Scan {status}".strip()
        if stage == "IMPORT":
            return f"Import {status}".strip()
        if stage == "JOB":
            return f"Job {status}".strip()
        if stage == "TABLE":
            table_name = row.get("tableName") or row.get("table") or ""
            return f"Table {table_name} {status}".strip()
        return status if status else "--"

    def _pick_status(self, row: dict[str, Any]) -> str:
        for key in ("status", "state", "stepStatus", "jobStatus"):
            if row.get(key) not in (None, ""):
                return str(row.get(key))
        return "--"

    def _pick_time(self, row: dict[str, Any]) -> str:
        for key in ("timestamp", "updatedAt", "createdAt", "startTime", "endTime", "scannedAt"):
            value = row.get(key)
            if value not in (None, ""):
                text = format_datetime_display(value)
                return text if text else str(value)
        return "--"

    def _pick_sequence(self, row: dict[str, Any]) -> str:
        for key in ("sequence", "seq", "step", "order"):
            if row.get(key) not in (None, ""):
                return str(row.get(key))
        return "-"

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0


class EtlJobLogsPage(QWidget):
    """Job logs page with background fetch and optional polling."""

    _POLL_MS = 3000

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._ui = JobLogsPageWidget()
        layout.addWidget(self._ui)

        self._auto_refresh = True
        self._fetch_in_flight = False
        self._last_payload: dict[str, Any] = {}
        self._fetch_thread: QThread | None = None
        self._fetch_worker: _JobLogsFetchWorker | None = None
        self._visible = False

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._POLL_MS)
        self._poll_timer.timeout.connect(self.refresh)

        self._ui.refresh_btn.clicked.connect(self.refresh)
        self._ui.auto_refresh_checkbox.stateChanged.connect(self._on_auto_refresh_toggled)
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._visible = True
        self.refresh()
        if self._auto_refresh:
            self._poll_timer.start()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self._visible = False
        self._poll_timer.stop()

    def refresh(self) -> None:
        if self._fetch_in_flight:
            return
        self._fetch_in_flight = True
        self._ui.page_status_label.setText("Loading job logs…")
        self._fetch_thread = QThread(self)
        self._fetch_worker = _JobLogsFetchWorker(self._token())
        self._fetch_worker.moveToThread(self._fetch_thread)
        self._fetch_thread.started.connect(self._fetch_worker.run)
        self._fetch_worker.finished.connect(self._on_fetch_finished)
        self._fetch_worker.finished.connect(self._fetch_thread.quit)
        self._fetch_thread.finished.connect(self._cleanup_fetch_thread)
        self._fetch_thread.start()

    def _token(self) -> str | None:
        profile = get_user_profile() or {}
        return profile.get("token") or profile.get("accessToken")

    def _on_auto_refresh_toggled(self, state: int) -> None:
        self._auto_refresh = Qt.CheckState(state) == Qt.CheckState.Checked
        if self._visible and self._auto_refresh:
            self._poll_timer.start()
        else:
            self._poll_timer.stop()

    @Slot(object, str)
    def _on_fetch_finished(self, payload: object, error_message: str) -> None:
        self._fetch_in_flight = False
        if error_message:
            self._ui.page_status_label.setText("Failed to load job logs.")
            show_auto_hiding_message(
                self,
                self._ui.page_status_label,
                str(error_message),
                error=True,
            )
            return

        try:
            self._last_payload = payload if isinstance(payload, dict) else {}
            self._ui.render_all_reports(self._last_payload)
            show_auto_hiding_message(self, self._ui.page_status_label, "", error=False)

            jobs = self._ui._extract_rows(self._last_payload, ("job", "jobs"))
            any_running = any(
                str((job or {}).get("status", "")).upper() in ("QUEUED", "RUNNING") for job in jobs
            )
            if not any_running:
                self._poll_timer.stop()
            elif self._visible and self._auto_refresh:
                self._poll_timer.start()
        except Exception:
            self._ui.page_status_label.setText("Failed to load job logs.")
            show_auto_hiding_message(
                self,
                self._ui.page_status_label,
                "Failed to load job logs.",
                error=True,
            )

    def _cleanup_fetch_thread(self) -> None:
        if self._fetch_worker is not None:
            self._fetch_worker.deleteLater()
            self._fetch_worker = None
        if self._fetch_thread is not None:
            self._fetch_thread.deleteLater()
            self._fetch_thread = None
