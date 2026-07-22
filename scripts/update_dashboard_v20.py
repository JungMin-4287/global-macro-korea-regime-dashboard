#!/usr/bin/env python3
"""Dashboard v20: use multi-horizon foreign-flow data instead of a fixed 20-day view.

The raw KOSPI foreign-flow and stock ownership histories already come from
KRX/pykrx with Naver Finance and GitHub CSV fallbacks. This version derives
1/5/10/20/60-session flow, acceleration, streak and ownership changes, then
uses both short-term reversal and medium-term persistence in the 0/4 gate.
No new dashboard panel is created.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd

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
import update_dashboard_v18 as v18
import update_dashboard_v19 as v19  # noqa: F401 - applies newest-price overlay

HORIZONS = (1, 5, 10, 20, 60)


def _num(value: Any) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _flow_series(foreign: dict[str, Any]) -> pd.Series:
    rows = foreign.get("points") or []
    if not rows:
        return pd.Series(dtype=float)
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame.get("date"), errors="coerce")
    frame["value"] = pd.to_numeric(frame.get("daily_net_buy_trn"), errors="coerce")
    return (
        frame.dropna(subset=["date", "value"])
        .drop_duplicates("date", keep="last")
        .set_index("date")["value"]
        .sort_index()
    )


def _ownership_series(foreign: dict[str, Any], key: str) -> pd.Series:
    rows = foreign.get("ownership") or []
    if not rows:
        return pd.Series(dtype=float)
    field = "samsung_pct" if key == "samsung" else "skhynix_pct"
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame.get("date"), errors="coerce")
    frame["value"] = pd.to_numeric(frame.get(field), errors="coerce")
    return (
        frame.dropna(subset=["date", "value"])
        .drop_duplicates("date", keep="last")
        .set_index("date")["value"]
        .sort_index()
    )


def _sum_tail(series: pd.Series, days: int) -> float | None:
    if series.empty:
        return None
    values = series.dropna().tail(days)
    return base.cf(values.sum()) if len(values) else None


def _change_tail(series: pd.Series, days: int) -> float | None:
    clean = series.dropna()
    if len(clean) <= days:
        return None
    return base.cf(float(clean.iloc[-1] - clean.iloc[-days - 1]))


def _streak(series: pd.Series) -> tuple[int, str]:
    clean = series.dropna()
    if clean.empty or float(clean.iloc[-1]) == 0:
        return 0, "중립"
    sign = 1 if float(clean.iloc[-1]) > 0 else -1
    count = 0
    for value in reversed(clean.tolist()):
        current = 1 if value > 0 else -1 if value < 0 else 0
        if current != sign:
            break
        count += 1
    return count, "순매수" if sign > 0 else "순매도"


def enrich_foreign_multi_horizon(payload: dict[str, Any]) -> None:
    cycle = payload.get("cycle_signals") or {}
    foreign = cycle.get("foreign") or {}
    flow = _flow_series(foreign)

    horizons = {str(days): _sum_tail(flow, days) for days in HORIZONS}
    prior_5d = base.cf(flow.iloc[-10:-5].sum()) if len(flow) >= 10 else None
    current_5d = horizons.get("5")
    acceleration_5d = base.cf(current_5d - prior_5d) if current_5d is not None and prior_5d is not None else None
    streak_days, streak_direction = _streak(flow)

    one = horizons.get("1")
    five = horizons.get("5")
    twenty = horizons.get("20")
    reversal = (
        "단기 순매수 반전" if one is not None and one > 0 and five is not None and five <= 0
        else "5일 순매수 전환" if five is not None and five > 0 and twenty is not None and twenty <= 0
        else "중기 순매수 지속" if five is not None and five > 0 and twenty is not None and twenty > 0
        else "순매도 지속" if five is not None and five < 0 and twenty is not None and twenty < 0
        else "혼조"
    )

    foreign["market_flow_multi_horizon"] = {
        "latest_date": flow.index[-1].strftime("%Y-%m-%d") if len(flow) else None,
        "net_buy_trn": horizons,
        "prior_5d_trn": prior_5d,
        "acceleration_5d_trn": acceleration_5d,
        "streak_days": streak_days,
        "streak_direction": streak_direction,
        "reversal_state": reversal,
        "observation_count": int(len(flow)),
        "source": foreign.get("source"),
    }
    for days in HORIZONS:
        foreign[f"net_buy_{days}d_trn"] = horizons.get(str(days))

    ownership_summary: dict[str, Any] = {}
    for key in ("samsung", "skhynix"):
        series = _ownership_series(foreign, key)
        changes = {str(days): _change_tail(series, days) for days in HORIZONS}
        ownership_summary[key] = {
            "latest_date": series.index[-1].strftime("%Y-%m-%d") if len(series) else None,
            "current_pct": base.cf(series.iloc[-1]) if len(series) else None,
            "change_pp": changes,
            "observation_count": int(len(series)),
        }
        for days in HORIZONS:
            foreign[f"{key}_foreign_ownership_{days}d_change_pp"] = changes.get(str(days))

    foreign["ownership_multi_horizon"] = ownership_summary

    sam5 = _num(foreign.get("samsung_foreign_ownership_5d_change_pp"))
    hyn5 = _num(foreign.get("skhynix_foreign_ownership_5d_change_pp"))
    sam20 = _num(foreign.get("samsung_foreign_ownership_20d_change_pp"))
    hyn20 = _num(foreign.get("skhynix_foreign_ownership_20d_change_pp"))

    short_turn = bool(five is not None and five > 0 and (prior_5d is None or five > prior_5d))
    medium_support = bool(twenty is not None and twenty > 0)
    ownership_short = bool(sam5 is not None and hyn5 is not None and sam5 > 0 and hyn5 > 0)
    ownership_medium = bool(sam20 is not None and hyn20 is not None and sam20 > 0 and hyn20 > 0)

    confirmed = bool(short_turn and medium_support and (ownership_short or ownership_medium))
    partial_checks = [
        bool(one is not None and one > 0),
        short_turn,
        medium_support,
        ownership_short,
        ownership_medium,
    ]
    partial_count = sum(partial_checks)
    partial = bool(not confirmed and partial_count >= 2)

    foreign["multi_horizon_gate"] = {
        "confirmed": confirmed,
        "partial": partial,
        "short_turn": short_turn,
        "medium_support": medium_support,
        "ownership_short": ownership_short,
        "ownership_medium": ownership_medium,
        "partial_count": partial_count,
        "signal": "수급 회복 확인" if confirmed else "단기 반전 진행" if partial else "외국인 매도 압력 지속",
        "logic": "1·5일 반전과 20일 지속성, 삼성전자·SK하이닉스 지분율 변화를 함께 평가",
    }
    foreign["signal"] = foreign["multi_horizon_gate"]["signal"]
    cycle["foreign"] = foreign
    payload["cycle_signals"] = cycle


def build_trend_gate_v20(payload: dict[str, Any], macro: dict[str, Any]) -> dict[str, Any]:
    gate = v14.build_trend_gate(payload, macro)
    foreign = ((payload.get("cycle_signals") or {}).get("foreign") or {})
    multi = foreign.get("market_flow_multi_horizon") or {}
    ownership = foreign.get("ownership_multi_horizon") or {}
    decision = foreign.get("multi_horizon_gate") or {}
    horizons = multi.get("net_buy_trn") or {}

    sam = ownership.get("samsung") or {}
    hyn = ownership.get("skhynix") or {}
    sam_change = sam.get("change_pp") or {}
    hyn_change = hyn.get("change_pp") or {}

    short = (
        f"1일 {base.cf(horizons.get('1'))}조원 · 5일 {base.cf(horizons.get('5'))}조원 · "
        f"20일 {base.cf(horizons.get('20'))}조원"
    )
    details = [
        f"5일 가속도 {base.cf(multi.get('acceleration_5d_trn'))}조원 · {multi.get('streak_days', 0)}일 연속 {multi.get('streak_direction', '중립')}",
        f"삼성 지분율 5일 {base.cf(sam_change.get('5'))}%p / 20일 {base.cf(sam_change.get('20'))}%p",
        f"하이닉스 지분율 5일 {base.cf(hyn_change.get('5'))}%p / 20일 {base.cf(hyn_change.get('20'))}%p",
        f"판정 {multi.get('reversal_state') or '-'} · 기준일 {multi.get('latest_date') or '-'}",
    ]

    for component in gate.get("components") or []:
        if component.get("name") == "외국인 수급":
            component["confirmed"] = bool(decision.get("confirmed"))
            component["partial"] = bool(decision.get("partial"))
            component["short"] = short
            component["details"] = details
            component["data_mode"] = "1·5·10·20·60일 다중 구간"

    score = sum(bool(item.get("confirmed")) for item in gate.get("components") or [])
    gate["score"] = score
    if score >= 4:
        gate["judgement"] = "추세 반등 확인"
        gate["interpretation"] = "네 조건이 동시에 충족됐습니다. 기존 과매도 반등이 추세 반등으로 전환됐을 가능성이 높습니다."
    elif score == 3:
        gate["judgement"] = "1차 분할매수 검토"
        gate["interpretation"] = "대부분의 조건이 개선됐습니다. 남은 한 조건과 치명적 위험 부재를 확인한 뒤 비중을 늘립니다."
    elif score == 2:
        gate["judgement"] = "탐색매수 가능"
        gate["interpretation"] = "바닥 후보 신호는 늘었지만 추세 반전 확정은 아닙니다. 예정 비중의 일부만 허용합니다."
    else:
        gate["judgement"] = "과매도·기술적 반등 단계"
        gate["interpretation"] = "과매도 근거와 추세 반등 확인을 구분해야 합니다. 단기 외국인 반전과 20일 지속성이 함께 확인되기 전에는 등급을 올리지 않습니다."
    gate["note"] = "외국인 수급은 20일 한 값이 아니라 1·5·10·20·60일 순매수, 5일 가속도와 종목별 지분율 변화를 함께 평가합니다."
    return gate


def finalise_html_v20() -> None:
    path: Path = base.OUTPUT_HTML
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(<script id="embedded" type="application/json">).*?(</script>)', r'\1{}\2', text, flags=re.S)
    text = re.sub(r'([?&]v=)\d+\b', r'\g<1>20', text)
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
    enrich_foreign_multi_horizon(payload)
    payload["trend_rebound_gate"] = build_trend_gate_v20(payload, macro)
    v17.adjust_actual_vkospi_gate(payload, macro)
    payload["positioning_analysis"] = v15.build_positioning_analysis(payload)
    payload["mid_cycle_clock"] = v17.build_mid_cycle_clock(payload)
    v19.audit_date_alignment(payload)
    base.OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    v7.append_archives()
    v9.persist_foreign_archives(payload)
    v13.finalise_html_v13()
    v14.finalise_html_v14()
    v15.finalise_html_v15()
    v17.finalise_html_v17()
    v18.finalise_html_v18()
    v19.finalise_html_v19()
    finalise_html_v20()
    print("dashboard v20 multi-horizon foreign-flow gate updated")
