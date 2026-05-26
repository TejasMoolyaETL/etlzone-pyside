from pathlib import Path

p = Path(__file__).resolve().parents[1] / "app/dmt/dmt_user_module_assignment/user_module_assignment_page.py"
t = p.read_text(encoding="utf-8")
repl = [
    ('Role-API Assignment page: left all APIs, right APIs assigned to selected role.',
     'DMT User-Module assignment: left all modules, right modules assigned to selected DMT user.'),
    ("from core.api import (\n    api_change_status_multiple_api_by_role_id,\n    api_get_all_apis,\n    api_get_all_roles,\n    api_get_api_access_by_role_id,\n    api_grant_multiple_api_access,\n    api_remove_multiple_api_by_role_id,\n)",
     "from core.api import (\n    api_assign_dmt_user_modules,\n    api_change_dmt_user_module_status_by_id,\n    api_get_all_dmt_users,\n    api_get_all_modules,\n    api_get_dmt_user_module_assignments_by_user_id,\n    api_remove_dmt_user_module_assignments,\n)"),
    ("_API_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (\n    (\"API Id\", (\"apiId\", \"api_id\", \"id\")),\n    (\"Name\", (\"apiName\", \"api_name\", \"name\", \"title\")),\n    (\"Method\", (\"httpMethod\", \"http_method\", \"method\", \"verb\")),\n    (\"Endpoint\", (\"apiEndpoint\", \"api_endpoint\", \"endpoint\", \"path\", \"urlPath\", \"url_path\", \"url\", \"uri\")),\n    (\"App Id\", (\"appId\", \"app_id\", \"appIdVal\", \"app_id_val\")),\n    (\"App Desc\", (\"appDesc\", \"app_desc\", \"appDescription\", \"app_description\", \"description\", \"desc\")),\n    (\"Created By\", (\"createdBy\", \"created_by\")),\n    (\"Created At\", (\"createdAt\", \"created_at\")),\n    (\"Modified By\", (\"modifiedBy\", \"modified_by\")),\n    (\"Modified At\", (\"modifiedAt\", \"modified_at\", \"updatedAt\", \"updated_at\")),\n)",
     "_MODULE_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (\n    (\"Module Id\", (\"moduleId\", \"id\")),\n    (\"Module Name\", (\"moduleName\", \"name\")),\n    (\"Status\", (\"status\", \"statusName\", \"statusLabel\", \"dmt_module_status\")),\n    (\"Created By\", (\"createdBy\", \"created_by\")),\n    (\"Created At\", (\"createdAt\", \"created_at\")),\n    (\"Modified By\", (\"modifiedBy\", \"modified_by\")),\n    (\"Modified At\", (\"modifiedAt\", \"modified_at\")),\n)"),
    ("_ROLE_API_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (\n    (\"API Id\", (\"apiId\", \"api_id\")),\n    (\"API Assign Id\", (\"apiAssignId\", \"api_assign_id\", \"assignId\", \"assign_id\")),\n    (\"API Name\", (\"apiName\", \"api_name\", \"name\", \"title\")),\n    (\n        \"API Endpoint\",\n        (\n            \"apiEndPoint\",\n            \"apiEndpoint\",\n            \"api_endpoint\",\n            \"endpoint\",\n            \"path\",\n            \"urlPath\",\n            \"url_path\",\n            \"url\",\n            \"uri\",\n        ),\n    ),\n    (\"Status\", (\"status\",)),\n)",
     "_USER_MODULE_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (\n    (\"Assignment Id\", (\"id\", \"assignmentId\", \"userModuleId\", \"userModuleAssignmentId\")),\n    (\"Module Id\", (\"moduleId\", \"module_id\")),\n    (\"Module Name\", (\"moduleName\", \"module_name\", \"name\")),\n    (\"Status\", (\"status\", \"statusName\", \"statusLabel\")),\n)"),
]
# class and symbol renames (order matters - longer first)
renames = [
    ("RoleApiAssignmentPage", "DmtUserModuleAssignmentPage"),
    ("_RoleApiAccessStatusDialog", "_UserModuleStatusDialog"),
    ("_normalize_role_api_row", "_normalize_user_module_row"),
    ("api_change_status_multiple_api_by_role_id", "api_change_dmt_user_module_status_by_id"),
    ("api_get_api_access_by_role_id", "api_get_dmt_user_module_assignments_by_user_id"),
    ("api_remove_multiple_api_by_role_id", "api_remove_dmt_user_module_assignments"),
    ("api_grant_multiple_api_access", "api_assign_dmt_user_modules"),
    ("api_get_all_roles", "api_get_all_dmt_users"),
    ("api_get_all_apis", "api_get_all_modules"),
    ("_ROLE_API_COLUMNS", "_USER_MODULE_COLUMNS"),
    ("_API_COLUMNS", "_MODULE_COLUMNS"),
    ("_assigned_api_keys_for_role", "_assigned_module_keys_for_user"),
    ("_checked_api_ids_for_role_deactivate", "_checked_assignment_ids_for_status"),
    ("_checked_assignment_ids_for_role_remove", "_checked_module_ids_for_remove"),
    ("_assign_selected_apis_to_role", "_assign_selected_modules_to_user"),
    ("_deactivate_selected_assignments", "_change_status_selected_assignments"),
    ("_api_id_from_role_api_row", "_module_id_from_user_module_row"),
    ("_assign_id_from_role_api_row", "_assign_id_from_user_module_row"),
    ("_selected_left_api_ids", "_selected_left_module_ids"),
    ("_apply_role_api_column_filters_refresh", "_apply_user_module_column_filters_refresh"),
    ("_schedule_role_api_filter_apply", "_schedule_user_module_filter_apply"),
    ("_filtered_role_api_rows", "_filtered_user_module_rows"),
    ("_write_role_api_rows", "_write_user_module_rows"),
    ("_role_api_data_row_offset", "_user_module_data_row_offset"),
    ("_reset_role_apis_table_columns_plain", "_reset_user_modules_table_columns_plain"),
    ("_on_role_filter_toggled", "_on_user_module_filter_toggled"),
    ("_load_role_apis", "_load_user_modules"),
    ("_on_role_changed", "_on_user_changed"),
    ("_populate_roles", "_populate_users"),
    ("_apply_api_column_filters_refresh", "_apply_module_column_filters_refresh"),
    ("_schedule_api_filter_apply", "_schedule_module_filter_apply"),
    ("_filtered_api_source_rows", "_filtered_module_source_rows"),
    ("_write_api_data_rows", "_write_module_data_rows"),
    ("_api_data_row_offset", "_module_data_row_offset"),
    ("_on_api_filter_toggled", "_on_module_filter_toggled"),
    ("_api_column_spec", "_module_column_spec"),
    ("_role_filter_apply_timer", "_user_module_filter_apply_timer"),
    ("_role_filter_visible", "_user_module_filter_visible"),
    ("_role_filter_btn", "_user_module_filter_btn"),
    ("_role_apis_table", "_user_modules_table"),
    ("_role_api_rows", "_user_module_rows"),
    ("_current_role_id", "_current_user_id"),
    ("_role_combo", "_user_combo"),
    ("_deactivate_assign_btn", "_change_status_btn"),
    ("_roles_msg", "_users_msg"),
    ("_rhs_api_identity", "_rhs_module_identity"),
    ("_lhs_api_identity", "_lhs_module_identity"),
    ("_LoadWorker", "_DmtUserModuleLoadWorker"),
    ("_roles", "_users"),
    ("_apis", "_modules"),
]
for a, b in repl:
    t = t.replace(a, b)
for a, b in renames:
    t = t.replace(a, b)
# title / labels
t = t.replace("API: Role-API Assignment", "DMT: User Module Assignment")
t = t.replace("Select Role", "Select DMT User")
t = t.replace("Loading roles and APIs", "Loading DMT users and modules")
t = t.replace("Failed to load roles.", "Failed to load DMT users.")
t = t.replace("Failed to load APIs.", "Failed to load modules.")
t = t.replace("Loading role APIs", "Loading user modules")
t = t.replace("Failed to load role APIs", "Failed to load user module assignments")
t = t.replace("No APIs assigned to selected role", "No modules assigned to selected user")
t = t.replace("Remove APIs", "Remove modules")
t = t.replace("from this role", "from this user")
t = t.replace("to this role", "to this user")
t = t.replace("Select a role first", "Select a DMT user first")
t = t.replace("at least one API on the left", "at least one module on the left")
t = t.replace("Failed to assign APIs", "Failed to assign modules")
t = t.replace("APIs assigned successfully", "Modules assigned successfully")
t = t.replace("Failed to remove APIs from role", "Failed to remove module assignments")
t = t.replace("API(s) removed from role", "Module assignment(s) removed")
t = t.replace("Already assigned to selected role", "Already assigned to selected user")
t = t.replace("role-driven", "user-driven")
t = t.replace("ACTIVE/INACTIVE", "Change status")
t = t.replace("_deactivate_assign_btn", "_change_status_btn")
p.write_text(t, encoding="utf-8")
print("wrote", p)
