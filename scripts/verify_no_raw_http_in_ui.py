#!/usr/bin/env python3
"""Fail if app/ or ui/ use raw HTTP clients — use core.api instead.

Run from repo root: python scripts/verify_no_raw_http_in_ui.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("app", "ui")

# Lines matching these patterns are forbidden outside core/api.py.
FORBIDDEN_LINE_RE = re.compile(
    r"(^\s*from\s+urllib\.|^\s*import\s+urllib\.|"
    r"^\s*from\s+requests\s+import|^\s*import\s+requests|"
    r"\burlopen\s*\()",
    re.MULTILINE,
)


def main() -> int:
    bad: list[str] = []
    for name in SCAN_DIRS:
        base = ROOT / name
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), start=1):
                if FORBIDDEN_LINE_RE.search(line):
                    rel = path.relative_to(ROOT)
                    bad.append(f"{rel}:{i}:{line.strip()}")
    if bad:
        print("Raw HTTP usage found in app/ or ui/ (use core.api instead):\n", file=sys.stderr)
        for item in bad:
            print(item, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
