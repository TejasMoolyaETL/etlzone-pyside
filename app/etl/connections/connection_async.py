"""Background API calls for ETL connection test/save (create + update UI)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from ui.form_page_styles import APP_FONT_SIZE_PX
from ui.theme import Theme

CONNECTION_FEEDBACK_PENDING_STYLE = (
    f"color: {Theme.TEXT_SECONDARY}; font-size: {APP_FONT_SIZE_PX}px; font-weight: 500;"
)


class ConnectionApiWorker(QObject):
    finished = Signal(object)

    def __init__(
        self,
        payload: dict[str, Any],
        on_call: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        fail_prefix: str,
    ) -> None:
        super().__init__()
        self._payload = payload
        self._on_call = on_call
        self._fail_prefix = fail_prefix

    @Slot()
    def run(self) -> None:
        try:
            result = self._on_call(self._payload)
        except Exception as exc:
            result = {"success": False, "message": f"{self._fail_prefix} ({type(exc).__name__})."}
        self.finished.emit(result)
