"""Helpers for connection/table/column metadata."""

from __future__ import annotations

from typing import Any

from app.etl.scan_connection.scan_connection import (
    _connection_id,
    _connection_name,
    _extract_table_name,
)


def connection_id(conn: dict[str, Any] | None) -> int | str | None:
    return _connection_id(conn)


def connection_label(conn: dict[str, Any] | None) -> str:
    return _connection_name(conn) or ""


def column_name(col: Any) -> str:
    if isinstance(col, dict):
        for key in ("COLUMN_NAME", "columnName", "column_name", "name"):
            value = col.get(key)
            if value not in (None, ""):
                return str(value).strip()
    return str(col).strip() if col not in (None, "") else ""


def table_names_from_rows(rows: list[Any]) -> list[str]:
    names: list[str] = []
    for row in rows:
        name = extraction_table_name(row)
        if name and name not in names:
            names.append(name)
    return sorted(names, key=str.lower)


def extraction_table_name(row: Any) -> str:
    if isinstance(row, dict):
        for key in ("tableName", "TABLE_NAME", "table_name", "name"):
            value = row.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return _extract_table_name(row) if row is not None else ""


def transformation_connection_id(row: dict[str, Any] | None) -> int | str | None:
    if not row:
        return None
    for key in ("connectionId", "connection_id", "CONNECTION_ID"):
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def transformation_table_name(record: dict[str, Any] | None) -> str:
    if not record:
        return ""
    value = record.get("tableName")
    if value is not None and str(value).strip():
        return str(value).strip()
    return extraction_table_name(record)


def transformation_source_alias(record: dict[str, Any] | None) -> str:
    if not record:
        return ""
    for key in (
        "aliasName",
        "alias_name",
        "ALIAS_NAME",
        "sourceAlias",
        "source_alias",
        "SOURCE_ALIAS",
        "alias",
        "ALIAS",
    ):
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def transformation_record_id(row: dict[str, Any] | None, *keys: str) -> int | str | None:
    if not row:
        return None
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None
