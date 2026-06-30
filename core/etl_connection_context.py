"""Shared active connection for ETL operational pages (Scan, Import, Extraction)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal

from core.api import api_get_all_connections


def etl_connection_name(conn: dict[str, Any] | None) -> str:
    if not conn:
        return ""
    return str(conn.get("connectionName") or "").strip()


def etl_connection_id(conn: dict[str, Any] | None) -> int | str | None:
    if not conn:
        return None
    for key in ("connectionId", "connectionID", "connection_id", "id"):
        value = conn.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def etl_connection_display_label(conn: dict[str, Any] | None) -> str:
    name = etl_connection_name(conn) or "Unnamed connection"
    conn_id = etl_connection_id(conn)
    if conn_id is None:
        return name
    return f"{name} (ID: {conn_id})"


def etl_connection_combo_index(combo, connection_id: int | str | None) -> int:
    if connection_id is None:
        return 0
    target = str(connection_id).strip()
    for index in range(combo.count()):
        data = combo.itemData(index)
        if isinstance(data, dict) and str(etl_connection_id(data) or "").strip() == target:
            return index
    return 0


class EtlConnectionContext(QObject):
    """Singleton holding the ETL connection list and active selection."""

    connections_changed = Signal()
    connection_selected = Signal(object)

    _instance: EtlConnectionContext | None = None

    def __init__(self) -> None:
        super().__init__()
        self._connections: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None

    @classmethod
    def instance(cls) -> EtlConnectionContext:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def connections(self) -> list[dict[str, Any]]:
        return list(self._connections)

    def current_connection(self) -> dict[str, Any] | None:
        return self._current

    def set_connections(self, connections: list[dict[str, Any]]) -> None:
        prev_id = etl_connection_id(self._current)
        self._connections = list(connections)
        rebound: dict[str, Any] | None = None
        if prev_id is not None:
            for conn in self._connections:
                if etl_connection_id(conn) == prev_id:
                    rebound = conn
                    break
        selection_changed = etl_connection_id(rebound) != prev_id
        self._current = rebound
        self.connections_changed.emit()
        if selection_changed:
            self.connection_selected.emit(self._current)

    def select_connection(self, conn: dict[str, Any] | None) -> None:
        if conn is not None:
            conn_id = etl_connection_id(conn)
            if conn_id is not None:
                for item in self._connections:
                    if etl_connection_id(item) == conn_id:
                        conn = item
                        break
        if self._current is conn:
            return
        if (
            self._current is not None
            and conn is not None
            and etl_connection_id(self._current) == etl_connection_id(conn)
        ):
            self._current = conn
            return
        self._current = conn
        self.connection_selected.emit(self._current)

    def select_by_id(self, connection_id: int | str | None) -> bool:
        if connection_id is None:
            self.select_connection(None)
            return False
        target = str(connection_id).strip()
        for conn in self._connections:
            if str(etl_connection_id(conn) or "").strip() == target:
                self.select_connection(conn)
                return True
        return False

    def refresh_connections(self, token: str | None) -> dict[str, Any]:
        result = api_get_all_connections(token)
        if result.get("success"):
            self.set_connections(list(result.get("data") or []))
        else:
            self.set_connections([])
        return result


def get_etl_connection_context() -> EtlConnectionContext:
    return EtlConnectionContext.instance()
