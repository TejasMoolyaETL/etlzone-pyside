"""Excel All Import hub: activity dashboard + import wizard."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget

from app.etl.excel.all_import_activity_page import AllImportActivityPage
from app.etl.excel.all_import_page import AllImportPage


class AllImportHubPage(QWidget):
    """Sidebar \"Excel All Import\" lands on the activity list; New Import opens the wizard."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.stack = QStackedWidget()
        self.activity = AllImportActivityPage()
        self.wizard = AllImportPage()
        self.stack.addWidget(self.activity)
        self.stack.addWidget(self.wizard)
        root.addWidget(self.stack)

        self.activity.new_import_requested.connect(self.open_new_import)
        self.activity.view_session_requested.connect(self.open_existing_session)
        self.wizard.exit_to_list_requested.connect(self.show_activity)

        self.stack.setCurrentWidget(self.activity)

    def go_to_nav_item(self, _nav_item: str) -> None:
        self.show_activity()

    def show_activity(self) -> None:
        was_visible = self.activity.isVisible() and self.stack.currentWidget() is self.activity
        self.stack.setCurrentWidget(self.activity)
        # Activity reloads in showEvent when it becomes visible; only force when already shown.
        if was_visible:
            self.activity.reload()

    def open_new_import(self) -> None:
        self.wizard.reset_for_new_import()
        self.stack.setCurrentWidget(self.wizard)

    def open_existing_session(self, row: dict[str, Any]) -> None:
        """Open the wizard filled with an existing Import Sessions row."""
        self.activity._clear_message()
        self.stack.setCurrentWidget(self.wizard)
        QApplication.processEvents()
        self.wizard.load_existing_session(row)
