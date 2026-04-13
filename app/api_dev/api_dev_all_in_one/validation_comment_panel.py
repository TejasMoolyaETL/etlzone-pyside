"""Comments panel for the selected API validation (API: All in One)."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from PySide6.QtCore import QEvent, QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.api_dev.api_dev_all_in_one.details_list_panel import _format_cell
from app.api_dev.api_dev_all_in_one.validations_list_panel import APIValidationsListPanel
from core.api import (
    api_add_validation_comment,
    api_get_all_validation_comments_by_id,
    api_update_validation_comment_by_id,
)
from core.user_context import get_user_email, get_user_profile
from ui.form_page_styles import (
    APP_FONT_SIZE_PX,
    FORM_ERROR_LABEL_STYLE,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    MODAL_FEEDBACK_SUCCESS_STYLE,
    MODAL_FIELD_LABEL_STYLE,
)

# Same key tuple as API Details list "Created At" column (timezone + display format).
_COMMENT_CREATED_AT_KEYS: tuple[str, ...] = (
    "createdAt",
    "created_at",
    "CreatedAt",
    "createDate",
    "creationDate",
    "dateCreated",
)


def _auth_token() -> str | None:
    profile = get_user_profile()
    t = (
        profile.get("token")
        or profile.get("accessToken")
        or profile.get("access_token")
        or profile.get("bearerToken")
        or profile.get("bearer_token")
        or profile.get("jwt")
        or profile.get("idToken")
        or profile.get("id_token")
    )
    return str(t) if t else None


def _add_identity(identities: set[str], value: Any) -> None:
    if value is None:
        return
    s = str(value).strip()
    if s:
        identities.add(s.lower())


def _current_user_identities() -> set[str]:
    profile = get_user_profile()
    identities: set[str] = set()
    for key in (
        "username",
        "userName",
        "user_name",
        "userId",
        "userid",
        "loginId",
        "login_id",
        "email",
        "createdBy",
        "sub",
    ):
        _add_identity(identities, profile.get(key))
    _add_identity(identities, get_user_email())
    nested = profile.get("user")
    if isinstance(nested, dict):
        for key in ("username", "userName", "user_name", "loginId", "email", "userId"):
            _add_identity(identities, nested.get(key))
    # Some sessions keep identity only inside JWT claims (e.g. sub=s11111).
    token = (
        profile.get("token")
        or profile.get("accessToken")
        or profile.get("access_token")
        or profile.get("jwt")
        or profile.get("idToken")
        or profile.get("id_token")
    )
    t = str(token or "").strip()
    if t and "." in t:
        try:
            payload_part = t.split(".")[1]
            payload_part += "=" * ((4 - len(payload_part) % 4) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_part.encode("utf-8")).decode("utf-8"))
            if isinstance(payload, dict):
                for key in ("sub", "username", "userName", "loginId", "userId", "email"):
                    _add_identity(identities, payload.get(key))
        except Exception:
            pass
    return identities


def _author_is_current_user(author: str, identities: set[str]) -> bool:
    au = (author or "").strip().lower()
    if not au or au == "unknown":
        return False
    if au in identities:
        return True
    profile = get_user_profile()
    for key in ("userName", "username", "loginId", "email"):
        v = profile.get(key)
        if v is not None and str(v).strip().lower() == au:
            return True
    nested = profile.get("user")
    if isinstance(nested, dict):
        for key in ("userName", "username", "loginId", "email"):
            v = nested.get(key)
            if v is not None and str(v).strip().lower() == au:
                return True
    if (get_user_email() or "").strip().lower() == au:
        return True
    return False


def _comment_id_from_row(row: dict[str, Any]) -> Any:
    cid = row.get("commentId")
    if cid is not None:
        return cid
    raw = row.get("raw")
    if isinstance(raw, dict):
        return (
            raw.get("commentId")
            or raw.get("comment_id")
            or raw.get("validationCommentId")
            or raw.get("validation_comment_id")
        )
    return None


def _created_at_from_row(row: dict[str, Any]) -> Any:
    v = row.get("createdAt")
    if v is not None and str(v).strip():
        return v
    raw = row.get("raw")
    if isinstance(raw, dict):
        return raw.get("createdAt") or raw.get("created_at")
    return None


def _dt_to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _validation_internal_id(row: dict[str, Any]) -> Any:
    return row.get("id") or row.get("internalId") or row.get("internal_id")


class _CommentWorker(QObject):
    finished = Signal(dict)

    def __init__(self, op: str, validation_id: Any, text: str) -> None:
        super().__init__()
        self._op = op
        self._validation_id = validation_id
        self._text = text

    @Slot()
    def run(self) -> None:
        tk = _auth_token()
        if self._op == "get_all":
            self.finished.emit(
                api_get_all_validation_comments_by_id(self._validation_id, token=tk)
            )
        elif self._op == "add":
            self.finished.emit(api_add_validation_comment(self._validation_id, self._text, token=tk))
        elif self._op == "update":
            self.finished.emit(
                api_update_validation_comment_by_id(self._validation_id, self._text, token=tk)
            )
        else:
            self.finished.emit({"success": False, "message": "Unknown operation."})


class ValidationCommentPanel(QWidget):
    def __init__(self, validations_panel: APIValidationsListPanel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._vp = validations_panel
        self._thread: QThread | None = None
        self._worker: _CommentWorker | None = None
        self._pending_op = ""
        self._busy = False
        self._chat_rows: list[dict[str, Any]] = []
        self._my_identities = _current_user_identities()
        self._show_loading_on_next_get = False
        self._chat_loading = False
        self._editing_comment_id: Any = None
        self._editing_created_at: Any = None

        self._load_timer = QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.setInterval(250)
        self._load_timer.timeout.connect(self._start_load_comments)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QWidget()
        header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        header_layout.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        title = QLabel("Comments")
        header_layout.addWidget(title)
        header_layout.addStretch()
        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setFixedWidth(100)
        self._btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_refresh.setEnabled(False)
        self._btn_refresh.clicked.connect(self._on_refresh_clicked)
        header_layout.addWidget(self._btn_refresh)
        layout.addWidget(header)

        self._context_lbl = QLabel("Select a validation row in the table.")
        self._context_lbl.setWordWrap(True)
        self._context_lbl.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        layout.addWidget(self._context_lbl)

        self._chat_scroll = QScrollArea()
        self._chat_scroll.setWidgetResizable(True)
        self._chat_scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #e2e8f0; border-radius: 6px; background: #ffffff; }"
        )
        self._chat_host = QWidget()
        self._chat_layout = QVBoxLayout(self._chat_host)
        self._chat_layout.setContentsMargins(8, 8, 8, 8)
        self._chat_layout.setSpacing(6)
        self._chat_scroll.setWidget(self._chat_host)
        layout.addWidget(self._chat_scroll, 1)

        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText("Type a message...")
        self._editor.setMinimumHeight(40)
        self._editor.setMaximumHeight(64)
        self._editor.setStyleSheet(
            f"QPlainTextEdit {{ font-size: {APP_FONT_SIZE_PX}px; padding: 4px 10px; "
            "border: 1px solid #d1d5db; border-radius: 16px; background: #ffffff; }}"
        )
        self._editor.installEventFilter(self)
        input_row.addWidget(self._editor, 1)
        self._btn_send = QPushButton("Send")
        self._btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_send.setFixedWidth(74)
        self._btn_send.setFixedHeight(34)
        self._btn_send.setStyleSheet(
            "QPushButton { background: #e2e8f0; color: #0f172a; border: 1px solid #cbd5e1; border-radius: 16px; "
            "font-weight: 600; padding: 0 12px; }"
            "QPushButton:hover { background: #cbd5e1; }"
            "QPushButton:pressed { background: #94a3b8; }"
            "QPushButton:disabled { background: #f1f5f9; color: #94a3b8; border: 1px solid #e2e8f0; }"
        )
        self._btn_send.setEnabled(False)
        self._btn_send.clicked.connect(self._on_send_clicked)
        input_row.addWidget(self._btn_send)
        layout.addLayout(input_row)
        self._hint = QLabel("Press Enter to send, Shift+Enter for new line.")
        self._hint.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        layout.addWidget(self._hint)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setVisible(False)
        layout.addWidget(self._status)

        self._vp.table.itemSelectionChanged.connect(self._on_selection_changed)
        self._update_context()
        self._render_chat()

    def _current_validation_id(self) -> Any:
        row = self._vp.get_selected_row()
        if not row:
            return None
        return _validation_internal_id(row)

    def _update_context(self) -> None:
        vid = self._current_validation_id()
        if vid is not None:
            self._context_lbl.setText(f"Validation id: {vid}")
        else:
            self._context_lbl.setText("Select a validation row in the table.")
        enabled = vid is not None and not self._busy
        self._btn_send.setEnabled(enabled)
        self._btn_refresh.setEnabled(enabled)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._editor and event.type() == QEvent.Type.KeyPress:
            key_event = event
            if getattr(key_event, "key", lambda: None)() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if not (getattr(key_event, "modifiers", lambda: Qt.KeyboardModifier.NoModifier)() & Qt.KeyboardModifier.ShiftModifier):
                    self._on_send_clicked()
                    return True
        return super().eventFilter(watched, event)

    def _on_selection_changed(self) -> None:
        self._editing_comment_id = None
        self._editing_created_at = None
        self._btn_send.setText("Send")
        self._update_context()
        if self._current_validation_id() is not None:
            self._show_loading_on_next_get = True
            self._chat_loading = True
            self._render_chat()
            self._load_timer.start()
        else:
            self._load_timer.stop()
            self._chat_rows = []
            self._show_loading_on_next_get = False
            self._chat_loading = False
            self._editing_comment_id = None
            self._editing_created_at = None
            self._editor.clear()
            self._status.setVisible(False)
            self._render_chat()

    def _on_refresh_clicked(self) -> None:
        self._show_loading_on_next_get = False
        self._start_load_comments()

    def _start_load_comments(self) -> None:
        if self._busy:
            return
        vid = self._current_validation_id()
        if vid is None:
            return
        self._run_worker(
            "get_all",
            vid,
            "",
            show_chat_loading=self._show_loading_on_next_get,
        )
        self._show_loading_on_next_get = False

    def _on_send_clicked(self) -> None:
        vid = self._current_validation_id()
        if vid is None:
            return
        text = self._editor.toPlainText().strip()
        if not text:
            self._flash_status("Type a message before sending.", error=True)
            return
        if self._editing_comment_id is not None:
            if not self._is_edit_window_open(self._editing_created_at):
                self._flash_status("Edit time expired (5 min).", error=True)
                self._editing_comment_id = None
                self._editing_created_at = None
                self._btn_send.setText("Send")
                return
            self._run_worker("update", self._editing_comment_id, text)
            return
        self._run_worker("add", vid, text)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._editor.setReadOnly(busy)
        self._update_context()

    def _run_worker(
        self,
        op: str,
        validation_id: Any,
        text: str,
        *,
        show_chat_loading: bool = False,
    ) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        self._cleanup_worker()
        self._pending_op = op
        if op == "get_all" and show_chat_loading:
            self._chat_loading = True
            self._render_chat()
        self._set_busy(True)
        self._status.setVisible(False)
        self._thread = QThread(self)
        self._worker = _CommentWorker(op, validation_id, text)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()

    @Slot()
    def _on_worker_finished(self, result: dict[str, Any]) -> None:
        self._set_busy(False)
        op = self._pending_op
        self._pending_op = ""
        ok = result.get("success") is True
        msg = str(result.get("message", "") or "").strip()

        if op == "get_all":
            self._chat_loading = False
            if ok:
                rows = result.get("comments")
                self._chat_rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
                self._render_chat()
                if msg:
                    self._flash_status(msg, error=False)
            else:
                self._chat_rows = []
                self._render_chat()
                self._flash_status(msg or "Failed to load comments.", error=True)
            return

        if ok:
            self._editor.clear()
            if op == "update":
                self._flash_status(msg or "Message updated.", error=False)
            else:
                self._flash_status(msg or "Message sent.", error=False)
            self._editing_comment_id = None
            self._editing_created_at = None
            self._btn_send.setText("Send")
            QTimer.singleShot(60, self._start_load_comments)
        else:
            if op == "update" and "expired" in msg.lower():
                self._editing_comment_id = None
                self._editing_created_at = None
                self._btn_send.setText("Send")
            self._flash_status(msg or "Request failed.", error=True)

    def _parse_dt(self, value: Any) -> datetime | None:
        s = str(value or "").strip()
        if not s:
            return None
        s = s.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            pass
        # Fallback: some Python versions / fractional lengths choke on fromisoformat.
        base = s.split("+", 1)[0].strip()
        if "T" in base:
            head = base.split("T", 1)[0] + "T" + base.split("T", 1)[1].split(".", 1)[0]
        else:
            head = base[:19] if len(base) >= 19 else base
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(head[:19], fmt)
            except ValueError:
                continue
        return None

    def _is_edit_window_open(self, created_at: Any) -> bool:
        """5-minute edit window. Naive API timestamps are treated as UTC (typical server time)."""
        dt = self._parse_dt(created_at)
        if dt is None:
            return False
        posted = _dt_to_utc(dt)
        now = datetime.now(timezone.utc)
        return now - posted <= timedelta(minutes=5)

    def _start_edit_comment(self, row: dict[str, Any]) -> None:
        comment_id = _comment_id_from_row(row)
        if comment_id is None:
            self._flash_status("Unable to edit this message.", error=True)
            return
        created_at = _created_at_from_row(row)
        if not self._is_edit_window_open(created_at):
            self._flash_status("Edit time expired (5 min).", error=True)
            return
        self._editing_comment_id = comment_id
        self._editing_created_at = created_at
        self._editor.setPlainText(str(row.get("comment", "") or ""))
        self._editor.setFocus()
        self._btn_send.setText("Update")

    def _clear_chat_widgets(self) -> None:
        while self._chat_layout.count():
            item = self._chat_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _render_chat(self) -> None:
        self._my_identities = _current_user_identities()
        self._clear_chat_widgets()
        if self._current_validation_id() is None:
            blank = QLabel("Select a validation row to view its chat.")
            blank.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
            self._chat_layout.addWidget(blank)
            self._chat_layout.addStretch(1)
            return
        if self._chat_loading:
            loading = QLabel("Loading chat...")
            loading.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
            self._chat_layout.addWidget(loading)
            self._chat_layout.addStretch(1)
            return
        if not self._chat_rows:
            blank = QLabel("No comments yet. Start the conversation.")
            blank.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
            self._chat_layout.addWidget(blank)
            self._chat_layout.addStretch(1)
            return
        for row in self._chat_rows:
            self._chat_layout.addWidget(self._build_chat_row(row))
        self._chat_layout.addStretch(1)
        QTimer.singleShot(0, self._scroll_chat_to_bottom)

    def _scroll_chat_to_bottom(self) -> None:
        bar = self._chat_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _build_chat_row(self, row: dict[str, Any]) -> QWidget:
        author = str(row.get("author", "") or "").strip() or "Unknown"
        when_raw = _created_at_from_row(row)
        when = _format_cell(when_raw, "createdAt", _COMMENT_CREATED_AT_KEYS)
        cid = _comment_id_from_row(row)
        window_open = self._is_edit_window_open(when_raw)
        show_pencil = _author_is_current_user(author, self._my_identities) and cid is not None
        pencil_enabled = show_pencil and window_open
        text = str(row.get("comment", "") or "")

        wrap = QWidget()
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 6, 0, 6)
        outer.setSpacing(4)

        meta = QLabel(author + (f"  ·  {when}" if when else ""))
        meta.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        meta.setWordWrap(True)
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(6)
        meta_row.addWidget(meta, 1)
        if show_pencil:
            edit_btn = QPushButton("✎")
            edit_btn.setToolTip(
                "Edit message (within 5 minutes of server post time)"
                if pencil_enabled
                else "Cannot edit: more than 5 minutes since this message (server time)"
            )
            edit_btn.setFixedSize(26, 26)
            edit_btn.setCursor(
                Qt.CursorShape.PointingHandCursor if pencil_enabled else Qt.CursorShape.ForbiddenCursor
            )
            if pencil_enabled:
                edit_btn.setStyleSheet(
                    "QPushButton { background: transparent; border: none; "
                    "color: #334155; font-size: 14px; font-weight: 700; padding: 0; }"
                    "QPushButton:hover { color: #0f172a; }"
                )
            else:
                edit_btn.setStyleSheet(
                    "QPushButton { background: transparent; border: none; "
                    "color: #94a3b8; font-size: 14px; font-weight: 700; padding: 0; }"
                )
            edit_btn.setEnabled(pencil_enabled)
            row_copy = dict(row)
            if cid is not None and "commentId" not in row_copy:
                row_copy["commentId"] = cid
            edit_btn.clicked.connect(lambda _checked=False, r=row_copy: self._start_edit_comment(r))
            meta_row.addWidget(edit_btn, 0, Qt.AlignmentFlag.AlignRight)
        outer.addLayout(meta_row)

        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet(f"color: #0f172a; font-size: {APP_FONT_SIZE_PX}px;")
        outer.addWidget(body)

        return wrap

    def _flash_status(self, text: str, *, error: bool) -> None:
        self._status.setText(text)
        self._status.setStyleSheet(FORM_ERROR_LABEL_STYLE if error else MODAL_FEEDBACK_SUCCESS_STYLE)
        self._status.setVisible(True)

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None
