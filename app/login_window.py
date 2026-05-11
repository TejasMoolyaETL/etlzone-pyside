from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path


# def _enable_auto_reload(app):
#     """Enable auto-reload during development if ETL_DISABLE_AUTORELOAD is not set."""
#     if os.getenv("ETL_DISABLE_AUTORELOAD") == "1":
#         return None
#     # Packaged app: never attach file watcher (would look like a full restart on any .py touch).
#     if getattr(sys, "frozen", False) or getattr(sys, "_MEIPASS", None) is not None:
#         return None
#     try:
#         from dev.auto_reload import enable_auto_reload
#         return enable_auto_reload(app)
#     except ImportError:
#         return None

from PySide6.QtCore import QObject, QThread, Qt, QRect, Signal, Slot
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSplashScreen,
    QVBoxLayout,
    QWidget,
)

from app.dashboard_window import DashboardWindow
from core.api import api_get_app_step_list, api_login, api_sign_out, session_has_sadmin_role
from core.nav_access import build_left_panel_access_state
from core.app_branding import (
    app_logo_path,
    app_window_icon,
    apply_window_icon,
    apply_windows_taskbar_app_id,
)
from core.app_version import APP_VERSION
from ui.widgets.password_edit import PasswordLineEdit
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_page_styles import (
    APP_FONT_SIZE_PX,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LINEEDIT_PLACEHOLDER_SUBSTYLE,
    LIST_PAGE_HEADER_BUTTON_FONT_PX,
    LIST_PAGE_HEADER_BUTTON_PADDING_H_PX,
    LIST_PAGE_HEADER_BUTTON_PADDING_V_PX,
    placeholder_enter,
)
from ui.styles import COLOR_ERROR, COLOR_SUCCESS, apply_app_theme
from ui.theme import Theme
from ui.widgets.required_label import field_caption_label
from core.user_context import (
    get_nav_access_steps,
    set_nav_access_steps,
    set_user_email,
    set_user_profile,
    set_user_role,
)


def _token_from_login_result(login_result: dict) -> str | None:
    t = (
        login_result.get("token")
        or login_result.get("accessToken")
        or login_result.get("access_token")
        or login_result.get("jwt")
        or login_result.get("idToken")
        or login_result.get("id_token")
    )
    if t is None:
        return None
    s = str(t).strip()
    return s if s else None


def _login_response_successful(response: object) -> bool:
    """True when api_login (or worker fallback) indicates a successful sign-in."""
    if not isinstance(response, dict):
        return False
    if response.get("success") is True:
        return True
    if response.get("success") is False:
        return False
    s = response.get("success")
    if isinstance(s, str) and s.strip().lower() in ("true", "1", "yes"):
        return True
    st = str(response.get("status") or response.get("Status") or "").strip().upper()
    if st in ("SUCCESS", "OK", "SUCCEEDED"):
        return True
    return bool(_token_from_login_result(response))


def _session_role_string(login_result: dict) -> str:
    """Normalize ``roles`` (list/str) or ``role`` for ``set_user_role`` (expects a string)."""
    dr = login_result.get("defaultRole") or login_result.get("default_role")
    if isinstance(dr, str) and dr.strip():
        return dr.strip()
    r = login_result.get("roles")
    if isinstance(r, list) and r:
        first = r[0]
        if isinstance(first, dict):
            rr = first.get("role") or first.get("roleName") or first.get("name")
            if rr is not None and str(rr).strip():
                return str(rr).strip()
        return str(first).strip()
    if isinstance(r, str) and r.strip():
        return r.strip()
    role_one = login_result.get("role")
    if isinstance(role_one, str) and role_one.strip():
        return role_one.strip()
    return ""


class _LoginThread(QThread):
    """Runs api_login in QThread.run() — reliable on all PySide builds (no moveToThread + started)."""

    login_done = Signal(object)

    def __init__(self, username: str, password: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._username = username
        self._password = password

    def run(self) -> None:
        log = logging.getLogger(__name__)
        log.info("[login] thread: calling api_login")
        try:
            response = api_login(self._username, self._password)
        except Exception as exc:
            log.exception("[login] thread: api_login raised")
            response = {
                "success": False,
                "message": f"Login failed ({type(exc).__name__}). Check your network and try again.",
            }
        accepted = isinstance(response, dict) and response.get("success") is True
        log.info(
            "[login] thread: api_login finished response_is_dict=%s server_accepted_login=%s",
            isinstance(response, dict),
            accepted,
        )
        self.login_done.emit(response)


class _PostLoginNavThread(QThread):
    """Fetches get-app-id-step-id-list in QThread.run(); main thread applies steps to the left panel."""

    steps_ready = Signal(object, int)

    def __init__(self, token: str, attempt_id: int, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._token = token
        self._attempt_id = attempt_id

    def run(self) -> None:
        log = logging.getLogger(__name__)
        log.info("[login] nav thread: calling get-app-id-step-id-list")
        try:
            res = api_get_app_step_list(self._token)
        except Exception:
            log.exception("[login] nav thread: get-app-id-step-id-list raised")
            res = {"success": False, "message": "Request failed.", "steps": []}
        log.info("[login] nav thread: get-app-id-step-id-list finished")
        self.steps_ready.emit(res, self._attempt_id)


class LoginWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Etlzone")
        apply_window_icon(self)
        self.dashboard_window = None
        self._post_login_thread: QThread | None = None
        self._post_login_attempt: int = 0

        self.base_pixmap = self._load_login_image()

        root = QWidget()
        self.setCentralWidget(root)

        main_layout = QHBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet(
            f"background-color: {Theme.BG_LOGIN_IMAGE};"
        )
        self.image_label.setMinimumSize(0, 0)
        self.image_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
        )
        left_layout.addWidget(self.image_label)

        right_container = QWidget()
        right_container.setStyleSheet(
            f"background-color: {Theme.BG_PAGE_ALT};"
        )
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(42, 36, 42, 36)
        right_layout.setSpacing(12)

        _login_subtitle_font_px = 14
        subtitle = QLabel("Sign in to continue")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(
            f"color: {Theme.TEXT_SECONDARY}; font-size: {_login_subtitle_font_px}px; font-weight: 500;"
        )

        _login_field_h = FORM_SINGLELINE_FIELD_HEIGHT_PX
        # Same border, radius, colors, and type size as each other; username padding on the edit,
        # password padding on the inner edit (PasswordLineEdit) so text lines up.
        _login_field_chrome = (
            f"border: 1px solid {Theme.BORDER_INPUT}; border-radius: 6px; "
            f"background-color: {Theme.BG_WHITE}; "
            f"font-size: {APP_FONT_SIZE_PX}px; font-weight: 400; color: {Theme.TEXT_INPUT};"
        )
        _login_password_shell = (
            f"border: 1px solid {Theme.BORDER_INPUT}; border-radius: 6px; "
            f"background-color: {Theme.BG_WHITE};"
        )
        self.username_input = QLineEdit()
        self.username_input.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.username_input.setPlaceholderText(placeholder_enter("username"))
        self.username_input.setText("")
        self.username_input.setFixedHeight(_login_field_h)
        self.username_input.setStyleSheet(
            f"{_login_field_chrome} padding: 2px 8px;" + LINEEDIT_PLACEHOLDER_SUBSTYLE
        )

        self.password_input = PasswordLineEdit(use_default_style=False)
        self.password_input.setPlaceholderText(placeholder_enter("password"))
        self.password_input.setText("")
        self.password_input.setFixedHeight(_login_field_h)
        # Shell only on the wrapper; typography on the inner QLineEdit (matches username QLineEdit).
        self.password_input.setStyleSheet(_login_password_shell)
        self.password_input.set_inner_padding(
            "2px 8px",
            font_size_px=APP_FONT_SIZE_PX,
            color=Theme.TEXT_INPUT,
        )

        form_widget = QWidget()
        form_widget.setObjectName("loginForm")
        form = QFormLayout(form_widget)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFormAlignment(Qt.AlignmentFlag.AlignHCenter)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        _login_lbl = (
            f"color: {Theme.TEXT_MUTED}; font-size: {APP_FONT_SIZE_PX}px; font-weight: 500; min-width: 64px;"
        )
        form.addRow(
            field_caption_label(
                "Username",
                _login_lbl,
                required=True,
                muted_color=Theme.TEXT_MUTED,
                font_size_px=APP_FONT_SIZE_PX,
            ),
            self.username_input,
        )
        form.addRow(
            field_caption_label(
                "Password",
                _login_lbl,
                required=True,
                muted_color=Theme.TEXT_MUTED,
                font_size_px=APP_FONT_SIZE_PX,
            ),
            self.password_input,
        )
        form_widget.setStyleSheet(
            f"#loginForm QLabel {{ color: {Theme.TEXT_MUTED}; font-size: {APP_FONT_SIZE_PX}px; "
            f"font-weight: 500; min-width: 64px; }}"
        )

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )

        self.login_button = QPushButton("Login")
        self.login_button.setDefault(True)
        _tbtn = Theme
        _bfs = LIST_PAGE_HEADER_BUTTON_FONT_PX
        _bpv = LIST_PAGE_HEADER_BUTTON_PADDING_V_PX
        _bph = LIST_PAGE_HEADER_BUTTON_PADDING_H_PX
        self.login_button.setStyleSheet(
            f"QPushButton {{ background: {_tbtn.LOGIN_GRADIENT_END}; color: {_tbtn.PANEL_TEXT_BRIGHT}; border: none; "
            f"border-radius: 6px; padding: {_bpv}px {_bph}px; font-size: {_bfs}px; font-weight: 500; }}"
            f"QPushButton:hover {{ background: {_tbtn.BG_LOGIN_IMAGE}; }}"
            f"QPushButton:pressed {{ background: {_tbtn.LOGIN_GRADIENT_START}; }}"
            f"QPushButton:disabled {{ background: #94a3b8; color: #e2e8f0; }}"
        )
        self.login_button.setFixedWidth(100)
        self.login_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_button.clicked.connect(self.handle_login)

        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("loginClearButton")
        self.clear_button.setProperty("buttonRole", "secondary")
        self.clear_button.setAutoDefault(False)
        self.clear_button.setDefault(False)
        self.clear_button.setFixedWidth(100)
        self.clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_button.setToolTip("Clear username and password")
        self.clear_button.setStyleSheet(
            f"QPushButton {{ background: {Theme.BG_WHITE}; color: {Theme.TEXT_INPUT}; "
            f"border: 1px solid {Theme.BORDER_INPUT}; border-radius: 6px; "
            f"padding: {_bpv}px {_bph}px; font-size: {_bfs}px; font-weight: 500; }}"
            f"QPushButton:hover {{ background: {Theme.BG_PAGE_ALT}; border-color: {Theme.TEXT_SECONDARY}; }}"
            f"QPushButton:pressed {{ background: {Theme.BORDER_DEFAULT}; }}"
            f"QPushButton:disabled {{ background: #f1f5f9; color: #94a3b8; border-color: #e2e8f0; }}"
        )
        self.clear_button.clicked.connect(self.handle_clear)

        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda: self.login_button.animateClick())

        button_row = QHBoxLayout()
        button_row.setSpacing(12)
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.addWidget(self.login_button, 0, Qt.AlignmentFlag.AlignVCenter)
        button_row.addWidget(self.clear_button, 0, Qt.AlignmentFlag.AlignVCenter)

        right_layout.addStretch()
        right_layout.addWidget(subtitle)
        right_layout.addSpacing(8)
        right_layout.addWidget(form_widget)
        right_layout.addLayout(button_row)
        right_layout.setAlignment(button_row, Qt.AlignmentFlag.AlignHCenter)
        right_layout.addWidget(self.status_label)
        right_layout.addStretch()

        main_layout.addWidget(left_container, 7)
        main_layout.addWidget(right_container, 3)
        main_layout.setStretch(0, 7)
        main_layout.setStretch(1, 3)

        self._login_in_progress = False
        self._login_thread: QThread | None = None

        self._update_image()

    def _load_login_image(self) -> QPixmap:
        # Optional login background image. Fall back to local file or gradient placeholder.
        image_path = Path(__file__).resolve().parents[1].joinpath("login_image.jpg")

        if os.path.exists(image_path):
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                return pixmap

        placeholder = QPixmap(1600, 1000)
        gradient = QLinearGradient(0, 0, 1600, 1000)
        gradient.setColorAt(0.0, QColor(Theme.LOGIN_GRADIENT_START))
        gradient.setColorAt(1.0, QColor(Theme.LOGIN_GRADIENT_END))

        painter = QPainter(placeholder)
        painter.fillRect(placeholder.rect(), gradient)
        r = placeholder.rect()
        title = "MY ETLZONE App"
        ver = f"v{APP_VERSION}"
        title_font = QFont("Segoe UI", 40, QFont.Weight.Bold)
        ver_font = QFont("Segoe UI", 12, QFont.Weight.Normal)
        fm_t = QFontMetrics(title_font)
        fm_v = QFontMetrics(ver_font)
        th, vh = fm_t.height(), fm_v.height()
        gap = 12
        cy = r.center().y()
        y_title = cy - (th + gap + vh) // 2
        painter.setFont(title_font)
        painter.setPen(QColor(Theme.PANEL_TEXT_BRIGHT))
        painter.drawText(
            QRect(r.left(), y_title, r.width(), th),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            title,
        )
        painter.setFont(ver_font)
        painter.setPen(QColor("#e2e8f0"))
        painter.drawText(
            QRect(r.left(), y_title + th + gap, r.width(), vh),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            ver,
        )
        painter.end()

        return placeholder

    def _update_image(self) -> None:
        if self.base_pixmap.isNull():
            return
        target_size = self.image_label.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            return
        scaled = self.base_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_image()

    def handle_clear(self) -> None:
        if self._login_in_progress:
            return
        self.username_input.clear()
        self.password_input.clear()
        cancel_auto_hide_message(self, self.status_label)
        self.status_label.setText("")
        self.username_input.setFocus()

    def handle_login(self) -> None:
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not username or not password:
            set_user_role("")
            set_user_email("")
            set_user_profile({})
            self._set_status("Please enter both username and password.", error=True)
            return

        if self._login_in_progress:
            return
        if self._post_login_thread is not None and self._post_login_thread.isRunning():
            self._set_status("Still signing you in. Please wait…", error=False)
            return
        self._login_in_progress = True
        self.login_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self._set_status("Signing in...", error=False)

        # Run login in QThread.run() (reliable); see _LoginThread.
        self._login_thread = _LoginThread(username, password, self)
        self._login_thread.login_done.connect(
            self._on_login_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        self._login_thread.finished.connect(self._cleanup_login_thread)
        self._login_thread.start()

    def _cleanup_login_thread(self) -> None:
        if self._login_thread is not None:
            self._login_thread.deleteLater()
            self._login_thread = None

    def _cleanup_post_login_thread(self) -> None:
        if self._post_login_thread is not None:
            self._post_login_thread.deleteLater()
            self._post_login_thread = None

    def _finalize_login_and_open_dashboard(self) -> None:
        log = logging.getLogger(__name__)
        log.info("[login] main: _finalize_login_and_open_dashboard")
        from core.app_preferences import get_timezone, set_display_timezone

        set_display_timezone("")
        tz = get_timezone()
        set_display_timezone(tz)
        self._open_dashboard_after_workspace_prep()

    @Slot(object, int)
    def _on_post_login_worker_finished(self, step_res: object, attempt_id: int) -> None:
        """Apply get-app-id-step-id-list to left nav (dashboard already open — avoids thread/signal races)."""
        if attempt_id != self._post_login_attempt:
            return
        steps: list = []
        if isinstance(step_res, dict):
            raw = step_res.get("steps")
            if isinstance(raw, list):
                steps = raw
        set_nav_access_steps(steps)
        dw = self.dashboard_window
        if dw is None:
            return
        try:
            dw.left_panel.apply_nav_access_state(
                build_left_panel_access_state(get_nav_access_steps())
            )
        except Exception:
            traceback.print_exc()

    def _on_login_finished(self, response: dict) -> None:
        log = logging.getLogger(__name__)
        log.info("[login] main: _on_login_finished received type=%s", type(response).__name__)
        username = self.username_input.text().strip()

        if not _login_response_successful(response):
            self._login_in_progress = False
            self.login_button.setEnabled(True)
            self.clear_button.setEnabled(True)
            set_user_role("")
            set_user_email("")
            set_user_profile({})
            set_nav_access_steps(None)
            msg = response.get("message", "Invalid username or password.")
            log.info("[login] main: server rejected login — %s", msg)
            self._set_status(
                msg,
                error=True,
                clear_on_user_activity=False,
            )
            return

        set_user_role(_session_role_string(response))
        set_user_email(response.get("email", username))
        set_user_profile(response)

        if session_has_sadmin_role(response):
            log.info("[login] main: SADMIN path → open dashboard")
            self._login_in_progress = False
            set_nav_access_steps(None)
            self._finalize_login_and_open_dashboard()
            return

        tok = _token_from_login_result(response)
        if not tok:
            log.info("[login] main: no JWT → open dashboard (empty nav steps)")
            self._login_in_progress = False
            # No JWT: cannot load get-app-id-step-id-list; treat as no steps so gated menus stay hidden.
            set_nav_access_steps([])
            self._finalize_login_and_open_dashboard()
            return

        # Open dashboard immediately; refresh left nav when get-app-id-step-id-list returns (avoids races
        # where thread.quit / finished ordering prevented the slot from opening the dashboard).
        log.info("[login] main: standard user → open dashboard then get-app-id-step-id-list")
        set_nav_access_steps([])
        self._set_status("Loading workspace…", error=False)
        self._finalize_login_and_open_dashboard()
        self._post_login_attempt += 1
        attempt = self._post_login_attempt
        self._post_login_thread = _PostLoginNavThread(tok, attempt, self)
        self._post_login_thread.steps_ready.connect(
            self._on_post_login_worker_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        self._post_login_thread.finished.connect(self._cleanup_post_login_thread)
        self._post_login_thread.start()

    def _set_status(
        self,
        text: str,
        *,
        error: bool,
        clear_on_user_activity: bool = True,
    ) -> None:
        color = COLOR_ERROR if error else COLOR_SUCCESS
        show_auto_hiding_message(
            self,
            self.status_label,
            text,
            error=error,
            style_sheet=f"color: {color};",
            clear_on_user_activity=clear_on_user_activity,
        )

    def _open_dashboard_after_workspace_prep(self) -> None:
        log = logging.getLogger(__name__)
        if self.dashboard_window is not None:
            log.warning("[login] main: dashboard already exists — skipping open")
            self._login_in_progress = False
            return
        try:
            log.info("[login] main: constructing DashboardWindow…")
            self.dashboard_window = DashboardWindow(on_sign_out=self.handle_sign_out)
            log.info("[login] main: DashboardWindow constructed")
        except Exception as e:
            log.exception("[login] main: DashboardWindow construction failed")
            self._login_in_progress = False
            self.login_button.setEnabled(True)
            self.clear_button.setEnabled(True)
            self._set_status(f"Failed to open dashboard: {e}", error=True)
            return
        self._present_dashboard_after_login()

    def _present_dashboard_after_login(self) -> None:
        log = logging.getLogger(__name__)
        log.info("[login] main: _present_dashboard_after_login")
        dw = self.dashboard_window
        if dw is None:
            log.error("[login] main: dashboard_window is None — cannot show")
            self._login_in_progress = False
            return
        app = QApplication.instance()
        try:
            dw.show()
            dw.showMaximized()
            dw.raise_()
            dw.activateWindow()
            if app is not None:
                app.setActiveWindow(dw)
            self.setVisible(False)
            self.lower()
            if app is not None:
                app.processEvents()
        except Exception:
            logging.getLogger(__name__).exception("present dashboard after login")
            self._login_in_progress = False
            if dw is not None:
                dw.close()
                self.dashboard_window = None
            self.login_button.setEnabled(True)
            self.clear_button.setEnabled(True)
            self.setVisible(True)
            return
        self._login_in_progress = False

    def handle_sign_out(self) -> None:
        api_sign_out()
        set_user_role("")
        set_user_email("")
        set_user_profile({})
        set_nav_access_steps(None)
        from core.app_preferences import set_display_timezone
        set_display_timezone("")
        self.password_input.clear()
        cancel_auto_hide_message(self, self.status_label)
        self.status_label.setText("")
        self.login_button.setEnabled(True)
        self.clear_button.setEnabled(True)
        self.showMaximized()
        self.raise_()
        self.activateWindow()
        if self.dashboard_window is not None:
            self.dashboard_window.close()
            self.dashboard_window = None


def run_app() -> None:
    """Run the application (used by `main.py`)."""
    if not logging.root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    apply_windows_taskbar_app_id()
    app = QApplication(sys.argv)
    _ico = app_window_icon()
    if not _ico.isNull():
        app.setWindowIcon(_ico)
    apply_app_theme(app)
    # reloader = _enable_auto_reload(app)
    # if reloader is not None:
    #     app._reloader = reloader
    splash_pix = QPixmap(520, 320)
    splash_pix.fill(QColor("#0f2340"))
    sp = splash_pix.rect()
    sp_painter = QPainter(splash_pix)
    ver = f"v{APP_VERSION}"
    _lp = app_logo_path()
    if _lp is not None:
        _lg = QPixmap(str(_lp))
        if not _lg.isNull():
            _sc = _lg.scaled(
                400,
                220,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            _x = (sp.width() - _sc.width()) // 2
            _y = (sp.height() - _sc.height()) // 2 - 18
            sp_painter.drawPixmap(_x, max(20, _y), _sc)
            ver_f = QFont("Segoe UI", 11, QFont.Weight.Normal)
            sp_painter.setFont(ver_f)
            sp_painter.setPen(QColor("#e2e8f0"))
            fm_v = QFontMetrics(ver_f)
            vh = fm_v.height()
            sp_painter.drawText(
                QRect(sp.left(), sp.bottom() - vh - 16, sp.width(), vh),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                ver,
            )
            sp_painter.end()
        else:
            _lp = None
    if _lp is None:
        title = "Etlzone"
        title_f = QFont("Segoe UI", 22, QFont.Weight.Bold)
        ver_f = QFont("Segoe UI", 11, QFont.Weight.Normal)
        fm_t = QFontMetrics(title_f)
        fm_v = QFontMetrics(ver_f)
        th, vh = fm_t.height(), fm_v.height()
        gap = 10
        cy = sp.center().y()
        y_title = cy - (th + gap + vh) // 2
        sp_painter.setFont(title_f)
        sp_painter.setPen(QColor("#f1f5f9"))
        sp_painter.drawText(
            QRect(sp.left(), y_title, sp.width(), th),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            title,
        )
        sp_painter.setFont(ver_f)
        sp_painter.setPen(QColor("#e2e8f0"))
        sp_painter.drawText(
            QRect(sp.left(), y_title + th + gap, sp.width(), vh),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            ver,
        )
        sp_painter.end()
    splash = QSplashScreen(splash_pix)
    if not _ico.isNull():
        splash.setWindowIcon(_ico)
    splash.show()
    QApplication.processEvents()
    window = LoginWindow()
    window.showMaximized()
    splash.finish(window)
    sys.exit(app.exec())
