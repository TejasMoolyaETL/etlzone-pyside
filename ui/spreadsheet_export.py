"""Write simple tabular data to .xlsx files."""

from __future__ import annotations

from typing import Any, Sequence


def write_xlsx(
    path: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    sheet_title: str = "Sheet1",
) -> None:
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise RuntimeError(
            "openpyxl is required to export Excel files. Install it with: pip install openpyxl"
        ) from exc

    wb = Workbook()
    ws = wb.active
    if ws is None:
        raise RuntimeError("Could not create worksheet.")
    ws.title = sheet_title[:31] or "Sheet1"
    ws.append(list(headers))
    for row in rows:
        ws.append(list(row))
    wb.save(path)
