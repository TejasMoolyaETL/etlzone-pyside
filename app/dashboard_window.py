"""Simple dashboard shown after login."""

from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QThread, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QResizeEvent
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
    CopyApiDevToMgmtPage,
    CreateAPIDetailPage,
    ViewAPIDetailPage,
)
from app.api_dev.api_validations import (
    APIValidationsPage,
    CreateAPIValidationPage,
    ViewAPIValidationPage,
)
from app.api_dev.api_dev_task import (
    APIDevTaskPage,
    CreateAPIDevTaskPage,
    ViewAPIDevTaskPage,
)
from app.api_dev.api_dev_validation_all_in_one import ApiDevAllInOnePage
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
from app.api_management.role_api_assignment_page import RoleApiAssignmentPage
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
from app.etl.connections import EtlConnectionsPage
from app.etl.scan_connection import EtlScanConnectionPage
from app.etl.import_metadata import EtlImportMetadataPage
from app.etl.extraction import EtlExtractionPage
from app.etl.job_logs import EtlJobLogsPage
from app.etl.data_transformation import DataTransformationPage
from app.user_profile.settings_page import SettingsPage
from app.user_management.users.user_list import UsersPage
from app.user_management.user_timepass.user_reset_password import ResetUserPasswordPage
from app.dmt.dmt_category import CategoryListPage, CreateCategoryPage, ViewCategoryPage
from app.dmt.dmt_module import CreateModulePage, ModuleListPage, ViewModulePage
from app.dmt.dmt_object import CreateDmtObjectPage, DmtObjectListPage, ViewDmtObjectPage
from app.dmt.dmt_object_tracker import (
    CreateDmtObjectTrackerPage,
    DmtObjectTrackerListPage,
    ViewDmtObjectTrackerPage,
)
from app.dmt.dmt_issue_tracker import (
    CreateDmtIssueTrackerPage,
    DmtIssueTrackerListPage,
    ViewDmtIssueTrackerPage,
)
from app.dm.dm_user import (
    CreateDmUserPage,
    DmCopyAppUsersPage,
    DmUploadUsersPage,
    DmUserListPage,
    ViewDmUserPage,
)
from app.dmt.dmt_user_module_assignment import (
    CreateDmtUserModuleAssignmentPage,
    DmtUserModuleAssignmentListPage,
    ViewDmtUserModuleAssignmentPage,
)
from app.master_setup import CreateMasterSetupPage, MasterSetupListPage, ViewMasterSetupPage
from app.master_setup_config import (
    CreateMasterSetupConfigPage,
    MasterSetupConfigListPage,
    ViewMasterSetupConfigPage,
)
from app.master_setup_key import (
    CreateMasterSetupKeyPage,
    MasterSetupKeyListPage,
    ViewMasterSetupKeyPage,
)
from app.dm.dm_company import CreateDmCompanyPage, DmCompanyListPage, ViewDmCompanyPage
from app.dm.dm_contact_person import (
    CreateDmContactPersonPage,
    DmContactPersonListPage,
    ViewDmContactPersonPage,
)
from app.dm.dm_company_contact_assignment import (
    CreateDmContactPersonCompanyAssignmentPage,
    DmContactPersonCompanyAssignmentListPage,
    ViewDmContactPersonCompanyAssignmentPage,
)
from app.dm.dm_project import CreateDmProjectPage, DmProjectListPage, ViewDmProjectPage
from app.dm.dm_user_project_mapping import DmUserProjectMappingPage
from app.lead_management.company import CompanyListPage, CreateCompanyPage, ViewCompanyPage
from app.lead_management.contact_person import (
    ContactPersonListPage,
    CreateContactPersonPage,
    ViewContactPersonPage,
)
from app.lead_management.contact_person_company_assignment import (
    ContactPersonCompanyAssignmentListPage,
    CreateContactPersonCompanyAssignmentPage,
    ViewContactPersonCompanyAssignmentPage,
)
from app.lead_management.leads import CreateLeadPage, LeadListPage, ViewLeadPage
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
from core.app_branding import apply_window_icon
from core.app_version import APP_VERSION
from core.config import app_updates_websocket_enabled, etl_monitor_websocket_enabled
from core.etl_monitor_ws_client import EtlMonitorWebSocketClient
from core.reminders_ws_client import AppUpdatesWebSocketClient
from core.ws_notification import WsNotificationPayload
from ui.ws_update_banner import WsUpdateBanner
from core.nav_access import build_left_panel_access_state
from core.left_panel_nav_items import (
    DATA_MIGRATION_ADMIN_SUB_OPTIONS,
    DATA_MIGRATION_ONBOARDING_SUB_OPTIONS,
    LEAD_MANAGEMENT_SUB_OPTIONS,
    MASTER_SETUP_CONFIG_ITEM,
    MASTER_SETUP_ITEM,
    MASTER_SETUP_KEY_ITEM,
)
from core.user_context import (
    get_nav_access_steps,
    get_user_email,
    get_user_profile,
    get_user_role,
)
from ui.widgets.app_left_panel import (
    API_MANAGEMENT_SUB_OPTIONS,
    API_SUB_OPTIONS,
    AppLeftPanel,
    OBJECT_TRACKER_SUB_OPTIONS,
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
from ui.form_page_focus import install_form_page_focus_on_all_stack_pages
from ui.theme import Theme
from ui.auto_update_dialog import AutoUpdateDialog
from ui.version_check_dialog import (
    show_version_check_error,
    show_version_check_needs_sign_in,
    show_version_check_unexpected,
    show_version_check_up_to_date,
)

class _AppVersionCheckWorker(QObject):
    finished = Signal(object)

    def __init__(self, token: str) -> None:
        super().__init__()
        self._token = token

    @Slot()
    def run(self) -> None:
        self.finished.emit(api_check_app_version(current_version=APP_VERSION, token=self._token))


def _version_check_banner_payload(result: dict) -> WsNotificationPayload | None:
    """Build WS-style strip content for a version API result; None when no UI is needed (up to date)."""
    if not result.get("success"):
        msg = str(result.get("message") or "Could not check for updates.").strip()
        return WsNotificationPayload(
            window_title="App update",
            header_title="Check for updates",
            headline=msg,
            body="",
            meta=(),
            action_url=None,
            action_label="Open link",
        )
    dl = result.get("downloadUrl")
    dl_str = str(dl).strip() if dl is not None else ""
    msg = str(result.get("message") or "").strip()
    server_ver = result.get("version")
    latest_raw = str(server_ver).strip() if server_ver is not None else ""
    if dl_str.startswith(("http://", "https://")):
        headline = msg or "A new app update is available."
        meta_rows: list[tuple[str, str]] = []
        if latest_raw:
            meta_rows.append(("Version", latest_raw))
        meta_rows.append(("Your version", APP_VERSION))
        return WsNotificationPayload(
            window_title="App update",
            header_title="App update",
            headline=headline,
            body="",
            meta=tuple(meta_rows),
            action_url=dl_str,
            action_label="Install",
        )
    if result.get("needsUpdateNoDownloadUrl"):
        hint = (
            msg
            or f"A newer version ({latest_raw or 'from server'}) is available, "
            "but no download link was provided."
        )
        meta_rows: list[tuple[str, str]] = []
        if latest_raw:
            meta_rows.append(("Version", latest_raw))
        return WsNotificationPayload(
            window_title="App update",
            header_title="App update",
            headline=hint,
            body="",
            meta=tuple(meta_rows),
            action_url=None,
            action_label="Open link",
        )
    return None


def _ws_payload_suggests_app_update(payload: WsNotificationPayload) -> bool:
    """True when the push looks like an app update — use the same banner as post-login (version API)."""
    url = (payload.action_url or "").strip()
    if url.lower().startswith(("http://", "https://")):
        return True
    blob = f"{payload.headline} {payload.body} {payload.header_title} {payload.window_title}".lower()
    if "update" in blob and any(
        x in blob for x in ("app", "version", "etl", "install", "build", "release")
    ):
        return True
    for label, _ in payload.meta:
        if label.lower().replace(" ", "") in ("version", "latestversion", "newversion", "targetversion"):
            return True
    return False


class DashboardWindow(QMainWindow):
    def __init__(self, on_sign_out=None) -> None:
        super().__init__()
        self.setWindowTitle("Etlzone")
        apply_window_icon(self)
        self.resize(1280, 800)
        self.on_sign_out = on_sign_out
        self._version_check_thread: QThread | None = None
        self._version_check_worker: _AppVersionCheckWorker | None = None
        self._version_check_banner_only = False
        self._version_check_wait_cursor = False
        self._reminders_ws = AppUpdatesWebSocketClient(self)
        self._reminders_ws.notification.connect(self._on_ws_notification)
        self._etl_monitor_ws = EtlMonitorWebSocketClient(self)
        self._create_menu_bar()

        root = QWidget()
        self.setCentralWidget(root)
        root_outer = QVBoxLayout(root)
        root_outer.setContentsMargins(0, 0, 0, 0)
        root_outer.setSpacing(0)

        self._ws_update_banner = WsUpdateBanner(self)
        self._ws_update_banner.install_requested.connect(self._check_for_latest_version)

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

        self.etl_connections_page = EtlConnectionsPage()
        self.stack.addWidget(self.etl_connections_page)
        self.etl_scan_connection_page = EtlScanConnectionPage()
        self.stack.addWidget(self.etl_scan_connection_page)
        self.etl_import_metadata_page = EtlImportMetadataPage()
        self.stack.addWidget(self.etl_import_metadata_page)
        self.etl_extraction_page = EtlExtractionPage()
        self.stack.addWidget(self.etl_extraction_page)
        self.etl_job_logs_page = EtlJobLogsPage(monitor_ws=self._etl_monitor_ws)
        self.stack.addWidget(self.etl_job_logs_page)
        self.etl_data_transformation_page = DataTransformationPage()
        self.stack.addWidget(self.etl_data_transformation_page)
        self._etl_pages: dict[str, QWidget] = {
            "Connections": self.etl_connections_page,
            "Scan": self.etl_scan_connection_page,
            "Import Metadata": self.etl_import_metadata_page,
            "Extraction": self.etl_extraction_page,
            "Job Logs": self.etl_job_logs_page,
        }
        self._data_transformation_pages: dict[str, QWidget] = {
            "DT: Object": self.etl_data_transformation_page,
            "DT: Job": self.etl_data_transformation_page,
            "DT: Flow": self.etl_data_transformation_page,
            "DT: Work Flow": self.etl_data_transformation_page,
            "DT: Step": self.etl_data_transformation_page,
        }

        self.create_category_page = CreateCategoryPage(
            on_back=self._show_object_tracker_category,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_category_page)
        self.view_category_page = ViewCategoryPage(
            on_back=self._show_object_tracker_category,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_category_page)
        self.create_module_page = CreateModulePage(
            on_back=self._show_object_tracker_module,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_module_page)
        self.view_module_page = ViewModulePage(
            on_back=self._show_object_tracker_module,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_module_page)

        self.create_dmt_object_page = CreateDmtObjectPage(
            on_back=self._show_object_tracker_object,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_dmt_object_page)
        self.view_dmt_object_page = ViewDmtObjectPage(
            on_back=self._show_object_tracker_object,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_dmt_object_page)
        self.create_dmt_object_tracker_page = CreateDmtObjectTrackerPage(
            on_back=self._show_object_tracker_list_tracker,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_dmt_object_tracker_page)
        self.view_dmt_object_tracker_page = ViewDmtObjectTrackerPage(
            on_back=self._show_object_tracker_list_tracker,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_dmt_object_tracker_page)
        self.create_dmt_issue_tracker_page = CreateDmtIssueTrackerPage(
            on_back=self._show_issue_tracker_list,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_dmt_issue_tracker_page)
        self.view_dmt_issue_tracker_page = ViewDmtIssueTrackerPage(
            on_back=self._show_issue_tracker_list,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_dmt_issue_tracker_page)
        self.create_dm_user_page = CreateDmUserPage(
            on_back=self._show_dm_user,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_dm_user_page)
        self.view_dm_user_page = ViewDmUserPage(
            on_back=self._show_dm_user,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_dm_user_page)
        self.dm_copy_app_users_page = DmCopyAppUsersPage(on_back=self._show_dm_user)
        self.stack.addWidget(self.dm_copy_app_users_page)
        self.dm_upload_users_page = DmUploadUsersPage(on_back=self._show_dm_user)
        self.stack.addWidget(self.dm_upload_users_page)
        self.create_dmt_user_module_assignment_page = CreateDmtUserModuleAssignmentPage(
            on_back=self._show_dmt_user_module_assignment,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_dmt_user_module_assignment_page)
        self.view_dmt_user_module_assignment_page = ViewDmtUserModuleAssignmentPage(
            on_back=self._show_dmt_user_module_assignment,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_dmt_user_module_assignment_page)
        self.create_master_setup_page = CreateMasterSetupPage(
            on_back=self._show_master_setup,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_master_setup_page)
        self.view_master_setup_page = ViewMasterSetupPage(
            on_back=self._show_master_setup,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_master_setup_page)
        self.create_master_setup_config_page = CreateMasterSetupConfigPage(
            on_back=self._show_master_setup_config,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_master_setup_config_page)
        self.view_master_setup_config_page = ViewMasterSetupConfigPage(
            on_back=self._show_master_setup_config,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_master_setup_config_page)
        self.create_master_setup_key_page = CreateMasterSetupKeyPage(
            on_back=self._show_master_setup_key,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_master_setup_key_page)
        self.view_master_setup_key_page = ViewMasterSetupKeyPage(
            on_back=self._show_master_setup_key,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_master_setup_key_page)
        self.create_company_page = CreateCompanyPage(
            on_back=self._show_lead_company,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_company_page)
        self.view_company_page = ViewCompanyPage(
            on_back=self._show_lead_company,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_company_page)
        self.create_dm_company_page = CreateDmCompanyPage(
            on_back=self._show_dm_company,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_dm_company_page)
        self.view_dm_company_page = ViewDmCompanyPage(
            on_back=self._show_dm_company,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_dm_company_page)
        self.create_dm_contact_person_page = CreateDmContactPersonPage(
            on_back=self._show_dm_contact_person,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_dm_contact_person_page)
        self.view_dm_contact_person_page = ViewDmContactPersonPage(
            on_back=self._show_dm_contact_person,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_dm_contact_person_page)
        self.create_dm_contact_person_company_assignment_page = CreateDmContactPersonCompanyAssignmentPage(
            on_back=self._show_dm_contact_person_company_assignment,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_dm_contact_person_company_assignment_page)
        self.view_dm_contact_person_company_assignment_page = ViewDmContactPersonCompanyAssignmentPage(
            on_back=self._show_dm_contact_person_company_assignment,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_dm_contact_person_company_assignment_page)
        self.create_dm_project_page = CreateDmProjectPage(
            on_back=self._show_dm_project,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_dm_project_page)
        self.view_dm_project_page = ViewDmProjectPage(
            on_back=self._show_dm_project,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_dm_project_page)
        self.create_contact_person_page = CreateContactPersonPage(
            on_back=self._show_lead_contact_person,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_contact_person_page)
        self.view_contact_person_page = ViewContactPersonPage(
            on_back=self._show_lead_contact_person,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_contact_person_page)
        self.create_contact_person_company_assignment_page = CreateContactPersonCompanyAssignmentPage(
            on_back=self._show_lead_contact_person_company_assignment,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_contact_person_company_assignment_page)
        self.view_contact_person_company_assignment_page = ViewContactPersonCompanyAssignmentPage(
            on_back=self._show_lead_contact_person_company_assignment,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_contact_person_company_assignment_page)
        self.create_lead_page = CreateLeadPage(
            on_back=self._show_leads,
            on_create_success=None,
        )
        self.stack.addWidget(self.create_lead_page)
        self.view_lead_page = ViewLeadPage(
            on_back=self._show_leads,
            on_update_success=None,
        )
        self.stack.addWidget(self.view_lead_page)

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

        self.copy_api_dev_to_mgmt_page = CopyApiDevToMgmtPage(
            on_back=self._show_api_details,
        )
        self.stack.addWidget(self.copy_api_dev_to_mgmt_page)

        # Create API Validation page (API: Validations)
        self.create_api_validation_page = CreateAPIValidationPage()
        self.stack.addWidget(self.create_api_validation_page)

        # View API Validation page (API: Validations)
        self.view_api_validation_page = ViewAPIValidationPage(
            on_back=self._show_api_validations,
            on_update_success=lambda: None,
        )
        self.stack.addWidget(self.view_api_validation_page)

        # Create/View API Task pages (API: Tasks)
        self.create_api_dev_task_page = CreateAPIDevTaskPage()
        self.stack.addWidget(self.create_api_dev_task_page)
        self.view_api_dev_task_page = ViewAPIDevTaskPage(
            on_back=self._show_api_dev_tasks,
            on_update_success=lambda: None,
        )
        self.stack.addWidget(self.view_api_dev_task_page)

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

        self._api_mgmt_pages = {}
        for name in API_MANAGEMENT_SUB_OPTIONS:
            if name == "API: App Id":
                page = ApiAppIdListPage()
            elif name == "API: List":
                page = ApiRegistryListPage()
            elif name == "API: API-Role Assignment":
                page = ApiRoleAssignmentPage()
            elif name == "API: Role-API Assignment":
                page = RoleApiAssignmentPage()
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
                    on_copy_to_mgmt_clicked=self._show_copy_api_dev_to_mgmt,
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
            elif name == "API: Tasks":
                page = APIDevTaskPage(
                    on_create_clicked=self._show_create_api_dev_task,
                    on_edit_clicked=lambda r, e: self._show_view_api_dev_task(r, e),
                )
                self.create_api_dev_task_page.on_back = self._show_api_dev_tasks
                self.create_api_dev_task_page.on_create_success = None
                self.view_api_dev_task_page.on_update_success = None
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

        # Data Migration sub-option pages (onboarding + admin)
        self._data_migration_pages: dict[str, QWidget] = {}

        def _register_data_migration_page(name: str, page: QWidget) -> None:
            self.stack.addWidget(page)
            self._data_migration_pages[name] = page

        for name in DATA_MIGRATION_ONBOARDING_SUB_OPTIONS:
            if name == "DM: Company":
                page = DmCompanyListPage(
                    on_create_clicked=self._show_create_dm_company,
                    on_edit_clicked=lambda c, e: self._show_view_dm_company(c, e),
                )
                self.create_dm_company_page.on_create_success = None
                self.view_dm_company_page.on_update_success = None
                _register_data_migration_page(name, page)
            elif name == "DM: Contact Person":
                page = DmContactPersonListPage(
                    on_create_clicked=self._show_create_dm_contact_person,
                    on_edit_clicked=lambda rec, e: self._show_view_dm_contact_person(rec, e),
                )
                self.create_dm_contact_person_page.on_create_success = None
                self.view_dm_contact_person_page.on_update_success = None
                _register_data_migration_page(name, page)
            elif name == "DM: Company Contact Assignment":
                page = DmContactPersonCompanyAssignmentListPage(
                    on_create_clicked=self._show_create_dm_contact_person_company_assignment,
                    on_edit_clicked=lambda rec, e: self._show_view_dm_contact_person_company_assignment(rec, e),
                )
                self.create_dm_contact_person_company_assignment_page.on_create_success = None
                self.view_dm_contact_person_company_assignment_page.on_update_success = None
                _register_data_migration_page(name, page)
            elif name == "DM: Project":
                page = DmProjectListPage(
                    on_create_clicked=self._show_create_dm_project,
                    on_edit_clicked=lambda rec, e: self._show_view_dm_project(rec, e),
                )
                self.create_dm_project_page.on_create_success = None
                self.view_dm_project_page.on_update_success = None
                _register_data_migration_page(name, page)
            else:
                _register_data_migration_page(name, self._make_placeholder_page(name))

        for name in DATA_MIGRATION_ADMIN_SUB_OPTIONS:
            if name == "DM: User":
                page = DmUserListPage(
                    on_create_clicked=self._show_create_dm_user,
                    on_edit_clicked=lambda user, e: self._show_view_dm_user(user, e),
                    on_copy_app_users_clicked=self._show_copy_dm_app_users,
                    on_upload_users_clicked=self._show_upload_dm_users,
                )
                self.create_dm_user_page.on_create_success = None
                self.view_dm_user_page.on_update_success = None
                _register_data_migration_page(name, page)
            elif name == "DM: User Project Mapping":
                page = DmUserProjectMappingPage()
                _register_data_migration_page(name, page)
            else:
                _register_data_migration_page(name, self._make_placeholder_page(name))

        # DMT Tracker sub-option pages
        self._object_tracker_pages: dict[str, QWidget] = {}
        for name in OBJECT_TRACKER_SUB_OPTIONS:
            if name == "DMT - Category":
                page = CategoryListPage(
                    on_create_clicked=self._show_create_category,
                    on_edit_clicked=lambda c, e: self._show_view_category(c, e),
                )
                # List pages auto-load on `showEvent`; avoid double GETs after create/update.
                self.create_category_page.on_create_success = None
                self.view_category_page.on_update_success = None
            elif name == "DMT - Module":
                page = ModuleListPage(
                    on_create_clicked=self._show_create_module,
                    on_edit_clicked=lambda m, e: self._show_view_module(m, e),
                )
                # List pages auto-load on `showEvent`; avoid double GETs after create/update.
                self.create_module_page.on_create_success = None
                self.view_module_page.on_update_success = None
            elif name == "DMT - Object":
                page = DmtObjectListPage(
                    on_create_clicked=self._show_create_dmt_object,
                    on_edit_clicked=lambda o, e: self._show_view_dmt_object(o, e),
                )
                # List pages auto-load on `showEvent`; avoid double GETs after create/update.
                self.create_dmt_object_page.on_create_success = None
                self.view_dmt_object_page.on_update_success = None
            elif name == "DMT - Object List Tracker":
                page = DmtObjectTrackerListPage(
                    on_create_clicked=self._show_create_dmt_object_tracker,
                    on_edit_clicked=lambda rec, e: self._show_view_dmt_object_tracker(rec, e),
                )
                # List pages auto-load on `showEvent`; avoid double GETs after create/update.
                self.create_dmt_object_tracker_page.on_create_success = None
                self.view_dmt_object_tracker_page.on_update_success = None
            elif name == "DMT - Issue Tracker":
                page = DmtIssueTrackerListPage(
                    on_create_clicked=self._show_create_dmt_issue_tracker,
                    on_edit_clicked=lambda rec, e: self._show_view_dmt_issue_tracker(rec, e),
                )
                self.create_dmt_issue_tracker_page.on_create_success = None
                self.view_dmt_issue_tracker_page.on_update_success = None
            elif name == "DMT: User Module Assignment":
                page = DmtUserModuleAssignmentListPage(
                    on_create_clicked=self._show_create_dmt_user_module_assignment,
                    on_edit_clicked=lambda rec, e: self._show_view_dmt_user_module_assignment(rec, e),
                )
                self.create_dmt_user_module_assignment_page.on_create_success = None
                self.view_dmt_user_module_assignment_page.on_update_success = None
            elif name == MASTER_SETUP_ITEM:
                page = MasterSetupListPage()
            else:
                page = self._make_placeholder_page(name)
            self.stack.addWidget(page)
            self._object_tracker_pages[name] = page

        self.master_setup_page = MasterSetupListPage(
            on_create_clicked=self._show_create_master_setup,
            on_edit_clicked=lambda r, e: self._show_view_master_setup(r, e),
        )
        # Master setup list pages auto-load on `showEvent`; avoid double GETs after create/update.
        self.create_master_setup_page.on_create_success = None
        self.view_master_setup_page.on_update_success = None
        self.stack.addWidget(self.master_setup_page)
        self.master_setup_config_page = MasterSetupConfigListPage(
            on_create_clicked=self._show_create_master_setup_config,
            on_edit_clicked=lambda r, e: self._show_view_master_setup_config(r, e),
        )
        # Master setup config list pages auto-load on `showEvent`; avoid double GETs after create/update.
        self.create_master_setup_config_page.on_create_success = None
        self.view_master_setup_config_page.on_update_success = None
        self.stack.addWidget(self.master_setup_config_page)
        self.master_setup_key_page = MasterSetupKeyListPage(
            on_create_clicked=self._show_create_master_setup_key,
            on_edit_clicked=lambda r, e: self._show_view_master_setup_key(r, e),
        )
        self.create_master_setup_key_page.on_create_success = self._on_master_setup_key_data_changed
        self.view_master_setup_key_page.on_update_success = self._on_master_setup_key_data_changed
        self.stack.addWidget(self.master_setup_key_page)

        self._lead_management_pages: dict[str, QWidget] = {}
        for name in LEAD_MANAGEMENT_SUB_OPTIONS:
            if name == "Lead: Company":
                page = CompanyListPage(
                    on_create_clicked=self._show_create_company,
                    on_edit_clicked=lambda company, e: self._show_view_company(company, e),
                )
                # Lead list pages auto-load on `showEvent`; avoid double GETs after create/update.
                self.create_company_page.on_create_success = None
                self.view_company_page.on_update_success = None
            elif name == "Lead: Contact Person":
                page = ContactPersonListPage(
                    on_create_clicked=self._show_create_contact_person,
                    on_edit_clicked=lambda rec, e: self._show_view_contact_person(rec, e),
                )
                # Lead list pages auto-load on `showEvent`; avoid double GETs after create/update.
                self.create_contact_person_page.on_create_success = None
                self.view_contact_person_page.on_update_success = None
            elif name == "Lead: Company Contact Assignment":
                page = ContactPersonCompanyAssignmentListPage(
                    on_create_clicked=self._show_create_contact_person_company_assignment,
                    on_edit_clicked=lambda rec, e: self._show_view_contact_person_company_assignment(rec, e),
                )
                # Lead list pages auto-load on `showEvent`; avoid double GETs after create/update.
                self.create_contact_person_company_assignment_page.on_create_success = None
                self.view_contact_person_company_assignment_page.on_update_success = None
            elif name == "Leads":
                page = LeadListPage(
                    on_create_clicked=self._show_create_lead,
                    on_edit_clicked=lambda rec, e: self._show_view_lead(rec, e),
                )
                # Lead list pages auto-load on `showEvent`; avoid double GETs after create/update.
                self.create_lead_page.on_create_success = None
                self.view_lead_page.on_update_success = None
            else:
                page = self._make_placeholder_page(name)
            self._lead_management_pages[name] = page
            self.stack.addWidget(page)

        root_layout.addWidget(self.stack, 1)
        install_form_page_focus_on_all_stack_pages(self.stack)
        root_outer.addWidget(content_row, 1)
        self.left_panel.set_current_item("Dashboard")
        # WebSocket + floating notification bar only after sign-in (this window is post-login).
        # Help → Check for update uses the same session and is only available here.
        if app_updates_websocket_enabled():
            self._reminders_ws.start()
        if etl_monitor_websocket_enabled():
            self._etl_monitor_ws.start()
        # Silent API check after sign-in: show the WS-style strip only when there is news (no modal).
        QTimer.singleShot(0, self._run_post_login_version_banner_check)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._ws_update_banner.isVisible():
            self._ws_update_banner.position_overlay()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._reminders_ws.stop()
        self._etl_monitor_ws.stop()
        super().closeEvent(event)

    @Slot(WsNotificationPayload)
    def _on_ws_notification(self, payload: WsNotificationPayload) -> None:
        # Match post-login strip: same copy and meta from GET app/version (not raw WS parsing).
        if _ws_payload_suggests_app_update(payload):
            self._check_for_latest_version(banner_only=True)
            return
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
        current = self.stack.currentWidget()
        if (
            current is self.etl_extraction_page
            and item_name != "Extraction"
            and not self.etl_extraction_page.confirm_leave_unsaved_columns()
        ):
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
        elif item_name in self._etl_pages:
            w = self._etl_pages[item_name]
            self.stack.setCurrentWidget(w)
            # ETL list pages reload in ``showEvent``; avoid duplicate GETs here.
            self.left_panel.set_current_item(item_name)
        elif item_name in self._data_transformation_pages:
            self.stack.setCurrentWidget(self.etl_data_transformation_page)
            self.etl_data_transformation_page.go_to_nav_item(item_name)
            self.left_panel.set_current_item(item_name)
        elif item_name == MASTER_SETUP_ITEM:
            self.stack.setCurrentWidget(self.master_setup_page)
            self.left_panel.set_current_item(MASTER_SETUP_ITEM)
        elif item_name == MASTER_SETUP_CONFIG_ITEM:
            self.stack.setCurrentWidget(self.master_setup_config_page)
            self.left_panel.set_current_item(MASTER_SETUP_CONFIG_ITEM)
        elif item_name == MASTER_SETUP_KEY_ITEM:
            self.stack.setCurrentWidget(self.master_setup_key_page)
            # Master Setup Key list reloads in ``showEvent``; avoid duplicate GETs here.
            self.left_panel.set_current_item(MASTER_SETUP_KEY_ITEM)
        elif item_name in self._lead_management_pages:
            w = self._lead_management_pages[item_name]
            self.stack.setCurrentWidget(w)
            # Lead list pages reload in ``showEvent``; avoid duplicate GETs here.
            self.left_panel.set_current_item(item_name)
        elif item_name in self._data_migration_pages:
            w = self._data_migration_pages[item_name]
            self.stack.setCurrentWidget(w)
            # DM list pages reload in ``showEvent``; avoid duplicate GETs here.
            self.left_panel.set_current_item(item_name)
        elif item_name in self._object_tracker_pages:
            self.stack.setCurrentWidget(self._object_tracker_pages[item_name])
            self.left_panel.set_current_item(item_name)
        elif item_name == "View Profile":
            self.stack.setCurrentWidget(self.view_profile_page)
            self.left_panel.set_current_item("View Profile")
        elif item_name == "Settings":
            self.stack.setCurrentWidget(self.settings_page)
            self.left_panel.set_current_item("Settings")
        elif item_name in self._org_pages:
            self.stack.setCurrentWidget(self._org_pages[item_name])
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
        # Create API Task page - form modified
        if self.stack.currentWidget() is self.create_api_dev_task_page:
            if self.create_api_dev_task_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_api_dev_task_page.reset_to_default()
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
        # View API Task page - edit mode
        if self.stack.currentWidget() is self.view_api_dev_task_page:
            if not self.view_api_dev_task_page.is_edit_mode():
                return True
            if not self.view_api_dev_task_page._has_unsaved_changes():
                return True
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Discard and leave?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Discard:
                self.view_api_dev_task_page._handle_cancel()
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
        # View Category page - edit mode
        if self.stack.currentWidget() is self.view_category_page:
            if self.view_category_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_category_page._handle_cancel()
                    return True
                return False
            return True
        # View Module page - edit mode
        if self.stack.currentWidget() is self.view_module_page:
            if self.view_module_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_module_page._handle_cancel()
                    return True
                return False
            return True
        # Create DMT Object page - form modified
        if self.stack.currentWidget() is self.create_dmt_object_page:
            if self.create_dmt_object_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_dmt_object_page.reset_to_default()
                    return True
                return False
            return True
        # View DMT Object page - edit mode
        if self.stack.currentWidget() is self.view_dmt_object_page:
            if self.view_dmt_object_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_dmt_object_page._handle_cancel()
                    return True
                return False
            return True
        # Create DMT Object Tracker page - form modified
        if self.stack.currentWidget() is self.create_dmt_object_tracker_page:
            if self.create_dmt_object_tracker_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_dmt_object_tracker_page.reset_to_default()
                    return True
                return False
            return True
        # View DMT Object Tracker page - edit mode
        if self.stack.currentWidget() is self.view_dmt_object_tracker_page:
            if self.view_dmt_object_tracker_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_dmt_object_tracker_page._handle_cancel()
                    return True
                return False
            return True
        # Create DMT Issue Tracker page - form modified
        if self.stack.currentWidget() is self.create_dmt_issue_tracker_page:
            if self.create_dmt_issue_tracker_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_dmt_issue_tracker_page.reset_to_default()
                    return True
                return False
            return True
        # View DMT Issue Tracker page - edit mode
        if self.stack.currentWidget() is self.view_dmt_issue_tracker_page:
            if self.view_dmt_issue_tracker_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_dmt_issue_tracker_page._handle_cancel()
                    return True
                return False
            return True
        # Create DMT User page - form modified
        if self.stack.currentWidget() is self.create_dm_user_page:
            if self.create_dm_user_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_dm_user_page.reset_to_default()
                    return True
                return False
            return True
        # View DMT User page - edit mode
        if self.stack.currentWidget() is self.view_dm_user_page:
            if self.view_dm_user_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_dm_user_page._handle_cancel()
                    return True
                return False
            return True
        if self.stack.currentWidget() is self.create_dmt_user_module_assignment_page:
            if self.create_dmt_user_module_assignment_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_dmt_user_module_assignment_page.reset_to_default()
                    return True
                return False
            return True
        if self.stack.currentWidget() is self.view_dmt_user_module_assignment_page:
            if self.view_dmt_user_module_assignment_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_dmt_user_module_assignment_page._handle_cancel()
                    return True
                return False
            return True
        # Create DM Company page - form modified
        if self.stack.currentWidget() is self.create_dm_company_page:
            if self.create_dm_company_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_dm_company_page.reset_to_default()
                    return True
                return False
            return True
        # View DM Company page - edit mode
        if self.stack.currentWidget() is self.view_dm_company_page:
            if self.view_dm_company_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_dm_company_page._handle_cancel()
                    return True
                return False
            return True
        # Create DM Contact Person page - form modified
        if self.stack.currentWidget() is self.create_dm_contact_person_page:
            if self.create_dm_contact_person_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_dm_contact_person_page.reset_to_default()
                    return True
                return False
            return True
        # View DM Contact Person page - edit mode
        if self.stack.currentWidget() is self.view_dm_contact_person_page:
            if self.view_dm_contact_person_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_dm_contact_person_page._handle_cancel()
                    return True
                return False
            return True
        if self.stack.currentWidget() is self.create_dm_contact_person_company_assignment_page:
            if self.create_dm_contact_person_company_assignment_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_dm_contact_person_company_assignment_page.reset_to_default()
                    return True
                return False
            return True
        if self.stack.currentWidget() is self.view_dm_contact_person_company_assignment_page:
            if self.view_dm_contact_person_company_assignment_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_dm_contact_person_company_assignment_page._handle_cancel()
                    return True
                return False
            return True
        if self.stack.currentWidget() is self.create_dm_project_page:
            if self.create_dm_project_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_dm_project_page.reset_to_default()
                    return True
                return False
            return True
        if self.stack.currentWidget() is self.view_dm_project_page:
            if self.view_dm_project_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_dm_project_page._handle_cancel()
                    return True
                return False
            return True
        # Create Company page - form modified
        if self.stack.currentWidget() is self.create_company_page:
            if self.create_company_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_company_page.reset_to_default()
                    return True
                return False
            return True
        # View Company page - edit mode
        if self.stack.currentWidget() is self.view_company_page:
            if self.view_company_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_company_page._handle_cancel()
                    return True
                return False
            return True
        if self.stack.currentWidget() is self.create_contact_person_page:
            if self.create_contact_person_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_contact_person_page.reset_to_default()
                    return True
                return False
            return True
        if self.stack.currentWidget() is self.view_contact_person_page:
            if self.view_contact_person_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_contact_person_page._handle_cancel()
                    return True
                return False
            return True
        if self.stack.currentWidget() is self.create_contact_person_company_assignment_page:
            if self.create_contact_person_company_assignment_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_contact_person_company_assignment_page.reset_to_default()
                    return True
                return False
            return True
        if self.stack.currentWidget() is self.view_contact_person_company_assignment_page:
            if self.view_contact_person_company_assignment_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_contact_person_company_assignment_page._handle_cancel()
                    return True
                return False
            return True
        # Create Master Setup page - form modified
        if self.stack.currentWidget() is self.create_master_setup_page:
            if self.create_master_setup_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_master_setup_page.reset_to_default()
                    return True
                return False
            return True
        # View Master Setup page - edit mode
        if self.stack.currentWidget() is self.view_master_setup_page:
            if self.view_master_setup_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_master_setup_page._handle_cancel()
                    return True
                return False
            return True
        # Create Master Setup Config page - form modified
        if self.stack.currentWidget() is self.create_master_setup_config_page:
            if self.create_master_setup_config_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_master_setup_config_page.reset_to_default()
                    return True
                return False
            return True
        # View Master Setup Config page - edit mode
        if self.stack.currentWidget() is self.view_master_setup_config_page:
            if self.view_master_setup_config_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_master_setup_config_page._handle_cancel()
                    return True
                return False
            return True
        if self.stack.currentWidget() is self.create_master_setup_key_page:
            if self.create_master_setup_key_page.is_dirty():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.create_master_setup_key_page.reset_to_default()
                    return True
                return False
            return True
        if self.stack.currentWidget() is self.view_master_setup_key_page:
            if self.view_master_setup_key_page.is_edit_mode():
                reply = QMessageBox.question(
                    self,
                    "Unsaved Changes",
                    "You have unsaved changes. Discard and leave?",
                    QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Discard:
                    self.view_master_setup_key_page._handle_cancel()
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

    def _show_copy_api_dev_to_mgmt(self) -> None:
        self.stack.setCurrentWidget(self.copy_api_dev_to_mgmt_page)

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

    def _show_api_dev_tasks(self) -> None:
        self.stack.setCurrentWidget(self._api_pages["API: Tasks"])

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

    def _show_create_api_dev_task(self) -> None:
        self.create_api_dev_task_page.on_back = self._show_api_dev_tasks
        self.create_api_dev_task_page.on_create_success = None
        self.stack.setCurrentWidget(self.create_api_dev_task_page)

    def _show_view_api_dev_task(self, record: dict, edit_mode: bool = False) -> None:
        self.view_api_dev_task_page.on_back = self._show_api_dev_tasks
        self.view_api_dev_task_page.on_update_success = None
        self.view_api_dev_task_page.set_task(record, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_api_dev_task_page)

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

    def _show_object_tracker_category(self) -> None:
        self.stack.setCurrentWidget(self._object_tracker_pages["DMT - Category"])

    def _show_create_category(self) -> None:
        self.stack.setCurrentWidget(self.create_category_page)

    def _show_view_category(self, category: dict, edit_mode: bool = False) -> None:
        self.view_category_page.set_category(category, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_category_page)

    def _show_object_tracker_module(self) -> None:
        self.stack.setCurrentWidget(self._object_tracker_pages["DMT - Module"])

    def _show_create_module(self) -> None:
        self.stack.setCurrentWidget(self.create_module_page)

    def _show_view_module(self, module: dict, edit_mode: bool = False) -> None:
        self.view_module_page.set_module(module, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_module_page)

    def _show_object_tracker_object(self) -> None:
        self.stack.setCurrentWidget(self._object_tracker_pages["DMT - Object"])

    def _show_create_dmt_object(self) -> None:
        self.stack.setCurrentWidget(self.create_dmt_object_page)

    def _show_view_dmt_object(self, obj: dict, edit_mode: bool = False) -> None:
        self.view_dmt_object_page.set_object(obj, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_dmt_object_page)

    def _show_object_tracker_list_tracker(self) -> None:
        self.stack.setCurrentWidget(self._object_tracker_pages["DMT - Object List Tracker"])

    def _show_create_dmt_object_tracker(self) -> None:
        self.stack.setCurrentWidget(self.create_dmt_object_tracker_page)

    def _show_view_dmt_object_tracker(self, rec: dict, edit_mode: bool = False) -> None:
        self.view_dmt_object_tracker_page.set_record(rec, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_dmt_object_tracker_page)

    def _show_issue_tracker_list(self) -> None:
        w = self._object_tracker_pages["DMT - Issue Tracker"]
        self.stack.setCurrentWidget(w)

    def _show_create_dmt_issue_tracker(self) -> None:
        self.stack.setCurrentWidget(self.create_dmt_issue_tracker_page)

    def _show_view_dmt_issue_tracker(self, rec: dict, edit_mode: bool = False) -> None:
        self.view_dmt_issue_tracker_page.set_record(rec, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_dmt_issue_tracker_page)

    def _show_dm_project(self) -> None:
        w = self._data_migration_pages["DM: Project"]
        self.stack.setCurrentWidget(w)

    def _show_create_dm_project(self) -> None:
        self.stack.setCurrentWidget(self.create_dm_project_page)

    def _show_view_dm_project(self, project: dict, edit_mode: bool = False) -> None:
        self.view_dm_project_page.set_project(project, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_dm_project_page)

    def _show_dm_user(self) -> None:
        w = self._data_migration_pages["DM: User"]
        self.stack.setCurrentWidget(w)

    def _show_copy_dm_app_users(self) -> None:
        self.stack.setCurrentWidget(self.dm_copy_app_users_page)

    def _show_upload_dm_users(self) -> None:
        self.stack.setCurrentWidget(self.dm_upload_users_page)

    def _show_create_dm_user(self) -> None:
        self.stack.setCurrentWidget(self.create_dm_user_page)

    def _show_dmt_user_module_assignment(self) -> None:
        w = self._object_tracker_pages["DMT: User Module Assignment"]
        self.stack.setCurrentWidget(w)

    def _show_create_dmt_user_module_assignment(self, prefill: dict | None = None) -> None:
        self.create_dmt_user_module_assignment_page.set_prefill(prefill)
        self.stack.setCurrentWidget(self.create_dmt_user_module_assignment_page)

    def _show_view_dmt_user_module_assignment(self, rec: dict, edit_mode: bool = False) -> None:
        self.view_dmt_user_module_assignment_page.set_assignment(rec, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_dmt_user_module_assignment_page)

    def _show_view_dm_user(self, user: dict, edit_mode: bool = False) -> None:
        self.view_dm_user_page.set_user(user, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_dm_user_page)

    def _show_master_setup(self) -> None:
        self.stack.setCurrentWidget(self.master_setup_page)

    def _show_master_setup_key(self) -> None:
        self.stack.setCurrentWidget(self.master_setup_key_page)

    def _on_master_setup_key_data_changed(self) -> None:
        """Refresh Master Setup Key list and Create Master Setup Value category combo."""
        self.master_setup_key_page.refresh()
        self.create_master_setup_page.refresh_categories()

    def _show_create_master_setup_key(self) -> None:
        self.stack.setCurrentWidget(self.create_master_setup_key_page)

    def _show_view_master_setup_key(self, record: dict, edit_mode: bool = False) -> None:
        self.view_master_setup_key_page.set_record(record, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_master_setup_key_page)

    def _show_master_setup_config(self) -> None:
        self.stack.setCurrentWidget(self.master_setup_config_page)

    def _show_lead_company(self) -> None:
        w = self._lead_management_pages["Lead: Company"]
        self.stack.setCurrentWidget(w)

    def _show_dm_company(self) -> None:
        w = self._data_migration_pages["DM: Company"]
        self.stack.setCurrentWidget(w)

    def _show_create_dm_company(self) -> None:
        self.stack.setCurrentWidget(self.create_dm_company_page)

    def _show_view_dm_company(self, company: dict, edit_mode: bool = False) -> None:
        self.view_dm_company_page.set_company(company, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_dm_company_page)

    def _show_dm_contact_person(self) -> None:
        w = self._data_migration_pages["DM: Contact Person"]
        self.stack.setCurrentWidget(w)

    def _show_create_dm_contact_person(self) -> None:
        self.stack.setCurrentWidget(self.create_dm_contact_person_page)

    def _show_view_dm_contact_person(self, rec: dict, edit_mode: bool = False) -> None:
        self.view_dm_contact_person_page.set_contact_person(rec, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_dm_contact_person_page)

    def _show_dm_contact_person_company_assignment(self) -> None:
        w = self._data_migration_pages["DM: Company Contact Assignment"]
        self.stack.setCurrentWidget(w)

    def _show_create_dm_contact_person_company_assignment(self, prefill: dict | None = None) -> None:
        self.create_dm_contact_person_company_assignment_page.set_prefill(prefill)
        self.stack.setCurrentWidget(self.create_dm_contact_person_company_assignment_page)

    def _show_view_dm_contact_person_company_assignment(self, rec: dict, edit_mode: bool = False) -> None:
        self.view_dm_contact_person_company_assignment_page.set_assignment(rec, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_dm_contact_person_company_assignment_page)

    def _show_create_company(self) -> None:
        self.stack.setCurrentWidget(self.create_company_page)

    def _show_view_company(self, company: dict, edit_mode: bool = False) -> None:
        self.view_company_page.set_company(company, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_company_page)

    def _show_lead_contact_person(self) -> None:
        w = self._lead_management_pages["Lead: Contact Person"]
        self.stack.setCurrentWidget(w)

    def _show_create_contact_person(self) -> None:
        self.stack.setCurrentWidget(self.create_contact_person_page)

    def _show_view_contact_person(self, rec: dict, edit_mode: bool = False) -> None:
        self.view_contact_person_page.set_contact_person(rec, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_contact_person_page)

    def _show_lead_contact_person_company_assignment(self) -> None:
        w = self._lead_management_pages["Lead: Company Contact Assignment"]
        self.stack.setCurrentWidget(w)

    def _show_leads(self) -> None:
        w = self._lead_management_pages["Leads"]
        self.stack.setCurrentWidget(w)

    def _show_create_lead(self) -> None:
        self.stack.setCurrentWidget(self.create_lead_page)

    def _show_view_lead(self, rec: dict, edit_mode: bool = False) -> None:
        self.view_lead_page.set_lead(rec, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_lead_page)

    def _show_create_contact_person_company_assignment(self, prefill: dict | None = None) -> None:
        self.create_contact_person_company_assignment_page.set_prefill(prefill)
        self.stack.setCurrentWidget(self.create_contact_person_company_assignment_page)

    def _show_view_contact_person_company_assignment(self, rec: dict, edit_mode: bool = False) -> None:
        self.view_contact_person_company_assignment_page.set_assignment(rec, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_contact_person_company_assignment_page)

    def _show_create_master_setup(self) -> None:
        self.stack.setCurrentWidget(self.create_master_setup_page)

    def _show_view_master_setup(self, record: dict, edit_mode: bool = False) -> None:
        self.view_master_setup_page.set_record(record, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_master_setup_page)

    def _show_create_master_setup_config(self) -> None:
        self.stack.setCurrentWidget(self.create_master_setup_config_page)

    def _show_view_master_setup_config(self, record: dict, edit_mode: bool = False) -> None:
        self.view_master_setup_config_page.set_record(record, edit_mode=edit_mode)
        self.stack.setCurrentWidget(self.view_master_setup_config_page)

    def _show_about_dialog(self) -> None:
        QMessageBox.information(
            self,
            "About",
            f"MY ETLZONE App\nVersion {APP_VERSION}",
        )

    def _run_post_login_version_banner_check(self) -> None:
        self._check_for_latest_version(banner_only=True)

    def _check_for_latest_version(self, _menu_checked: bool = False, *, banner_only: bool = False) -> None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        if not token:
            if not banner_only:
                show_version_check_needs_sign_in(self)
            return
        if self._version_check_thread is not None and self._version_check_thread.isRunning():
            return
        self._version_check_banner_only = banner_only
        self._version_check_wait_cursor = not banner_only
        if self._version_check_wait_cursor:
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
        banner_only = self._version_check_banner_only
        self._version_check_banner_only = False
        if banner_only:
            if isinstance(result, dict):
                payload = _version_check_banner_payload(result)
            else:
                payload = WsNotificationPayload(
                    window_title="App update",
                    header_title="Check for updates",
                    headline="Unexpected response while checking for updates.",
                    body="",
                    meta=(),
                    action_url=None,
                    action_label="Open link",
                )
            if payload is not None:
                self._ws_update_banner.show_payload(payload)
            return
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
            if pkg not in ("zip", "dmg"):
                pkg = "setup"
            AutoUpdateDialog(
                self,
                new_version=latest_raw or "?",
                download_url=dl_str,
                checksum=cs or None,
                extra_message="",
                update_package=pkg,
                inno_silent_install=(pkg == "setup"),
            ).exec()
            return
        if result.get("needsUpdateNoDownloadUrl"):
            hint = (
                msg
                or f"A newer version ({latest_raw or 'from server'}) is available, "
                "but the response did not include a download URL. "
                "Ensure the API returns downloadUrl or downloadWindowsUrl "
                "(or nest those fields under data / result)."
            )
            show_version_check_error(self, hint)
            return
        show_version_check_up_to_date(
            self,
            msg or "You are up to date.",
            current_version=APP_VERSION,
        )

    def _cleanup_version_check_thread(self) -> None:
        if self._version_check_wait_cursor:
            QApplication.restoreOverrideCursor()
            self._version_check_wait_cursor = False
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
