"""Simple dashboard shown after login."""

import traceback

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.api_dev.api_details import (
    APIDetailsPage,
    CreateAPIDetailPage,
    ViewAPIDetailPage,
)
from app.api_dev.api_validations import (
    APIValidationsPage,
    CreateAPIValidationPage,
    ViewAPIValidationPage,
)
from app.api_dev.api_dev_all_in_one import ApiDevAllInOnePage
from app.api_dev.api_project import (
    APIProjectsPage,
    CreateProjectPage,
    ViewProjectPage,
)
from app.api_dev.api_userType import (
    APIUserInvolvedPage,
    CreateUserTypePage,
    ViewUserTypePage,
)
from app.api_management.api_app_id import ApiAppIdListPage
from app.api_management.api_registry_list import ApiRegistryListPage
from app.api_management.api_role_assignment_page import ApiRoleAssignmentPage
from app.user_management.user_role_assignment.user_role_assignment_list import (
    UserRoleAssignmentListPage,
)
from app.user_management.user_role_assignment.user_role_assignment_create import (
    CreateUserRoleAssignmentPage,
)
from app.user_management.users.user_create import CreateUserPage
from app.user_management.reporting_manager.reporting_manager_list import (
    ReportingManagerPage,
)
from app.user_management.users.user_view import ViewUserPage
from app.db_management.db_design_project_page import DbDesignProjectPage
from app.user_profile.settings_page import SettingsPage
from app.user_management.users.user_list import UsersPage
from app.user_management.user_timepass.user_reset_password import ResetUserPasswordPage
from app.org_management.bu.bu_create import CreateBuPage
from app.org_management.bu.bu_list import BuListPage
from app.org_management.bu.bu_view import ViewBuPage
from app.org_management.dept.dept_create import CreateDeptPage
from app.org_management.dept.dept_list import DeptListPage
from app.org_management.dept.dept_view import ViewDeptPage
from app.org_management.position.position_create import CreatePositionPage
from app.org_management.position.position_list import PositionListPage
from app.org_management.position.position_view import ViewPositionPage
from app.org_management.role.role_create import CreateRolePage
from app.org_management.role.roles_list import RolesListPage
from app.org_management.role.roles_view import ViewRolePage
from app.org_management.org.org_create import CreateOrgPage
from app.org_management.org.org_list import OrgListPage
from app.org_management.org.org_view import ViewOrgPage
from app.user_profile.profile_view import ViewProfilePage
from core.api import api_check_app_version
from core.app_version import APP_VERSION
from core.reminders_ws_client import AppUpdatesWebSocketClient
from core.ws_notification import WsNotificationPayload
from ui.ws_update_banner import WsUpdateBanner
from core.nav_access import build_left_panel_access_state
from core.user_context import (
    get_nav_access_steps,
    get_user_email,
    get_user_profile,
    get_user_role,
)
from ui.widgets.app_left_panel import (
    API_MANAGEMENT_SUB_OPTIONS,
    API_SUB_OPTIONS,
    APP_ACCESS_CONTROL_SUB_OPTIONS,
    AppLeftPanel,
    ORG_MANAGEMENT_SUB_OPTIONS,
    USER_MANAGEMENT_SUB_OPTIONS,
)
from ui.form_page_styles import (
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    themed_list_page_header_stylesheet,
)
from ui.styles import TITLE_STYLE, SUBTITLE_STYLE
from ui.theme import Theme
from ui.auto_update_dialog import AutoUpdateDialog
from ui.version_check_dialog import (
    show_version_check_error,
    show_version_check_needs_sign_in,
    show_version_check_unexpected,
    show_version_check_up_to_date,
)

# When GET app/version returns no custom "message", explain setup .exe vs .zip to the user.
_UPDATE_HELP_EXTRA_SETUP = (
    "You will download the Windows setup program (Inno Setup). It upgrades the installed "
    "copy and restarts the new version (silent install when possible)."
)
_UPDATE_HELP_EXTRA_ZIP = (
    "You will download a .zip of the application folder. The app extracts it automatically, "
    "starts the new build, then exits — no separate installer."
)


class _AppVersionCheckWorker(QObject):
    finished = Signal(object)

    def __init__(self, token: str) -> None:
        super().__init__()
        self._token = token

    @Slot()
    def run(self) -> None:
        self.finished.emit(api_check_app_version(current_version=APP_VERSION, token=self._token))


class DashboardWindow(QMainWindow):
    def __init__(self, on_sign_out=None) -> None:
        super().__init__()
        self.setWindowTitle("MY ETLZONE App")
        self.resize(1280, 800)
        self.on_sign_out = on_sign_out
        self._version_check_thread: QThread | None = None
        self._version_check_worker: _AppVersionCheckWorker | None = None
        self._reminders_ws = AppUpdatesWebSocketClient(self)
        self._reminders_ws.notification.connect(self._on_ws_notification)
        self._create_menu_bar()

        root = QWidget()
        self.setCentralWidget(root)
        root_outer = QVBoxLayout(root)
        root_outer.setContentsMargins(0, 0, 0, 0)
        root_outer.setSpacing(0)

        self._ws_update_banner = WsUpdateBanner(root)
        root_outer.addWidget(self._ws_update_banner)

        content_row = QWidget()
        root_layout = QHBoxLayout(content_row)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Left side: panel only (no side strip; show-button appears only when panel is hidden)
        self._panel_visible = True
        self._panel_fixed = False
        left_side = QWidget()
        left_side_layout = QHBoxLayout(left_side)
        left_side_layout.setContentsMargins(0, 0, 0, 0)
        left_side_layout.setSpacing(0)

        _profile = get_user_profile()
        _username = (
            _profile.get("username")
            or _profile.get("userName")
            or _profile.get("userId")
            or get_user_email()
        )
        _role = (
            _profile.get("defaultRole")
            or _profile.get("default_role")
            or get_user_role()
            or _profile.get("roles")
            or ""
        )
        _panel_title = f"{_username} ({_role})" if _role else str(_username)
        self.left_panel = AppLeftPanel(title=_panel_title)
        self.left_panel.apply_nav_access_state(
            build_left_panel_access_state(get_nav_access_steps())
        )
        self.left_panel.navigation_requested.connect(self._handle_left_navigation)
        self.left_panel.pin_toggled.connect(self._on_pin_toggled)
        self.left_panel.hide_panel_requested.connect(self._toggle_left_panel)
        self.left_panel.set_hide_panel_button_enabled(True)
        left_side_layout.addWidget(self.left_panel)

        self._show_panel_btn = QPushButton("\u25B6")  # ▶
        self._show_panel_btn.setObjectName("showPanelBtn")
        self._show_panel_btn.setFixedSize(24, 65)
        self._show_panel_btn.setToolTip("Show left panel")
        self._show_panel_btn.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)
        t = Theme
        self._show_panel_btn.setStyleSheet(
            f"#showPanelBtn {{ background-color: {t.SHOW_PANEL_STRIP_BG}; "
            f"color: {t.SHOW_PANEL_STRIP_TEXT}; border: none; "
            f"border-right: 1px solid {t.SHOW_PANEL_STRIP_BORDER}; "
            f"font-size: 11px; padding: 0; margin: 0; }}"
            f"#showPanelBtn:hover {{ background-color: {t.SHOW_PANEL_STRIP_HOVER}; }}"
        )
        self._show_panel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._show_panel_btn.clicked.connect(self._show_left_panel)
        self._show_panel_btn.setVisible(False)
        self._show_panel_btn.setParent(left_side)

        root_layout.addWidget(left_side)
        self._left_side_widget = left_side
        self._left_side_layout = left_side_layout

        self.stack = QStackedWidget()
        self.stack.setStyleSheet(
            f"QStackedWidget {{ background-color: {Theme.BG_APP}; }}"
        )

        # Dashboard page
        dashboard_page = QWidget()
        layout = QVBoxLayout(dashboard_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        dashboard_header = QWidget()
        th = Theme
        dashboard_header.setStyleSheet(
            themed_list_page_header_stylesheet(
                widget_bg=th.HEADER_NAV,
                label_color=th.PANEL_TEXT_BRIGHT,
                button_bg=th.HEADER_ACCENT,
                button_color=th.PANEL_TEXT_BRIGHT,
                button_hover=th.HEADER_ACCENT_HOVER,
                button_pressed=th.HEADER_ACCENT_PRESSED,
            )
        )
        dashboard_header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        header_layout = QHBoxLayout(dashboard_header)
        header_layout.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        header_layout.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        dashboard_title = QLabel("Dashboard")
        header_layout.addWidget(dashboard_title)
        header_layout.addStretch()
        sign_out_btn = QPushButton("Sign out")
        sign_out_btn.setFixedWidth(120)
        sign_out_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sign_out_btn.clicked.connect(self._handle_sign_out)
        header_layout.addWidget(sign_out_btn)
        layout.addWidget(dashboard_header)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(40, 40, 40, 40)
        content_layout.setSpacing(16)
        content_layout.addStretch()

        layout.addWidget(content)

        self.stack.addWidget(dashboard_page)

        # Users page
        self.users_page = UsersPage(
            on_create_clicked=self._show_create_user,
            on_edit_clicked=lambda u, e: self._show_view_user(u, e),
        )
        self.stack.addWidget(self.users_page)

        # View User page
        # List reloads via UsersPage.showEvent; avoid duplicate refresh after save.
        self.view_user_page = ViewUserPage(
            on_back=self._show_users,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_user_page)

        # DB Design Project page
        self.db_design_project_page = DbDesignProjectPage()
        self.stack.addWidget(self.db_design_project_page)

        # Create User page
        self.create_user_page = CreateUserPage(on_back=self._show_users)
        self.stack.addWidget(self.create_user_page)

        # Create Project page (created before _api_pages, on_create_success set below)
        self.create_project_page = CreateProjectPage(on_back=self._show_api_projects)
        self.stack.addWidget(self.create_project_page)

        # Create User Type page (for API: User Involved) - on_create_success set in loop
        self.create_user_type_page = CreateUserTypePage()
        self.stack.addWidget(self.create_user_type_page)

        # Create API Detail page (API: Details list)
        self.create_api_detail_page = CreateAPIDetailPage()
        self.stack.addWidget(self.create_api_detail_page)

        # View Project page
        self.view_project_page = ViewProjectPage(
            on_back=self._show_api_projects,
            on_update_success=lambda: None,
        )
        self.stack.addWidget(self.view_project_page)

        # View User Type page (API: User Involved)
        self.view_user_type_page = ViewUserTypePage(
            on_back=self._show_api_user_involved,
            on_update_success=lambda: None,
        )
        self.stack.addWidget(self.view_user_type_page)

        # View API Detail page (API: Details)
        self.view_api_detail_page = ViewAPIDetailPage(
            on_back=self._show_api_details,
            on_update_success=lambda: None,
        )
        self.stack.addWidget(self.view_api_detail_page)

        # Create API Validation page (API: Validations)
        self.create_api_validation_page = CreateAPIValidationPage()
        self.stack.addWidget(self.create_api_validation_page)

        # View API Validation page (API: Validations)
        self.view_api_validation_page = ViewAPIValidationPage(
            on_back=self._show_api_validations,
            on_update_success=lambda: None,
        )
        self.stack.addWidget(self.view_api_validation_page)

        # View Profile page
        self.view_profile_page = ViewProfilePage(on_back=self._show_dashboard)
        self.stack.addWidget(self.view_profile_page)

        # Settings page
        self.settings_page = SettingsPage()
        self.stack.addWidget(self.settings_page)

        self.user_role_assignment_list_page = UserRoleAssignmentListPage(
            on_create_clicked=self._show_create_user_role_assignment,
            on_edit_clicked=lambda u, e: self._show_view_user(u, e),
        )
        self.stack.addWidget(self.user_role_assignment_list_page)
        self.create_user_role_assignment_page = CreateUserRoleAssignmentPage(
            on_back=self._show_user_role_assignment,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_user_role_assignment_page)

        self.reset_user_password_page = ResetUserPasswordPage()
        self.stack.addWidget(self.reset_user_password_page)

        self.reporting_manager_list_page = ReportingManagerPage()
        self.stack.addWidget(self.reporting_manager_list_page)

        self._user_mgmt_pages = {}
        for name in USER_MANAGEMENT_SUB_OPTIONS:
            if name == "Users":
                page = self.users_page
            elif name == "Reporting Manager":
                page = self.reporting_manager_list_page
            elif name == "User-Roles Assignment":
                page = self.user_role_assignment_list_page
            elif name == "Reset User Password":
                page = self.reset_user_password_page
            else:
                page = self._make_placeholder_page(name)
                self.stack.addWidget(page)
            self._user_mgmt_pages[name] = page

        # Org Management sub-option pages
        self._org_pages = {}
        for name in ORG_MANAGEMENT_SUB_OPTIONS:
            if name == "Organizations":
                page = OrgListPage(
                    on_create_clicked=self._show_create_org,
                    on_view_clicked=lambda o: self._show_view_org(o, edit_mode=False),
                    on_edit_org=lambda o: self._show_view_org(o, edit_mode=True),
                )
            elif name == "Business Units":
                page = BuListPage(
                    on_create_clicked=self._show_create_bu,
                    on_view_clicked=lambda b: self._show_view_bu(b, edit_mode=False),
                    on_edit_bu=lambda b: self._show_view_bu(b, edit_mode=True),
                )
            elif name == "Departments":
                page = DeptListPage(
                    on_create_clicked=self._show_create_dept,
                    on_view_clicked=lambda d: self._show_view_dept(d, edit_mode=False),
                    on_edit_dept=lambda d: self._show_view_dept(d, edit_mode=True),
                )
            elif name == "Positions":
                page = PositionListPage(
                    on_create_clicked=self._show_create_position,
                    on_view_clicked=lambda p: self._show_view_position(p, edit_mode=False),
                    on_edit_position=lambda p: self._show_view_position(p, edit_mode=True),
                )
            elif name == "Roles":
                page = RolesListPage(
                    on_create_clicked=self._show_create_role,
                    on_view_clicked=lambda r: self._show_view_role(r, edit_mode=False),
                    on_edit_role=lambda r: self._show_view_role(r, edit_mode=True),
                )
            else:
                page = self._make_placeholder_page(name)
            self.stack.addWidget(page)
            self._org_pages[name] = page

        self._app_access_pages = {}
        for name in APP_ACCESS_CONTROL_SUB_OPTIONS:
            page = self._make_placeholder_page(name)
            self.stack.addWidget(page)
            self._app_access_pages[name] = page

        self._api_mgmt_pages = {}
        for name in API_MANAGEMENT_SUB_OPTIONS:
            if name == "API: App Id":
                page = ApiAppIdListPage()
            elif name == "API: List":
                page = ApiRegistryListPage()
            elif name == "API: API-Role Assignment":
                page = ApiRoleAssignmentPage()
            else:
                page = self._make_placeholder_page(name)
            self.stack.addWidget(page)
            self._api_mgmt_pages[name] = page

        # Create/view success callbacks: omit list.refresh when that list reloads in showEvent
        # (avoids double fetch / thread overlap). Cross-page sync uses dedicated helpers instead.
        self.create_org_page = CreateOrgPage(
            on_back=self._show_organization,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_org_page)
        self.view_org_page = ViewOrgPage(
            on_back=self._show_organization,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_org_page)

        self.create_bu_page = CreateBuPage(
            on_back=self._show_business_unit,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_bu_page)
        self.view_bu_page = ViewBuPage(
            on_back=self._show_business_unit,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_bu_page)

        self.create_dept_page = CreateDeptPage(
            on_back=self._show_department,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_dept_page)
        self.view_dept_page = ViewDeptPage(
            on_back=self._show_department,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_dept_page)

        self.create_position_page = CreatePositionPage(
            on_back=self._show_position,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_position_page)
        self.view_position_page = ViewPositionPage(
            on_back=self._show_position,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_position_page)

        self.create_role_page = CreateRolePage(
            on_back=self._show_role,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_role_page)
        self.view_role_page = ViewRolePage(
            on_back=self._show_role,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_role_page)

        # API sub-option pages
        self._api_pages = {}
        for name in API_SUB_OPTIONS:
            if name == "API: Projects":
                page = APIProjectsPage(
                    on_create_clicked=self._show_create_project,
                    on_edit_clicked=lambda p, e: self._show_update_project(p, e, self._show_api_projects),
                )
                # Projects list reloads via showEvent on APIProjectsPage; only sync User Involved here.
                self.create_project_page.on_create_success = (
                    self._refresh_api_user_involved_after_project_change
                )
                self.view_project_page.on_update_success = (
                    self._refresh_api_user_involved_after_project_change
                )
            elif name == "API: User Involved":
                page = APIUserInvolvedPage(
                    on_create_clicked=self._show_create_user_type,
                    on_edit_clicked=lambda r, e: self._show_view_user_type(r, e),
                )
                self.create_user_type_page.on_back = self._show_api_user_involved
                # List reloads in showEvent; omit callback to avoid a second refresh racing the loader.
                self.create_user_type_page.on_create_success = None
                self.view_user_type_page.on_update_success = None
            elif name == "API: Details":
                page = APIDetailsPage(
                    on_create_clicked=self._show_create_api_detail,
                    on_edit_clicked=lambda r, e: self._show_view_api_detail(r, e),
                )
                self.create_api_detail_page.on_back = self._show_api_details
                self.create_api_detail_page.on_create_success = None
                self.view_api_detail_page.on_update_success = None
            elif name == "API: Validations":
                page = APIValidationsPage(
                    on_create_clicked=self._show_create_api_validation,
                    on_edit_clicked=lambda r, e: self._show_view_api_validation(r, e),
                )
                self.create_api_validation_page.on_back = self._show_api_validations
                self.create_api_validation_page.on_create_success = None
                self.view_api_validation_page.on_update_success = None
            elif name == "API: All in One":
                page = ApiDevAllInOnePage(
                    on_add_detail_clicked=self._show_create_api_detail_from_testing,
                    on_edit_detail_clicked=lambda r, e: self._show_view_api_detail_from_testing(r, e),
                    on_add_validation_clicked=self._show_create_api_validation_from_testing,
                    on_edit_validation_clicked=lambda r, e: self._show_view_api_validation_from_testing(r, e),
                )
                self._api_dev_all_in_one_page = page
            else:
                page = self._make_placeholder_page(name)
            self.stack.addWidget(page)
            self._api_pages[name] = page

        root_layout.addWidget(self.stack, 1)
        root_outer.addWidget(content_row, 1)
        self.left_panel.set_current_item("Dashboard")
        self._reminders_ws.start()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._reminders_ws.stop()
        super().closeEvent(event)

    @Slot(WsNotificationPayload)
    def _on_ws_notification(self, payload: WsNotificationPayload) -> None:
        self._ws_update_banner.show_payload(payload)

    def _make_placeholder_page(self, title: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)
        label = QLabel(title)
        label.setStyleSheet(TITLE_STYLE)
        sub = QLabel("Coming soon.")
        sub.setStyleSheet(SUBTITLE_STYLE)
        layout.addWidget(label)
        layout.addWidget(sub)
        layout.addStretch()
        return page

    def _handle_left_navigation(self, item_name: str) -> None:
        if not self._confirm_leave_if_unsaved():
            return
        if item_name == "Dashboard":
            self.stack.setCurrentIndex(0)
            self.left_panel.set_current_item("Dashboard")
        elif item_name in self._user_mgmt_pages:
            self.stack.setCurrentWidget(self._user_mgmt_pages[item_name])
            self.left_panel.set_current_item(item_name)
        elif item_name == "DB Design Project":
            self.stack.setCurrentWidget(self.db_design_project_page)
            self.left_panel.set_current_item("DB Design Project")
        elif item_name == "View Profile":
            self.stack.setCurrentWidget(self.view_profile_page)
            self.left_panel.set_current_item("View Profile")
        elif item_name == "Settings":
            self.stack.setCurrentWidget(self.settings_page)
            self.left_panel.set_current_item("Settings")
        elif item_name in self._org_pages:
            self.stack.setCurrentWidget(self._org_pages[item_name])
            self.left_panel.set_current_item(item_name)
        elif item_name in self._app_access_pages:
            self.stack.setCurrentWidget(self._app_access_pages[item_name])
            self.left_panel.set_current_item(item_name)
        elif item_name in self._api_mgmt_pages:
            self.stack.setCurrentWidget(self._api_mgmt_pages[item_name])
            self.left_panel.set_current_item(item_name)
        elif item_name in self._api_pages:
            self.stack.setCurrentWidget(self._api_pages[item_name])
            self.left_panel.set_current_item(item_name)
        elif item_name == "Sign Out":
            self._handle_sign_out()

    def _toggle_left_panel(self) -> None:
        if self._panel_fixed:
            return
        self._panel_visible = False
        self._left_side_layout.removeWidget(self.left_panel)
        self.left_panel.hide()
        self._left_side_layout.addWidget(self._show_panel_btn, 0, Qt.AlignmentFlag.AlignTop)
        self._show_panel_btn.show()

    def _show_left_panel(self) -> None:
        self._panel_visible = True
        self._left_side_layout.removeWidget(self._show_panel_btn)
        self._show_panel_btn.hide()
        self._left_side_layout.addWidget(self.left_panel)
        self.left_panel.show()

    def _on_pin_toggled(self, checked: bool) -> None:
        self._panel_fixed = checked
        self.left_panel.set_hide_panel_button_enabled(not self._panel_fixed)
        if self._panel_fixed and not self._panel_visible:
            self._show_left_panel()

    def _confirm_leave_if_unsaved(self) -> bool:
        """If current page has unsaved changes, show confirmation. Return True to allow navigation."""
        # Create User page - form modified
        if self.stack.currentWidget() is self.create_user_page:
            if self.create_user_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_user_page.reset_to_default()
                    return True
                return False
            return True
        # Create API Detail page - form modified
        if self.stack.currentWidget() is self.create_api_detail_page:
            if self.create_api_detail_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_api_detail_page.reset_to_default()
                    return True
                return False
            return True
        # Create API Validation page - form modified
        if self.stack.currentWidget() is self.create_api_validation_page:
            if self.create_api_validation_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_api_validation_page.reset_to_default()
                    return True
                return False
            return True
        # Create User Type page - form modified
        if self.stack.currentWidget() is self.create_user_type_page:
            if self.create_user_type_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_user_type_page.reset_to_default()
                    return True
                return False
            return True
        # Create Department page - form modified
        if self.stack.currentWidget() is self.create_dept_page:
            if self.create_dept_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_dept_page.reset_to_default()
                    return True
                return False
            return True
        # Create Position page - form modified
        if self.stack.currentWidget() is self.create_position_page:
            if self.create_position_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_position_page.reset_to_default()
                    return True
                return False
            return True
        # Create Role page - form modified
        if self.stack.currentWidget() is self.create_role_page:
            if self.create_role_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_role_page.reset_to_default()
                    return True
                return False
            return True
        # Create Project page - form modified
        if self.stack.currentWidget() is self.create_project_page:
            if self.create_project_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_project_page.reset_to_default()
                    return True
                return False
            return True
        # View API Detail page - edit mode
        if self.stack.currentWidget() is self.view_api_detail_page:
            if not self.view_api_detail_page.is_edit_mode():
                return True
            if not self.view_api_detail_page._has_unsaved_changes():
                return True
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Discard and leave?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Discard:
                self.view_api_detail_page._handle_cancel()
                return True
            return False
        # View API Validation page - edit mode
        if self.stack.currentWidget() is self.view_api_validation_page:
            if not self.view_api_validation_page.is_edit_mode():
                return True
            if not self.view_api_validation_page._has_unsaved_changes():
                return True
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Discard and leave?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Discard:
                self.view_api_validation_page._handle_cancel()
                return True
            return False
        # View User Type page - edit mode
        if self.stack.currentWidget() is self.view_user_type_page:
            if not self.view_user_type_page.is_edit_mode():
                return True
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Discard and leave?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Discard:
                self.view_user_type_page._handle_cancel()
                return True
            return False
        # View Project page - edit mode (same as View Profile)
        if self.stack.currentWidget() is self.view_project_page:
            if not self.view_project_page.is_edit_mode():
                return True
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Discard and leave?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Discard:
                self.view_project_page._handle_cancel()
                return True
            return False
        # View User page - edit mode
        if self.stack.currentWidget() is self.view_user_page:
            if self.view_user_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_user_page._handle_cancel()
                    return True
                return False
            return True
        # View Profile page - edit mode
        if self.stack.currentWidget() is self.view_profile_page:
            if not self.view_profile_page.is_edit_mode():
                return True
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Discard and leave?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Discard:
                self.view_profile_page._handle_cancel()
                return True
            return False
        # View Org page - edit mode
        if self.stack.currentWidget() is self.view_org_page:
            if self.view_org_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_org_page._handle_cancel()
                    return True
                return False
            return True
        # View Business Unit page - edit mode
        if self.stack.currentWidget() is self.view_bu_page:
            if self.view_bu_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_bu_page._handle_cancel()
                    return True
                return False
            return True
        # View Department page - edit mode
        if self.stack.currentWidget() is self.view_dept_page:
            if self.view_dept_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_dept_page._handle_cancel()
                    return True
                return False
            return True
        # View Position page - edit mode
        if self.stack.currentWidget() is self.view_position_page:
            if self.view_position_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_position_page._handle_cancel()
                    return True
                return False
            return True
        # View Role page - edit mode
        if self.stack.currentWidget() is self.view_role_page:
            if self.view_role_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_role_page._handle_cancel()
                    return True
                return False
            return True
        return True

    def _create_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(lambda: self.close())
        file_menu.addAction(exit_action)

        system_menu = menu_bar.addMenu("System")
        sign_out_action = QAction("Sign out", self)
        sign_out_action.triggered.connect(lambda: self._handle_sign_out())
        system_menu.addAction(sign_out_action)

        help_menu = menu_bar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(lambda: self._show_about_dialog())
        help_menu.addAction(about_action)
        check_version_action = QAction("Check for update", self)
        check_version_action.triggered.connect(self._check_for_latest_version)
        help_menu.addAction(check_version_action)

    def _show_dashboard(self) -> None:
        self.stack.setCurrentIndex(0)

    def _show_users(self) -> None:
        self.stack.setCurrentWidget(self.users_page)

    def _show_create_user(self) -> None:
        self.stack.setCurrentWidget(self.create_user_page)

    def _show_view_user(self, user: dict, edit_mode: bool = False) -> None:
        self.view_user_page.set_user(user, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_user_page)

    def _show_user_role_assignment(self) -> None:
        self.stack.setCurrentWidget(self.user_role_assignment_list_page)

    def _show_create_user_role_assignment(self) -> None:
        self.stack.setCurrentWidget(self.create_user_role_assignment_page)

    def _show_organization(self) -> None:
        self.stack.setCurrentWidget(self._org_pages["Organizations"])

    def _show_create_org(self) -> None:
        self.stack.setCurrentWidget(self.create_org_page)

    def _show_view_org(self, org: dict, edit_mode: bool = False) -> None:
        self.view_org_page.set_org(org, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_org_page)

    def _show_business_unit(self) -> None:
        self.stack.setCurrentWidget(self._org_pages["Business Units"])

    def _show_department(self) -> None:
        self.stack.setCurrentWidget(self._org_pages["Departments"])

    def _show_create_dept(self) -> None:
        self.stack.setCurrentWidget(self.create_dept_page)

    def _show_view_dept(self, dept: dict, edit_mode: bool = False) -> None:
        self.view_dept_page.set_dept(dept, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_dept_page)

    def _show_position(self) -> None:
        self.stack.setCurrentWidget(self._org_pages["Positions"])

    def _show_create_position(self) -> None:
        self.stack.setCurrentWidget(self.create_position_page)

    def _show_view_position(self, pos: dict, edit_mode: bool = False) -> None:
        self.view_position_page.set_position(pos, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_position_page)

    def _show_role(self) -> None:
        self.stack.setCurrentWidget(self._org_pages["Roles"])

    def _show_create_role(self) -> None:
        self.stack.setCurrentWidget(self.create_role_page)

    def _show_view_role(self, role: dict, edit_mode: bool = False) -> None:
        self.view_role_page.set_role(role, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_role_page)

    def _show_create_bu(self) -> None:
        self.stack.setCurrentWidget(self.create_bu_page)

    def _show_view_bu(self, bu: dict, edit_mode: bool = False) -> None:
        self.view_bu_page.set_bu(bu, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_bu_page)

    def _refresh_api_user_involved_after_project_change(self) -> None:
        """Sync API: User Involved after project create/update. Projects list reloads when that page is shown."""
        pg = self._api_pages.get("API: User Involved")
        if pg is None:
            return
        try:
            pg.refresh()
        except Exception:
            traceback.print_exc()

    def _show_api_projects(self) -> None:
        self.stack.setCurrentWidget(self._api_pages["API: Projects"])

    def _show_api_user_involved(self) -> None:
        self.stack.setCurrentWidget(self._api_pages["API: User Involved"])

    def _show_api_details(self) -> None:
        self.stack.setCurrentWidget(self._api_pages["API: Details"])

    def _show_create_api_detail(self) -> None:
        self.create_api_detail_page.on_back = self._show_api_details
        self.create_api_detail_page.on_create_success = None
        self.stack.setCurrentWidget(self.create_api_detail_page)

    def _show_view_api_detail(self, record: dict, edit_mode: bool = False) -> None:
        """Show the API detail view page for a record from the Details list."""
        self.view_api_detail_page.set_record(record, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_api_detail_page)

    def _show_api_validations(self) -> None:
        self.stack.setCurrentWidget(self._api_pages["API: Validations"])

    def _show_create_api_validation(self) -> None:
        self.create_api_validation_page.on_back = self._show_api_validations
        self.create_api_validation_page.on_create_success = None
        self.stack.setCurrentWidget(self.create_api_validation_page)

    def _show_view_api_validation(self, record: dict, edit_mode: bool = False) -> None:
        """Show the API validation view page for a record from the Validations list."""
        self.view_api_validation_page.on_back = self._show_api_validations
        self.view_api_validation_page.on_update_success = None
        self.view_api_validation_page.set_record(record, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_api_validation_page)

    def _show_api_testing(self) -> None:
        self.stack.setCurrentWidget(self._api_pages["API: All in One"])

    def _show_create_api_detail_from_testing(self) -> None:
        self.create_api_detail_page.on_back = self._show_api_testing
        self.create_api_detail_page.on_create_success = None
        self.stack.setCurrentWidget(self.create_api_detail_page)

    def _show_view_api_detail_from_testing(self, record: dict, edit_mode: bool = False) -> None:
        self.view_api_detail_page.on_back = self._show_api_testing
        self.view_api_detail_page.on_update_success = None
        self.view_api_detail_page.set_record(record, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_api_detail_page)

    def _show_create_api_validation_from_testing(self) -> None:
        self.create_api_validation_page.on_back = self._show_api_testing
        self.create_api_validation_page.on_create_success = None
        self.stack.setCurrentWidget(self.create_api_validation_page)

    def _show_view_api_validation_from_testing(self, record: dict, edit_mode: bool = False) -> None:
        self.view_api_validation_page.on_back = self._show_api_testing
        self.view_api_validation_page.on_update_success = None
        self.view_api_validation_page.set_record(record, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_api_validation_page)

    def _show_create_project(self) -> None:
        self.create_project_page.on_back = self._show_api_projects
        self.create_project_page.on_create_success = self._refresh_api_user_involved_after_project_change
        self.stack.setCurrentWidget(self.create_project_page)

    def _show_create_user_type(self) -> None:
        self.create_user_type_page.on_back = self._show_api_user_involved
        self.create_user_type_page.on_create_success = None
        self.stack.setCurrentWidget(self.create_user_type_page)

    def _show_view_user_type(self, record: dict, edit_mode: bool = False) -> None:
        """Show the user type view page for a record from the User Involved list."""
        self.view_user_type_page.set_record(record, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_user_type_page)

    def _show_update_project(
        self,
        project: dict,
        edit_mode: bool = False,
        back_target=None,
    ) -> None:
        if back_target is not None:
            self.view_project_page.on_back = back_target
        else:
            self.view_project_page.on_back = self._show_api_projects
        self.view_project_page.set_project(project, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_project_page)

    def _show_view_profile(self) -> None:
        self.stack.setCurrentWidget(self.view_profile_page)

    def _show_about_dialog(self) -> None:
        QMessageBox.information(
            self,
            "About",
            f"MY ETLZONE App\nVersion {APP_VERSION}",
        )

    def _check_for_latest_version(self) -> None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        if not token:
            show_version_check_needs_sign_in(self)
            return
        if self._version_check_thread is not None and self._version_check_thread.isRunning():
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self._version_check_thread = QThread(self)
        self._version_check_worker = _AppVersionCheckWorker(token)
        self._version_check_worker.moveToThread(self._version_check_thread)
        self._version_check_thread.started.connect(self._version_check_worker.run)
        self._version_check_worker.finished.connect(
            self._on_version_check_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        self._version_check_worker.finished.connect(self._version_check_thread.quit)
        self._version_check_thread.finished.connect(self._cleanup_version_check_thread)
        self._version_check_thread.start()

    @Slot()
    def _on_version_check_finished(self, result: object) -> None:
        if not isinstance(result, dict):
            show_version_check_unexpected(self)
            return
        if not result.get("success"):
            show_version_check_error(
                self,
                str(result.get("message") or "Could not check for updates."),
            )
            return
        dl = result.get("downloadUrl")
        dl_str = str(dl).strip() if dl is not None else ""
        msg = str(result.get("message") or "").strip()
        server_ver = result.get("version")
        latest_raw = str(server_ver).strip() if server_ver is not None else ""
        if dl_str:
            checksum = result.get("checksum")
            cs = str(checksum).strip() if checksum is not None else ""
            pkg = str(result.get("packageType") or "setup").strip().lower()
            if pkg != "zip":
                pkg = "setup"
            extra = msg or (
                _UPDATE_HELP_EXTRA_ZIP if pkg == "zip" else _UPDATE_HELP_EXTRA_SETUP
            )
            AutoUpdateDialog(
                self,
                new_version=latest_raw or "?",
                download_url=dl_str,
                checksum=cs or None,
                extra_message=extra,
                update_package=pkg,
                inno_silent_install=pkg != "zip",
            ).exec()
            return
        show_version_check_up_to_date(
            self,
            msg or "You are up to date.",
            current_version=APP_VERSION,
        )

    def _cleanup_version_check_thread(self) -> None:
        QApplication.restoreOverrideCursor()
        if self._version_check_worker is not None:
            self._version_check_worker.deleteLater()
            self._version_check_worker = None
        if self._version_check_thread is not None:
            self._version_check_thread.deleteLater()
            self._version_check_thread = None

    def _handle_sign_out(self) -> None:
        self._reminders_ws.stop()
        if callable(self.on_sign_out):
            self.on_sign_out()
            return
        self.close()
