"""Installation-style setup wizard for DT Step configuration."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.etl.data_transformation.constants import (
    STEP_SETUP_HINTS,
    STEP_SETUP_LABELS,
    SUMMARY_BAR_STYLE,
)
from app.etl.data_transformation.data_service import TransformationDataService
from app.etl.data_transformation.widgets.step_column_step import StepColumnStepWidget
from app.etl.data_transformation.widgets.step_join_step import StepJoinStepWidget
from app.etl.data_transformation.widgets.step_source_step import StepSourceStepWidget
from app.etl.data_transformation.widgets.step_target_step import StepTargetStepWidget
from app.etl.data_transformation.widgets.step_transform_step import StepTransformStepWidget
from ui.form_page_styles import (
    FORM_PAGE_FONT_SIZE_PX,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
)


def _step_nav_button_stylesheet(*, active: bool, completed: bool) -> str:
    if active:
        color = "#0f172a"
        weight = "font-weight: 600;"
        bg = "background: #e0f2fe; border-radius: 6px;"
    elif completed:
        color = "#16a34a"
        weight = ""
        bg = "background: transparent;"
    else:
        color = "#64748b"
        weight = ""
        bg = "background: transparent;"
    return (
        f"QPushButton {{ font-size: {FORM_PAGE_FONT_SIZE_PX}px; border: none; "
        f"padding: 4px 8px; color: {color}; {weight} {bg} }}"
        "QPushButton:hover { text-decoration: underline; color: #2563eb; }"
        "QPushButton:disabled { color: #cbd5e1; }"
    )


class StepSetupWizardWidget(QWidget):
    def __init__(self, service: TransformationDataService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._flow_id: int | str | None = None
        self._step_index = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self._step_header = QHBoxLayout()
        self._step_header.setSpacing(8)
        self._step_buttons: list[QPushButton] = []
        for index, label in enumerate(STEP_SETUP_LABELS):
            if index > 0:
                arrow = QLabel("›")
                arrow.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: #94a3b8;")
                self._step_header.addWidget(arrow)
            step_btn = QPushButton(f"{index + 1}. {label}")
            step_btn.setFlat(True)
            step_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            step_btn.clicked.connect(
                lambda _checked=False, step_index=index: self._on_step_clicked(step_index)
            )
            self._step_buttons.append(step_btn)
            self._step_header.addWidget(step_btn)
        self._step_header.addStretch()
        root.addLayout(self._step_header)

        self._context_panel = QFrame()
        self._context_panel.setObjectName("dtSummary")
        self._context_panel.setStyleSheet(SUMMARY_BAR_STYLE)
        context_layout = QVBoxLayout(self._context_panel)
        context_layout.setContentsMargins(12, 10, 12, 10)
        context_layout.setSpacing(4)

        self._step_progress_label = QLabel()
        self._step_progress_label.setStyleSheet(
            f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; font-weight: 600; color: #0f172a;"
        )
        context_layout.addWidget(self._step_progress_label)

        self._step_hint_label = QLabel()
        self._step_hint_label.setWordWrap(True)
        self._step_hint_label.setStyleSheet("font-size: 11px; color: #64748b;")
        context_layout.addWidget(self._step_hint_label)

        self._step_status_label = QLabel()
        self._step_status_label.setWordWrap(True)
        self._step_status_label.setStyleSheet("font-size: 11px; color: #334155;")
        context_layout.addWidget(self._step_status_label)

        root.addWidget(self._context_panel)

        self.stack = QStackedWidget()
        self.source_step = StepSourceStepWidget(service)
        self.target_step = StepTargetStepWidget(service)
        self.column_step = StepColumnStepWidget(service)
        self.join_step = StepJoinStepWidget(service)
        self.transform_step = StepTransformStepWidget(service)
        self._step_widgets = (
            self.source_step,
            self.target_step,
            self.column_step,
            self.join_step,
            self.transform_step,
        )
        self.stack.addWidget(self.source_step)
        self.stack.addWidget(self.target_step)
        self.stack.addWidget(self.column_step)
        self.stack.addWidget(self.join_step)
        self.stack.addWidget(self.transform_step)
        root.addWidget(self.stack, 1)

        nav = QHBoxLayout()
        nav.addStretch()
        self.back_btn = QPushButton("Back")
        self.next_btn = QPushButton("Next")
        self.finish_btn = QPushButton("Finish")
        for btn in (self.back_btn, self.next_btn, self.finish_btn):
            btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self.next_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self.finish_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        nav.addWidget(self.finish_btn)
        root.addLayout(nav)

        self.back_btn.clicked.connect(self._on_back)
        self.next_btn.clicked.connect(self._on_next)
        self.finish_btn.clicked.connect(self._on_finish)
        self._refresh_nav()

    def set_flow_id(self, flow_id: int | str | None) -> None:
        self._flow_id = flow_id
        self._step_index = 0
        self.stack.setCurrentIndex(0)
        self.source_step.reset()
        self.target_step.reset()
        self.column_step.reset()
        self.join_step.reset()
        self.transform_step.reset()
        if flow_id is not None:
            self.source_step.set_flow_id(flow_id)
            self.target_step.set_flow_id(flow_id)
            self.column_step.set_flow_id(flow_id)
            self.join_step.set_flow_id(flow_id)
            self.transform_step.set_flow_id(flow_id)
            ok, msg = self.source_step.load_connections()
            if not ok:
                QMessageBox.warning(self, "Failed", msg)
                return
            ok, msg = self.source_step.load_sources(flow_id)
            if not ok:
                QMessageBox.warning(self, "Failed", msg)
                return
            ok, msg = self.target_step.load_connections()
            if not ok:
                QMessageBox.warning(self, "Failed", msg)
                return
            ok, msg = self.target_step.load_existing_target(flow_id)
            if not ok:
                QMessageBox.warning(self, "Failed", msg)
                return
            ok, msg = self.column_step.load_columns(flow_id)
            if not ok:
                QMessageBox.warning(self, "Failed", msg)
                return
            ok, msg = self.join_step.load_joins(flow_id)
            if not ok:
                QMessageBox.warning(self, "Failed", msg)
                return
            ok, msg = self.transform_step.load_steps(flow_id)
            if not ok:
                QMessageBox.warning(self, "Failed", msg)
        self._refresh_nav()

    def _current_step_widget(self) -> QWidget:
        return self._step_widgets[self._step_index]

    def _refresh_step_context(self) -> None:
        total = len(STEP_SETUP_LABELS)
        label = STEP_SETUP_LABELS[self._step_index]
        self._step_progress_label.setText(f"Step {self._step_index + 1} of {total} — {label}")
        hint = (
            STEP_SETUP_HINTS[self._step_index]
            if self._step_index < len(STEP_SETUP_HINTS)
            else ""
        )
        self._step_hint_label.setText(hint)

        widget = self._current_step_widget()
        if hasattr(widget, "setup_status"):
            summary, complete = widget.setup_status()
            icon = "✓" if complete else "○"
            color = "#15803d" if complete else "#b45309"
            self._step_status_label.setText(f"{icon} {summary}")
            self._step_status_label.setStyleSheet(f"font-size: 11px; color: {color};")
        else:
            self._step_status_label.clear()

    def _refresh_step_header(self) -> None:
        for index, btn in enumerate(self._step_buttons):
            widget = self._step_widgets[index]
            complete = False
            if hasattr(widget, "setup_status"):
                _, complete = widget.setup_status()
            btn.setStyleSheet(
                _step_nav_button_stylesheet(
                    active=index == self._step_index,
                    completed=complete and index != self._step_index,
                )
            )
            suffix = ""
            if complete and index != self._step_index:
                suffix = " ✓"
            btn.setText(f"{index + 1}. {STEP_SETUP_LABELS[index]}{suffix}")

    def _load_step_data(self, step_index: int) -> tuple[bool, str]:
        if self._flow_id is None:
            return True, ""
        flow_id = self._flow_id
        if step_index == 0:
            ok, msg = self.source_step.load_connections()
            if not ok:
                return False, msg
            return self.source_step.load_sources(flow_id)
        if step_index == 1:
            ok, msg = self.target_step.load_connections()
            if not ok:
                return False, msg
            return self.target_step.load_existing_target(flow_id)
        if step_index == 2:
            return self.column_step.load_columns(flow_id)
        if step_index == 3:
            return self.join_step.load_joins(flow_id)
        if step_index == 4:
            return self.transform_step.load_steps(flow_id)
        return True, ""

    def _confirm_incomplete_step(self) -> bool:
        widget = self._current_step_widget()
        if not hasattr(widget, "setup_status"):
            return True
        summary, complete = widget.setup_status()
        if complete:
            return True
        reply = QMessageBox.question(
            self,
            "Step not complete",
            f"{summary}\n\nYou can finish this step later. Continue to the next step?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _go_to_step(self, step_index: int, *, reload: bool = True) -> None:
        if step_index < 0 or step_index >= len(STEP_SETUP_LABELS):
            return
        if step_index == self._step_index:
            self._refresh_nav()
            return
        if reload and self._flow_id is not None:
            ok, msg = self._load_step_data(step_index)
            if not ok:
                QMessageBox.warning(self, "Failed", msg)
                return
        self._step_index = step_index
        self.stack.setCurrentIndex(step_index)
        self._refresh_nav()

    def _on_step_clicked(self, step_index: int) -> None:
        if self._flow_id is None:
            QMessageBox.information(
                self,
                "Select a flow",
                "Click Switch Flow above to choose a work flow and flow before editing steps.",
            )
            return
        self._go_to_step(step_index, reload=True)

    def _refresh_nav(self) -> None:
        last_index = len(STEP_SETUP_LABELS) - 1
        has_flow = self._flow_id is not None
        self.back_btn.setEnabled(has_flow and self._step_index > 0)
        self.next_btn.setVisible(self._step_index < last_index)
        self.next_btn.setEnabled(has_flow)
        self.finish_btn.setVisible(self._step_index >= last_index)
        self.finish_btn.setEnabled(has_flow)
        for btn in self._step_buttons:
            btn.setEnabled(has_flow)
        self._context_panel.setVisible(has_flow)
        self._refresh_step_header()
        self._refresh_step_context()

    def _on_back(self) -> None:
        if self._step_index <= 0:
            return
        self._go_to_step(self._step_index - 1, reload=False)

    def _on_next(self) -> None:
        if self._step_index >= len(STEP_SETUP_LABELS) - 1:
            return
        if not self._confirm_incomplete_step():
            return
        self._go_to_step(self._step_index + 1, reload=True)

    def _build_finish_summary(self) -> str:
        lines = ["Setup summary for the selected flow:", ""]
        for index, widget in enumerate(self._step_widgets):
            label = STEP_SETUP_LABELS[index]
            if hasattr(widget, "setup_status"):
                summary, complete = widget.setup_status()
                status = "Done" if complete else "Incomplete"
                lines.append(f"• {label}: {status} — {summary}")
            else:
                lines.append(f"• {label}")
        return "\n".join(lines)

    def refresh_progress(self) -> None:
        self._refresh_step_header()
        self._refresh_step_context()

    def _on_finish(self) -> None:
        QMessageBox.information(self, "Setup complete", self._build_finish_summary())
