# Line-by-Line Explanation of ETL_App_V2

This document explains each line (or logical block) of the application code in sequence, file by file. The virtual environment (`.venv`) is excluded.

---

## 1. `main.py` — Entry point

| Line(s) | Code | Explanation |
|--------|------|-------------|
| 1 | `"""Project entry point."""` | Module docstring: this file is the application entry point. |
| 3 | `from app.login_window import run_app` | Imports the `run_app` function, which creates the Qt app and shows the login window. |
| 6–7 | `def main() -> None:` / `run_app()` | Defines `main()` and calls `run_app()` to start the GUI. |
| 10–11 | `if __name__ == "__main__":` / `main()` | When the script is run directly (e.g. `python main.py`), calls `main()`; when imported, this block is skipped. |

---

## 2. `core/config.py` — Central configuration

| Line(s) | Code | Explanation |
|--------|------|-------------|
| 1–5 | Docstring | Describes the module: change only `API_BASE_URL` (or env `ETL_API_BASE_URL`) to point to another backend. |
| 7 | `from __future__ import annotations` | Enables postponed evaluation of type hints (strings), avoiding circular imports. |
| 9 | `import os` | For reading environment variables. |
| 12 | `API_BASE_URL = os.getenv(...).rstrip("/")` | Backend base URL from env or default; trailing slash removed. |
| 15 | `LOGIN_URL = f"{API_BASE_URL}/api/auth/login"` | Full URL for login. |
| 18 | `UPDATE_PROFILE_PATH = os.getenv(...)` | Path for profile update; overridable via env. |
| 21–22 | `UPDATE_USER_PATH` / `DELETE_USER_PATH` | Paths for user update and delete (used with `API_BASE_URL`). |
| 24–26 | `DELETE_API_DETAIL_PATH` | Path for deleting an API detail by id. |
| 29–31 | `DELETE_API_VALIDATION_PATH` | Path for deleting an API validation by id. |

---

## 3. `core/user_context.py` — Session / user state

| Line(s) | Code | Explanation |
|--------|------|-------------|
| 1–4 | Docstring, `from __future__`, `typing` | Module for login session state. |
| 7–9 | `current_user_role`, `current_user_email`, `current_user_profile` | Global variables holding the current user's role, email, and full profile from login. |
| 12–14 | `set_user_role(value)` | Sets `current_user_role` (or `""`). |
| 17–18 | `get_user_role()` | Returns current user role. |
| 22–24 | `set_user_email(value)` | Sets `current_user_email`. |
| 27–28 | `get_user_email()` | Returns current user email. |
| 31–34 | `set_user_profile(profile)` | Stores a copy of the profile dict from login. |
| 37–39 | `get_user_profile()` | Returns a copy of the stored profile. |

---

## 4. `core/api.py` — HTTP client and API functions

**Imports and helpers (Lines 1–48)**  
- **1–21:** Docstring; imports `base64`, `json`, `sys`, `time`, `typing`, `urllib.error`, `urllib.request`; imports from `core.config` (`API_BASE_URL`, `LOGIN_URL`, paths for delete/update).  
- **24–44:** `_log_api(...)` — Logs request method, URL, body (passwords redacted), and response to stderr.  
- **47–48:** `_api_url(path)` — Returns `API_BASE_URL` + path, normalizing leading slash.

**HTTP primitives (Lines 51–169)**  
- **51–73:** `_http_get_json` — GET request with JSON Accept and User-Agent; returns parsed JSON or `{}`; logs request/response.  
- **76–97:** `_http_post_json` — POST JSON body; same logging and return convention.  
- **100–121:** `_http_put_json` — PUT JSON; same pattern.  
- **124–141:** `_http_delete` — DELETE with optional headers; returns JSON or `{}`.  
- **144–169:** `_http_delete_json` — DELETE with JSON body; same pattern.

**JWT and error parsing (Lines 172–216)**  
- **172–184:** `_decode_jwt_role(token)` — Splits JWT (header.payload.signature), base64-decodes payload, returns `role` or `userType` or `user_type`.  
- **187–216:** `_extract_error_message(payload, fallback)` — Tries common keys (`message`, `error`, `detail`, etc.) and nested structures; returns first non-empty string or `fallback`.

**Auth and profile (Lines 219–384)**  
- **219–288:** `api_login(user_name, password)` — POST to `LOGIN_URL` with `userName`/`password`; normalizes response to `success`, `role`, `message`; extracts role from payload or JWT; on HTTP/URL/timeout errors returns failure dict.  
- **291–294:** `api_sign_out()` — Short sleep and returns `{"success": True}` (client-side only).  
- **297–317:** `_do_update_profile_request` — Runs POST or PUT for profile update; returns `(payload, None)` or `(None, HTTPError)`.  
- **320–384:** `api_update_profile(profile, token)` — Builds body (email, firstName, lastName, mobileNumber with country code); tries POST then PUT on 403; returns success/error dict.

**Users (Lines 387–733)**  
- **387–419:** `api_get_all_users(token)` — GET `api/get-all-user` with Bearer token; normalizes list or dict response to `{success, data, message}`.  
- **422–451:** `api_get_all_user_type_in_api_project(token)` — GET user types; same response shape.  
- **454–403:** `api_delete_user_type_in_api_project_by_id(internal_id, token)` — DELETE by id.  
- **406–429:** `api_create_user_type_in_api_project(project_id, role, token)` — POST to create role.  
- **432–484:** `api_update_user_type_in_api_project_by_id(internal_id, role, token)` — PUT to update.  
- **487–528:** `api_get_all_projects(token)` — GET projects; normalizes to `{success, data, message}`.  
- **531–598:** `api_create_project(...)` — POST with projectName, projectDesc, etc.; port as int.  
- **601–569:** `api_update_project(project_id, ...)` — PUT update.  
- **572–609:** `api_delete_project(project_id, token)` — DELETE project.  
- **612–673:** `api_create_user(...)` — POST create user with email, password, optional fields.  
- **676–733:** `api_update_user(user_id, ...)` — PUT (or POST on 403) to update user; returns success/error.  
- **736–734:** `api_delete_user(user_id, token)` — DELETE user by id.

**API details and validations (Lines 736–1014)**  
- **736–767:** `api_get_all_api_details(token)` — GET all API details.  
- **770–844:** `api_create_api_detail(project_id, ...)` — POST with folder, apiMethod, apiName, paths, etc.  
- **847–906:** `api_update_api_detail_by_id(api_id, ...)` — PUT update.  
- **909–966:** `api_delete_api_detail_by_id(api_id, token)` — DELETE using `DELETE_API_DETAIL_PATH`.  
- **969–1000:** `api_get_all_api_validations(token)` — GET validations.  
- **1003–908:** `api_create_api_validation(..., api_id, ...)` — POST; `api_id` required.  
- **911–968:** `api_update_api_validation_by_id`, `api_delete_api_validation_by_id` — PUT and DELETE.

**User timezone and password (Lines 1017–1109)**  
- **1017–1068:** `api_update_user_timezone(user_id, timezone, token)` — PUT/POST to update timezone.  
- **1071–1109:** `api_change_password(old_password, new_password, token)` — POST; success when response `status == "SUCCESS"`.

---

## 5. `core/app_preferences.py` — Preferences and timezone

| Line(s) | Code | Explanation |
|--------|------|-------------|
| 1–14 | Docstring, imports, `_OFFSET_FIX`, `_PREFS_FILE`, `_display_timezone` | Regex to fix Java-style timezone offset; path to `.etl_app_prefs.json`; in-memory display timezone. |
| 20–27 | `_load_prefs()` | Reads JSON from prefs file; returns dict or `{}`. |
| 30–36 | `_save_prefs(prefs)` | Writes prefs dict to file. |
| 39–57 | `_IANA_TIMEZONES` | Fallback list of IANA timezone names when `zoneinfo` is unavailable. |
| 60–70 | `get_iana_timezone_list()` | Returns `[""] + sorted(zoneinfo.available_timezones())` or `_IANA_TIMEZONES`. |
| 73–83 | `DATE_KEYS` | Frozenset of key names that should be formatted as datetime (createdAt, updatedAt, etc.). |
| 86–106 | `_get_zoneinfo(tz_id)` | Returns `ZoneInfo(tz_id)` or fixed-offset fallback for common zones on Windows. |
| 109–147 | `get_timezone()` | Returns `_display_timezone` if set; else from user profile (recursive extract); else from prefs file. |
| 150–157 | `set_display_timezone(tz_id)` | Sets global display timezone and saves to prefs. |
| 160–198 | `to_utc_iso(date_str, end_of_day)` | Converts user date/datetime (in user timezone) to UTC ISO string for API. |
| 201–283 | `format_datetime(value)` | Converts backend date/datetime (UTC) to user timezone for display; handles int/float timestamps, ISO strings, Java-style offsets. |

---

## 6. `ui/styles.py` — Shared UI constants

| Line(s) | Code | Explanation |
|--------|------|-------------|
| 1–8 | Docstring, color constants | `COLOR_ERROR`, `COLOR_SUCCESS`, card/activity background and border hex colors. |
| 10–12 | `TITLE_STYLE`, `SUBTITLE_STYLE` | Font size, weight, and color for titles and subtitles. |
| 14–24 | `PANEL_STYLESHEET` | QSS for left panel: dark blue frame, label/button styles (DM_Tool style). |

---

## 7. `dev/__init__.py` and `dev/auto_reload.py`

**`dev/__init__.py`**  
- Single line: docstring "Development utilities (auto-reload, etc.)."

**`dev/auto_reload.py`**  
- **1–11:** Imports; `_SKIP_DIRS = {"__pycache__", ".git", ".venv", ...}`.  
- **14–26:** `DevAutoReloader.__init__` — Stores app and watch dir; creates `QFileSystemWatcher` and single-shot `QTimer` (250 ms); connects timeout to `_restart_app`; adds Python files to watcher; connects `fileChanged` to `_on_file_changed`.  
- **27–36:** `_add_python_files` — Walks directory, skips `_SKIP_DIRS`, adds all `.py` paths to watcher.  
- **37–41:** `_on_file_changed` — Re-adds path if needed and starts restart timer.  
- **42–45:** `_restart_app` — Quits app and `os.execv(sys.executable, [sys.executable, *sys.argv])`.  
- **48–55:** `enable_auto_reload(app)` — If `ETL_DISABLE_AUTORELOAD != "1"`, creates `DevAutoReloader` for project root (parent of `dev/`). |

---

## 8. `ui/widgets/__init__.py` and `ui/widgets/password_edit.py`

**`ui/widgets/__init__.py`**  
- Docstring: "Shared reusable widgets."

**`ui/widgets/password_edit.py`**  
- **1–27:** Imports; `_eye_icon(visible)` — Paints a QPixmap (eye open/closed) and returns QIcon.  
- **30–71:** `PasswordLineEdit` — QWidget with QLineEdit (Password echo) + toggle button; default style; `_toggle_visibility` switches echo mode and icon.  
- **83–117:** Proxies `text`, `setText`, `clear`, `setEchoMode`, `setPlaceholderText`, `set_inner_padding`; `setStyleSheet` wraps selector for `#passwordLineEdit`; `setReadOnly`, `setFocus`; `textChanged` and `editingFinished` exposed as properties.  

---

## 9. `ui/widgets/app_left_panel.py` — Left navigation panel

| Line(s) | Code | Explanation |
|--------|------|-------------|
| 1–19 | Imports, constants | `DEFAULT_PANEL_ITEMS`, `USER_MANAGEMENT_SUB_OPTIONS`, `API_SUB_OPTIONS`, `DEFAULT_PANEL_BOTTOM_ITEMS`. |
| 22–45 | `_CollapsibleWidget` | QWidget with `QPropertyAnimation` on `maximumHeight`; `expand()` / `collapse()` animate height. |
| 48–71 | `AppLeftPanel.__init__` | Fixed width 260; panel QFrame with `PANEL_STYLESHEET`; root and panel layouts. |
| 77–119 | Title frame | Title label + pin button (📌); pin toggled emits `pin_toggled`. |
| 126–163 | Content | Buttons for `_items`; "User Management" toggle + collapsible sub-options; same for "API Management". |
| 195–227 | Bottom items, pin/expand state | Bottom buttons; API and User Management sections expanded by default; `set_pin_checked`. |
| 216–227 | `_on_user_mgmt_toggle`, `_on_api_toggle` | Expand/collapse sub-containers when toggles are checked. |

---

## 10. `app/login_window.py` — Login screen and app startup

| Line(s) | Code | Explanation |
|--------|------|-------------|
| 1–14 | Imports, `_enable_auto_reload(app)` | If `ETL_DISABLE_AUTORELOAD != "1"`, calls `dev.auto_reload.enable_auto_reload(app)`. |
| 16–42 | Qt imports, app imports | LoginWindow, DashboardWindow, PasswordLineEdit, api_login/sign_out, styles, user_context. |
| 46–57 | `LoginWindow.__init__` | Window title "MY ETLZONE App"; `dashboard_window = None`; load login image; central widget and main H layout. |
| 60–76 | Left (image) side | Label for image; dark background; size policy Ignored so it scales. |
| 72–103 | Right (form) side | Subtitle "Sign in to continue"; username QLineEdit; PasswordLineEdit with placeholder and padding; form layout with labels; status label; Login button and Enter shortcut. |
| 134–146 | Layout stretch and split | Left 7, right 3 stretch; `_update_image()`. |
| 148–184 | `_load_login_image`, `_update_image`, `resizeEvent` | Loads `login_image.jpg` or draws gradient placeholder with "MY ETLZONE App"; scales pixmap to label on resize. |
| 189–225 | `handle_login` | Reads username/password; if empty clears user context and shows error; disables button, calls `api_login`; on success sets user type/email/profile, timezone from profile, opens dashboard; on failure clears context and shows message. |
| 227–231 | `_set_status(text, error)` | Sets status label color (red/green) and text. |
| 233–245 | `open_dashboard` | Creates `DashboardWindow(on_sign_out=handle_sign_out, role=...)`, hides login, shows dashboard maximized. |
| 247–259 | `handle_sign_out` | Calls `api_sign_out`, clears user context and timezone, closes dashboard, clears password, shows login maximized. |
| 262–270 | `run_app()` | Creates QApplication, optionally attaches reloader, creates LoginWindow, shows maximized, `sys.exit(app.exec())`. |

---

## 11. `app/dashboard_window.py` — Main window after login

- **1–38:** Imports; `DashboardWindow(QMainWindow)` with title, size, `on_sign_out`, menu bar.  
- **48–122:** Left side: panel visibility state; narrow toggle bar (◀/▶) with same background as panel; `AppLeftPanel` with title from profile (username + role); navigation and pin signals connected; stack for pages.  
- **126–284:** Stack contents: dashboard page (title, subtitle, Sign out); Users, View User, DB Design Project, Create User; Create Project, Create User Type, Create API Detail; View Project, View User Type, View API Detail; Create/View API Validation; View Profile, Settings; then user-management and API sub-pages (Users, API: Projects, API: User Involved, API: Details (Old), API: Validations (Old), API: Details); placeholders for other menu items. Callbacks (`on_back`, `on_create_success`, `on_edit_clicked`, etc.) wired so list pages refresh after create/update.  
- **287–299:** `_make_placeholder_page(title)` — "Coming soon" page.  
- **301–316:** `_handle_left_navigation(item_name)` — If confirm-leave passes, switches stack to Dashboard, user mgmt page, DB Design Project, View Profile, Settings, API page, or triggers Sign Out.  
- **318–337:** `_toggle_left_panel`, `_show_left_panel`, `_on_pin_toggled` — Show/hide panel; when pinned, panel stays visible and hide button disabled.  
- **339–393:** `_confirm_leave_if_unsaved` — For Create User, Create API Detail/Validation, Create User Type, Create Project, and View (API Detail, Validation, User Type, Project, User, Profile) pages, if there are unsaved changes asks "Discard and leave?"; Discard resets or cancels and allows navigation.  
- **395–410:** Menu bar: File (Exit), System (Sign out), Help (About).  
- **412–444:** `_show_dashboard`, `_show_users`, `_show_create_user`, `_show_view_user` — Switch stack to corresponding widget.  
- **446–439:** `_show_api_projects`, `_show_api_user_involved`, `_show_api_details`, `_show_api_validations`, `_show_api_testing` — Switch to API list/testing pages.  
- **414–447:** `_show_create_api_detail`, `_show_view_api_detail`, and same for validation — Set `on_back`/`on_create_success`/`on_update_success` and switch to create or view page.  
- **449–447:** `_show_create_api_detail_from_testing`, `_show_view_api_detail_from_testing`, and validation variants — Back target is API: Details (testing) page; refresh callbacks for details/validations.  
- **449–461:** `_show_create_project`, `_show_create_user_type`, `_show_view_user_type`, `_show_update_project` — Wire back and refresh, set project/user-type record, switch stack.  
- **463–475:** `_show_view_profile`, `_show_about_dialog`, `_handle_sign_out` — Show profile page; About message box; call `on_sign_out` or close. |

---

## 12. `app/settings_page.py` — Settings and change password

- **1–36:** Imports; constants `PAGE_TITLE`, `PAGE_SUBTITLE`, `CARD_STYLE`, `SECTION_LABEL`, `OPTION_ROW`.  
- **39–119:** `ChangePasswordDialog` — Three PasswordLineEdit fields (current, new, confirm); validation (non-empty, length ≥ 6, match); gets token from profile; `api_change_password`; on success shows green message and accepts after 800 ms.  
- **122–318:** `SettingsPage` — Title "Settings"; Account card with "Change Password" button opening dialog; Preferences card: timezone combo (IANA list), theme combo (Light/Dark/System), notifications checkbox; "Save preferences" calls `api_update_user_timezone` if user_id and token exist, then `set_user_profile` and `set_display_timezone`; success/error message with 800 ms clear.  
- **316–324:** `_apply_saved_timezone` — Sets combo from `get_timezone()`; `showEvent` re-applies when page is shown. |

---

## 13. `app/profile_view.py` — View/Edit profile

- **1–28:** Imports; `_NoShadowComboBox` (removes dropdown shadow); `_EMAIL_REGEX`; `_EMAIL_KEYS`, `_MOBILE_KEYS`; `_COUNTRY_CODES`; `_MOBILE_VALIDATION` (min/max length and regex per country).  
- **150–163:** `_validate_mobile(country_code, number)` — Returns (is_valid, error_message).  
- **166–212:** `_COUNTRY_COMBO_STYLESHEET`; `_READONLY_KEYS`, `_READONLY_EDIT_KEYS`, `_HIDDEN_KEYS`, `_AUDIT_KEYS`; `_PROFILE_COL1`, `_PROFILE_COL2`, `_FIELD_GROUPS`, `_LABEL_OVERRIDES`; label/input styles.  
- **255–276:** `_parse_mobile(value)` — Returns (country_code, number).  
- **279–301:** `_format_value`, `_label_for_key`, `_key_variants_for`, `_get_initials`.  
- **309–455:** `ViewProfilePage` — Header with avatar (initials) and title "Profile"; card with grid: two columns of fields from `_PROFILE_COL1`/`_PROFILE_COL2`; mobile as country combo + number; email/mobile validation and styling; Back, Edit, Cancel, Save; stacked display vs edit buttons.  
- **457–541:** `_refresh_values` (sync from profile); `showEvent`; `_handle_back`; `_update_email_style`, `_validate_email_on_blur`; `_update_mobile_style`, `_validate_mobile_on_blur`; `_handle_edit` (enable editable fields, show Save/Cancel); `_handle_save` (build profile from fields, `api_update_profile`, update `set_user_profile`, success then switch to view); `_handle_cancel`; `is_edit_mode`; `_switch_to_view_mode`. |

---

## 14. `app/user_list.py` — Users table

- **1–55:** Imports; `_HIDDEN_KEYS`; `_COLUMN_SPEC` (header name + key variants); `_flatten_user`, `_ordered_keys`, `_format_cell` (dates via `format_datetime`).  
- **84–158:** `UsersPage.__init__`, `_build_ui` — Title row with Refresh and Create; filter toggle button (icon from assets); message label; subtitle; QTableWidget with styling, context menu, double-click; Copy shortcut.  
- **251–275:** `_on_filter_toggled`, `_apply_filter` — Filter row (row 0) with one QLineEdit per column; hide rows that don’t contain filter text.  
- **277–341:** `_get_user_at_row`, `_on_context_menu` (Display/Edit/Delete User), `_on_row_double_clicked`, `_handle_delete_user` (confirm then `api_delete_user`), `_copy_selection` (tab-separated to clipboard).  
- **363–354:** `showEvent` → `_load_users`; `refresh`; `_load_users` (token from profile, `api_get_all_users`, `_populate_table` or `_show_empty_table`).  
- **395–453:** `_populate_table` — Builds columns from `_COLUMN_SPEC` and extra keys; optional filter row; fills table; UserRole on first column stores full user dict. |

---

## 15. `app/user_create.py` — Create user form

- **1–88:** Imports; `_EMAIL_REGEX`; `_COUNTRY_CODES`; `_ROLES`; `_MONTH_NAMES`; `_CALENDAR_STYLE` (QCalendarWidget QSS).  
- **136–223:** `_SimpleDropdown` — Button + QMenu; `selectionChanged` signal; `currentIndex`, `currentData`, `findData`, `blockSignals`.  
- **226–308:** `_DatePickerDialog` — Month/year dropdowns + calendar; `selected_date()`; `_DatePickerEdit` widget with read-only line edit and dialog.  
- **355–364:** `_MOBILE_VALIDATION`, `_validate_mobile`; `_COUNTRY_COMBO_STYLESHEET`; label/input styles; `_NoShadowComboBox`.  
- **384–535:** `CreateUserPage._build_ui` — Header with avatar "+"; card with form: Username (read-only, "(Generated by backend)"), Email*, Password*, First/Last Name, Role, Mobile (country + number), Valid From/To (date pickers), Status; Create User / Cancel.  
- **537–651:** `_set_error`/`_set_success`; `_get_default_values`; `is_dirty()` (compare to defaults); `reset_to_default`; `request_back` (confirm if dirty); `_on_status_changed` (disable Valid From/To when INACTIVE); `_on_role_changed` (confirm SADMIN); `_update_email_style`, `_update_mobile_style`; `_handle_create` (validate email, password length, mobile; `to_utc_iso` for validFrom/validTo; `api_create_user`; on success message and navigate back after 800 ms). |

---

## 16. `app/user_view.py` — View/Edit user (from list)

- **1–244:** Imports; label/input styles; `_EMAIL_REGEX`; `_COUNTRY_CODES`; `_MOBILE_VALIDATION`; `_validate_mobile`; `_COUNTRY_COMBO_STYLESHEET`; `_USER_COL1`/`_USER_COL2`; `_READONLY_KEYS`; `_parse_mobile`; `_get_value`, `_get_initials`; `_NoShadowComboBox`.  
- **291–455:** `ViewUserPage` — Same layout as profile: avatar, title "User", card with two-column grid; Role and Status as combos; mobile as country + number; Valid From/To read-only; Back, Edit, Cancel, Save.  
- **312–318:** `set_user(user, edit_mode)` — Stores user, `_refresh_values`, then edit or view mode.  
- **458–523:** `_handle_edit`, `_handle_cancel`, `_switch_to_view_mode`.  
- **525–512:** `_handle_save` — Validates email and mobile; gets user_id and token; builds validFrom/validTo with `to_utc_iso`; `api_update_user`; updates `self._user` from response; success message, switch to view, call `on_update_success`, clear message after 1500 ms.  

---

## 17. Other app pages (summary)

- **`app/api_project_list.py`**, **`app/api_project_create.py`**, **`app/api_project_view.py`** — List/create/view API projects; same patterns as users (table, form, view/edit with Back/Create/Edit/Save/Cancel and API calls from `core.api`).  
- **`app/api_userType_list.py`**, **`app/api_userType_create.py`**, **`app/api_userType_view.py`** — User types per project (list, create, view/edit).  
- **`app/api_details_list.py`**, **`app/api_details_create.py`**, **`app/api_details_view.py`** — API details (list, create, view/edit).  
- **`app/api_validations_list.py`**, **`app/api_validations_create.py`**, **`app/api_validations_view.py`** — API validations (list, create, view/edit).  
- **`app/api_testing_page.py`** — Combined API: Details page with add/edit detail and add/edit validation; uses same create/view pages with different `on_back`/refresh targets.  
- **`app/db_design_project_page.py`** — DB design canvas: draggable table widgets, relationship arrows, field definitions (column name, type, nullable, PK, default); uses `QGraphicsScene`/`QGraphicsView` and custom MIME for links.  

---

## Flow summary

1. **Start:** `main.py` → `run_app()` in `login_window.py` → `QApplication`, optional auto-reload, `LoginWindow` shown.  
2. **Login:** User enters credentials → `api_login` → on success `set_user_role`/`set_user_email`/`set_user_profile`, timezone from profile → `DashboardWindow` shown, login hidden.  
3. **Dashboard:** Left panel navigates to Dashboard, Users, API (Projects, User Involved, Details, Validations, API: Details), DB Design Project, View Profile, Settings, or Sign Out. Each destination is a widget in a `QStackedWidget`. Create/View pages are separate widgets; list pages have Create/Edit buttons that switch stack and set `on_back`/refresh callbacks.  
4. **Data:** All API calls go through `core.api` with token from `get_user_profile()`. Dates are sent as UTC ISO (`to_utc_iso`) and displayed with `format_datetime` in user timezone from Settings/profile.  
5. **Sign out:** Dashboard calls `on_sign_out` → login’s `handle_sign_out` → clear context, close dashboard, show login.  

This completes the line-by-line (and block-by-block) explanation of the application code.
