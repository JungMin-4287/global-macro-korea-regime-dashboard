#!/usr/bin/env python3
"""Dashboard v6: preserve VKOSPI chart fields and cache-bust shareable assets."""
from __future__ import annotations

import update_dashboard as base
import update_dashboard_v5 as v5  # noqa: F401 - applies v5 data-source patches

ORIGINAL_METRICS = base.metrics


def metrics_v6(key, df, source):
    metrics, enriched = ORIGINAL_METRICS(key, df, source)
    if key != "VKOSPI":
        return metrics, enriched

    history = metrics.get("history") or []
    if history:
        tail = enriched.tail(len(history))
        for item, (_, row) in zip(history, tail.iterrows()):
            item["sma20"] = base.cf(row.get("sma20"))
            item["sma50"] = base.cf(row.get("sma50"))
    metrics["history_points"] = len(history)
    return metrics, enriched


def cache_bust_html():
    path = base.OUTPUT_HTML
    text = path.read_text(encoding="utf-8")
    replacements = {
        'href="styles.css"': 'href="styles.css?v=6"',
        'src="js/core.js"': 'src="js/core.js?v=6"',
        'src="js/charts.js"': 'src="js/charts.js?v=6"',
        'src="js/panels.js"': 'src="js/panels.js?v=6"',
        'src="js/app.js"': 'src="js/app.js?v=6"',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


base.metrics = metrics_v6

if __name__ == "__main__":
    base.main()
    cache_bust_html()
