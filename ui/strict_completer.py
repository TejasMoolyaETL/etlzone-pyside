"""Shared helpers for QCompleter-backed fields: only exact list display strings are valid."""

from __future__ import annotations

from typing import Iterable

from PySide6.QtWidgets import QCompleter

from ui.form_combobox_style import apply_completer_popup_list_style


def strict_list_selection_message(select_what: str) -> str:
    """User-facing error when text does not match an allowed completion.

    select_what: phrase after "select", e.g. "a project", "an organization".
    """
    return (
        f"Please select {select_what} from the search list. Typed values are not allowed."
    )


def style_completer_popup(completer: QCompleter | None) -> None:
    """Apply shared combo-list hover chrome to a line-edit :class:`QCompleter` popup."""
    apply_completer_popup_list_style(completer)
    if completer is not None:
        from ui.list_field_keyboard import install_line_edit_completer_tab_commit

        install_line_edit_completer_tab_commit(completer)


def is_exact_completion_display(text: str, allowed_displays: Iterable[str]) -> bool:
    """True if stripped text is exactly one of the allowed completion strings."""
    t = (text or "").strip()
    if not t:
        return False
    return t in set(allowed_displays)
