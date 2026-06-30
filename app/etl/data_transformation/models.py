"""Data models for transformation wizard state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceFieldRef:
    table: str
    column: str

    @property
    def qualified_name(self) -> str:
        return f"{self.table}.{self.column}"


@dataclass
class FieldMappingRow:
    target_column: str = ""
    source_table: str = ""
    source_column: str = ""
    expression: str = ""
    output_name: str = ""

    def to_api_dict(self) -> dict[str, str]:
        return {
            "targetColumn": self.target_column,
            "sourceTable": self.source_table,
            "sourceColumn": self.source_column,
            "expression": self.expression,
            "outputField": self.output_name or self.target_column,
        }


@dataclass
class TransformationState:
    """In-memory wizard state shared across steps."""

    connections: list[dict[str, Any]] = field(default_factory=list)
    source_connection: dict[str, Any] | None = None
    target_connection: dict[str, Any] | None = None
    source_tables: list[str] = field(default_factory=list)
    target_table: str = ""
    source_columns: dict[str, list[str]] = field(default_factory=dict)
    target_columns: list[str] = field(default_factory=list)
    mappings: list[FieldMappingRow] = field(default_factory=list)

    def source_connection_label(self) -> str:
        if not self.source_connection:
            return "—"
        from app.etl.data_transformation.metadata_helpers import connection_label

        return connection_label(self.source_connection)

    def target_connection_label(self) -> str:
        if not self.target_connection:
            return "—"
        from app.etl.data_transformation.metadata_helpers import connection_label

        return connection_label(self.target_connection)

    def mapped_target_count(self) -> int:
        return sum(1 for m in self.mappings if m.target_column)
