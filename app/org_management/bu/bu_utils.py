"""Helpers for business unit API shapes (flat + nested organization / parent)."""

from __future__ import annotations

from typing import Any


def get_bu_id(bu: dict[str, Any]) -> Any:
    """Resolve BU id from common keys."""
    for k in ("buId", "bu_id", "id"):
        v = bu.get(k)
        if v is not None:
            return v
    return None


def get_bu_name(bu: dict[str, Any]) -> str:
    """Resolve BU name from common keys."""
    return str((bu.get("buName") or bu.get("bu_name") or "")).strip()


def get_bu_display_name(bu: dict[str, Any]) -> str:
    """Display BU as 'Name (ID)' for selector clarity."""
    name = get_bu_name(bu)
    bu_id = get_bu_id(bu)
    if name and bu_id is not None:
        return f"{name} ({bu_id})"
    if name:
        return name
    if bu_id is not None:
        return str(bu_id)
    return ""


def get_organization_id_from_bu(bu: dict[str, Any]) -> Any:
    """Resolve organization id from common API shapes.

    Supports:
    - organizationId, organization_id (scalar on BU)
    - orgId on BU root (scalar, not a nested object)
    - organization: { orgId | org_id | id, ... }
    """
    for k in ("organizationId", "organization_id"):
        v = bu.get(k)
        if v is not None:
            return v
    oid = bu.get("orgId")
    if oid is not None and not isinstance(oid, dict):
        return oid
    org = bu.get("organization")
    if isinstance(org, dict):
        for k in ("orgId", "org_id", "id"):
            v = org.get(k)
            if v is not None:
                return v
    return None


def get_organization_name_from_bu(bu: dict[str, Any]) -> str | None:
    """Resolve organization name from common API shapes."""
    for key in ("organizationName", "organization_name", "orgName", "org_name"):
        v = bu.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    org = bu.get("organization")
    if isinstance(org, dict):
        for key in ("orgName", "org_name", "name"):
            v = org.get(key)
            if v is not None and str(v).strip():
                return str(v).strip()
    return None


def get_parent_bu_id_from_bu(bu: dict[str, Any]) -> Any:
    """Resolve parent BU id from common API shapes.

    Supports:
    - parentBu, parent_bu, parentBuId, parent_bu_id, parentId (scalar)
    - parentBu / parent_bu holding an object: { buId | bu_id | id, buName?, ... }
    - parent, parentBusinessUnit, parent_business_unit: { buId | bu_id | id, ... }
    """
    for k in ("parentBu", "parent_bu", "parentBuId", "parent_bu_id", "parentId", "parent_id"):
        v = bu.get(k)
        if v is None:
            continue
        if isinstance(v, dict):
            for pk in ("buId", "bu_id", "id"):
                if v.get(pk) is not None:
                    return v[pk]
            continue
        return v

    for nested_key in ("parent", "parentBusinessUnit", "parent_business_unit"):
        obj = bu.get(nested_key)
        if isinstance(obj, dict):
            for pk in ("buId", "bu_id", "id"):
                if obj.get(pk) is not None:
                    return obj[pk]
    return None


def get_parent_bu_name_from_bu(bu: dict[str, Any]) -> str | None:
    """Resolve parent BU name from common API shapes."""
    for key in ("parentBuName", "parent_bu_name", "parentName", "parent_name"):
        v = bu.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()

    for key in ("parentBu", "parent_bu", "parent", "parentBusinessUnit", "parent_business_unit"):
        obj = bu.get(key)
        if isinstance(obj, dict):
            for nk in ("buName", "bu_name", "name"):
                nv = obj.get(nk)
                if nv is not None and str(nv).strip():
                    return str(nv).strip()
    return None
