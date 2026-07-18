#!/usr/bin/env python3
"""Dashboard v7.

- Keep the public HTML lightweight: load market_data.json at runtime instead of
  embedding the complete history in every HTML rebuild.
- Append one deduplicated end-of-day row per asset to daily_archive.csv.
- Preserve the v6 VKOSPI history enhancements and data-source fallbacks.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

import update_dashboard as base
import update_dashboard_v6 as v6  # noqa: F401 - applies v5/v6 patches

ARCHIVE = base.DATA_DIR / "daily_archive.csv"


def append_daily_archive() -> None:
    payload = json.loads(base.OUTPUT_JSON.read_text(encoding="utf-8"))
    generated_at = payload.get("generated_at")
    rows = []
    for key, asset in (payload.get("assets") or {}).items():
        rows.append({
            "date": asset.get("date"),
            "asset": key,
            "name": asset.get("name"),
            "close": asset.get("close"),
            "change_pct": asset.get("change_pct"),
            "ratio30": asset.get("ratio30"),
            "ratio50": asset.get("ratio50"),
            "ratio60": asset.get("ratio60"),
            "ratio100": asset.get("ratio100"),
            "ratio120": asset.get("ratio120"),
            "ratio200": asset.get("ratio200"),
            "current_drawdown_pct": asset.get("current_drawdown_pct"),
            "mdd_252_pct": asset.get("mdd_252_pct"),
            "source": asset.get("source"),
            "generated_at": generated_at,
        })
    if not rows:
        return

    latest = pd.DataFrame(rows)
    if ARCHIVE.exists():
        try:
            old = pd.read_csv(ARCHIVE)
            latest = pd.concat([old, latest], ignore_index=True)
        except Exception:
            pass
    latest = latest.dropna(subset=["date", "asset"])
    latest = latest.drop_duplicates(["date", "asset"], keep="last").sort_values(["date", "asset"])
    latest.to_csv(ARCHIVE, index=False, encoding="utf-8-sig")


def make_html_lightweight() -> None:
    path: Path = base.OUTPUT_HTML
    text = path.read_text(encoding="utf-8")
    text = re.sub(
        r'(<script id="embedded" type="application/json">).*?(</script>)',
        r'\1{}\2',
        text,
        flags=re.S,
    )
    replacements = {
        'href="styles.css"': 'href="styles.css?v=7"',
        'href="styles.css?v=6"': 'href="styles.css?v=7"',
        'src="js/core.js"': 'src="js/core.js?v=7"',
        'src="js/core.js?v=6"': 'src="js/core.js?v=7"',
        'src="js/charts.js"': 'src="js/charts.js?v=7"',
        'src="js/charts.js?v=6"': 'src="js/charts.js?v=7"',
        'src="js/panels.js"': 'src="js/panels.js?v=7"',
        'src="js/panels.js?v=6"': 'src="js/panels.js?v=7"',
        'src="js/app.js"': 'src="js/app.js?v=7"',
        'src="js/app.js?v=6"': 'src="js/app.js?v=7"',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    base.main()
    append_daily_archive()
    make_html_lightweight()
