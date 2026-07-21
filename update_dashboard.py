#!/usr/bin/env python3
"""Single entrypoint for the Korea market dashboard pipeline.

Run only this file from GitHub Actions or locally. Legacy versioned scripts remain
internal compatibility modules until they are gradually consolidated.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
LATEST_PIPELINE = SCRIPTS / "update_dashboard_v17.py"


def main() -> None:
    if not LATEST_PIPELINE.exists():
        raise FileNotFoundError(f"Dashboard pipeline not found: {LATEST_PIPELINE}")
    sys.path.insert(0, str(SCRIPTS))
    runpy.run_path(str(LATEST_PIPELINE), run_name="__main__")


if __name__ == "__main__":
    main()
