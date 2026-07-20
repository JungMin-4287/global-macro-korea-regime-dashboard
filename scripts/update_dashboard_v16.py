#!/usr/bin/env python3
"""Dashboard v16: use actual VKOSPI only for the rebound gate.

A same-day manual actual VKOSPI snapshot can override a failed or proxy series.
A one-day decline is partial improvement only; gate ③ confirmation requires
an actual VKOSPI multi-day downtrend plus USD/KRW stability.
"""
from __future__ import annotations

import json

import update_dashboard as base
import update_dashboard_v7 as v7
import update_dashboard_v8 as v8
import update_dashboard_v9 as v9
import update_dashboard_v12 as v12
import update_dashboard_v13 as v13
import update_dashboard_v14 as v14
import update_dashboard_v15 as v15

VK_MANUAL = base.DATA_DIR / "vkospi_manual.json"


def apply_actual_vkospi_snapshot(payload: dict) -> None:
    try:
        snap = json.loads(VK_MANUAL.read_text(encoding="utf-8"))
    except Exception:
        return
    if not snap.get("date") or snap.get("close") is None:
        return

    assets = payload.setdefault("assets", {})
    previous = assets.get("VKOSPI") or {}
    proxy_kind = str(previous.get("data_kind") or "")
    proxy_source = str(previous.get("source") or "")
    is_proxy = "proxy" in proxy_kind.lower() or "실현변동성" in proxy_source or "대체" in proxy_source

    actual = dict(previous)
    if is_proxy:
        actual["proxy_close"] = previous.get("close")
        actual["proxy_change_pct"] = previous.get("change_pct")
        actual["proxy_source"] = previous.get("source")
        actual["history"] = []
        for key in list(actual):
            if key.startswith("sma") or key.startswith("ratio") or key.startswith("dev"):
                actual[key] = None

    actual.update({
        "name": "VKOSPI",
        "type": "volatility",
        "date": snap.get("date"),
        "close": snap.get("close"),
        "change_pct": snap.get("change_pct"),
        "source": snap.get("source"),
        "data_kind": snap.get("data_kind", "actual_vkospi_manual_snapshot"),
        "actual_vkospi": True,
        "is_closing_snapshot": bool(snap.get("is_closing_snapshot")),
        "trend_confirmation_available": False,
        "interpretation": "실제 VKOSPI 종가 스냅샷. 당일 하락은 부분 개선이며 3일·5일 하락 전환 확인 전에는 게이트 확정에 사용하지 않습니다.",
        "manual_note": snap.get("note"),
    })
    assets["VKOSPI"] = actual


def build_macro_context_actual(payload: dict) -> dict:
    macro = v14.build_macro_context(payload)
    vk = (payload.get("assets") or {}).get("VKOSPI") or {}
    actual = bool(vk.get("actual_vkospi"))
    one_day_falling = actual and vk.get("change_pct") is not None and float(vk.get("change_pct")) < 0
    trend_available = bool(vk.get("trend_confirmation_available"))

    if actual and not trend_available:
        macro["vkospi_falling"] = False
        macro["vkospi_partial_falling"] = one_day_falling
        macro["combined_confirmed"] = False
        fx_stable = bool((macro.get("usdkrw") or {}).get("stable"))
        if fx_stable and one_day_falling:
            macro["combined_interpretation"] = "원/달러는 안정되고 실제 VKOSPI도 당일 하락했지만, 3일·5일 하락 전환이 없어 게이트 ③은 부분 개선입니다."
        elif one_day_falling:
            macro["combined_interpretation"] = "실제 VKOSPI는 당일 하락했지만 원/달러 안정과 다일 하락 전환이 모두 확인되지 않아 부분 개선에 그칩니다."
        macro["vkospi_source_status"] = "actual_manual_snapshot_partial_only"
    return macro


if __name__ == "__main__":
    base.main()
    payload = json.loads(base.OUTPUT_JSON.read_text(encoding="utf-8"))
    payload["cycle_signals"] = v8.build_cycle_signals(payload)
    v12.sanitise_errors(payload)
    v13.apply_event_gated_logic(payload)
    apply_actual_vkospi_snapshot(payload)
    macro = build_macro_context_actual(payload)
    payload["macro_context"] = macro
    payload["trend_rebound_gate"] = v14.build_trend_gate(payload, macro)
    payload["positioning_analysis"] = v15.build_positioning_analysis(payload)

    gate = payload.get("trend_rebound_gate") or {}
    for component in gate.get("components") or []:
        if component.get("name") == "환율·변동성":
            fx = (macro.get("usdkrw") or {}).get("change_5d_pct")
            partial = bool((macro.get("usdkrw") or {}).get("stable") or macro.get("vkospi_partial_falling"))
            component["confirmed"] = bool(macro.get("combined_confirmed"))
            component["partial"] = partial and not component["confirmed"]
            component["short"] = f"원/달러 5일 {base.cf(fx)}% · 실제 VKOSPI 당일 하락/다일 전환 미확인"
    gate["score"] = sum(bool(x.get("confirmed")) for x in gate.get("components") or [])
    gate["note"] = "실제 VKOSPI와 실현변동성 대체값을 분리합니다. 단일 일간 하락은 부분 개선이며 게이트 점수에는 반영하지 않습니다."

    base.OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    v7.append_archives()
    v9.persist_foreign_archives(payload)
    v13.finalise_html_v13()
    v14.finalise_html_v14()
    v15.finalise_html_v15()
    print("dashboard v16 actual VKOSPI gate policy updated")
