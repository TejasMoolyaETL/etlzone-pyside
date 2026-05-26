"""One-off: generate dm_user_project_mapping_page.py from role_api_assignment_page.py."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / "app/api_management/role_api_assignment_page.py").read_text(encoding="utf-8")

repls = [
    (
        "Role-API Assignment page: left all APIs, right APIs assigned to selected role.",
        "DM User Project Mapping: left all users, right users assigned to selected project.",
    ),
    ("RoleApiAssignmentPage", "DmUserProjectMappingPage"),
    ("_RoleApiAccessStatusDialog", "_UserProjectStatusDialog"),
    ("_LoadWorker", "_DmUserProjectLoadWorker"),
    ("API: Role-API Assignment", "DM: User Project Mapping"),
    (
        "Role-driven assignment view. Does not change API: API-Role Assignment behavior.",
        "Project-driven user assignment (DM user–project mapping).",
    ),
    ("_API_COLUMNS", "_USER_COLUMNS"),
    ("_ROLE_API_COLUMNS", "_PROJECT_USER_COLUMNS"),
    ("_normalize_role_api_row", "_normalize_project_user_row"),
    (
        "from core.api import (\n"
        "    api_change_status_multiple_api_by_role_id,\n"
        "    api_get_all_apis,\n"
        "    api_get_all_roles,\n"
        "    api_get_api_access_by_role_id,\n"
        "    api_grant_multiple_api_access,\n"
        "    api_remove_multiple_api_by_role_id,\n"
        ")",
        "from core.api import (\n"
        "    api_assign_dm_users_to_project,\n"
        "    api_change_dm_user_project_status_by_ids,\n"
        "    api_delete_dm_user_projects_by_ids,\n"
        "    api_get_all_dm_projects,\n"
        "    api_get_all_dmt_users,\n"
        "    api_get_dm_users_by_project_id,\n"
        "    api_get_master_key_by_app_id_field_name,\n"
        "    master_key_row_display_label,\n"
        "    master_key_row_seq_value,\n"
        ")",
    ),
    ("_roles: list", "_projects: list"),
    ("_apis: list", "_users: list"),
    ("_role_api_rows", "_project_user_rows"),
    ("_role_apis_table", "_project_users_table"),
    ("_role_combo", "_project_combo"),
    ("_current_role_id", "_current_project_id"),
    ("_assigned_api_keys_for_role", "_assigned_user_keys_for_project"),
    ("_lhs_api_identity", "_lhs_user_identity"),
    ("_rhs_api_identity", "_rhs_user_identity"),
    ("_api_id_from_role_api_row", "_user_id_from_project_user_row"),
    ("_assign_id_from_role_api_row", "_mapping_id_from_project_user_row"),
    ("_load_role_apis", "_load_project_users"),
    ("_populate_roles", "_populate_projects"),
    ("_on_role_changed", "_on_project_changed"),
    ("_role_filter_btn", "_project_user_filter_btn"),
    ("_role_filter_visible", "_project_user_filter_visible"),
    ("_role_filter_apply_timer", "_project_user_filter_apply_timer"),
    ("_role_api_data_row_offset", "_project_user_data_row_offset"),
    ("_schedule_role_api_filter_apply", "_schedule_project_user_filter_apply"),
    ("_filtered_role_api_rows", "_filtered_project_user_rows"),
    ("_write_role_api_rows", "_write_project_user_rows"),
    ("_apply_role_api_column_filters_refresh", "_apply_project_user_column_filters_refresh"),
    ("_on_role_filter_toggled", "_on_project_user_filter_toggled"),
    ("_reset_role_apis_table_columns_plain", "_reset_project_users_table_columns_plain"),
    ("_set_roles_feedback", "_set_projects_feedback"),
    ("_clear_roles_feedback", "_clear_projects_feedback"),
    ("_roles_msg", "_projects_msg"),
    ("_selected_left_api_ids", "_selected_left_user_ids"),
    ("_checked_assignment_ids_for_role_remove", "_checked_mapping_ids_for_remove"),
    ("_checked_api_ids_for_role_deactivate", "_checked_mapping_ids_for_status"),
    ("_assign_selected_apis_to_role", "_assign_selected_users_to_project"),
    ("_deactivate_selected_assignments", "_change_status_selected_mappings"),
    ("_deactivate_assign_btn", "_change_status_btn"),
    ("_api_column_spec", "_user_column_spec"),
    ("_api_data_row_offset", "_user_data_row_offset"),
    ("_schedule_api_filter_apply", "_schedule_user_filter_apply"),
    ("_filtered_api_source_rows", "_filtered_user_source_rows"),
    ("_write_api_data_rows", "_write_user_data_rows"),
    ("_apply_api_column_filters_refresh", "_apply_user_column_filters_refresh"),
    ("_on_api_filter_toggled", "_on_user_filter_toggled"),
    ("_style_assigned_lhs_row", "_style_assigned_lhs_row"),
    ("api_get_all_roles", "api_get_all_dm_projects"),
    ("api_get_all_apis", "api_get_all_dmt_users"),
    ("api_get_api_access_by_role_id", "api_get_dm_users_by_project_id"),
    ("api_grant_multiple_api_access", "api_assign_dm_users_to_project"),
    ("api_remove_multiple_api_by_role_id", "api_delete_dm_user_projects_by_ids"),
    ("api_change_status_multiple_api_by_role_id", "api_change_dm_user_project_status_by_ids"),
    ("Select Role", "Select Project"),
    ("selected role", "selected project"),
    ("this role", "this project"),
    ("from role", "from project"),
    ("to role", "to project"),
    ("for role", "for project"),
    ("Loading roles and APIs", "Loading projects and users"),
    ("Loading role APIs", "Loading project users"),
    ("Failed to load role APIs", "Failed to load project users"),
    ("No APIs assigned to selected role", "No users assigned to selected project"),
    ("Remove APIs", "Remove users"),
    ("API(s) removed from role", "User(s) removed from project"),
    ("APIs assigned successfully", "Users assigned successfully"),
    ("Failed to assign APIs", "Failed to assign users"),
    ("Failed to remove APIs from role", "Failed to remove users from project"),
    ("Failed to update API access status for role", "Failed to update mapping status"),
    ("API access status updated", "Mapping status updated"),
    (
        "Check one or more rows with an API Assign Id to remove.",
        "Check one or more rows with a Mapping Id to remove.",
    ),
    (
        "Check one or more rows with a resolvable API id to change status.",
        "Check one or more rows with a Mapping Id to change status.",
    ),
    ("Already assigned to selected role", "Already assigned to selected project"),
    ("Select a role first", "Select a project first"),
    ("Select at least one API on the left table", "Select at least one user on the left table"),
    ("ACTIVE/INACTIVE", "Change status"),
    ("_radio_active", "_status_placeholder"),
    ("_radio_inactive", "_status_placeholder2"),
]

out = src
for old, new in repls:
    out = out.replace(old, new)

user_cols = """_USER_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("User Id", ("userId", "user_id", "id")),
    ("Username", ("username", "userName", "user_name")),
    ("First Name", ("firstName", "first_name")),
    ("Last Name", ("lastName", "last_name")),
    ("Email", ("email",)),
    ("Mobile", ("mobile", "mobileNumber", "mobile_number")),
    ("Created By", ("createdBy", "created_by")),
    ("Created At", ("createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified At", ("modifiedAt", "modified_at", "updatedAt", "updated_at")),
)"""

proj_user_cols = """_PROJECT_USER_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("User Id", ("userId", "user_id")),
    ("Mapping Id", ("id", "mappingId", "mapping_id", "userProjectId", "user_project_id")),
    ("Username", ("username", "userName", "user_name", "name")),
    ("Email", ("email",)),
    ("Status", ("status", "statusName", "statusLabel", "status_seq", "statusSeq")),
    ("User Type", ("userType", "user_type", "userTypeName", "user_type_name")),
)"""

out = re.sub(
    r"_USER_COLUMNS: tuple\[tuple\[str, tuple\[str, \.\.\.\]\], \.\.\.\] = \(.*?\n\)",
    user_cols,
    out,
    count=1,
    flags=re.DOTALL,
)
out = re.sub(
    r"_PROJECT_USER_COLUMNS: tuple\[tuple\[str, tuple\[str, \.\.\.\]\], \.\.\.\] = \(.*?\n\)",
    proj_user_cols,
    out,
    count=1,
    flags=re.DOTALL,
)

dest_dir = ROOT / "app/dm/dm_user_project_mapping"
dest_dir.mkdir(parents=True, exist_ok=True)
(dest_dir / "dm_user_project_mapping_page.py").write_text(out, encoding="utf-8")
print("Wrote", dest_dir / "dm_user_project_mapping_page.py")
