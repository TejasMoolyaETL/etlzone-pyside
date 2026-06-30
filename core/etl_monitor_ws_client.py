"""WebSocket client for live ETL job monitor events."""

from __future__ import annotations

import json
import sys
from typing import Any

from PySide6.QtCore import QByteArray, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtNetwork import QAbstractSocket, QNetworkRequest
from PySide6.QtWebSockets import QWebSocket

from core.config import (
    etl_monitor_websocket_origin,
    etl_monitor_websocket_url,
    etl_monitor_websocket_use_auth_header,
)
from core.user_context import get_user_profile


def _flatten_monitor_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Merge top-level fields with common nested envelopes (Kafka / WS wrappers)."""
    out: dict[str, Any] = dict(data)
    for key in ("data", "payload", "body", "record", "content", "event", "message"):
        nested = data.get(key)
        if isinstance(nested, dict):
            for nk, nv in nested.items():
                if nk not in out or out[nk] in (None, ""):
                    out[nk] = nv
        elif isinstance(nested, str) and nested.strip().startswith("{"):
            try:
                inner = json.loads(nested)
            except (json.JSONDecodeError, TypeError):
                inner = None
            if isinstance(inner, dict):
                for nk, nv in inner.items():
                    if nk not in out or out[nk] in (None, ""):
                        out[nk] = nv
    return out


def monitor_log_id(payload: dict[str, Any]) -> str:
    """Primary key for live monitor rows (one visible row per log id)."""
    if not isinstance(payload, dict):
        return ""
    for key in ("logId", "log_id", "LogId", "id", "ID"):
        if key in payload and payload.get(key) not in (None, ""):
            return str(payload.get(key)).strip()
    lower_map = {str(k).lower(): k for k in payload}
    for key in ("logid", "log_id", "id"):
        actual = lower_map.get(key)
        if actual is not None and payload.get(actual) not in (None, ""):
            return str(payload.get(actual)).strip()
    return ""


def parse_etl_monitor_log(raw: str) -> dict[str, Any] | None:
    """Parse a WebSocket text frame into a monitor log dict."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(data, dict):
        return _flatten_monitor_payload(data)
    return None


class EtlMonitorWebSocketClient(QObject):
    """Connects to ``/ws/etl`` and emits parsed log payloads."""

    log_received = Signal(dict)
    connection_changed = Signal(bool)
    connection_error = Signal(str)
    _BUFFER_MAX = 500

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._buffer: list[dict[str, Any]] = []
        self._ws = QWebSocket()
        self._ws.connected.connect(self._on_connected)
        self._ws.textMessageReceived.connect(self._on_text_message)
        self._ws.binaryMessageReceived.connect(self._on_binary_message)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.errorOccurred.connect(self._on_socket_error)
        self._want_running = False
        self._reconnect_ms = 3000
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._open_socket)
        self._last_error = ""

    def start(self) -> None:
        self._want_running = True
        self._last_error = ""
        self._open_socket()

    def stop(self) -> None:
        self._want_running = False
        self._reconnect_timer.stop()
        if self._ws.state() != QAbstractSocket.SocketState.UnconnectedState:
            self._ws.close()
        self.connection_changed.emit(False)

    def buffered_logs(self) -> list[dict[str, Any]]:
        """Newest-first copy of events received while connected."""
        return list(self._buffer)

    def clear_buffer(self) -> None:
        self._buffer.clear()

    def is_connected(self) -> bool:
        return self._ws.state() == QAbstractSocket.SocketState.ConnectedState

    def _remember_log(self, payload: dict[str, Any]) -> None:
        entry = dict(payload)
        log_id = monitor_log_id(entry)
        if log_id:
            self._buffer = [row for row in self._buffer if monitor_log_id(row) != log_id]
        self._buffer.insert(0, entry)
        if len(self._buffer) > self._BUFFER_MAX:
            self._buffer = self._buffer[: self._BUFFER_MAX]

    def _token(self) -> str | None:
        profile = get_user_profile() or {}
        tok = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(tok).strip() if tok else None

    @Slot()
    def _open_socket(self) -> None:
        if not self._want_running:
            return
        state = self._ws.state()
        if state in (
            QAbstractSocket.SocketState.ConnectedState,
            QAbstractSocket.SocketState.ConnectingState,
        ):
            return
        url = QUrl(etl_monitor_websocket_url())
        if not url.isValid():
            self._report_error("Invalid WebSocket URL.")
            self._schedule_reconnect()
            return

        origin = etl_monitor_websocket_origin()
        use_auth = etl_monitor_websocket_use_auth_header()
        if origin or use_auth:
            req = QNetworkRequest(url)
            if origin:
                req.setRawHeader(b"Origin", origin.encode("utf-8"))
            if use_auth:
                token = self._token()
                if token:
                    req.setRawHeader(b"Authorization", f"Bearer {token}".encode("utf-8"))
            self._ws.open(req)
        else:
            # Same as browser: plain WebSocket URL, no extra handshake headers.
            self._ws.open(url)

    def _report_error(self, message: str) -> None:
        self._last_error = message
        print(f"[EtlMonitorWS] {message}", file=sys.stderr, flush=True)
        self.connection_error.emit(message)

    def _schedule_reconnect(self) -> None:
        if self._want_running and not self._reconnect_timer.isActive():
            self._reconnect_timer.start(self._reconnect_ms)

    @Slot()
    def _on_connected(self) -> None:
        self._last_error = ""
        self.connection_changed.emit(True)

    def _emit_log(self, payload: dict[str, Any]) -> None:
        self._remember_log(payload)
        self.log_received.emit(payload)

    @Slot(str)
    def _on_text_message(self, message: str) -> None:
        payload = parse_etl_monitor_log(message)
        if payload is not None:
            self._emit_log(payload)

    @Slot(QByteArray)
    def _on_binary_message(self, message: QByteArray) -> None:
        try:
            text = bytes(message).decode("utf-8")
        except UnicodeDecodeError:
            return
        payload = parse_etl_monitor_log(text)
        if payload is not None:
            self._emit_log(payload)

    @Slot()
    def _on_disconnected(self) -> None:
        self.connection_changed.emit(False)
        if self._want_running:
            self._schedule_reconnect()

    @Slot(QAbstractSocket.SocketError)
    def _on_socket_error(self, _: QAbstractSocket.SocketError) -> None:
        err = self._ws.errorString().strip() or "WebSocket error"
        url_s = etl_monitor_websocket_url()
        self._report_error(f"{err} (URL: {url_s})")
        if self._want_running:
            self._schedule_reconnect()
