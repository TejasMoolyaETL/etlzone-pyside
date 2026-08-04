"""Shared constants for Excel UI."""

from __future__ import annotations

IMPORT_STATE_NAV_ITEM = "Import State"
UPLOAD_FILE_NAV_ITEM = "Upload File"
EXTRACT_FILE_NAV_ITEM = "Extract File"

SOURCE_TYPE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Excel", "EXCEL"),
    ("CSV", "CSV"),
    ("JSON", "JSON"),
)
