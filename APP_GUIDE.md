# ETL App – File-by-File Guide & Removal Suggestions

This document explains what each part of the app does and what you can safely remove or simplify if you want to trim the codebase.

---

## 1. App flow (high level)

```
main() → run_app() (login_window) → Login → DashboardWindow
         ↓
    Left panel: Dashboard | DB Design Project | User Management (Users, Reset Pwd, User Access) | API (Projects, User Involved, Details, Validations) | View Profile | Settings | Sign Out
         ↓
    Stack: one of many pages (dashboard, users list, create user, view user, API projects, create project, API user type, API details, API validations, profile, settings, placeholders, etc.)
```

---

## 2. Root

### `main.py`
- **Purpose:** Entry point. Calls `run_app()` from `app.login_window`.
- **Lines:** `main()` and `if __name__ == "__main__": main()`.
- **Remove?** No. Required.

---

## 3. `core/` – Backend config, API, session, preferences

### `core/config.py`
- **Purpose:** Single place for API base URL and endpoint paths (env overrides supported).
- **Key:** `API_BASE_URL`, `LOGIN_URL`, `UPDATE_PROFILE_PATH`, `UPDATE_USER_PATH`, `DELETE_USER_PATH`, `DELETE_API_DETAIL_PATH`, `DELETE_API_VALIDATION_PATH`.
- **Remove?** No. Keep; change only if you drop an API.

### `core/api.py`
- **Purpose:** All HTTP calls to the backend (login, profile, users, projects, API details, API validations, timezone, change password).
- **Structure:** Helpers (`_api_url`, `_http_get_json`, `_http_post_json`, etc.), then one function per API (e.g. `api_login`, `api_get_all_users`, `api_create_project`).
- **Remove?** Do not delete the file. You can remove individual `api_*` functions only if you also remove every screen and flow that calls them (see dashboard and app pages).

### `core/user_context.py`
- **Purpose:** In-memory session: current user type, email, and full profile (set after login, read by dashboard and pages).
- **Remove?** No. Required for post-login behavior.

### `core/app_preferences.py`
- **Purpose:** Persisted preferences (e.g. timezone), IANA timezone list, and date/time formatting helpers (`format_datetime`, `DATE_KEYS`).
- **Remove?** You can remove or shorten the hardcoded `_IANA_TIMEZONES` list if you always use `zoneinfo.available_timezones()`. Rest is used by Settings and formatting.

---

## 4. `ui/` – Shared UI building blocks and styles

### `ui/styles.py`
- **Purpose:** Shared colors, typography, and `PANEL_STYLESHEET` for the left panel.
- **Remove?** No. Used by multiple app and panel widgets.

### `ui/widgets/__init__.py`
- **Purpose:** Package marker (can be empty).
- **Remove?** Keep for package.

### `ui/widgets/app_left_panel.py`
- **Purpose:** Left sidebar: title (username + role), pin button, nav items (Dashboard, DB Design Project), collapsible “User Management” and “API” sections, bottom items (View Profile, Settings, Sign Out). Emits `navigation_requested(item_name)` and `pin_toggled(checked)`.
- **Key constants:** `DEFAULT_PANEL_ITEMS`, `USER_MANAGEMENT_SUB_OPTIONS`, `API_SUB_OPTIONS`, `DEFAULT_PANEL_BOTTOM_ITEMS`. Changing these changes what appears in the menu.
- **Remove?** No. You can simplify by removing menu items you don’t use (and their pages in `dashboard_window`).

### `ui/widgets/password_edit.py`
- **Purpose:** Password line edit with show/hide toggle (used on login and change-password).
- **Remove?** No. Used by login and settings.

---

## 5. `app/` – Windows and pages

### `app/login_window.py`
- **Purpose:** Login screen: image, username, password, Sign in; calls `api_login`, stores profile/role via `set_user_profile` / `set_user_type` / `set_user_email`, then opens `DashboardWindow`. Optional dev auto-reload.
- **Remove?** No. You can remove the left image or auto-reload if you don’t need them.

### `app/dashboard_window.py`
- **Purpose:** Main window after login. Builds left side (panel + toggle bar), creates every page widget, adds them to a `QStackedWidget`, wires navigation from the left panel to `_handle_left_navigation`, and handles panel show/hide and pin. Also “unsaved changes” confirmations for create forms and Back from view pages.
- **Remove?** No. To simplify: remove a feature by (1) removing the corresponding item from `USER_MANAGEMENT_SUB_OPTIONS` or `API_SUB_OPTIONS` or panel items in `app_left_panel.py`, (2) removing the page creation and wiring for that item here (and the corresponding app page file if nothing else uses it).

### `app/profile_view.py`
- **Purpose:** View/edit profile (from `get_user_profile()`), save via `api_update_profile`. Shows audit fields only for SADMIN.
- **Remove?** Only if you remove “View Profile” from the panel and from `dashboard_window`.

### `app/settings_page.py`
- **Purpose:** Settings UI: timezone selector (saved via `api_update_user_timezone` and local prefs), and “Change password” dialog (calls `api_change_password`).
- **Remove?** Only if you remove “Settings” from the panel and dashboard.

### `app/user_list.py`
- **Purpose:** Users list (from `api_get_all_users`), Create / Edit, delete; navigates to create user or view user.
- **Remove?** Only if you remove “Users” under User Management and all create/view user flows.

### `app/user_create.py`
- **Purpose:** Create-user form; calls `api_create_user`. Role dropdown USER/PADMIN/SADMIN.
- **Remove?** Only if you remove user creation from the app (and the “Create” path from `user_list` and dashboard).

### `app/user_view.py`
- **Purpose:** View/edit single user; calls `api_update_user`.
- **Remove?** Only if you remove “Edit” from users list and the corresponding navigation in dashboard.

### `app/db_design_project_page.py`
- **Purpose:** DB Design Project page: draggable table shapes on a canvas, mock table definitions (no backend).
- **Remove?** Safe to remove if you don’t need this feature: remove “DB Design Project” from panel items and the widget from `dashboard_window`; you can delete this file.

### `app/api_project_list.py`
- **Purpose:** API projects list (from `api_get_all_projects`), Create / Edit, delete.
- **Remove?** Only if you remove “API: Projects” and all API project flows.

### `app/api_project_create.py`
- **Purpose:** Create API project form; calls `api_create_project`.
- **Remove?** Only if you remove create-project from API projects flow.

### `app/api_project_view.py`
- **Purpose:** View/edit single API project; calls `api_update_project`, `api_delete_project`.
- **Remove?** Only if you remove “Edit” for API projects.

### `app/api_userType_list.py`
- **Purpose:** “API: User Involved” list (user types in projects from `api_get_all_user_type_in_api_project`); Create / Edit / Delete.
- **Remove?** Only if you remove “API: User Involved” and related create/view pages.

### `app/api_userType_create.py`
- **Purpose:** Create user type in API project; calls `api_create_user_type_in_api_project`.
- **Remove?** Only if you remove “API: User Involved” create flow.

### `app/api_userType_view.py`
- **Purpose:** View/edit user type in API project; calls `api_update_user_type_in_api_project_by_id`.
- **Remove?** Only if you remove “API: User Involved” edit flow.

### `app/api_details_list.py`
- **Purpose:** “API: Details (Old)” list; from `api_get_all_api_details`; Create / Edit / Delete.
- **Remove?** Only if you remove “API: Details (Old)” and related create/view.

### `app/api_details_create.py`
- **Purpose:** Create API detail form; calls `api_create_api_detail`.
- **Remove?** Only if you remove API details create flow.

### `app/api_details_view.py`
- **Purpose:** View/edit API detail; calls `api_update_api_detail_by_id`, `api_delete_api_detail_by_id`.
- **Remove?** Only if you remove API details edit flow.

### `app/api_validations_list.py`
- **Purpose:** “API: Validations (Old)” list; from `api_get_all_api_validations`; Create / Edit / Delete.
- **Remove?** Only if you remove “API: Validations (Old)” and related create/view.

### `app/api_validations_create.py`
- **Purpose:** Create API validation form; calls `api_create_api_validation`.
- **Remove?** Only if you remove API validations create flow.

### `app/api_validations_view.py`
- **Purpose:** View/edit API validation; calls `api_update_api_validation_by_id`.
- **Remove?** Only if you remove API validations edit flow.

### `app/api_testing_page.py`
- **Purpose:** “API: Details” page (testing UI): combine details + validations; add/edit detail and add/edit validation.
- **Remove?** Only if you remove “API: Details” from the API sub-options and its wiring in dashboard.

---

## 6. `dev/` – Development tools

### `dev/__init__.py`
- **Purpose:** Package marker.
- **Remove?** Optional; keep if you use `dev.auto_reload`.

### `dev/auto_reload.py`
- **Purpose:** Watches Python files and restarts the app on change (for development). Used only when `login_window` imports it and `ETL_DISABLE_AUTORELOAD` is not set.
- **Remove?** Safe to remove for production or if you don’t want auto-reload: set `ETL_DISABLE_AUTORELOAD=1` or remove the `_enable_auto_reload` block in `login_window.py` and you can delete this file.

---

## 7. What you can remove (summary)

| Goal | What to do |
|------|------------|
| Remove DB Design Project | Remove from `DEFAULT_PANEL_ITEMS` in `app_left_panel.py`; remove `db_design_project_page` creation and navigation in `dashboard_window.py`; delete `app/db_design_project_page.py`. |
| Remove “Reset User Password” / “User Access Control” | Remove those strings from `USER_MANAGEMENT_SUB_OPTIONS` in `app_left_panel.py`; in `dashboard_window.py` they already use placeholder pages—no extra file to delete. |
| Remove “API: Details (Old)” or “API: Validations (Old)” | Remove that item from `API_SUB_OPTIONS`; remove the corresponding page creation and wiring in `dashboard_window.py`; you can delete the corresponding list/create/view files if nothing else references them. |
| Remove “API: Details” (testing page) | Remove “API: Details” from `API_SUB_OPTIONS`; remove `APITestingPage` and its wiring in `dashboard_window.py`; delete `app/api_testing_page.py`. |
| Remove “API: User Involved” | Remove from `API_SUB_OPTIONS`; remove API user type list/create/view pages and wiring; delete `api_userType_list.py`, `api_userType_create.py`, `api_userType_view.py`; remove or stub the related `api_*` functions in `core/api.py` if no other caller remains. |
| Remove Users / Create User / View User | Remove “Users” from `USER_MANAGEMENT_SUB_OPTIONS`; remove users list, create user, view user pages and wiring; delete `user_list.py`, `user_create.py`, `user_view.py`; remove or stub user-management APIs in `core/api.py` if unused. |
| Remove View Profile or Settings | Remove from `DEFAULT_PANEL_BOTTOM_ITEMS` and from navigation in `dashboard_window.py`; delete `profile_view.py` or `settings_page.py` if fully unused. |
| Disable dev auto-reload | Use `ETL_DISABLE_AUTORELOAD=1` or remove the auto-reload block in `login_window.py`; optionally delete `dev/auto_reload.py`. |

---

## 8. Dependency order (for safe removal)

- **Do not remove:** `main.py`, `core/config.py`, `core/user_context.py`, `app/login_window.py`, `app/dashboard_window.py`, `ui/widgets/app_left_panel.py`, `ui/styles.py`, `ui/widgets/password_edit.py`.
- **API layer:** Before removing an `api_*` function, ensure no app page or other code calls it (search for the function name).
- **Panel items:** Each panel item (Dashboard, DB Design Project, Users, View Profile, Settings, API: Projects, etc.) is wired in `dashboard_window.py`. Remove the item from the panel first, then remove the page creation and the page class/file.

Use this guide to understand each file and to remove only the parts you don’t need while keeping the rest of the app working.
