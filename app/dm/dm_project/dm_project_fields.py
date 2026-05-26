"""Shared helpers for DM: Project forms."""

from __future__ import annotations

from datetime import date
from typing import Any, Sequence

from PySide6.QtWidgets import QComboBox

from core.api import (
    api_get_all_dm_companies,
    master_key_row_seq_value,
)
from ui.searchable_form_combo import (
    combo_resolved_item_data,
    coerce_master_key_payload_int,
    coerce_reference_id_payload,
    populate_master_key_by_field_name,
    reset_searchable_combo,
    set_searchable_combo_by_user_data,
    wire_searchable_labeled_rows_combo,
    wire_searchable_master_key_combo,
)

FIELD_MIG_SRC_TGT = "mig_src_tgt"
FIELD_DELIVERY_MODEL = "delivery_model"
FIELD_MIG_TYPE = "mig_type"
FIELD_STATUS = "dm_project_status"
FIELD_SOURCE = "lead_source"
FIELD_LAPTOP_OWNERSHIP = "laptop_ownership"
FIELD_ACCOMMODATION_OWNERSHIP = "accommodation_ownership"
FIELD_TRAVEL_EXPENSE_OWNERSHIP = "travel_expense_ownership"
FIELD_PER_DIEM_OWNERSHIP = "per_diem_ownership"
FIELD_EXTRACTION_OWNERSHIP = "extraction_ownership"
FIELD_TRANSFORMATION_OWNERSHIP = "transformation_ownership"
FIELD_LOADING_OWNERSHIP = "loading_ownership"

MASTER_KEY_FIELD_BY_PAYLOAD_KEY: dict[str, str] = {
    "srcLandscape": FIELD_MIG_SRC_TGT,
    "tgtLandscape": FIELD_MIG_SRC_TGT,
    "deliveryModel": FIELD_DELIVERY_MODEL,
    "migrationType": FIELD_MIG_TYPE,
    "status": FIELD_STATUS,
    "source": FIELD_SOURCE,
    "laptopOwnership": FIELD_LAPTOP_OWNERSHIP,
    "accommodationOwnership": FIELD_ACCOMMODATION_OWNERSHIP,
    "travelExpenseOwnership": FIELD_TRAVEL_EXPENSE_OWNERSHIP,
    "perDiemOwnership": FIELD_PER_DIEM_OWNERSHIP,
    "extractionOwnership": FIELD_EXTRACTION_OWNERSHIP,
    "transformationOwnership": FIELD_TRANSFORMATION_OWNERSHIP,
    "loadingOwnership": FIELD_LOADING_OWNERSHIP,
}

DM_COMPANY_COMBO_KEYS: frozenset[str] = frozenset(
    {
        "clientCompanyId",
        "implementationPartnerId",
        "endClientName",
        "intermediateClient1",
        "intermediateClient2",
        "intermediateClient3",
        "intermediateClient4",
    }
)

COMPANY_COMBO_RECORD_ID_KEYS: dict[str, tuple[str, ...]] = {
    "clientCompanyId": ("clientCompanyId",),
    "implementationPartnerId": ("implementationPartnerId",),
    "endClientName": ("endClientId",),
    "intermediateClient1": ("intermediateClient1Id",),
    "intermediateClient2": ("intermediateClient2Id",),
    "intermediateClient3": ("intermediateClient3Id",),
    "intermediateClient4": ("intermediateClient4Id",),
}

COMPANY_COMBO_STRICT_PHRASE: dict[str, str] = {
    "clientCompanyId": "a client company",
    "implementationPartnerId": "an implementation partner",
    "endClientName": "an end client",
    "intermediateClient1": "intermediate client 1",
    "intermediateClient2": "intermediate client 2",
    "intermediateClient3": "intermediate client 3",
    "intermediateClient4": "intermediate client 4",
}

PROJECT_TEXT_FIELD_KEYS: tuple[str, ...] = ("region", "commentAtEtlzone")


def auth_token() -> str | None:
    from core.user_context import get_user_profile

    p = get_user_profile()
    t = p.get("token") or p.get("accessToken") or p.get("access_token") or p.get("jwt")
    return str(t) if t else None


def seq_from_record(rec: dict[str, Any], *keys: str) -> Any | None:
    for key in keys:
        v = rec.get(key)
        if v is None:
            continue
        if isinstance(v, dict):
            seq = master_key_row_seq_value(v)
            if seq is not None:
                return seq
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, float) and v == int(v):
            return int(v)
        s = str(v).strip()
        if s.isdigit():
            return int(s)
    return None


def id_from_record(rec: dict[str, Any], *keys: str) -> Any | None:
    for key in keys:
        v = rec.get(key)
        if v is not None and str(v).strip() != "":
            return v
    return None


def coerce_seq_int(seq_val: Any) -> int:
    if isinstance(seq_val, bool):
        return int(seq_val)
    if isinstance(seq_val, int):
        return seq_val
    if isinstance(seq_val, float) and seq_val == int(seq_val):
        return int(seq_val)
    s = str(seq_val).strip()
    if s.isdigit():
        return int(s)
    raise ValueError(f"Not a whole number: {seq_val!r}")


def format_master_display(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for k in ("keyValue", "key_value", "name", "label"):
            t = str(value.get(k) or "").strip()
            if t:
                return t
        seq = master_key_row_seq_value(value)
        return str(seq) if seq is not None else ""
    return str(value)


def parse_date_ymd(value: Any) -> date | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if "T" in s:
        s = s.split("T", 1)[0].strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            y, m, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
            return date(y, m, d)
        except ValueError:
            return None
    return None


def populate_master_key_combo(combo: QComboBox | None, field_name: str, *, token: str | None) -> None:
    if combo is None:
        return
    populate_master_key_by_field_name(
        combo,
        field_name,
        token=token,
        include_placeholder=False,
    )


def _scalar_company_id(row: dict[str, Any]) -> Any | None:
    """Resolve company id from flat or nested API shapes (new rows may nest ``companyId``)."""
    for key in ("companyId", "companyID", "id", "company_id"):
        raw = row.get(key)
        if raw is None:
            continue
        if isinstance(raw, dict):
            nested = id_from_record(raw, "companyId", "id", "keyValue")
            if nested is not None:
                return nested
            continue
        if isinstance(raw, bool):
            continue
        text = str(raw).strip()
        if text:
            return raw
    return None


def _company_rows(token: str | None) -> list[tuple[str, Any]]:
    result = api_get_all_dm_companies(token=token)
    rows = result.get("data") if result.get("success") else []
    out: list[tuple[str, Any]] = []
    if not isinstance(rows, list):
        return out
    seen_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        cid = _scalar_company_id(row)
        if cid is None:
            continue
        id_key = str(cid).strip()
        if not id_key or id_key in seen_ids:
            continue
        seen_ids.add(id_key)
        name = str(row.get("companyName") or row.get("name") or "").strip()
        label = f"{cid} | {name}" if name else str(cid)
        out.append((label, cid))
    return out


def populate_dm_company_combo(
    combo: QComboBox | None,
    *,
    search_field_label: str,
    token: str | None,
    rows: Sequence[tuple[str, Any]] | None = None,
) -> None:
    """Load choices from ``api/dm/company/get-all-company``."""
    if combo is None:
        return
    wire_searchable_labeled_rows_combo(
        combo,
        rows=rows if rows is not None else _company_rows(token),
        search_field_label=search_field_label,
        select_first_on_fill=False,
    )


def populate_client_company_combo(combo: QComboBox | None, *, token: str | None) -> None:
    populate_dm_company_combo(combo, search_field_label="Client company", token=token)


def populate_implementation_partner_combo(combo: QComboBox | None, *, token: str | None) -> None:
    populate_dm_company_combo(combo, search_field_label="Implementation partner", token=token)


def apply_combo_from_record(combo: QComboBox | None, value: Any) -> None:
    if combo is None:
        return
    if value is None:
        reset_searchable_combo(combo)
        return
    set_searchable_combo_by_user_data(combo, value)


def _payload_str(value: Any | None) -> str:
    return str(value or "").strip()


def coerce_optional_dm_company_id_payload(value: Any) -> int:
    """Optional DM project company combos: blank → ``0`` (backend rejects null)."""
    parsed = coerce_reference_id_payload(value)
    return 0 if parsed is None else parsed


def bool_from_record(rec: dict[str, Any], *keys: str) -> bool:
    for key in keys:
        v = rec.get(key)
        if v is None:
            continue
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)) and v in (0, 1):
            return bool(v)
        s = str(v).strip().lower()
        if s in ("true", "1", "yes"):
            return True
        if s in ("false", "0", "no"):
            return False
    return False


def build_project_payload(
    *,
    project_name: str,
    delivery_model: Any,
    client_company_id: Any | None = None,
    src_landscape: Any | None = None,
    tgt_landscape: Any | None = None,
    migration_type: Any | None = None,
    start_date: str | None = None,
    go_live_date: str | None = None,
    status: Any | None = None,
    implementation_partner_id: Any | None = None,
    region: str | None = None,
    source: Any | None = None,
    laptop_ownership: Any | None = None,
    accommodation_ownership: Any | None = None,
    travel_expense_ownership: Any | None = None,
    per_diem_ownership: Any | None = None,
    extraction_ownership: Any | None = None,
    transformation_ownership: Any | None = None,
    loading_ownership: Any | None = None,
    end_client_name: Any | None = None,
    intermediate_client1: Any | None = None,
    intermediate_client2: Any | None = None,
    intermediate_client3: Any | None = None,
    intermediate_client4: Any | None = None,
    comment_at_etlzone: str | None = None,
    extraction_scope: bool = False,
    transformation_scope: bool = False,
    load_scope: bool = False,
) -> dict[str, Any]:
    """JSON body for DM project create/update (matches backend contract)."""
    return {
        "projectName": project_name.strip(),
        "clientCompanyId": coerce_reference_id_payload(client_company_id),
        "srcLandscape": coerce_master_key_payload_int(src_landscape),
        "tgtLandscape": coerce_master_key_payload_int(tgt_landscape),
        "migrationType": coerce_master_key_payload_int(migration_type),
        "startDate": _payload_str(start_date),
        "goLiveDate": _payload_str(go_live_date),
        "status": coerce_master_key_payload_int(status),
        "deliveryModel": coerce_seq_int(delivery_model),
        "implementationPartnerId": coerce_optional_dm_company_id_payload(
            implementation_partner_id
        ),
        "region": _payload_str(region),
        "leadSource": coerce_master_key_payload_int(source),
        "laptopOwnership": coerce_master_key_payload_int(laptop_ownership),
        "accomadationOwnership": coerce_master_key_payload_int(accommodation_ownership),
        "extractionOwnership": coerce_master_key_payload_int(extraction_ownership),
        "transformationOwnership": coerce_master_key_payload_int(transformation_ownership),
        "travelExpenseOwnership": coerce_master_key_payload_int(travel_expense_ownership),
        "perDiemOwnership": coerce_master_key_payload_int(per_diem_ownership),
        "loadingOwnership": coerce_master_key_payload_int(loading_ownership),
        "extractionScope": bool(extraction_scope),
        "transformationScope": bool(transformation_scope),
        "loadScope": bool(load_scope),
        "endClientName": coerce_optional_dm_company_id_payload(end_client_name),
        "intermediateClient1": coerce_optional_dm_company_id_payload(intermediate_client1),
        "intermediateClient2": coerce_optional_dm_company_id_payload(intermediate_client2),
        "intermediateClient3": coerce_optional_dm_company_id_payload(intermediate_client3),
        "intermediateClient4": coerce_optional_dm_company_id_payload(intermediate_client4),
        "commentAtEtlzone": _payload_str(comment_at_etlzone),
    }


def prepare_dm_project_api_payload(
    *,
    project_name: str,
    delivery_model: int,
    entity_values: dict[str, Any | None],
    optional_masters: dict[str, int | None],
    start_date: str | None,
    go_live_date: str | None,
    region: str,
    comment_at_etlzone: str,
    extraction_scope: bool,
    transformation_scope: bool,
    load_scope: bool,
    extraction_ownership: int,
    transformation_ownership: int,
    loading_ownership: int,
) -> dict[str, Any]:
    """Full create/update JSON body (same shape as ``api/dm-project/create`` and PUT update)."""
    return build_project_payload(
        project_name=project_name,
        delivery_model=delivery_model,
        client_company_id=entity_values.get("clientCompanyId"),
        src_landscape=optional_masters.get("srcLandscape"),
        tgt_landscape=optional_masters.get("tgtLandscape"),
        migration_type=optional_masters.get("migrationType"),
        start_date=start_date,
        go_live_date=go_live_date,
        status=optional_masters.get("status"),
        implementation_partner_id=entity_values.get("implementationPartnerId"),
        region=region,
        source=optional_masters.get("source"),
        laptop_ownership=optional_masters.get("laptopOwnership"),
        accommodation_ownership=optional_masters.get("accommodationOwnership"),
        travel_expense_ownership=optional_masters.get("travelExpenseOwnership"),
        per_diem_ownership=optional_masters.get("perDiemOwnership"),
        extraction_ownership=extraction_ownership,
        transformation_ownership=transformation_ownership,
        loading_ownership=loading_ownership,
        end_client_name=entity_values.get("endClientName"),
        intermediate_client1=entity_values.get("intermediateClient1"),
        intermediate_client2=entity_values.get("intermediateClient2"),
        intermediate_client3=entity_values.get("intermediateClient3"),
        intermediate_client4=entity_values.get("intermediateClient4"),
        comment_at_etlzone=comment_at_etlzone,
        extraction_scope=extraction_scope,
        transformation_scope=transformation_scope,
        load_scope=load_scope,
    )


def wire_master_key_combo(combo: QComboBox, *, label: str) -> None:
    from ui.form_combobox_style import apply_form_combobox_field
    from ui.form_page_styles import MODAL_FIELD_HEIGHT_PX

    apply_form_combobox_field(combo, height_px=MODAL_FIELD_HEIGHT_PX, min_width=280)
    wire_searchable_master_key_combo(combo, search_field_label=label)


def resolved_combo_id(combo: QComboBox | None) -> Any:
    return combo_resolved_item_data(combo)
