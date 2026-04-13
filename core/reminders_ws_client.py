"""Plain WebSocket client for app update / reminder push notifications."""

from __future__ import annotations

import sys

from PySide6.QtCore import QByteArray, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtNetwork import QAbstractSocket, QNetworkRequest
from PySide6.QtWebSockets import QWebSocket

from core.config import (
    app_updates_websocket_connect_message_template,
    app_updates_websocket_origin,
    app_updates_websocket_url,
    app_updates_websocket_use_auth_header,
)
from core.user_context import get_user_profile
from core.ws_notification import WsNotificationPayload, parse_ws_notification


class AppUpdatesWebSocketClient(QObject):
    """Connects to the backend WebSocket; emits structured notification payloads."""

    notification = Signal(WsNotificationPayload)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._ws = QWebSocket()
        self._ws.connected.connect(self._on_connected)
        self._ws.textMessageReceived.connect(self._on_text_message)
        self._ws.binaryMessageReceived.connect(self._on_binary_message)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.errorOccurred.connect(self._on_socket_error)
        self._want_running = False
        self._reconnect_ms = 12_000
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._open_socket)
        self._handshake_hint_printed = False

    def start(self) -> None:
        self._want_running = True
        self._open_socket()

    def stop(self) -> None:
        self._want_running = False
        self._reconnect_timer.stop()
        self._ws.close()

    def _ws_url(self) -> QUrl:
        return QUrl(app_updates_websocket_url())

    def _token(self) -> str | None:
        profile = get_user_profile()
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
        if self._ws.state() == QAbstractSocket.SocketState.ConnectedState:
            return
        if self._ws.state() == QAbstractSocket.SocketState.ConnectingState:
            return
        url = self._ws_url()
        if not url.isValid():
            print("[AppUpdatesWS] Invalid WebSocket URL.", file=sys.stderr, flush=True)
            self._schedule_reconnect()
            return
        req = QNetworkRequest(url)
        origin = app_updates_websocket_origin().strip()
        if origin:
            req.setRawHeader(b"Origin", origin.encode("utf-8"))
        if app_updates_websocket_use_auth_header():
            token = self._token()
            if token:
                req.setRawHeader(b"Authorization", f"Bearer {token}".encode("utf-8"))
        self._ws.open(req)

    def _schedule_reconnect(self) -> None:
        if not self._want_running:
            return
        if not self._reconnect_timer.isActive():
            self._reconnect_timer.start(self._reconnect_ms)

    @Slot()
    def _on_connected(self) -> None:
        self._handshake_hint_printed = False
        tmpl = app_updates_websocket_connect_message_template()
        if tmpl:
            token = self._token() or ""
            self._ws.sendTextMessage(tmpl.replace("{token}", token))

    @Slot(str)
    def _on_text_message(self, message: str) -> None:
        self._handle_server_payload(message)

    @Slot(QByteArray)
    def _on_binary_message(self, message: QByteArray) -> None:
        try:
            s = bytes(message).decode("utf-8")
        except UnicodeDecodeError:
            return
        self._handle_server_payload(s)

    def _handle_server_payload(self, raw: str) -> None:
        payload = parse_ws_notification(raw)
        if payload is not None:
            self.notification.emit(payload)

    @Slot()
    def _on_disconnected(self) -> None:
        if self._want_running:
            self._schedule_reconnect()

    @Slot(QAbstractSocket.SocketError)
    def _on_socket_error(self, _: QAbstractSocket.SocketError) -> None:
        err = self._ws.errorString()
        url_s = app_updates_websocket_url()
        print(f"[AppUpdatesWS] socket error: {err}", file=sys.stderr, flush=True)
        print(f"[AppUpdatesWS] attempted URL: {url_s}", file=sys.stderr, flush=True)
        if not self._handshake_hint_printed and (
            "handshake" in err.lower() or "Unknown error" in err
        ):
            self._handshake_hint_printed = True
            print(
                "[AppUpdatesWS] Check: URL/path (ETL_WS_URL / ETL_WS_PATH), "
                "allowed Origin (ETL_WS_ORIGIN), and whether the server expects "
                "Authorization on the handshake (set ETL_WS_AUTH_HEADER=0 to disable). "
                "If the server requires a subscribe message after connect, set "
                "ETL_WS_CONNECT_MESSAGE (use {token} if needed).",
                file=sys.stderr,
                flush=True,
            )
        if self._want_running:
            self._schedule_reconnect()
