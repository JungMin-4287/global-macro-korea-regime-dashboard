#!/usr/bin/env python3
"""Dashboard v6: preserve VKOSPI chart fields for the shareable HTML."""
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


base.metrics = metrics_v6

if __name__ == "__main__":
    base.main()
