"""One-off transform: DM company-contact assignment -> DMT user-module assignment."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app" / "dmt" / "dmt_user_module_assignment"

REPLACEMENTS = [
    ('"""Lead Company Contact Assignment list page (company + linked contacts)."""', '"""DMT User Module Assignment list (users + linked modules)."""'),
    ('"""Create Company Contact Assignment page."""', '"""Create DMT User Module Assignment page."""'),
    ('"""View / edit Company Contact Assignment page."""', '"""View / edit DMT User Module Assignment page."""'),
    ("api_delete_dm_contact_person_company_assignment,\n    api_get_all_dm_companies,", "api_get_all_dmt_users,\n    api_get_dmt_user_module_assignments_by_user_id,\n    api_remove_dmt_user_module_assignments,"),
    ("api_create_dm_contact_person_company_assignment,\n    api_get_all_dm_contact_persons,\n    api_get_all_dm_companies,", "api_assign_dmt_user_modules,\n    api_change_dmt_user_module_status_by_id,\n    api_get_all_dmt_users,\n    api_get_all_modules,"),
    ("api_get_all_dm_contact_persons,\n    api_get_all_dm_companies,\n    api_update_dm_contact_person_company_assignment,", "api_change_dmt_user_module_status_by_id,\n    api_get_all_dmt_users,\n    api_get_all_modules,"),
    ("_ASSIGNMENT_STATUS_FIELD_NAME = \"lead_company_contact_assignment_status\"", "_ASSIGNMENT_STATUS_FIELD_NAME = \"api_status\""),
    ("_COMPANY_COLUMNS", "_USER_COLUMNS"),
    ("_CONTACT_COLUMNS", "_MODULE_COLUMNS"),
    ("DmContactPersonCompanyAssignmentListPage", "DmtUserModuleAssignmentListPage"),
    ("CreateDmContactPersonCompanyAssignmentPage", "CreateDmtUserModuleAssignmentPage"),
    ("ViewDmContactPersonCompanyAssignmentPage", "ViewDmtUserModuleAssignmentPage"),
    ("DM: Company Contact Assignment", "DMT: User Module Assignment"),
    ("dm-company-contact-assignment", "dmt-user-module-assignment"),
    ("_company_", "_user_"),
    ("_contact_", "_module_"),
    ("_contacts_", "_modules_"),
    ("_company", "_user"),
    ("_contact", "_module"),
    ("company", "user"),
    ("Company", "User"),
    ("Contact", "Module"),
    ("contact", "module"),
    ("companies", "users"),
    ("Companies", "Users"),
    ("contacts", "modules"),
    ("Contacts", "Modules"),
    ("api_get_all_dm_companies", "api_get_all_dmt_users"),
    ("api_get_all_dm_contact_persons", "api_get_all_modules"),
    ("api_create_dm_contact_person_company_assignment", "api_assign_dmt_user_modules"),
    ("api_update_dm_contact_person_company_assignment", "api_change_dmt_user_module_status_by_id"),
    ("api_delete_dm_contact_person_company_assignment", "api_remove_dmt_user_module_assignments"),
    ("CreateDmContactPersonCompanyAssignmentPage", "CreateDmtUserModuleAssignmentPage"),
    ("DmContactPersonCompanyAssignmentListPage", "DmtUserModuleAssignmentListPage"),
    ("ViewDmContactPersonCompanyAssignmentPage", "ViewDmtUserModuleAssignmentPage"),
    ("Create Company Contact Assignment", "Create User Module Assignment"),
    ("Company Contant Assignment Details", "User Module Assignment Details"),
    ("Company Contact Assignment", "User Module Assignment"),
    ("companyContactId", "userModuleId"),
    ("contactPersonId", "moduleId"),
    ("contactId", "moduleId"),
    ("contactPersonName", "moduleName"),
    ("companyName", "userName"),
    ("companyId", "userId"),
    ("idCompany", "idUser"),
    ("_populate_company_combo", "_populate_user_combo"),
    ("_populate_contact_person_combo", "_populate_module_combo"),
    ("_record_company_id", "_record_user_id"),
    ("_record_contact_id", "_record_module_id"),
    ("_company_combo", "_user_combo"),
    ("_contact_person_combo", "_module_combo"),
    ("Company*", "DMT User*"),
    ("Contact Person*", "Module*"),
    ("search_field_label=\"Company\"", "search_field_label=\"DMT User\""),
    ("search_field_label=\"Contact Person\"", "search_field_label=\"Module\""),
    ("a company", "a DMT user"),
    ("a contact person", "a module"),
    ("Company is required.", "DMT User is required."),
    ("Contact Person is required.", "Module is required."),
    ("Failed to load companies.", "Failed to load users."),
    ("No companies returned.", "No users returned."),
    ("Select a company after companies load.", "Select a user after users load."),
    ("Selected company is missing a company id.", "Selected user is missing a user id."),
    ("No contacts linked to this company.", "No modules linked to this user."),
]

USER_COLUMNS_BLOCK = '''# Left: DMT users (subset of fields for split view).
_USER_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("User", ("userId", "id")),
    ("First Name", ("firstName", "first_name")),
    ("Last Name", ("lastName", "last_name")),
    ("Email", ("email",)),
    ("Status", ("status",)),
)

# Right: modules assigned to the selected user.
_MODULE_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Assignment Id", ("assignmentId", "userModuleId", "id", "linkId")),
    ("Assignment Status", ("assignmentStatus", "assignment_status")),
    ("Module Id", ("moduleId", "id")),
    ("Module Name", ("moduleName", "name")),
    ("Module Status", ("status", "moduleStatus", "api_status")),
)
'''

def transform_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    if path.name.endswith("_list.py"):
        # Replace column definitions block
        start = text.find("# Left:")
        end = text.find("\n\n\ndef _pick", start)
        if start >= 0 and end > start:
            text = text[:start] + USER_COLUMNS_BLOCK + text[end:]
    path.write_text(text, encoding="utf-8")


def main() -> None:
    for name in (
        "dmt_user_module_assignment_list.py",
        "dmt_user_module_assignment_create.py",
        "dmt_user_module_assignment_view.py",
    ):
        transform_file(ROOT / name)
    print("Transformed", ROOT)


if __name__ == "__main__":
    main()
