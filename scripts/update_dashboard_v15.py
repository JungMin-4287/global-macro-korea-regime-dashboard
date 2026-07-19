#!/usr/bin/env python3
"""Dashboard v15: distinguish position liquidation from a memory downcycle.

Adds no new large panel. It enriches the existing positioning card with:
- a manual institutional global-memory L/S snapshot;
- a daily public-data positioning proxy with an explicit coverage ratio;
- an L/S direction x DRAM/EPS direction judgement.

The manual prime-broker snapshot is never included in the daily regime score.
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
import update_dashboard_v12 as v12
import update_dashboard_v13 as v13
import update_dashboard_v14 as v14


def _num(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def _percentile(values: list[float], current: float | None) -> float | None:
    clean = np.asarray([x for x in values if x is not None and math.isfinite(float(x))], dtype=float)
    if current is None or len(clean) < 10:
        return None
    return base.cf(float((clean <= current).mean() * 100))


def _asset_return_percentile(asset: dict[str, Any], days: int = 20) -> float | None:
    rows = asset.get("history") or []
    frame = pd.DataFrame(rows)
    if frame.empty or "close" not in frame:
        return None
    close = pd.to_numeric(frame["close"], errors="coerce").dropna()
    returns = (close / close.shift(days) - 1) * 100
    returns = returns.dropna()
    if len(returns) < 30:
        return None
    return _percentile(returns.tolist(), float(returns.iloc[-1]))


def _find_column(frame: pd.DataFrame, keywords: tuple[str, ...]) -> Any | None:
    for column in frame.columns:
        text = str(column).replace(" ", "")
        if any(keyword.replace(" ", "") in text for keyword in keywords):
            return column
    return None


def _krx_short_ratio(ticker: str, start: str, end: str, mode: str) -> tuple[pd.Series, str]:
    """Return KRX short ratio series when the public pykrx endpoint is available."""
    from pykrx import stock

    if mode == "balance":
        names = ("get_shorting_balance_by_date",)
        source = "KRX 공매도 순보유잔고 비중"
    else:
        names = ("get_shorting_value_by_date", "get_shorting_volume_by_date")
        source = "KRX 공매도 거래 비중"

    errors: list[str] = []
    for name in names:
        func = getattr(stock, name, None)
        if func is None:
            continue
        try:
            raw = func(start.replace("-", ""), end.replace("-", ""), ticker)
            if raw is None or raw.empty:
                continue
            raw = raw.copy()
            raw.index = pd.to_datetime(raw.index, errors="coerce")
            ratio_col = _find_column(raw, ("비중", "공매도비중", "잔고비중"))
            if ratio_col is not None:
                series = pd.to_numeric(raw[ratio_col], errors="coerce")
            else:
                short_col = _find_column(raw, ("공매도거래대금", "공매도", "잔고금액"))
                total_col = _find_column(raw, ("거래대금", "시가총액", "전체거래대금"))
                if short_col is None or total_col is None or short_col == total_col:
                    continue
                numerator = pd.to_numeric(raw[short_col], errors="coerce")
                denominator = pd.to_numeric(raw[total_col], errors="coerce").replace(0, np.nan)
                series = numerator / denominator * 100
            series = series.dropna().sort_index()
            if len(series) >= 10:
                return series, source
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    raise RuntimeError(" / ".join(errors[-2:]) or f"{source} 미산출")


def _foreign_score(foreign: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    points = foreign.get("points") or []
    flow_frame = pd.DataFrame(points)
    flow_score = None
    if not flow_frame.empty and "daily_net_buy_trn" in flow_frame:
        daily = pd.to_numeric(flow_frame["daily_net_buy_trn"], errors="coerce").dropna()
        rolling = daily.rolling(20).sum().dropna()
        if len(rolling) >= 10:
            flow_score = _percentile(rolling.tolist(), float(rolling.iloc[-1]))

    own_frame = pd.DataFrame(foreign.get("ownership") or [])
    ownership_scores: list[float] = []
    if not own_frame.empty:
        for column in ("samsung_pct", "skhynix_pct"):
            if column not in own_frame:
                continue
            values = pd.to_numeric(own_frame[column], errors="coerce").dropna()
            changes = values.diff(20).dropna()
            if len(changes) >= 10:
                score = _percentile(changes.tolist(), float(changes.iloc[-1]))
                if score is not None:
                    ownership_scores.append(score)
    ownership_score = base.cf(float(np.mean(ownership_scores))) if ownership_scores else None

    available = [x for x in (flow_score, ownership_score) if x is not None]
    combined = base.cf(float(np.mean(available))) if available else None
    return combined, {
        "flow_20d_percentile": flow_score,
        "ownership_change_percentile": ownership_score,
        "latest_20d_net_buy_trn": foreign.get("net_buy_20d_trn"),
        "source": foreign.get("source") or "KRX 외국인 수급",
    }


def build_positioning_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    assets = payload.get("assets") or {}
    manual = payload.get("manual") or {}
    p = manual.get("positioning") or {}
    institution = p.get("global_memory_ls") or {}
    foreign = ((payload.get("cycle_signals") or {}).get("foreign") or {})

    components: list[dict[str, Any]] = []
    errors: list[str] = []

    foreign_score, foreign_detail = _foreign_score(foreign)
    components.append({
        "name": "한국 외국인 수급·지분율",
        "score": foreign_score,
        "weight": 25,
        "available": foreign_score is not None,
        "detail": foreign_detail,
    })

    end = (assets.get("KOSPI") or {}).get("date") or payload.get("generated_at", "")[:10]
    start = (pd.Timestamp(end) - pd.Timedelta(days=550)).strftime("%Y-%m-%d")

    for mode, name, weight in (("balance", "KRX 공매도 잔고", 20), ("trading", "KRX 공매도 거래", 10)):
        stock_scores: list[float] = []
        latest_values: dict[str, Any] = {}
        sources: list[str] = []
        for ticker, label in (("005930", "삼성전자"), ("000660", "SK하이닉스")):
            try:
                series, source = _krx_short_ratio(ticker, start, end, mode)
                current = float(series.iloc[-1])
                crowded_short_pct = _percentile(series.tolist(), current)
                if crowded_short_pct is not None:
                    stock_scores.append(100 - crowded_short_pct)
                latest_values[label] = base.cf(current)
                sources.append(source)
            except Exception as exc:
                errors.append(f"{label} {name}: {exc}")
        score = base.cf(float(np.mean(stock_scores))) if stock_scores else None
        components.append({
            "name": name,
            "score": score,
            "weight": weight,
            "available": score is not None,
            "detail": {"latest_ratio_pct": latest_values, "source": " / ".join(sorted(set(sources))) if sources else "미산출"},
        })

    momentum_scores = [
        _asset_return_percentile(assets.get(key) or {}, 20)
        for key in ("SAMSUNG", "SKHYNIX", "SOX")
    ]
    momentum_scores = [x for x in momentum_scores if x is not None]
    momentum_score = base.cf(float(np.mean(momentum_scores))) if momentum_scores else None
    components.append({
        "name": "메모리·SOX 상승 확산도",
        "score": momentum_score,
        "weight": 10,
        "available": momentum_score is not None,
        "detail": {"source": "삼성전자·SK하이닉스·SOX 20일 수익률의 자체 역사 백분위"},
    })

    weighted = [(float(c["score"]), int(c["weight"])) for c in components if c.get("available") and c.get("score") is not None]
    active_weight = sum(weight for _, weight in weighted)
    proxy_score = base.cf(sum(score * weight for score, weight in weighted) / active_weight) if active_weight else None
    coverage = active_weight  # conceptual full model has a 100-point weight budget

    if proxy_score is None:
        proxy_state = "미산출"
    elif proxy_score >= 80:
        proxy_state = "극단적 과밀 롱"
    elif proxy_score >= 65:
        proxy_state = "강한 롱"
    elif proxy_score >= 45:
        proxy_state = "중립·정상 수준"
    elif proxy_score >= 30:
        proxy_state = "디레버리징·비관"
    else:
        proxy_state = "투매·극단적 숏"

    ls_direction = str(institution.get("direction") or "unknown").lower()
    memory = manual.get("memory") or {}
    dram_direction = str(institution.get("dram_asp_direction") or memory.get("dram_price_momentum") or "unknown").lower()
    eps_direction = str(institution.get("eps_revision_direction") or memory.get("earnings_revision_breadth") or "unknown").lower()
    fundamental_up = dram_direction in {"up", "rising", "positive", "상승", "상향"} and eps_direction in {"up", "rising", "positive", "상승", "상향"}
    fundamental_down = dram_direction in {"down", "falling", "negative", "하락", "하향"} or eps_direction in {"down", "falling", "negative", "하락", "하향"}

    if ls_direction in {"down", "falling", "declining", "하락"} and fundamental_up:
        combined_judgement = "포지션 청산 우세·저점 접근 후보"
        combined_text = "기관 메모리 L/S는 급락했지만 DRAM ASP와 EPS 방향은 상향입니다. 확인된 다운사이클보다 과밀 롱 해소 가능성이 우세합니다. 다만 가격 반응과 외국인 수급 회복 전에는 저점 확정으로 보지 않습니다."
    elif ls_direction in {"down", "falling", "declining", "하락"} and fundamental_down:
        combined_judgement = "다운사이클 선반영 경고"
        combined_text = "포지션 축소와 DRAM·EPS 하향이 같은 방향입니다. 단순 디레버리징보다 실제 업황 하강을 선반영할 가능성이 커졌습니다."
    elif ls_direction in {"down", "falling", "declining", "하락"}:
        combined_judgement = "포지션 정상화·업황 확인 대기"
        combined_text = "롱 청산은 확인되지만 EPS 방향 자료가 충분하지 않습니다. DRAM 가격과 이익 추정치가 함께 꺾이는지 확인해야 합니다."
    elif fundamental_up:
        combined_judgement = "펀더멘털 동반 상승"
        combined_text = "포지션과 업황이 함께 개선되는 정상 상승 국면입니다. 과밀 수준이 다시 높아지는지는 별도로 점검합니다."
    else:
        combined_judgement = "후기 모멘텀·방향 확인"
        combined_text = "포지션이 늘어나는 가운데 업황 상향이 뚜렷하지 않으면 후기 모멘텀 위험이 커질 수 있습니다."

    return {
        "institutional_snapshot": institution,
        "daily_proxy": {
            "score": proxy_score,
            "state": proxy_state,
            "coverage_pct": coverage,
            "components": components,
            "missing_components": ["ETF 설정·환매", "옵션 put/call", "대차잔고", "미국 메모리 FINRA·공식 short interest"],
            "note": "확보된 공개 데이터만으로 활성 가중치를 재정규화한 1단계 프록시입니다. 커버리지가 100%가 아니며 기관 L/S 수동값은 점수에 포함하지 않습니다.",
        },
        "combined_judgement": {
            "label": combined_judgement,
            "text": combined_text,
            "ls_direction": ls_direction,
            "dram_asp_direction": dram_direction,
            "eps_revision_direction": eps_direction,
        },
        "not_in_regime_score": True,
        "errors": errors,
        "updated_at": payload.get("generated_at"),
    }


def finalise_html_v15() -> None:
    path: Path = base.OUTPUT_HTML
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(<script id="embedded" type="application/json">).*?(</script>)', r'\1{}\2', text, flags=re.S)
    text = re.sub(r'href="styles\.css(?:\?v=\d+)?"', 'href="styles.css?v=15"', text)
    text = re.sub(r'href="gate\.css(?:\?v=\d+)?"', 'href="gate.css?v=15"', text)
    if "positioning.css" not in text:
        text = text.replace('<link rel="stylesheet" href="gate.css?v=15">', '<link rel="stylesheet" href="gate.css?v=15">\n  <link rel="stylesheet" href="positioning.css?v=15">')
    else:
        text = re.sub(r'href="positioning\.css(?:\?v=\d+)?"', 'href="positioning.css?v=15"', text)
    for name in ("core", "charts", "psychology-fix", "panels", "foreign-fix", "gate", "app"):
        text = re.sub(rf'src="js/{name}\.js(?:\?v=\d+)?"', f'src="js/{name}.js?v=15"', text)
    if "js/positioning.js" not in text:
        text = text.replace('<script src="js/app.js?v=15"></script>', '<script src="js/positioning.js?v=15"></script>\n<script src="js/app.js?v=15"></script>')
    else:
        text = re.sub(r'src="js/positioning\.js(?:\?v=\d+)?"', 'src="js/positioning.js?v=15"', text)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    base.main()
    payload = json.loads(base.OUTPUT_JSON.read_text(encoding="utf-8"))
    payload["cycle_signals"] = v8.build_cycle_signals(payload)
    v12.sanitise_errors(payload)
    v13.apply_event_gated_logic(payload)
    macro = v14.build_macro_context(payload)
    payload["macro_context"] = macro
    payload["trend_rebound_gate"] = v14.build_trend_gate(payload, macro)
    payload["positioning_analysis"] = build_positioning_analysis(payload)
    base.OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    v7.append_archives()
    v9.persist_foreign_archives(payload)
    v13.finalise_html_v13()
    v14.finalise_html_v14()
    finalise_html_v15()
    print("dashboard v15 memory positioning analysis updated")
