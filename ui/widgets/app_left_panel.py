"""Left panel with navigation options (DM_Tool style)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QEasingCurve, QPropertyAnimation, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from core.left_panel_nav_items import (
    APP_CONFIG_SUB_OPTIONS,
    API_MANAGEMENT_SUB_OPTIONS,
    API_SUB_OPTIONS,
    LEAD_MANAGEMENT_SUB_OPTIONS,
    MASTER_SETUP_ITEM,
    OBJECT_TRACKER_SUB_OPTIONS,
    ORG_MANAGEMENT_SUB_OPTIONS,
    USER_MANAGEMENT_SUB_OPTIONS,
)
from core.nav_access import LeftPanelAccessState
from ui.styles import PANEL_STYLESHEET

_FIX_PIN_ICON_PATH = Path(__file__).resolve().parents[2] / "assets" / "fix_pin.png"


def _make_tinted_icon(path: Path, r: int, g: int, b: int) -> QIcon | None:
    """Load icon and tint non-transparent pixels to the given RGB (keeps alpha)."""
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None
    img = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() > 0:
                img.setPixelColor(x, y, QColor(r, g, b, c.alpha()))
    return QIcon(QPixmap.fromImage(img))

# Order: Dashboard, Org Management, User Management, API Management,
#        API Development, DB Design Project, Lead Management, DMT Tracker, App Config (before bottom actions)
DEFAULT_PANEL_ITEMS = ["Dashboard", "DB Design Project"]

# Bottom section items (pinned at bottom)
DEFAULT_PANEL_BOTTOM_ITEMS = ["View Profile", "Settings", "Sign Out"]


class _CollapsibleWidget(QWidget):
    """Widget that animates its height when expanded/collapsed."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._content_height = 0
        self._animation = QPropertyAnimation(self, b"maximumHeight")
        self._animation.setDuration(200)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_content_height(self, height: int) -> None:
        self._content_height = height

    def expand(self) -> None:
        self._animation.stop()
        self._animation.setStartValue(self.maximumHeight())
        self._animation.setEndValue(self._content_height)
        self._animation.start()

    def collapse(self) -> None:
        self._animation.stop()
        self._animation.setStartValue(self.maximumHeight())
        self._animation.setEndValue(0)
        self._animation.start()


class AppLeftPanel(QWidget):
    """Left sidebar with navigation buttons. Emits navigation_requested(item_name)."""

    navigation_requested = Signal(str)
    pin_toggled = Signal(bool)
    hide_panel_requested = Signal()

    def __init__(
        self,
        items: list[str] | None = None,
        bottom_items: list[str] | None = None,
        title: str = "Menu",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._default_panel_width = 280
        self._min_panel_width = 220
        self._max_panel_width = 520
        self._resizing_panel = False
        self._resize_start_global_x = 0
        self._resize_start_width = self._default_panel_width
        self.setMinimumWidth(self._min_panel_width)
        self.setMaximumWidth(self._max_panel_width)
        self.setFixedWidth(self._default_panel_width)
        self._items = items or DEFAULT_PANEL_ITEMS
        self._bottom_items = bottom_items or DEFAULT_PANEL_BOTTOM_ITEMS

        panel = QFrame()
        panel.setStyleSheet(PANEL_STYLESHEET)

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(panel, 1)

        self._resize_handle = QFrame()
        self._resize_handle.setObjectName("leftPanelResizeHandle")
        self._resize_handle.setFixedWidth(6)
        self._resize_handle.setCursor(Qt.CursorShape.SizeHorCursor)
        self._resize_handle.setStyleSheet(
            "#leftPanelResizeHandle { background: #d1d5db; border: none; }"
            "#leftPanelResizeHandle:hover { background: #94a3b8; }"
        )
        self._resize_handle.installEventFilter(self)
        root_layout.addWidget(self._resize_handle)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_frame = QFrame()
        title_frame.setObjectName("panelTitleFrame")
        title_frame.setMinimumHeight(72)
        title_frame.setStyleSheet(
            "#panelTitleFrame { background-color: #0f2340; border: none; border-bottom: 1px solid #475569; }"
        )
        title_frame_layout = QVBoxLayout(title_frame)
        title_frame_layout.setContentsMargins(14, 6, 4, 28)
        title_frame_layout.setSpacing(0)
        # Hide panel (arrow) + Pin in top-right corner
        pin_row = QHBoxLayout()
        pin_row.setContentsMargins(0, 10, 2, 0)
        pin_row.setSpacing(6)
        pin_row.addStretch()
        self._hide_panel_btn = QPushButton("\u25C0")  # ◀
        self._hide_panel_btn.setObjectName("panelArrowBtn")
        self._hide_panel_btn.setFixedSize(18, 18)
        self._hide_panel_btn.setToolTip("Hide left panel")
        self._hide_panel_btn.setStyleSheet(
            "#panelArrowBtn { background: transparent; color: #e2e8f0; border: none; outline: none;"
            " font-size: 11px; padding: 0; margin: 0; min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px; }"
            "#panelArrowBtn:hover { background: transparent; }"
            "#panelArrowBtn:disabled { background: transparent; color: #64748b; }"
            "#panelArrowBtn:focus { border: none; outline: none; }"
        )
        self._hide_panel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hide_panel_btn.clicked.connect(self.hide_panel_requested.emit)
        pin_row.addWidget(self._hide_panel_btn)
        self._pin_btn = QPushButton()
        self._pin_btn.setObjectName("panelPinBtn")
        self._pin_btn.setFixedSize(18, 18)
        self._pin_btn.setCheckable(True)
        self._pin_btn.setToolTip("Keep panel visible (fix)")
        self._pin_icon_pinned: QIcon | None = None
        self._pin_icon_unpinned: QIcon | None = None
        if _FIX_PIN_ICON_PATH.exists():
            self._pin_icon_pinned = _make_tinted_icon(_FIX_PIN_ICON_PATH, 128, 128, 128)  # grey when pinned
            self._pin_icon_unpinned = _make_tinted_icon(_FIX_PIN_ICON_PATH, 255, 255, 255)  # white when unpinned
        self._pin_btn.setIconSize(QSize(14, 14))
        self._pin_btn.setStyleSheet(
            "#panelPinBtn {"
            "  background: transparent; border: none; outline: none;"
            "  padding: 0; margin: 0; min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px;"
            "}"
            "#panelPinBtn:hover { background: transparent; }"
            "#panelPinBtn:checked { background: transparent; }"
            "#panelPinBtn:focus { border: none; outline: none; }"
        )
        self._pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pin_btn.setVisible(True)
        self._pin_shadow = QGraphicsDropShadowEffect(self._pin_btn)
        self._pin_shadow.setBlurRadius(8)
        self._pin_shadow.setXOffset(0)
        self._pin_shadow.setYOffset(1)
        self._pin_shadow.setColor(QColor(0, 0, 0, 80))

        def _update_pin_icon() -> None:
            if self._pin_btn.isChecked():
                if self._pin_icon_pinned:
                    self._pin_btn.setIcon(self._pin_icon_pinned)
            else:
                if self._pin_icon_unpinned:
                    self._pin_btn.setIcon(self._pin_icon_unpinned)

        def _on_pin_toggled(checked: bool) -> None:
            self._pin_btn.setToolTip("Unpin to allow hiding panel" if checked else "Keep panel visible (fix)")
            _update_pin_icon()
            if checked:
                self._pin_btn.setGraphicsEffect(self._pin_shadow)
            else:
                self._pin_btn.setGraphicsEffect(None)
            self.pin_toggled.emit(checked)

        self._pin_btn.toggled.connect(_on_pin_toggled)
        _update_pin_icon()
        pin_row.addWidget(self._pin_btn)
        title_frame_layout.addLayout(pin_row)
        # Title below pin row
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("panelTitleLabel")
        title_label.setStyleSheet(
            "#panelTitleLabel {"
            "  font-size: 14px; font-weight: 700; color: #ffffff;"
            "  background-color: transparent; border: none; padding: 0 0 0 10px;"
            "}"
        )
        title_label.setWordWrap(True)
        title_row.addWidget(title_label)
        title_row.addStretch()
        title_frame_layout.addLayout(title_row)
        layout.addWidget(title_frame)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(14, 10, 6, 18)
        content_layout.setSpacing(10)

        _toggle_style = (
            "QPushButton { color: #ffffff; background-color: transparent; border: none; "
            "border-bottom: 1px solid #3d5a7a; border-radius: 6px; text-align: left; padding: 8px 10px; }"
            "QPushButton:hover { background-color: #19365f; }"
            "QPushButton:checked { background-color: #1e3a5f; border-left: 3px solid #3b82f6; padding-left: 7px; }"
        )
        _sub_btn_style = (
            "QPushButton { color: #ffffff; background-color: transparent; border: none; "
            "border-radius: 4px; text-align: left; padding: 6px 10px; font-size: 12px; }"
            "QPushButton:hover { background-color: #1e3a5f; color: #e2e8f0; }"
        )
        _nav_selected_style = (
            "QPushButton { color: #e2e8f0; background-color: #1e3a5f; border: none; border-left: 3px solid #3b82f6; "
            "border-radius: 4px; text-align: left; padding: 6px 10px; font-size: 12px; padding-left: 10px; }"
            "QPushButton:hover { background-color: #234876; color: #f1f5f9; }"
        )
        self._nav_buttons: dict[str, QPushButton] = {}
        self._nav_normal_style = _sub_btn_style
        self._nav_selected_style = _nav_selected_style

        # 1. Dashboard (single button)
        dashboard_btn = QPushButton("Dashboard")
        dashboard_btn.setStyleSheet(_sub_btn_style)
        dashboard_btn.clicked.connect(lambda: self.navigation_requested.emit("Dashboard"))
        self._nav_buttons["Dashboard"] = dashboard_btn
        content_layout.addWidget(dashboard_btn)

        # 2. Org Management (collapsible, start collapsed)
        self._org_mgmt_toggle = QPushButton("Org Management")
        self._org_mgmt_toggle.setCheckable(True)
        self._org_mgmt_toggle.setChecked(False)
        self._org_mgmt_toggle.setStyleSheet(_toggle_style)
        self._org_mgmt_toggle.clicked.connect(self._on_org_mgmt_toggle)
        content_layout.addWidget(self._org_mgmt_toggle)
        self._org_mgmt_sub_container = _CollapsibleWidget()
        self._org_mgmt_sub_container.setMaximumHeight(0)
        org_mgmt_layout = QVBoxLayout(self._org_mgmt_sub_container)
        org_mgmt_layout.setContentsMargins(20, 4, 0, 8)
        org_mgmt_layout.setSpacing(6)
        for opt in ORG_MANAGEMENT_SUB_OPTIONS:
            btn = QPushButton(opt)
            btn.setStyleSheet(_sub_btn_style)
            btn.clicked.connect(lambda checked=False, name=opt: self.navigation_requested.emit(name))
            self._nav_buttons[opt] = btn
            org_mgmt_layout.addWidget(btn)
        content_layout.addWidget(self._org_mgmt_sub_container)
        self._org_mgmt_sub_container.setMinimumHeight(0)
        self._org_mgmt_sub_container.set_content_height(len(ORG_MANAGEMENT_SUB_OPTIONS) * 36 + 20)

        # 3. User Management (collapsible, start collapsed)
        self._user_mgmt_toggle = QPushButton("User Management")
        self._user_mgmt_toggle.setCheckable(True)
        self._user_mgmt_toggle.setChecked(False)
        self._user_mgmt_toggle.setStyleSheet(_toggle_style)
        self._user_mgmt_toggle.clicked.connect(self._on_user_mgmt_toggle)
        content_layout.addWidget(self._user_mgmt_toggle)
        self._user_mgmt_sub_container = _CollapsibleWidget()
        self._user_mgmt_sub_container.setMaximumHeight(0)
        user_mgmt_layout = QVBoxLayout(self._user_mgmt_sub_container)
        user_mgmt_layout.setContentsMargins(20, 4, 0, 8)
        user_mgmt_layout.setSpacing(6)
        for opt in USER_MANAGEMENT_SUB_OPTIONS:
            btn = QPushButton(opt)
            btn.setStyleSheet(_sub_btn_style)
            btn.clicked.connect(lambda checked=False, name=opt: self.navigation_requested.emit(name))
            self._nav_buttons[opt] = btn
            user_mgmt_layout.addWidget(btn)
        content_layout.addWidget(self._user_mgmt_sub_container)
        self._user_mgmt_sub_container.setMinimumHeight(0)
        self._user_mgmt_sub_container.set_content_height(len(USER_MANAGEMENT_SUB_OPTIONS) * 36 + 20)

        # 4. API Management (collapsible, start collapsed)
        self._api_mgmt_toggle = QPushButton("API Management")
        self._api_mgmt_toggle.setCheckable(True)
        self._api_mgmt_toggle.setChecked(False)
        self._api_mgmt_toggle.setStyleSheet(_toggle_style)
        self._api_mgmt_toggle.clicked.connect(self._on_api_mgmt_toggle)
        content_layout.addWidget(self._api_mgmt_toggle)
        self._api_mgmt_sub_container = _CollapsibleWidget()
        self._api_mgmt_sub_container.setMaximumHeight(0)
        api_mgmt_layout = QVBoxLayout(self._api_mgmt_sub_container)
        api_mgmt_layout.setContentsMargins(20, 4, 0, 8)
        api_mgmt_layout.setSpacing(6)
        for opt in API_MANAGEMENT_SUB_OPTIONS:
            btn = QPushButton(opt)
            btn.setStyleSheet(_sub_btn_style)
            btn.clicked.connect(lambda checked=False, name=opt: self.navigation_requested.emit(name))
            self._nav_buttons[opt] = btn
            api_mgmt_layout.addWidget(btn)
        content_layout.addWidget(self._api_mgmt_sub_container)
        self._api_mgmt_sub_container.setMinimumHeight(0)
        self._api_mgmt_sub_container.set_content_height(len(API_MANAGEMENT_SUB_OPTIONS) * 36 + 20)

        # 5. API Development (collapsible, start collapsed)
        self._api_toggle = QPushButton("API Development")
        self._api_toggle.setCheckable(True)
        self._api_toggle.setChecked(False)
        self._api_toggle.setStyleSheet(_toggle_style)
        self._api_toggle.clicked.connect(self._on_api_toggle)
        content_layout.addWidget(self._api_toggle)
        self._api_sub_container = _CollapsibleWidget()
        self._api_sub_container.setMaximumHeight(0)
        sub_layout = QVBoxLayout(self._api_sub_container)
        sub_layout.setContentsMargins(20, 4, 0, 8)
        sub_layout.setSpacing(6)
        for opt in API_SUB_OPTIONS:
            btn = QPushButton(opt)
            btn.setStyleSheet(_sub_btn_style)
            btn.clicked.connect(lambda checked=False, name=opt: self.navigation_requested.emit(name))
            self._nav_buttons[opt] = btn
            sub_layout.addWidget(btn)
        content_layout.addWidget(self._api_sub_container)
        self._api_sub_container.setMinimumHeight(0)
        self._api_sub_container.set_content_height(len(API_SUB_OPTIONS) * 36 + 20)

        # 6. DB Design Project (single button)
        self._db_design_btn = QPushButton("DB Design Project")
        self._db_design_btn.setStyleSheet(_sub_btn_style)
        self._db_design_btn.clicked.connect(
            lambda: self.navigation_requested.emit("DB Design Project")
        )
        self._nav_buttons["DB Design Project"] = self._db_design_btn
        content_layout.addWidget(self._db_design_btn)

        # 7. Lead Management (collapsible, start collapsed)
        self._lead_mgmt_toggle = QPushButton("Lead Management")
        self._lead_mgmt_toggle.setCheckable(True)
        self._lead_mgmt_toggle.setChecked(False)
        self._lead_mgmt_toggle.setStyleSheet(_toggle_style)
        self._lead_mgmt_toggle.clicked.connect(self._on_lead_mgmt_toggle)
        content_layout.addWidget(self._lead_mgmt_toggle)
        self._lead_mgmt_sub_container = _CollapsibleWidget()
        self._lead_mgmt_sub_container.setMaximumHeight(0)
        lead_mgmt_layout = QVBoxLayout(self._lead_mgmt_sub_container)
        lead_mgmt_layout.setContentsMargins(20, 4, 0, 8)
        lead_mgmt_layout.setSpacing(6)
        for opt in LEAD_MANAGEMENT_SUB_OPTIONS:
            btn = QPushButton(opt)
            btn.setStyleSheet(_sub_btn_style)
            btn.clicked.connect(lambda checked=False, name=opt: self.navigation_requested.emit(name))
            self._nav_buttons[opt] = btn
            lead_mgmt_layout.addWidget(btn)
        content_layout.addWidget(self._lead_mgmt_sub_container)
        self._lead_mgmt_sub_container.setMinimumHeight(0)
        self._lead_mgmt_sub_container.set_content_height(len(LEAD_MANAGEMENT_SUB_OPTIONS) * 36 + 20)

        # 8. DMT Tracker (collapsible, start collapsed)
        self._object_tracker_toggle = QPushButton("DMT Tracker")
        self._object_tracker_toggle.setCheckable(True)
        self._object_tracker_toggle.setChecked(False)
        self._object_tracker_toggle.setStyleSheet(_toggle_style)
        self._object_tracker_toggle.clicked.connect(self._on_object_tracker_toggle)
        content_layout.addWidget(self._object_tracker_toggle)
        self._object_tracker_sub_container = _CollapsibleWidget()
        self._object_tracker_sub_container.setMaximumHeight(0)
        object_tracker_layout = QVBoxLayout(self._object_tracker_sub_container)
        object_tracker_layout.setContentsMargins(20, 4, 0, 8)
        object_tracker_layout.setSpacing(6)
        for opt in OBJECT_TRACKER_SUB_OPTIONS:
            btn = QPushButton(opt)
            btn.setStyleSheet(_sub_btn_style)
            btn.clicked.connect(lambda checked=False, name=opt: self.navigation_requested.emit(name))
            self._nav_buttons[opt] = btn
            object_tracker_layout.addWidget(btn)
        content_layout.addWidget(self._object_tracker_sub_container)
        self._object_tracker_sub_container.setMinimumHeight(0)
        self._object_tracker_sub_container.set_content_height(len(OBJECT_TRACKER_SUB_OPTIONS) * 36 + 20)

        # 9. App Config (collapsible, start collapsed)
        self._app_config_toggle = QPushButton("App Config")
        self._app_config_toggle.setCheckable(True)
        self._app_config_toggle.setChecked(False)
        self._app_config_toggle.setStyleSheet(_toggle_style)
        self._app_config_toggle.clicked.connect(self._on_app_config_toggle)
        content_layout.addWidget(self._app_config_toggle)
        self._app_config_sub_container = _CollapsibleWidget()
        self._app_config_sub_container.setMaximumHeight(0)
        app_config_layout = QVBoxLayout(self._app_config_sub_container)
        app_config_layout.setContentsMargins(20, 4, 0, 8)
        app_config_layout.setSpacing(6)
        for opt in APP_CONFIG_SUB_OPTIONS:
            btn = QPushButton(opt)
            btn.setStyleSheet(_sub_btn_style)
            btn.clicked.connect(lambda checked=False, name=opt: self.navigation_requested.emit(name))
            self._nav_buttons[opt] = btn
            app_config_layout.addWidget(btn)
        content_layout.addWidget(self._app_config_sub_container)
        self._app_config_sub_container.setMinimumHeight(0)
        self._app_config_sub_container.set_content_height(len(APP_CONFIG_SUB_OPTIONS) * 36 + 20)

        content_layout.addStretch()

        for item in self._bottom_items:
            button = QPushButton(item)
            button.setStyleSheet(_sub_btn_style)
            button.clicked.connect(
                lambda checked=False, name=item: self.navigation_requested.emit(name)
            )
            if item != "Sign Out":
                self._nav_buttons[item] = button
            content_layout.addWidget(button)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("leftPanelOuterScroll")
        scroll_area.setWidgetResizable(True)
        # Keep vertical behavior as before; allow horizontal when panel width gets too small.
        content_widget.setMinimumWidth(260)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet(
            "QScrollArea#leftPanelOuterScroll { border: none; background: transparent; }"
            "QScrollArea#leftPanelOuterScroll > QWidget > QWidget { background: transparent; }"
        )
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if obj is getattr(self, "_resize_handle", None):
            if event.type() == QEvent.Type.MouseButtonPress and getattr(event, "button", lambda: None)() == Qt.MouseButton.LeftButton:
                self._resizing_panel = True
                self._resize_start_global_x = int(event.globalPosition().x())  # type: ignore[attr-defined]
                self._resize_start_width = self.width()
                return True
            if event.type() == QEvent.Type.MouseMove and self._resizing_panel:
                current_x = int(event.globalPosition().x())  # type: ignore[attr-defined]
                delta = current_x - self._resize_start_global_x
                new_width = max(
                    self._min_panel_width,
                    min(self._max_panel_width, self._resize_start_width + delta),
                )
                self.setFixedWidth(new_width)
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and self._resizing_panel:
                self._resizing_panel = False
                return True
        return super().eventFilter(obj, event)

    def apply_nav_access_state(self, state: LeftPanelAccessState) -> None:
        """Show or hide menu sections and sub-items from GET get-app-id-step-id-list (see :mod:`core.nav_access`)."""

        def _pair(toggle: QPushButton, container: _CollapsibleWidget, show: bool) -> None:
            toggle.setVisible(show)
            container.setVisible(show)
            if not show:
                toggle.setChecked(False)
                container.setMaximumHeight(0)

        def _sub_visible(lbl: str) -> bool:
            if state.unrestricted:
                return True
            return lbl in state.visible_gated_nav_labels

        def _apply_subs(labels: list[str], container: _CollapsibleWidget) -> None:
            n = 0
            for lbl in labels:
                vis = _sub_visible(lbl)
                self._nav_buttons[lbl].setVisible(vis)
                if vis:
                    n += 1
            container.set_content_height(n * 36 + 20 if n else 20)

        _pair(
            self._org_mgmt_toggle,
            self._org_mgmt_sub_container,
            state.show_org_management,
        )
        if state.show_org_management:
            _apply_subs(ORG_MANAGEMENT_SUB_OPTIONS, self._org_mgmt_sub_container)

        _pair(
            self._user_mgmt_toggle,
            self._user_mgmt_sub_container,
            state.show_user_management,
        )
        if state.show_user_management:
            _apply_subs(USER_MANAGEMENT_SUB_OPTIONS, self._user_mgmt_sub_container)

        _pair(
            self._api_mgmt_toggle,
            self._api_mgmt_sub_container,
            state.show_api_management,
        )
        if state.show_api_management:
            _apply_subs(API_MANAGEMENT_SUB_OPTIONS, self._api_mgmt_sub_container)

        self._db_design_btn.setVisible(state.show_db_design_project)

        _pair(
            self._lead_mgmt_toggle,
            self._lead_mgmt_sub_container,
            state.show_lead_management,
        )
        if state.show_lead_management:
            _apply_subs(LEAD_MANAGEMENT_SUB_OPTIONS, self._lead_mgmt_sub_container)

        _pair(
            self._object_tracker_toggle,
            self._object_tracker_sub_container,
            state.show_dmt_tracker,
        )
        if state.show_dmt_tracker:
            _apply_subs(OBJECT_TRACKER_SUB_OPTIONS, self._object_tracker_sub_container)

        _pair(self._api_toggle, self._api_sub_container, state.show_api_development)
        if state.show_api_development:
            _apply_subs(API_SUB_OPTIONS, self._api_sub_container)

        self._api_toggle.setText(state.api_development_title)
        _pair(
            self._app_config_toggle,
            self._app_config_sub_container,
            state.show_app_config,
        )
        if state.show_app_config:
            _apply_subs(APP_CONFIG_SUB_OPTIONS, self._app_config_sub_container)

    def set_pin_checked(self, checked: bool) -> None:
        self._pin_btn.setChecked(checked)
        self._pin_btn.setToolTip("Unpin to allow hiding panel" if checked else "Keep panel visible (fix)")

    def set_hide_panel_button_enabled(self, enabled: bool) -> None:
        """Enable or disable the hide (arrow) button, e.g. when panel is pinned."""
        self._hide_panel_btn.setEnabled(enabled)
        self._hide_panel_btn.setToolTip("Panel is fixed visible" if not enabled else "Hide left panel")

    def set_current_item(self, item_name: str) -> None:
        """Highlight the nav button for the current page; expand section if item is a child, else collapse all."""
        for name, btn in self._nav_buttons.items():
            btn.setStyleSheet(self._nav_selected_style if name == item_name else self._nav_normal_style)
        if item_name in ORG_MANAGEMENT_SUB_OPTIONS:
            self._collapse_others_except(self._org_mgmt_toggle)
            self._org_mgmt_toggle.setChecked(True)
            self._org_mgmt_sub_container.expand()
        elif item_name in USER_MANAGEMENT_SUB_OPTIONS:
            self._collapse_others_except(self._user_mgmt_toggle)
            self._user_mgmt_toggle.setChecked(True)
            self._user_mgmt_sub_container.expand()
        elif item_name in API_MANAGEMENT_SUB_OPTIONS:
            self._collapse_others_except(self._api_mgmt_toggle)
            self._api_mgmt_toggle.setChecked(True)
            self._api_mgmt_sub_container.expand()
        elif item_name in API_SUB_OPTIONS:
            self._collapse_others_except(self._api_toggle)
            self._api_toggle.setChecked(True)
            self._api_sub_container.expand()
        elif item_name in LEAD_MANAGEMENT_SUB_OPTIONS:
            self._collapse_others_except(self._lead_mgmt_toggle)
            self._lead_mgmt_toggle.setChecked(True)
            self._lead_mgmt_sub_container.expand()
        elif item_name in OBJECT_TRACKER_SUB_OPTIONS:
            self._collapse_others_except(self._object_tracker_toggle)
            self._object_tracker_toggle.setChecked(True)
            self._object_tracker_sub_container.expand()
        elif item_name in APP_CONFIG_SUB_OPTIONS:
            self._collapse_others_except(self._app_config_toggle)
            self._app_config_toggle.setChecked(True)
            self._app_config_sub_container.expand()
        else:
            self.collapse_all_sections()

    def collapse_all_sections(self) -> None:
        """Collapse collapsible sections (e.g. when clicking Dashboard)."""
        self._org_mgmt_toggle.setChecked(False)
        self._org_mgmt_sub_container.collapse()
        self._user_mgmt_toggle.setChecked(False)
        self._user_mgmt_sub_container.collapse()
        self._api_mgmt_toggle.setChecked(False)
        self._api_mgmt_sub_container.collapse()
        self._api_toggle.setChecked(False)
        self._api_sub_container.collapse()
        self._lead_mgmt_toggle.setChecked(False)
        self._lead_mgmt_sub_container.collapse()
        self._object_tracker_toggle.setChecked(False)
        self._object_tracker_sub_container.collapse()
        self._app_config_toggle.setChecked(False)
        self._app_config_sub_container.collapse()

    def _collapse_others_except(self, except_toggle: QPushButton) -> None:
        """Collapse all sections except the one whose toggle is given (accordion: only one open)."""
        if except_toggle is not self._org_mgmt_toggle:
            self._org_mgmt_toggle.setChecked(False)
            self._org_mgmt_sub_container.collapse()
        if except_toggle is not self._user_mgmt_toggle:
            self._user_mgmt_toggle.setChecked(False)
            self._user_mgmt_sub_container.collapse()
        if except_toggle is not self._api_mgmt_toggle:
            self._api_mgmt_toggle.setChecked(False)
            self._api_mgmt_sub_container.collapse()
        if except_toggle is not self._api_toggle:
            self._api_toggle.setChecked(False)
            self._api_sub_container.collapse()
        if except_toggle is not self._lead_mgmt_toggle:
            self._lead_mgmt_toggle.setChecked(False)
            self._lead_mgmt_sub_container.collapse()
        if except_toggle is not self._object_tracker_toggle:
            self._object_tracker_toggle.setChecked(False)
            self._object_tracker_sub_container.collapse()
        if except_toggle is not self._app_config_toggle:
            self._app_config_toggle.setChecked(False)
            self._app_config_sub_container.collapse()

    def _on_org_mgmt_toggle(self) -> None:
        if self._org_mgmt_toggle.isChecked():
            self._collapse_others_except(self._org_mgmt_toggle)
            self._org_mgmt_sub_container.expand()
        else:
            self._org_mgmt_sub_container.collapse()

    def _on_user_mgmt_toggle(self) -> None:
        if self._user_mgmt_toggle.isChecked():
            self._collapse_others_except(self._user_mgmt_toggle)
            self._user_mgmt_sub_container.expand()
        else:
            self._user_mgmt_sub_container.collapse()

    def _on_api_mgmt_toggle(self) -> None:
        if self._api_mgmt_toggle.isChecked():
            self._collapse_others_except(self._api_mgmt_toggle)
            self._api_mgmt_sub_container.expand()
        else:
            self._api_mgmt_sub_container.collapse()

    def _on_api_toggle(self) -> None:
        if self._api_toggle.isChecked():
            self._collapse_others_except(self._api_toggle)
            self._api_sub_container.expand()
        else:
            self._api_sub_container.collapse()

    def _on_lead_mgmt_toggle(self) -> None:
        if self._lead_mgmt_toggle.isChecked():
            self._collapse_others_except(self._lead_mgmt_toggle)
            self._lead_mgmt_sub_container.expand()
        else:
            self._lead_mgmt_sub_container.collapse()

    def _on_object_tracker_toggle(self) -> None:
        if self._object_tracker_toggle.isChecked():
            self._collapse_others_except(self._object_tracker_toggle)
            self._object_tracker_sub_container.expand()
        else:
            self._object_tracker_sub_container.collapse()

    def _on_app_config_toggle(self) -> None:
        if self._app_config_toggle.isChecked():
            self._collapse_others_except(self._app_config_toggle)
            self._app_config_sub_container.expand()
        else:
            self._app_config_sub_container.collapse()
