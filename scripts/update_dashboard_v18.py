#!/usr/bin/env python3
"""Dashboard v18: render VKOSPI moving averages only with sufficient history.

The frontend recalculates 20-day and 50-day averages from valid VKOSPI closes.
Missing observations remain null, never zero, so Chart.js does not draw a false
vertical jump from zero. This version keeps the v17 mid-cycle clock intact.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import update_dashboard as base
import update_dashboard_v7 as v7
import update_dashboard_v8 as v8
import update_dashboard_v9 as v9
import update_dashboard_v12 as v12
import update_dashboard_v13 as v13
import update_dashboard_v14 as v14
import update_dashboard_v15 as v15
import update_dashboard_v16 as v16
import update_dashboard_v17 as v17


def finalise_html_v18() -> None:
    path: Path = base.OUTPUT_HTML
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(<script id="embedded" type="application/json">).*?(</script>)', r'\1{}\2', text, flags=re.S)

    for css in ("styles", "gate", "positioning", "midcycle"):
        text = re.sub(rf'href="{css}\.css(?:\?v=\d+)?"', f'href="{css}.css?v=18"', text)

    for name in ("core", "charts", "psychology-fix", "panels", "foreign-fix", "gate", "positioning", "midcycle", "app"):
        text = re.sub(rf'src="js/{name}\.js(?:\?v=\d+)?"', f'src="js/{name}.js?v=18"', text)

    if "js/vkospi-fix.js" not in text:
        text = text.replace(
            '<script src="js/app.js?v=18"></script>',
            '<script src="js/vkospi-fix.js?v=18"></script>\n<script src="js/app.js?v=18"></script>',
        )
    else:
        text = re.sub(r'src="js/vkospi-fix\.js(?:\?v=\d+)?"', 'src="js/vkospi-fix.js?v=18"', text)

    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    base.main()
    payload = json.loads(base.OUTPUT_JSON.read_text(encoding="utf-8"))
    payload["cycle_signals"] = v8.build_cycle_signals(payload)
    v12.sanitise_errors(payload)
    v13.apply_event_gated_logic(payload)
    v16.apply_actual_vkospi_snapshot(payload)
    macro = v16.build_macro_context_actual(payload)
    payload["macro_context"] = macro
    payload["trend_rebound_gate"] = v14.build_trend_gate(payload, macro)
    v17.adjust_actual_vkospi_gate(payload, macro)
    payload["positioning_analysis"] = v15.build_positioning_analysis(payload)
    payload["mid_cycle_clock"] = v17.build_mid_cycle_clock(payload)
    base.OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    v7.append_archives()
    v9.persist_foreign_archives(payload)
    v13.finalise_html_v13()
    v14.finalise_html_v14()
    v15.finalise_html_v15()
    v17.finalise_html_v17()
    finalise_html_v18()
    print("dashboard v18 VKOSPI rolling-average gap fix updated")
