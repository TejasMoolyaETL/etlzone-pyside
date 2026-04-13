"""HTTP method dropdown shared by API Details (create/view), API catalog create/edit dialogs, and anywhere else that needs the same list."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox

HTTP_API_METHODS: tuple[str, ...] = (
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "HEAD",
    "OPTIONS",
)


def configure_api_method_combo(
    combo: QComboBox,
    *,
    current: str | None = None,
    default_index: int = 0,
) -> None:
    """Populate the combo with standard methods; set selection from ``current`` (uppercased).

    If ``current`` is not in the standard list, it is inserted so existing API data still displays.
    """
    combo.clear()
    for m in HTTP_API_METHODS:
        combo.addItem(m)
    if current is not None and str(current).strip():
        u = str(current).strip().upper()
        if combo.findText(u) < 0:
            combo.insertItem(0, u)
        combo.setCurrentText(u)
    else:
        idx = min(max(default_index, 0), max(combo.count() - 1, 0))
        combo.setCurrentIndex(idx)
