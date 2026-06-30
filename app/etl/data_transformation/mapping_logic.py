"""Field mapping rules and definition export."""

from __future__ import annotations

from app.etl.data_transformation.metadata_helpers import connection_id, connection_label
from app.etl.data_transformation.models import FieldMappingRow, TransformationState


def build_auto_mappings(state: TransformationState) -> list[FieldMappingRow]:
    """Map each target column to a matching source column when names align."""
    rows: list[FieldMappingRow] = []
    for tgt in state.target_columns:
        src_table = ""
        src_col = ""
        for table, cols in state.source_columns.items():
            if tgt in cols:
                src_table, src_col = table, tgt
                break
            for col in cols:
                if col.lower() == tgt.lower():
                    src_table, src_col = table, col
                    break
            if src_table:
                break
        expr = f"{src_table}.{src_col}" if src_table and src_col else ""
        rows.append(
            FieldMappingRow(
                target_column=tgt,
                source_table=src_table,
                source_column=src_col,
                expression=expr,
                output_name=tgt,
            )
        )
    return rows


def mapping_from_source_field(
    state: TransformationState,
    table: str,
    column: str,
    *,
    target_column: str = "",
) -> FieldMappingRow:
    tgt = target_column or column
    return FieldMappingRow(
        target_column=tgt,
        source_table=table,
        source_column=column,
        expression=f"{table}.{column}",
        output_name=tgt,
    )


def export_definition(state: TransformationState) -> dict:
    return {
        "sourceConnectionId": connection_id(state.source_connection),
        "sourceConnectionName": connection_label(state.source_connection),
        "sourceTables": list(state.source_tables),
        "targetConnectionId": connection_id(state.target_connection),
        "targetConnectionName": connection_label(state.target_connection),
        "targetTable": state.target_table,
        "fieldMappings": [m.to_api_dict() for m in state.mappings if m.target_column or m.source_column],
    }
