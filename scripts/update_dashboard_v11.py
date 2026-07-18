#!/usr/bin/env python3
"""Dashboard v11: v10 data collection plus non-blank foreign metric cards."""
from __future__ import annotations

import json
import re
from pathlib import Path

import update_dashboard as base
import update_dashboard_v7 as v7
import update_dashboard_v8 as v8
import update_dashboard_v9 as v9
import update_dashboard_v10 as v10  # applies robust daily foreign-flow parser


def finalise_html() -> None:
    path: Path = base.OUTPUT_HTML
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(<script id="embedded" type="application/json">).*?(</script>)', r'\1{}\2', text, flags=re.S)
    text = re.sub(r'href="styles\.css(?:\?v=\d+)?"', 'href="styles.css?v=11"', text)
    for name in ("core", "charts", "panels"):
        text = re.sub(rf'src="js/{name}\.js(?:\?v=\d+)?"', f'src="js/{name}.js?v=11"', text)
    text = re.sub(r'src="js/app\.js(?:\?v=\d+)?"', 'src="js/app.js?v=11"', text)
    if 'js/foreign-fix.js' not in text:
        text = text.replace(
            '<script src="js/app.js?v=11"></script>',
            '<script src="js/foreign-fix.js?v=11"></script>\n<script src="js/app.js?v=11"></script>',
        )
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    base.main()
    payload = json.loads(base.OUTPUT_JSON.read_text(encoding="utf-8"))
    payload["cycle_signals"] = v8.build_cycle_signals(payload)
    payload["cycle_signals"]["foreign"]["collection_errors"] = payload["cycle_signals"].get("errors", [])
    base.OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    v7.append_archives()
    v9.persist_foreign_archives(payload)
    finalise_html()
    print("dashboard v11 foreign cards updated")
