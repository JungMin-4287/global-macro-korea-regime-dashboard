#!/usr/bin/env python3
"""Dashboard v13.

- Keep the existing indicator set; do not add a new panel.
- Apply the Hana oversold / hyperscaler-event framework as a judgement gate.
- Load the centred psychology-chart renderer with label clamping.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import update_dashboard as base
import update_dashboard_v7 as v7
import update_dashboard_v8 as v8
import update_dashboard_v9 as v9
import update_dashboard_v10 as v10  # noqa: F401
import update_dashboard_v11 as v11  # noqa: F401
import update_dashboard_v12 as v12  # applies KRX schema patch


def _num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if result == result else None
    except Exception:
        return None


def _return(asset: dict[str, Any], days: int) -> float | None:
    rows = asset.get("history") or []
    closes = [_num(row.get("close")) for row in rows]
    closes = [value for value in closes if value is not None]
    if len(closes) <= days or not closes[-days - 1]:
        return None
    return (closes[-1] / closes[-days - 1] - 1) * 100


def _positive_revision(value: Any) -> bool:
    text = str(value or "").lower()
    return any(token in text for token in ("up", "positive", "raise", "상향", "강화"))


def _negative_revision(value: Any) -> bool:
    text = str(value or "").lower()
    return any(token in text for token in ("down", "negative", "cut", "하향", "악화"))


def apply_event_gated_logic(payload: dict[str, Any]) -> None:
    manual = payload.get("manual") or {}
    logic = manual.get("hana_oversold_event_logic") or {}
    if not logic:
        return

    assets = payload.get("assets") or {}
    foreign = ((payload.get("cycle_signals") or {}).get("foreign") or {})
    ai = manual.get("ai_capex") or {}
    sox = assets.get("SOX") or {}
    sox_return_5d = _return(sox, 5)

    foreign_positive = (_num(foreign.get("net_buy_5d_trn")) or 0) > 0
    capex_positive = _positive_revision(ai.get("bigtech_capex_revision")) or _positive_revision(ai.get("cloud_growth_revision"))
    capex_negative = _negative_revision(ai.get("bigtech_capex_revision")) or _negative_revision(ai.get("cloud_growth_revision"))
    funding_stress = str(ai.get("oracle_credit_stress") or "").lower() in {"high", "worsening", "negative", "악화", "위험"}

    for key in ("SAMSUNG", "SKHYNIX"):
        asset = assets.get(key)
        if not asset:
            continue

        ratio30 = _num(asset.get("ratio30"))
        drawdown = _num(asset.get("current_drawdown_pct"))
        rebound = bool(asset.get("rebound_3d"))
        stock_return_5d = _return(asset, 5)
        relative_strength = (
            stock_return_5d is not None and sox_return_5d is not None and stock_return_5d > sox_return_5d
        )

        ownership_change_key = (
            "samsung_foreign_ownership_20d_change_pp"
            if key == "SAMSUNG"
            else "skhynix_foreign_ownership_20d_change_pp"
        )
        ownership_up = (_num(foreign.get(ownership_change_key)) or 0) > 0

        confirmations = {
            "3거래일 반전": rebound,
            "SOX 대비 5일 상대강도 개선": relative_strength,
            "KOSPI 외국인 5일 순매수": foreign_positive,
            "외국인 지분율 20일 상승": ownership_up,
            "빅테크 CAPEX·클라우드 상향": capex_positive,
        }
        confirmation_count = sum(bool(value) for value in confirmations.values())
        fatal_risk = capex_negative or funding_stress
        oversold = (
            ratio30 is not None
            and ratio30 < 98
            and drawdown is not None
            and drawdown <= (-20 if key == "SAMSUNG" else -30)
        )

        if key == "SAMSUNG":
            if fatal_risk:
                judgement = "매수 보류"
                sizing = "신규 매수 중단"
            elif oversold and confirmation_count >= 3 and rebound and foreign_positive:
                judgement = "1차 분할매수"
                sizing = "예정 비중의 20~30%"
            elif oversold:
                judgement = "실적 전 탐색매수"
                sizing = "예정 비중의 10~15% 이내"
            else:
                judgement = asset.get("signal") or "관찰"
                sizing = "기존 판정 유지"
        else:
            if fatal_risk:
                judgement = "매수 보류"
                sizing = "신규 매수 중단"
            elif oversold and confirmation_count >= 4 and rebound and foreign_positive:
                judgement = "1차 분할매수"
                sizing = "예정 비중의 20~30%"
            elif oversold and confirmation_count >= 2:
                judgement = "실적 전 탐색매수"
                sizing = "예정 비중의 10% 이내"
            elif oversold:
                judgement = "매수 보류·탐색매수 근접"
                sizing = "확인 신호 전 대기"
            else:
                judgement = asset.get("signal") or "관찰"
                sizing = "기존 판정 유지"

        asset["signal"] = judgement
        asset["trade_judgement"] = judgement
        asset["event_gate"] = {
            "confirmation_count": confirmation_count,
            "confirmations": confirmations,
            "fatal_risk": fatal_risk,
            "oversold_support_only": oversold,
            "allowed_sizing": sizing,
            "source": logic.get("source"),
            "rule": "MDD·DRAM 가격·ETF 유입은 과매도 가점일 뿐 단독 등급 상향 조건이 아니다.",
        }

        interpretation = asset.get("disparity_interpretation") or {}
        technical_action = interpretation.get("action") or ""
        checked = [name for name, value in confirmations.items() if value]
        waiting = [name for name, value in confirmations.items() if not value]
        interpretation["headline"] = f"기술적 구간: {interpretation.get('zone', '관찰')} · 트레이딩 판정: {judgement}"
        interpretation["action"] = (
            f"{technical_action} 하나증권 자료의 과매도 근거는 가점으로만 사용합니다. "
            f"현재 확인 {confirmation_count}개({', '.join(checked) if checked else '없음'}). "
            f"추가 확인: {', '.join(waiting[:3]) if waiting else '충족'}. 허용 비중: {sizing}."
        )
        asset["disparity_interpretation"] = interpretation

    payload["analysis_policy"] = {
        "new_indicator_policy": "필수성이 낮은 신규 지표·패널 추가 중단",
        "hana_logic_source": logic.get("source"),
        "hana_logic_usage": "기존 지표의 해석과 등급 상향 게이트로만 사용",
    }


def finalise_html_v13() -> None:
    path: Path = base.OUTPUT_HTML
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(<script id="embedded" type="application/json">).*?(</script>)', r'\1{}\2', text, flags=re.S)
    text = re.sub(r'href="styles\.css(?:\?v=\d+)?"', 'href="styles.css?v=13"', text)
    for name in ("core", "charts", "panels", "foreign-fix", "app"):
        text = re.sub(rf'src="js/{name}\.js(?:\?v=\d+)?"', f'src="js/{name}.js?v=13"', text)

    if "js/psychology-fix.js" not in text:
        text = text.replace(
            '<script src="js/charts.js?v=13"></script>',
            '<script src="js/charts.js?v=13"></script>\n<script src="js/psychology-fix.js?v=13"></script>',
        )
    else:
        text = re.sub(r'src="js/psychology-fix\.js(?:\?v=\d+)?"', 'src="js/psychology-fix.js?v=13"', text)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    base.main()
    payload = json.loads(base.OUTPUT_JSON.read_text(encoding="utf-8"))
    payload["cycle_signals"] = v8.build_cycle_signals(payload)
    v12.sanitise_errors(payload)
    apply_event_gated_logic(payload)
    base.OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    v7.append_archives()
    v9.persist_foreign_archives(payload)
    finalise_html_v13()
    print("dashboard v13 event-gated logic and psychology chart updated")
