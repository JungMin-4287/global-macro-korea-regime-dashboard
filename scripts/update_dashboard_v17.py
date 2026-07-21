#!/usr/bin/env python3
"""Dashboard v17: add a compact Evercore mid-cycle clock to the existing SOX card.

No new dashboard panel is created. Daily data updates:
- SOX drawdown from its 252-session closing peak;
- elapsed calendar weeks and trading days since that peak;
- SOX relative performance versus the S&P 500 from the same date.

The SOX/SPX relative P/E is a dated manual research snapshot because a stable,
free daily forward-P/E series is not available. It is never added to the 0/4
trend-rebound score.
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

base.ASSETS["SPX"] = {"name": "S&P500", "type": "benchmark", "yf": "^GSPC"}


def _num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def _frame(asset: dict[str, Any]) -> pd.DataFrame:
    rows = asset.get("history") or []
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out["date"] = pd.to_datetime(out.get("date"), errors="coerce")
    out["close"] = pd.to_numeric(out.get("close"), errors="coerce")
    return out.dropna(subset=["date", "close"]).sort_values("date").set_index("date")


def build_mid_cycle_clock(payload: dict[str, Any]) -> dict[str, Any]:
    assets = payload.get("assets") or {}
    manual = payload.get("manual") or {}
    ref = manual.get("mid_cycle_correction_reference") or {}
    sox = _frame(assets.get("SOX") or {}).tail(252)
    spx = _frame(assets.get("SPX") or {}).tail(520)

    if sox.empty:
        return {
            "available": False,
            "judgement": "SOX 시계 미산출",
            "interpretation": "SOX 종가 이력을 받지 못했습니다.",
            "reference": ref,
            "not_in_trend_rebound_gate_score": True,
        }

    peak_date = sox["close"].idxmax()
    peak_close = float(sox.loc[peak_date, "close"])
    current_date = sox.index[-1]
    current_close = float(sox["close"].iloc[-1])
    drawdown = base.cf((current_close / peak_close - 1) * 100)
    trading_days = int(max(0, sox.loc[peak_date:].shape[0] - 1))
    calendar_weeks = base.cf(max(0.0, (current_date - peak_date).days / 7.0))

    spx_return = None
    relative_return = None
    if not spx.empty:
        window = spx[(spx.index >= peak_date) & (spx.index <= current_date)]
        if len(window) >= 2:
            spx_return = base.cf((float(window["close"].iloc[-1]) / float(window["close"].iloc[0]) - 1) * 100)
            relative_return = base.cf(drawdown - spx_return) if drawdown is not None else None

    average_dd = _num(ref.get("average_sox_drawdown_pct")) or -13.0
    median_weeks = _num(ref.get("median_duration_weeks")) or 6.0
    trough_relative_pe = _num(ref.get("trough_relative_pe_to_spx")) or 1.0
    current_relative_pe = _num(ref.get("current_relative_pe_to_spx_snapshot"))

    magnitude_confirmed = bool(drawdown is not None and drawdown <= average_dd)
    duration_confirmed = bool(calendar_weeks is not None and calendar_weeks >= median_weeks)
    valuation_confirmed = bool(current_relative_pe is not None and current_relative_pe <= trough_relative_pe + 0.05)
    valuation_partial = bool(current_relative_pe is not None and current_relative_pe <= 1.10 and not valuation_confirmed)

    conditions = [
        {
            "name": "낙폭",
            "confirmed": magnitude_confirmed,
            "partial": False,
            "current": drawdown,
            "target": average_dd,
            "text": f"현재 {drawdown}% · 역사 평균 {average_dd}%",
            "update_mode": "daily",
        },
        {
            "name": "기간",
            "confirmed": duration_confirmed,
            "partial": bool(calendar_weeks is not None and calendar_weeks >= max(0, median_weeks - 1) and not duration_confirmed),
            "current": calendar_weeks,
            "target": median_weeks,
            "text": f"현재 {calendar_weeks}주 · 중간값 {median_weeks}주",
            "update_mode": "daily",
        },
        {
            "name": "상대 PER",
            "confirmed": valuation_confirmed,
            "partial": valuation_partial,
            "current": current_relative_pe,
            "target": trough_relative_pe,
            "text": f"현재 {current_relative_pe}배 · 역사 바닥 {trough_relative_pe}배",
            "update_mode": "manual_snapshot",
        },
    ]
    score = sum(bool(item["confirmed"]) for item in conditions)

    memory = manual.get("memory") or {}
    dram_up = str(memory.get("dram_price_momentum") or "").lower() in {"up", "rising", "상승", "상향"}
    eps_up = str(memory.get("earnings_revision_breadth") or "").lower() in {"up", "rising", "상승", "상향"}
    fundamentals_intact = bool(dram_up and eps_up)

    if score == 3:
        judgement = "역사적 미드사이클 바닥 조건 충족"
        interpretation = "낙폭·기간·상대 밸류에이션이 모두 과거 바닥 범위에 들어왔습니다. 다만 실제 매수 등급 상향은 외국인 수급과 가격 반응 게이트가 확인될 때만 허용합니다."
    elif score == 2:
        judgement = "미드사이클 바닥 접근"
        interpretation = "세 조건 중 두 가지가 충족됐습니다. 남은 조건이 채워지는 동안 전저점 방어와 SOX 상대강도 회복을 확인합니다."
    elif magnitude_confirmed:
        judgement = "낙폭은 충분·시간과 밸류 확인 필요"
        interpretation = "가격 조정은 역사 평균보다 깊지만 조정 기간과 상대 PER가 과거 바닥 수준에 완전히 도달하지 않았습니다. 추가 하락보다 2~3주 박스권으로 시간을 채울 수도 있습니다."
    else:
        judgement = "미드사이클 조정 진행"
        interpretation = "아직 과거 평균 낙폭·기간·밸류에이션 바닥 조건이 충분히 충족되지 않았습니다."

    if fundamentals_intact:
        interpretation += " DRAM 가격과 EPS 방향이 상향인 현재 조합은 확정적 다운사이클보다 포지션·밸류에이션 조정 가설을 지지합니다."
    else:
        interpretation += " DRAM 가격이나 EPS가 하향으로 바뀌면 미드사이클 가설보다 다운사이클 선반영 위험을 높여야 합니다."

    return {
        "available": True,
        "score": score,
        "total": 3,
        "judgement": judgement,
        "interpretation": interpretation,
        "peak_date": peak_date.strftime("%Y-%m-%d"),
        "current_date": current_date.strftime("%Y-%m-%d"),
        "peak_close": base.cf(peak_close),
        "current_close": base.cf(current_close),
        "drawdown_pct": drawdown,
        "trading_days_since_peak": trading_days,
        "calendar_weeks_since_peak": calendar_weeks,
        "spx_return_since_sox_peak_pct": spx_return,
        "sox_relative_return_vs_spx_pct": relative_return,
        "relative_pe_to_spx_snapshot": current_relative_pe,
        "relative_pe_reference_date": ref.get("reference_date"),
        "relative_pe_is_manual": True,
        "conditions": conditions,
        "fundamentals_intact": fundamentals_intact,
        "historical_post_correction_bounce_pct": ref.get("average_post_correction_bounce_pct"),
        "historical_post_correction_bounce_weeks": ref.get("average_post_correction_bounce_weeks"),
        "reference": ref,
        "not_in_trend_rebound_gate_score": True,
        "updated_at": payload.get("generated_at"),
    }


def adjust_actual_vkospi_gate(payload: dict[str, Any], macro: dict[str, Any]) -> None:
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


def finalise_html_v17() -> None:
    path: Path = base.OUTPUT_HTML
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(<script id="embedded" type="application/json">).*?(</script>)', r'\1{}\2', text, flags=re.S)
    for css in ("styles", "gate", "positioning", "midcycle"):
        if css == "midcycle" and "midcycle.css" not in text:
            text = text.replace('</head>', '  <link rel="stylesheet" href="midcycle.css?v=17">\n</head>')
        else:
            text = re.sub(rf'href="{css}\.css(?:\?v=\d+)?"', f'href="{css}.css?v=17"', text)
    for name in ("core", "charts", "psychology-fix", "panels", "foreign-fix", "gate", "positioning", "app"):
        text = re.sub(rf'src="js/{name}\.js(?:\?v=\d+)?"', f'src="js/{name}.js?v=17"', text)
    if "js/midcycle.js" not in text:
        text = text.replace('<script src="js/app.js?v=17"></script>', '<script src="js/midcycle.js?v=17"></script>\n<script src="js/app.js?v=17"></script>')
    else:
        text = re.sub(r'src="js/midcycle\.js(?:\?v=\d+)?"', 'src="js/midcycle.js?v=17"', text)
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
    adjust_actual_vkospi_gate(payload, macro)
    payload["positioning_analysis"] = v15.build_positioning_analysis(payload)
    payload["mid_cycle_clock"] = build_mid_cycle_clock(payload)
    base.OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    v7.append_archives()
    v9.persist_foreign_archives(payload)
    v13.finalise_html_v13()
    v14.finalise_html_v14()
    v15.finalise_html_v15()
    finalise_html_v17()
    print("dashboard v17 Evercore mid-cycle clock updated")
