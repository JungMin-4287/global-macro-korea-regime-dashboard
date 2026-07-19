#!/usr/bin/env python3
"""Dashboard v14.

- Add USD/KRW as a hidden macro input, not as a new chart panel.
- Combine existing earnings, foreign-flow, VKOSPI and price-response data into
  one compact 0/4 trend-rebound gate.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import update_dashboard as base
import update_dashboard_v7 as v7
import update_dashboard_v8 as v8
import update_dashboard_v9 as v9
import update_dashboard_v10 as v10  # noqa: F401
import update_dashboard_v11 as v11  # noqa: F401
import update_dashboard_v12 as v12
import update_dashboard_v13 as v13

base.ASSETS["USDKRW"] = {"name": "원/달러", "type": "macro", "yf": "KRW=X"}


def _num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def _history(asset: dict[str, Any]) -> pd.DataFrame:
    rows = asset.get("history") or []
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame.get("date"), errors="coerce")
    frame["close"] = pd.to_numeric(frame.get("close"), errors="coerce")
    return frame.dropna(subset=["date", "close"]).sort_values("date").set_index("date")


def _return(asset: dict[str, Any], days: int) -> float | None:
    frame = _history(asset)
    if len(frame) <= days:
        return None
    start = float(frame.close.iloc[-days - 1])
    return base.cf((float(frame.close.iloc[-1]) / start - 1) * 100) if start else None


def _defended_recent_low(asset: dict[str, Any], days: int = 5) -> bool:
    frame = _history(asset)
    if len(frame) <= days:
        return False
    latest = float(frame.close.iloc[-1])
    prior_low = float(frame.close.iloc[-days - 1:-1].min())
    return latest >= prior_low


def build_macro_context(payload: dict[str, Any]) -> dict[str, Any]:
    assets = payload.get("assets") or {}
    fx = assets.get("USDKRW") or {}
    vk = assets.get("VKOSPI") or {}
    fx_frame = _history(fx)

    fx_5d = _return(fx, 5)
    fx_vol20 = None
    fx_prev_vol20 = None
    if len(fx_frame) >= 26:
        returns = fx_frame.close.pct_change().dropna()
        fx_vol20 = base.cf(float(returns.tail(20).std()) * np.sqrt(252) * 100)
        fx_prev_vol20 = base.cf(float(returns.iloc[:-5].tail(20).std()) * np.sqrt(252) * 100)
    vol_change = base.cf(fx_vol20 - fx_prev_vol20) if fx_vol20 is not None and fx_prev_vol20 is not None else None

    fx_stable = fx_5d is not None and fx_5d <= 0.5 and (vol_change is None or vol_change <= 0)
    fx_risk = fx_5d is not None and fx_5d >= 1.5
    vk_change = _num(vk.get("change_pct"))
    vk_close = _num(vk.get("close"))
    vk_sma20 = _num(vk.get("sma20"))
    vk_falling = vk_change is not None and vk_change < 0 and (vk_sma20 is None or (vk_close is not None and vk_close <= vk_sma20))

    if fx_stable and vk_falling:
        combined = "원/달러 상승 압력과 국내 공포가 함께 완화되고 있어 외국인 수급 회복에 유리한 환경입니다."
    elif fx_risk and not vk_falling:
        combined = "원/달러와 VKOSPI가 모두 불안해 외국인 수급과 반도체 반등 신뢰도를 낮춥니다."
    elif fx_stable:
        combined = "환율은 안정됐지만 VKOSPI 공포 완화가 아직 확인되지 않았습니다."
    elif vk_falling:
        combined = "VKOSPI는 하락 중이지만 원/달러 안정이 부족해 외국인 수급 회복을 확정하기 어렵습니다."
    else:
        combined = "환율과 VKOSPI가 동시에 안정되는지 추가 확인이 필요합니다."

    return {
        "usdkrw": {
            "date": fx.get("date"),
            "close": fx.get("close"),
            "change_1d_pct": fx.get("change_pct"),
            "change_5d_pct": fx_5d,
            "realized_vol_20d_pct": fx_vol20,
            "previous_realized_vol_20d_pct": fx_prev_vol20,
            "vol_change_5d_pp": vol_change,
            "stable": fx_stable,
            "risk": fx_risk,
            "source": fx.get("source"),
            "interpretation": "안정" if fx_stable else "급등 위험" if fx_risk else "중립·관찰",
        },
        "vkospi_falling": vk_falling,
        "combined_confirmed": bool(fx_stable and vk_falling),
        "combined_interpretation": combined,
    }


def build_trend_gate(payload: dict[str, Any], macro: dict[str, Any]) -> dict[str, Any]:
    assets = payload.get("assets") or {}
    cycle = payload.get("cycle_signals") or {}
    foreign = cycle.get("foreign") or {}
    earnings_rows = (cycle.get("earnings_trust") or {}).get("rows") or []

    earnings_statuses = [str(row.get("status") or "") for row in earnings_rows]
    earnings_confirmed = any("하향 조정에 둔감" in x for x in earnings_statuses) and not any(
        "상향에도 주가 약세" in x or "하향 조정에 민감" in x for x in earnings_statuses
    )
    earnings_partial = any(row.get("available") for row in earnings_rows) and not earnings_confirmed
    earnings_short = next((x for x in earnings_statuses if "스냅샷 축적 중" not in x), "신규 EPS 스냅샷 대기")

    flow20 = _num(foreign.get("net_buy_20d_trn"))
    sam_own = _num(foreign.get("samsung_foreign_ownership_20d_change_pp"))
    hyn_own = _num(foreign.get("skhynix_foreign_ownership_20d_change_pp"))
    ownership_values = [x for x in (sam_own, hyn_own) if x is not None]
    foreign_confirmed = bool(flow20 is not None and flow20 > 0 and len(ownership_values) == 2 and all(x > 0 for x in ownership_values))
    foreign_partial = bool((flow20 is not None and flow20 > 0) or any(x > 0 for x in ownership_values)) and not foreign_confirmed
    foreign_short = f"20일 {base.cf(flow20)}조원 · 지분율 {base.cf(sam_own)}/{base.cf(hyn_own)}%p"

    macro_confirmed = bool(macro.get("combined_confirmed"))
    fx = macro.get("usdkrw") or {}
    macro_partial = bool(fx.get("stable") or macro.get("vkospi_falling")) and not macro_confirmed
    macro_short = f"원/달러 5일 {base.cf(fx.get('change_5d_pct'))}% · VKOSPI {'하락' if macro.get('vkospi_falling') else '미확인'}"

    sox = assets.get("SOX") or {}
    sox5 = _return(sox, 5)
    stock_checks = []
    for key in ("SAMSUNG", "SKHYNIX"):
        asset = assets.get(key) or {}
        r5 = _return(asset, 5)
        relative = r5 is not None and sox5 is not None and r5 > sox5
        defended = _defended_recent_low(asset, 5)
        rebound = bool(asset.get("rebound_3d"))
        stock_checks.append({"key": key, "relative": relative, "defended": defended, "rebound": rebound, "ok": defended and (relative or rebound)})
    price_confirmed = len(stock_checks) == 2 and all(x["ok"] for x in stock_checks)
    price_partial = any(x["ok"] for x in stock_checks) and not price_confirmed
    price_short = " · ".join(f"{x['key']} {'방어' if x['defended'] else '신저점 위험'}/{ '상대강도' if x['relative'] else 'RS 미확인'}" for x in stock_checks)

    components = [
        {"name": "이익 신뢰", "confirmed": earnings_confirmed, "partial": earnings_partial, "short": earnings_short},
        {"name": "외국인 수급", "confirmed": foreign_confirmed, "partial": foreign_partial, "short": foreign_short},
        {"name": "환율·변동성", "confirmed": macro_confirmed, "partial": macro_partial, "short": macro_short},
        {"name": "가격 반응", "confirmed": price_confirmed, "partial": price_partial, "short": price_short},
    ]
    score = sum(bool(item["confirmed"]) for item in components)
    if score >= 4:
        judgement = "추세 반등 확인"
        interpretation = "네 조건이 동시에 충족됐습니다. 기존 과매도 반등이 추세 반등으로 전환됐을 가능성이 높습니다."
    elif score == 3:
        judgement = "1차 분할매수 검토"
        interpretation = "대부분의 조건이 개선됐습니다. 남은 한 조건과 치명적 위험 부재를 확인한 뒤 비중을 늘립니다."
    elif score == 2:
        judgement = "탐색매수 가능"
        interpretation = "바닥 후보 신호는 늘었지만 추세 반전 확정은 아닙니다. 예정 비중의 일부만 허용합니다."
    else:
        judgement = "과매도·기술적 반등 단계"
        interpretation = "과매도 근거와 추세 반등 확인을 구분해야 합니다. 외국인 수급과 가격 반응이 회복되기 전에는 등급을 올리지 않습니다."

    return {
        "score": score,
        "total": 4,
        "judgement": judgement,
        "interpretation": interpretation,
        "components": components,
        "note": "MDD·DRAM 가격·ETF 유입은 가점일 뿐, 이 4개 게이트를 대체하지 않습니다.",
        "updated_at": payload.get("generated_at"),
    }


def finalise_html_v14() -> None:
    path: Path = base.OUTPUT_HTML
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(<script id="embedded" type="application/json">).*?(</script>)', r'\1{}\2', text, flags=re.S)
    text = re.sub(r'href="styles\.css(?:\?v=\d+)?"', 'href="styles.css?v=14"', text)
    text = re.sub(r'href="gate\.css(?:\?v=\d+)?"', 'href="gate.css?v=14"', text)
    for name in ("core", "charts", "psychology-fix", "panels", "foreign-fix", "gate", "app"):
        text = re.sub(rf'src="js/{name}\.js(?:\?v=\d+)?"', f'src="js/{name}.js?v=14"', text)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    base.main()
    payload = json.loads(base.OUTPUT_JSON.read_text(encoding="utf-8"))
    payload["cycle_signals"] = v8.build_cycle_signals(payload)
    v12.sanitise_errors(payload)
    v13.apply_event_gated_logic(payload)
    macro = build_macro_context(payload)
    payload["macro_context"] = macro
    payload["trend_rebound_gate"] = build_trend_gate(payload, macro)
    base.OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    v7.append_archives()
    v9.persist_foreign_archives(payload)
    v13.finalise_html_v13()
    finalise_html_v14()
    print("dashboard v14 USDKRW macro context and 4-gate trend score updated")
