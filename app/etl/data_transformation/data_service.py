"""API access for Data Transformation wizard and catalog."""

from __future__ import annotations

from typing import Any

from app.etl.data_transformation.metadata_helpers import (
    column_name,
    connection_id,
    extraction_table_name,
    table_names_from_rows,
    transformation_connection_id,
    transformation_record_id,
    transformation_source_alias,
    transformation_table_name,
)
from core.api import (
    api_create_transformation_column,
    api_create_transformation_flow,
    api_create_transformation_job,
    api_create_transformation_join,
    api_create_transformation_object,
    api_create_transformation_source,
    api_create_transformation_step,
    api_create_transformation_target,
    api_create_transformation_workflow,
    api_delete_transformation_columns_by_flow,
    api_delete_transformation_join,
    api_delete_transformation_source,
    api_delete_transformation_step,
    api_delete_transformation_flow,
    api_delete_transformation_job,
    api_delete_transformation_object,
    api_delete_transformation_workflow,
    api_get_all_connections,
    api_get_extracted_metadata_tables_by_connection,
    api_get_extraction_tables_by_connection,
    api_get_imported_tables,
    api_get_metadata_table_columns,
    api_get_table_columns_from_etl_details,
    api_get_transformation_columns_by_flow,
    api_get_transformation_join_by_id,
    api_get_transformation_joins_by_flow,
    api_get_transformation_step_by_id,
    api_get_transformation_step_masters,
    api_get_transformation_steps_by_flow,
    api_get_transformation_flows_by_workflow,
    api_get_transformation_jobs,
    api_get_transformation_objects,
    api_get_transformation_source_by_flow,
    api_get_transformation_source_by_id,
    api_get_transformation_sources_by_flow,
    api_get_transformation_target_by_flow,
    api_get_transformation_workflows,
    api_update_transformation_column,
    api_update_transformation_join,
    api_update_transformation_step,
    api_update_transformation_flow,
    api_update_transformation_job,
    api_update_transformation_object,
    api_update_transformation_source,
    api_update_transformation_target,
    api_update_transformation_workflow,
    api_validate_group_table_where_clause,
)
from core.user_context import get_user_profile


def _rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in (result.get("data") or []) if isinstance(r, dict)]


def _name_map(rows: list[dict[str, Any]], id_keys: tuple[str, ...], name_keys: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in rows:
        row_id = None
        for key in id_keys:
            value = row.get(key)
            if value is not None and str(value).strip() != "":
                row_id = str(value).strip()
                break
        if not row_id:
            continue
        label = ""
        for key in name_keys:
            text = str(row.get(key) or "").strip()
            if text:
                label = text
                break
        out[row_id] = label or row_id
    return out


def _source_record_id(row: dict[str, Any] | None) -> int | str | None:
    if not row:
        return None
    for key in ("id", "sourceId", "ID"):
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _id_from_mutation_result(result: dict[str, Any]) -> int | str | None:
    data = result.get("data")
    if isinstance(data, dict):
        return _source_record_id(data)
    return None


def _join_record_id(row: dict[str, Any] | None) -> int | str | None:
    if not row:
        return None
    for key in ("id", "joinId", "join_id", "ID"):
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _step_record_id(row: dict[str, Any] | None) -> int | str | None:
    if not row:
        return None
    for key in ("id", "stepId", "step_id", "ID"):
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _column_record_id(row: dict[str, Any] | None) -> int | str | None:
    if not row:
        return None
    for key in ("id", "columnId", "column_id", "ID"):
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _target_record_id(row: dict[str, Any] | None) -> int | str | None:
    if not row:
        return None
    for key in ("id", "targetId", "target_id", "ID"):
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _target_has_data(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    if _target_record_id(row) is not None:
        return True
    if transformation_connection_id(row) is not None:
        return True
    if transformation_table_name(row):
        return True
    if str(row.get("loadType") or row.get("load_type") or "").strip():
        return True
    if row.get("commitSize") is not None or row.get("commit_size") is not None:
        return True
    return False


class TransformationDataService:
    def __init__(self, token: str | None = None) -> None:
        self._token = token

    def refresh_token(self) -> None:
        profile = get_user_profile() or {}
        self._token = profile.get("token") or profile.get("accessToken")

    def load_connections(self) -> tuple[bool, list[dict[str, Any]], str]:
        self.refresh_token()
        result = api_get_all_connections(self._token)
        if not result.get("success"):
            return False, [], str(result.get("message") or "Failed to load connections.")
        rows = [
            c for c in (result.get("connections") or result.get("data") or []) if isinstance(c, dict)
        ]
        return True, rows, ""

    def load_imported_tables(self, conn: dict[str, Any] | None) -> tuple[bool, list[str], str]:
        cid = connection_id(conn)
        if cid is None:
            return False, [], "Connection ID is required."
        result = api_get_imported_tables(cid, token=self._token)
        if not result.get("success"):
            return False, [], str(result.get("message") or "Failed to load imported tables.")
        return True, table_names_from_rows(list(result.get("tables") or [])), ""

    def load_table_columns(
        self, conn: dict[str, Any] | None, table_name: str
    ) -> tuple[bool, list[str], str]:
        cid = connection_id(conn)
        tbl = (table_name or "").strip()
        if cid is None or not tbl:
            return False, [], "Connection and table name are required."
        result = api_get_metadata_table_columns(cid, tbl, token=self._token)
        if not result.get("success"):
            return False, [], str(result.get("message") or "Failed to load columns.")
        cols = [column_name(c) for c in (result.get("columns") or [])]
        return True, [c for c in cols if c], ""

    def load_source_columns_map(
        self, conn: dict[str, Any] | None, tables: list[str]
    ) -> tuple[bool, dict[str, list[str]], str]:
        out: dict[str, list[str]] = {}
        for table in tables:
            ok, cols, msg = self.load_table_columns(conn, table)
            if not ok:
                return False, {}, msg
            out[table] = cols
        return True, out, ""

    def load_objects(self) -> tuple[bool, list[dict[str, Any]], str]:
        self.refresh_token()
        result = api_get_transformation_objects(token=self._token)
        if not result.get("success"):
            return False, [], str(result.get("message") or "Failed to load objects.")
        return True, _rows(result), ""

    def load_jobs(self, objects: list[dict[str, Any]] | None = None) -> tuple[bool, list[dict[str, Any]], str]:
        self.refresh_token()
        result = api_get_transformation_jobs(token=self._token)
        if not result.get("success"):
            return False, [], str(result.get("message") or "Failed to load jobs.")
        rows = _rows(result)
        if objects:
            names = _name_map(objects, ("id", "objectId"), ("objectName", "name"))
            for row in rows:
                oid = str(row.get("objectId") or "").strip()
                if oid and oid in names:
                    row["objectName"] = names[oid]
        return True, rows, ""

    def load_workflows(self, jobs: list[dict[str, Any]] | None = None) -> tuple[bool, list[dict[str, Any]], str]:
        self.refresh_token()
        result = api_get_transformation_workflows(token=self._token)
        if not result.get("success"):
            return False, [], str(result.get("message") or "Failed to load work flows.")
        rows = _rows(result)
        if jobs:
            names = _name_map(jobs, ("id", "jobId"), ("jobName", "name"))
            for row in rows:
                jid = str(row.get("jobId") or "").strip()
                if jid and jid in names:
                    row["jobName"] = names[jid]
        return True, rows, ""

    def load_flows_by_workflow(
        self, workflow_id: int | str | None
    ) -> tuple[bool, list[dict[str, Any]], str]:
        if workflow_id is None or str(workflow_id).strip() == "":
            return True, [], ""
        self.refresh_token()
        result = api_get_transformation_flows_by_workflow(workflow_id, token=self._token)
        if not result.get("success"):
            return False, [], str(result.get("message") or "Failed to load flows.")
        return True, _rows(result), ""

    def load_extracted_metadata_tables(
        self, connection_id_value: int | str | None
    ) -> tuple[bool, list[dict[str, Any]], str]:
        if connection_id_value is None or str(connection_id_value).strip() == "":
            return True, [], ""
        self.refresh_token()
        result = api_get_extracted_metadata_tables_by_connection(
            connection_id_value, token=self._token
        )
        if not result.get("success"):
            return False, [], str(result.get("message") or "Failed to load extracted tables.")
        rows: list[dict[str, Any]] = []
        for item in result.get("tables") or []:
            if isinstance(item, dict):
                rows.append(item)
            elif isinstance(item, str) and item.strip():
                rows.append({"tableName": item.strip()})
        return True, rows, ""

    def load_extraction_tables(
        self, connection_id_value: int | str | None
    ) -> tuple[bool, list[dict[str, Any]], str]:
        if connection_id_value is None or str(connection_id_value).strip() == "":
            return True, [], ""
        self.refresh_token()
        result = api_get_extraction_tables_by_connection(connection_id_value, token=self._token)
        if not result.get("success"):
            return False, [], str(result.get("message") or "Failed to load extraction tables.")
        rows = [r for r in (result.get("tables") or []) if isinstance(r, dict)]
        return True, rows, ""

    def load_transformation_sources_by_flow(
        self, flow_id: int | str | None
    ) -> tuple[bool, list[dict[str, Any]], str]:
        if flow_id is None or str(flow_id).strip() == "":
            return True, [], ""
        self.refresh_token()
        result = api_get_transformation_sources_by_flow(flow_id, token=self._token)
        if not result.get("success"):
            message = str(result.get("message") or "Failed to load source configurations.")
            if any(
                phrase in message.lower()
                for phrase in (
                    "not found",
                    "no source",
                    "source not present",
                    "does not exist",
                    "doesn't exist",
                    "not exist",
                    "not present",
                )
            ):
                return True, [], ""
            return False, [], message
        rows = [r for r in (result.get("data") or []) if isinstance(r, dict)]
        return True, rows, ""

    def load_transformation_source_by_flow(
        self, flow_id: int | str | None
    ) -> tuple[bool, dict[str, Any] | None, str]:
        ok, rows, msg = self.load_transformation_sources_by_flow(flow_id)
        if not ok:
            return False, None, msg
        return True, (rows[0] if rows else None), ""

    def load_transformation_source_by_id(
        self, source_id: int | str
    ) -> tuple[bool, dict[str, Any] | None, str]:
        self.refresh_token()
        result = api_get_transformation_source_by_id(source_id, token=self._token)
        if not result.get("success"):
            return False, None, str(result.get("message") or "Failed to load source configuration.")
        data = result.get("data")
        return True, (data if isinstance(data, dict) else None), ""

    def save_transformation_source(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.refresh_token()
        result = api_create_transformation_source(payload, token=self._token)
        record_id = _id_from_mutation_result(result)
        if record_id is not None:
            result["recordId"] = record_id
        return result

    def update_transformation_source(
        self, source_id: int | str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.refresh_token()
        return api_update_transformation_source(source_id, payload, token=self._token)

    def delete_transformation_source(self, source_id: int | str) -> dict[str, Any]:
        self.refresh_token()
        return api_delete_transformation_source(source_id, token=self._token)

    def save_transformation_target(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.refresh_token()
        result = api_create_transformation_target(payload, token=self._token)
        record_id = _id_from_mutation_result(result)
        if record_id is not None:
            result["recordId"] = record_id
        return result

    def load_transformation_target_by_flow(
        self, flow_id: int | str | None
    ) -> tuple[bool, dict[str, Any] | None, str]:
        if flow_id is None or str(flow_id).strip() == "":
            return True, None, ""
        self.refresh_token()
        result = api_get_transformation_target_by_flow(flow_id, token=self._token)
        if not result.get("success"):
            message = str(result.get("message") or "Failed to load target configuration.")
            if any(
                phrase in message.lower()
                for phrase in (
                    "not found",
                    "no target",
                    "target not present",
                    "does not exist",
                    "doesn't exist",
                    "not exist",
                    "not present",
                )
            ):
                return True, None, ""
            return False, None, message
        data = result.get("data")
        if isinstance(data, dict) and _target_has_data(data):
            return True, data, ""
        rows = _rows(result)
        if rows and _target_has_data(rows[0]):
            return True, rows[0], ""
        return True, None, ""

    def update_transformation_target(
        self, target_id: int | str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.refresh_token()
        return api_update_transformation_target(target_id, payload, token=self._token)

    def load_transformation_columns_by_flow(
        self, flow_id: int | str | None
    ) -> tuple[bool, list[dict[str, Any]], str]:
        if flow_id is None or str(flow_id).strip() == "":
            return True, [], ""
        self.refresh_token()
        result = api_get_transformation_columns_by_flow(flow_id, token=self._token)
        if not result.get("success"):
            message = str(result.get("message") or "Failed to load column mappings.")
            if any(
                phrase in message.lower()
                for phrase in (
                    "not found",
                    "no column",
                    "columns not present",
                    "does not exist",
                    "doesn't exist",
                    "not exist",
                    "not present",
                )
            ):
                return True, [], ""
            return False, [], message
        rows = [r for r in (result.get("data") or []) if isinstance(r, dict)]
        return True, rows, ""

    @staticmethod
    def build_flow_source_columns(columns: list[dict[str, Any]]) -> list[str]:
        """All sourceColumn values from GET column/flow/{flowId}."""
        names: list[str] = []
        for col in columns:
            for key in ("sourceColumn", "source_column", "SOURCE_COLUMN"):
                text = str(col.get(key) or "").strip()
                if text and text not in names:
                    names.append(text)
                    break
        return names

    @staticmethod
    def build_flow_column_catalog(
        columns: list[dict[str, Any]],
    ) -> tuple[list[str], dict[str, str]]:
        """Source columns and source→target map from GET column/flow/{flowId}."""
        source_columns: list[str] = []
        source_to_target: dict[str, str] = {}
        for col in columns:
            source = ""
            for key in ("sourceColumn", "source_column", "SOURCE_COLUMN"):
                text = str(col.get(key) or "").strip()
                if text:
                    source = text
                    break
            if not source:
                continue
            target = ""
            for key in ("targetColumn", "target_column", "TARGET_COLUMN"):
                text = str(col.get(key) or "").strip()
                if text:
                    target = text
                    break
            if source not in source_columns:
                source_columns.append(source)
            if source not in source_to_target:
                source_to_target[source] = target or source
        return source_columns, source_to_target

    @staticmethod
    def build_mapped_columns_by_source(
        sources: list[dict[str, Any]], columns: list[dict[str, Any]]
    ) -> dict[str, list[str]]:
        """Map column rows to source ids; rows without sourceAlias apply to every source."""
        columns_by_alias: dict[str, list[str]] = {}
        unscoped: list[str] = []
        for col in columns:
            alias = transformation_source_alias(col)
            name = ""
            for key in ("sourceColumn", "source_column", "SOURCE_COLUMN"):
                text = str(col.get(key) or "").strip()
                if text:
                    name = text
                    break
            if not name:
                continue
            if alias:
                bucket = columns_by_alias.setdefault(alias, [])
                if name not in bucket:
                    bucket.append(name)
            elif name not in unscoped:
                unscoped.append(name)

        by_source_id: dict[str, list[str]] = {}
        for source in sources:
            sid = transformation_record_id(source, "id", "sourceId", "source_id", "ID")
            if sid is None:
                continue
            alias = transformation_source_alias(source)
            names = list(columns_by_alias.get(alias or "", []))
            for name in unscoped:
                if name not in names:
                    names.append(name)
            by_source_id[str(sid).strip()] = names
        return by_source_id

    def load_source_column_options_for_flow(
        self, flow_id: int | str | None
    ) -> tuple[bool, list[dict[str, Any]], dict[str, list[dict[str, Any]]], str]:
        """Load alias entries and column metadata keyed by source alias."""
        if flow_id is None or str(flow_id).strip() == "":
            return True, [], {}, ""
        self.refresh_token()
        ok, sources, msg = self.load_transformation_sources_by_flow(flow_id)
        if not ok:
            return False, [], {}, msg

        sources_by_table: dict[str, list[dict[str, Any]]] = {}
        tables_by_connection: dict[str, list[str]] = {}
        for row in sources:
            cid = transformation_connection_id(row)
            table_name = transformation_table_name(row) or str(row.get("tableName") or "").strip()
            if table_name:
                sources_by_table.setdefault(table_name, []).append(row)
            if cid is None or not table_name:
                continue
            key = str(cid).strip()
            names = tables_by_connection.setdefault(key, [])
            if table_name not in names:
                names.append(table_name)

        metadata_rows: list[dict[str, Any]] = []
        for cid_text, table_names in tables_by_connection.items():
            cid: int | str = int(cid_text) if cid_text.isdigit() else cid_text
            result = api_get_table_columns_from_etl_details(
                cid, table_names, token=self._token
            )
            if not result.get("success"):
                return False, [], {}, str(
                    result.get("message") or "Failed to load source table columns."
                )
            metadata_rows.extend(
                [r for r in (result.get("rows") or []) if isinstance(r, dict)]
            )

        alias_entries, columns_by_alias = self._build_column_alias_catalog(
            sources, metadata_rows, sources_by_table
        )
        return True, alias_entries, columns_by_alias, ""

    @staticmethod
    def _build_column_alias_catalog(
        sources: list[dict[str, Any]],
        metadata_rows: list[dict[str, Any]],
        sources_by_table: dict[str, list[dict[str, Any]]],
    ) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        columns_by_alias: dict[str, list[dict[str, Any]]] = {}
        alias_entries: list[dict[str, Any]] = []
        seen_aliases: set[str] = set()

        def _append_column(alias: str, row: dict[str, Any]) -> None:
            column_name = ""
            for key in ("columnName", "column_name", "COLUMN_NAME", "fieldName", "name"):
                text = str(row.get(key) or "").strip()
                if text:
                    column_name = text
                    break
            if not column_name:
                return
            bucket = columns_by_alias.setdefault(alias, [])
            if any(
                str(existing.get("columnName") or existing.get("column_name") or "").strip()
                == column_name
                for existing in bucket
            ):
                return
            bucket.append(row)

        for source in sources:
            alias = transformation_source_alias(source)
            table_name = transformation_table_name(source) or str(
                source.get("tableName") or ""
            ).strip()
            if not alias:
                continue
            if alias not in seen_aliases:
                seen_aliases.add(alias)
                alias_entries.append(
                    {"alias": alias, "tableName": table_name, "source": source}
                )

        for row in metadata_rows:
            table_name = str(
                row.get("tableName") or row.get("table_name") or row.get("TABLE_NAME") or ""
            ).strip()
            aliases: list[str] = []
            for source in sources_by_table.get(table_name, []):
                candidate = transformation_source_alias(source)
                if candidate and candidate not in aliases:
                    aliases.append(candidate)
            row_alias = transformation_source_alias(row)
            if row_alias and row_alias not in aliases:
                aliases.append(row_alias)
            if not aliases:
                continue
            for alias in aliases:
                if alias not in seen_aliases:
                    seen_aliases.add(alias)
                    source_match = next(
                        (
                            s
                            for s in sources
                            if transformation_source_alias(s) == alias
                        ),
                        None,
                    )
                    alias_entries.append(
                        {
                            "alias": alias,
                            "tableName": table_name
                            or (
                                transformation_table_name(source_match)
                                if isinstance(source_match, dict)
                                else ""
                            ),
                            "source": source_match,
                        }
                    )
                _append_column(alias, row)

        for entry in alias_entries:
            alias = str(entry.get("alias") or "").strip()
            if alias and alias not in columns_by_alias:
                columns_by_alias[alias] = []

        return alias_entries, columns_by_alias

    def save_transformation_column(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.refresh_token()
        result = api_create_transformation_column(payload, token=self._token)
        record_id = _id_from_mutation_result(result)
        if record_id is not None:
            result["recordId"] = record_id
        return result

    def update_transformation_column(
        self, column_id: int | str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.refresh_token()
        return api_update_transformation_column(column_id, payload, token=self._token)

    def delete_transformation_columns_by_flow(self, flow_id: int | str) -> dict[str, Any]:
        self.refresh_token()
        return api_delete_transformation_columns_by_flow(flow_id, token=self._token)

    def load_transformation_joins_by_flow(
        self, flow_id: int | str | None
    ) -> tuple[bool, list[dict[str, Any]], str]:
        if flow_id is None or str(flow_id).strip() == "":
            return True, [], ""
        self.refresh_token()
        result = api_get_transformation_joins_by_flow(flow_id, token=self._token)
        if not result.get("success"):
            message = str(result.get("message") or "Failed to load join configurations.")
            if any(
                phrase in message.lower()
                for phrase in (
                    "not found",
                    "no join",
                    "joins not present",
                    "does not exist",
                    "doesn't exist",
                    "not exist",
                    "not present",
                )
            ):
                return True, [], ""
            return False, [], message
        rows = [r for r in (result.get("data") or []) if isinstance(r, dict)]
        return True, rows, ""

    def load_transformation_join_by_id(
        self, join_id: int | str
    ) -> tuple[bool, dict[str, Any] | None, str]:
        self.refresh_token()
        result = api_get_transformation_join_by_id(join_id, token=self._token)
        if not result.get("success"):
            return False, None, str(result.get("message") or "Failed to load join configuration.")
        data = result.get("data")
        return True, (data if isinstance(data, dict) else None), ""

    def save_transformation_join(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.refresh_token()
        result = api_create_transformation_join(payload, token=self._token)
        record_id = _id_from_mutation_result(result)
        if record_id is not None:
            result["recordId"] = record_id
        return result

    def update_transformation_join(
        self, join_id: int | str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.refresh_token()
        return api_update_transformation_join(join_id, payload, token=self._token)

    def delete_transformation_join(self, join_id: int | str) -> dict[str, Any]:
        self.refresh_token()
        return api_delete_transformation_join(join_id, token=self._token)

    def load_transformation_step_masters(self) -> tuple[bool, list[dict[str, Any]], str]:
        self.refresh_token()
        result = api_get_transformation_step_masters(token=self._token)
        if not result.get("success"):
            return False, [], str(result.get("message") or "Failed to load step masters.")
        rows = [r for r in (result.get("data") or []) if isinstance(r, dict)]
        return True, rows, ""

    def load_transformation_steps_by_flow(
        self, flow_id: int | str | None
    ) -> tuple[bool, list[dict[str, Any]], str]:
        if flow_id is None or str(flow_id).strip() == "":
            return True, [], ""
        self.refresh_token()
        result = api_get_transformation_steps_by_flow(flow_id, token=self._token)
        if not result.get("success"):
            message = str(result.get("message") or "Failed to load transform steps.")
            if any(
                phrase in message.lower()
                for phrase in (
                    "not found",
                    "no step",
                    "steps not present",
                    "does not exist",
                    "doesn't exist",
                    "not exist",
                    "not present",
                )
            ):
                return True, [], ""
            return False, [], message
        rows = [r for r in (result.get("data") or []) if isinstance(r, dict)]
        return True, rows, ""

    def load_transformation_step_by_id(
        self, step_id: int | str
    ) -> tuple[bool, dict[str, Any] | None, str]:
        self.refresh_token()
        result = api_get_transformation_step_by_id(step_id, token=self._token)
        if not result.get("success"):
            return False, None, str(result.get("message") or "Failed to load transform step.")
        data = result.get("data")
        return True, (data if isinstance(data, dict) else None), ""

    def save_transformation_step(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.refresh_token()
        result = api_create_transformation_step(payload, token=self._token)
        record_id = _id_from_mutation_result(result)
        if record_id is not None:
            result["recordId"] = record_id
        return result

    def update_transformation_step(
        self, step_id: int | str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        self.refresh_token()
        return api_update_transformation_step(step_id, payload, token=self._token)

    def delete_transformation_step(self, step_id: int | str) -> dict[str, Any]:
        self.refresh_token()
        return api_delete_transformation_step(step_id, token=self._token)

    def validate_where_clause(
        self, connection_id_value: int | str, table_name: str, where_clause: str
    ) -> dict[str, Any]:
        self.refresh_token()
        return api_validate_group_table_where_clause(
            connection_id_value,
            table_name,
            where_clause,
            token=self._token,
        )

    def save_object(self, payload: dict[str, Any], object_id: int | str | None = None) -> dict[str, Any]:
        self.refresh_token()
        if object_id is None:
            return api_create_transformation_object(payload, token=self._token)
        return api_update_transformation_object(object_id, payload, token=self._token)

    def delete_object(self, object_id: int | str) -> dict[str, Any]:
        self.refresh_token()
        return api_delete_transformation_object(object_id, token=self._token)

    def save_job(self, payload: dict[str, Any], job_id: int | str | None = None) -> dict[str, Any]:
        self.refresh_token()
        if job_id is None:
            return api_create_transformation_job(payload, token=self._token)
        return api_update_transformation_job(job_id, payload, token=self._token)

    def delete_job(self, job_id: int | str) -> dict[str, Any]:
        self.refresh_token()
        return api_delete_transformation_job(job_id, token=self._token)

    def save_workflow(self, payload: dict[str, Any], workflow_id: int | str | None = None) -> dict[str, Any]:
        self.refresh_token()
        if workflow_id is None:
            return api_create_transformation_workflow(payload, token=self._token)
        return api_update_transformation_workflow(workflow_id, payload, token=self._token)

    def delete_workflow(self, workflow_id: int | str) -> dict[str, Any]:
        self.refresh_token()
        return api_delete_transformation_workflow(workflow_id, token=self._token)

    def save_flow(self, payload: dict[str, Any], flow_id: int | str | None = None) -> dict[str, Any]:
        self.refresh_token()
        if flow_id is None:
            return api_create_transformation_flow(payload, token=self._token)
        return api_update_transformation_flow(flow_id, payload, token=self._token)

    def delete_flow(self, flow_id: int | str) -> dict[str, Any]:
        self.refresh_token()
        return api_delete_transformation_flow(flow_id, token=self._token)
