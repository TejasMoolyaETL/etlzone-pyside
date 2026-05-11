"""Comment panel for selected DMT Object Tracker row."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QLabel, QWidget

from app.api_dev.api_dev_validation_all_in_one.api_dev_validation_comment_panel import (
    _COMMENT_AUX_LABEL_STYLE,
    _current_user_identities,
    ValidationCommentPanel,
)
from core.api import (
    api_add_object_tracker_comment,
    api_delete_object_tracker_comment_by_id,
    api_get_object_tracker_comments_by_object_id,
    api_update_object_tracker_comment_by_id,
)
from core.user_context import get_user_profile


def _auth_token() -> str | None:
    profile = get_user_profile()
    token = (
        profile.get("token")
        or profile.get("accessToken")
        or profile.get("access_token")
        or profile.get("jwt")
        or profile.get("id_token")
    )
    text = str(token or "").strip()
    return text if text else None


class _ObjectTrackerCommentWorker(QObject):
    """Background worker for object-tracker comment CRUD."""

    finished = Signal(dict)

    def __init__(self, op: str, object_id: Any, text: str, token: str | None) -> None:
        super().__init__()
        self._op = op
        self._object_id = object_id
        self._text = text
        self._token = token

    @Slot()
    def run(self) -> None:  # noqa: D401 - Qt slot
        try:
            tk = self._token
            if self._op == "get_all":
                self.finished.emit(api_get_object_tracker_comments_by_object_id(self._object_id, token=tk))
                return
            if self._op == "add":
                self.finished.emit(api_add_object_tracker_comment(self._object_id, self._text, token=tk))
                return
            if self._op == "update":
                self.finished.emit(api_update_object_tracker_comment_by_id(self._object_id, self._text, token=tk))
                return
            if self._op == "delete":
                self.finished.emit(api_delete_object_tracker_comment_by_id(self._object_id, token=tk))
                return
            self.finished.emit({"success": False, "message": f"Unsupported op '{self._op}'."})
        except Exception as exc:  # pragma: no cover - defensive worker guard
            self.finished.emit({"success": False, "message": f"{exc}"})


class ObjectTrackerCommentPanel(ValidationCommentPanel):
    """Reuse All-in-One comment UI for DMT tracker comments."""

    def __init__(self, vp: Any, parent: QWidget | None = None) -> None:
        super().__init__(vp, parent)
        title = self.findChild(QLabel, "commentPanelHeaderTitle")
        header = title.parentWidget() if title is not None else None
        if header is not None:
            header.setVisible(False)
            header.setMaximumHeight(0)
            header.setMinimumHeight(0)

    def _refresh_comment_access(self) -> None:
        # Object tracker comments do not have separate nav action keys yet.
        self._can_comment_display = True
        self._can_comment_create = True
        self._can_comment_edit = True
        self._can_comment_delete = True
        self._update_context()

    def _current_validation_id(self) -> Any:
        row = self._vp.get_selected_row()
        if not row:
            return None
        return row.get("objectTrackerId") or row.get("trackerId") or row.get("id")

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
        self._worker = _ObjectTrackerCommentWorker(op, validation_id, text, _auth_token())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()

    def _render_chat(self) -> None:
        self._my_identities = _current_user_identities()
        self._clear_chat_widgets()
        if self._current_validation_id() is None:
            blank = QLabel("Select an object tracker row to view its chat.")
            blank.setStyleSheet(_COMMENT_AUX_LABEL_STYLE)
            self._chat_layout.addWidget(blank)
            self._chat_layout.addStretch(1)
            return
        if not self._can_comment_display:
            blank = QLabel("Require Permission.")
            blank.setStyleSheet(_COMMENT_AUX_LABEL_STYLE)
            self._chat_layout.addWidget(blank)
            self._chat_layout.addStretch(1)
            return
        if self._chat_loading:
            loading = QLabel("Loading chat...")
            loading.setStyleSheet(_COMMENT_AUX_LABEL_STYLE)
            self._chat_layout.addWidget(loading)
            self._chat_layout.addStretch(1)
            return
        if not self._chat_rows:
            blank = QLabel("No comments yet. Start the conversation.")
            blank.setStyleSheet(_COMMENT_AUX_LABEL_STYLE)
            self._chat_layout.addWidget(blank)
            self._chat_layout.addStretch(1)
            return
        for row in self._chat_rows:
            self._chat_layout.addWidget(self._build_chat_row(row))
        self._chat_layout.addStretch(1)
        QTimer.singleShot(0, self._scroll_chat_to_bottom)
