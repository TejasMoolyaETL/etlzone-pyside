"""API: All in One — details + validations tables with one shared toolbar.

Uses replicated list panels in this package only (no imports from ``api_details`` /
``api_validations`` list modules).
"""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSplitter, QVBoxLayout, QWidget

from app.api_dev.api_dev_all_in_one.details_list_panel import APIDetailsListPanel
from app.api_dev.api_dev_all_in_one.validation_comment_panel import ValidationCommentPanel
from app.api_dev.api_dev_all_in_one.validations_list_panel import APIValidationsListPanel
from core.api import api_get_all_api_details_all_in_one
from core.nav_access import nav_action_visible_from_steps
from core.user_context import get_nav_access_steps, get_user_profile
from ui.form_page_styles import (
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
)
from ui.theme import Theme

# Lower-left section title strip — same compact style as Comments panel header.
_ALL_IN_ONE_VALIDATIONS_TITLE_HEIGHT_PX = 22
_ALL_IN_ONE_VALIDATIONS_TITLE_MARGINS = (6, 0, 6, 0)


def _all_in_one_validations_section_title_stylesheet() -> str:
    z = Theme
    return (
        f"QWidget {{ background: {z.HEADER_NAV}; }}"
        f"QLabel {{ color: {z.PANEL_TEXT_BRIGHT}; font-size: 9px; font-weight: 600; }}"
    )


class _AllInOneLoadWorker(QObject):
    finished = Signal(bool, object, object, str)

    def __init__(self, token: str | None) -> None:
        super().__init__()
        self._token = token

    @Slot()
    def run(self) -> None:
        try:
            result = api_get_all_api_details_all_in_one(token=self._token)
        except Exception as exc:
            self.finished.emit(False, [], [], f"Load failed ({type(exc).__name__}).")
            return
        if not result.get("success"):
            self.finished.emit(
                False,
                [],
                [],
                str(result.get("message", "Failed to load data.")),
            )
            return
        details = result.get("details") or []
        validations = result.get("validations") or []
        self.finished.emit(True, details, validations, "")


class ApiDevAllInOnePage(QWidget):
    """Details + validations + comments; top bar matches list pages (e.g. API: Validations); subsection titles unchanged."""

    def __init__(
        self,
        on_add_detail_clicked: Callable[[], None] | None = None,
        on_edit_detail_clicked: Callable[[dict[str, Any], bool], None] | None = None,
        on_add_validation_clicked: Callable[[], None] | None = None,
        on_edit_validation_clicked: Callable[[dict[str, Any], bool], None] | None = None,
    ) -> None:
        super().__init__()
        self._details_page = APIDetailsListPanel(
            on_create_clicked=on_add_detail_clicked,
            on_edit_clicked=on_edit_detail_clicked,
            auto_refresh_on_show=False,
            show_toolbar=False,
        )
        self._validations_page = APIValidationsListPanel(
            on_create_clicked=on_add_validation_clicked,
            on_edit_clicked=on_edit_validation_clicked,
            auto_refresh_on_show=False,
            show_toolbar=False,
        )
        self._load_thread: QThread | None = None
        self._load_worker: _AllInOneLoadWorker | None = None
        self._loading = False
        self._pending_refresh = False
        self._lower_split_applied = False
        self._can_display_all_in_one = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        header_layout.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        title = QLabel("API: All in One")
        header_layout.addWidget(title)
        header_layout.addStretch()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedWidth(100)
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self.refresh)
        header_layout.addWidget(self._refresh_btn)
        layout.addWidget(header)

        self._lower_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._validations_section = QWidget()
        _vsec = QVBoxLayout(self._validations_section)
        _vsec.setContentsMargins(0, 0, 0, 0)
        _vsec.setSpacing(0)
        _val_title_bar = QWidget()
        _val_title_bar.setFixedHeight(_ALL_IN_ONE_VALIDATIONS_TITLE_HEIGHT_PX)
        _val_title_bar.setStyleSheet(_all_in_one_validations_section_title_stylesheet())
        _val_title_layout = QHBoxLayout(_val_title_bar)
        _val_title_layout.setContentsMargins(*_ALL_IN_ONE_VALIDATIONS_TITLE_MARGINS)
        _val_title_layout.setSpacing(0)
        _val_title = QLabel("API: Validations")
        _val_title_layout.addWidget(_val_title)
        _val_title_layout.addStretch()
        _vsec.addWidget(_val_title_bar)
        _vsec.addWidget(self._validations_page, 1)
        self._lower_splitter.addWidget(self._validations_section)
        self._comment_panel = ValidationCommentPanel(self._validations_page, self)
        self._lower_splitter.addWidget(self._comment_panel)
        self._lower_splitter.setSizes([1, 1])
        self._lower_splitter.setStretchFactor(0, 1)
        self._lower_splitter.setStretchFactor(1, 1)

        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(self._details_page)
        main_splitter.addWidget(self._lower_splitter)
        main_splitter.setSizes([400, 400])
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 1)
        layout.addWidget(main_splitter)

    def _apply_lower_splitter_50_50(self) -> None:
        w = self._lower_splitter.width()
        if w < 40:
            return
        left = w // 2
        right = max(1, w - left)
        self._lower_splitter.setSizes([left, right])
        self._lower_split_applied = True

    def _get_token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _refresh_combined(self) -> None:
        self._refresh_display_access()
        if not self._can_display_all_in_one:
            self._details_page.reset_after_parent_load_failure("Require Permission.")
            self._validations_page.apply_rows_from_parent_load([])
            return
        if self._loading:
            self._pending_refresh = True
            return
        token = self._get_token()
        self._loading = True
        self._details_page.set_loading_state(True)
        self._validations_page.set_loading_state(True)
        self._load_thread = QThread(self)
        self._load_worker = _AllInOneLoadWorker(token)
        self._load_worker.moveToThread(self._load_thread)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.finished.connect(self._on_combined_loaded)
        self._load_worker.finished.connect(self._load_thread.quit)
        self._load_thread.finished.connect(self._cleanup_combined_loader)
        self._load_thread.start()

    @Slot()
    def _on_combined_loaded(
        self, success: bool, details: object, validations: object, message: str
    ) -> None:
        self._loading = False
        try:
            if not success:
                self._details_page.reset_after_parent_load_failure(
                    message or "Failed to load data."
                )
                self._validations_page.apply_rows_from_parent_load([])
            else:
                d_rows = list(details) if isinstance(details, list) else []
                v_rows = list(validations) if isinstance(validations, list) else []
                self._details_page.apply_rows_from_parent_load(
                    [r for r in d_rows if isinstance(r, dict)]
                )
                self._validations_page.apply_rows_from_parent_load(
                    [r for r in v_rows if isinstance(r, dict)]
                )
        except Exception:
            traceback.print_exc()
            self._details_page.reset_after_parent_load_failure("Failed to display data.")
            self._validations_page.apply_rows_from_parent_load([])
        finally:
            if self._pending_refresh:
                self._pending_refresh = False
                self._refresh_combined()

    def _cleanup_combined_loader(self) -> None:
        if self._load_worker is not None:
            self._load_worker.deleteLater()
            self._load_worker = None
        if self._load_thread is not None:
            self._load_thread.deleteLater()
            self._load_thread = None

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_display_access()
        self._refresh_combined()
        if not self._lower_split_applied:
            QTimer.singleShot(0, self._maybe_apply_lower_split_50_50)

    def _maybe_apply_lower_split_50_50(self) -> None:
        if self._lower_split_applied:
            return
        self._apply_lower_splitter_50_50()
        if not self._lower_split_applied:
            QTimer.singleShot(50, self._maybe_apply_lower_split_50_50)


    def refresh(self) -> None:
        self._refresh_combined()

    def refresh_details(self) -> None:
        self._refresh_combined()

    def refresh_validations(self) -> None:
        self._refresh_combined()

    def _refresh_display_access(self) -> None:
        steps = get_nav_access_steps()
        if steps is None:
            self._can_display_all_in_one = True
        else:
            self._can_display_all_in_one = nav_action_visible_from_steps(
                "API: All in One", "display", steps
            )
        self._refresh_btn.setEnabled(self._can_display_all_in_one)
        self._refresh_btn.setToolTip(
            "" if self._can_display_all_in_one else "Require Permission."
        )
