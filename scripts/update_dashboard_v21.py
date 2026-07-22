#!/usr/bin/env python3
"""Dashboard v21: technical rebound signals and explicit freshness checks.

Adds the daily RSI/MACD/Sigma confirmation shown in the user's broker charts,
uses Micron and Sandisk as US memory lead indicators, and distinguishes normal
US/Korea market-close timing from genuinely stale observations.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests

import update_dashboard as base
import update_dashboard_v7 as v7
import update_dashboard_v8 as v8
import update_dashboard_v9 as v9
import update_dashboard_v10 as v10
import update_dashboard_v12 as v12
import update_dashboard_v13 as v13
import update_dashboard_v14 as v14
import update_dashboard_v15 as v15
import update_dashboard_v16 as v16
import update_dashboard_v17 as v17
import update_dashboard_v18 as v18
import update_dashboard_v19 as v19  # applies Naver latest-day overlay
import update_dashboard_v20 as v20


base.ASSETS.update({
    "KOSPI200": {"name": "KOSPI200 현물(선물 대용)", "type": "index", "pykrx": "1028", "yf": "^KS200"},
    "MU": {"name": "Micron", "type": "global_stock", "yf": "MU"},
    "SNDK": {"name": "Sandisk", "type": "global_stock", "yf": "SNDK"},
})

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}
ORIGINAL_BREADTH = base.breadth


def _yahoo_chart(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Fetch Yahoo's public chart JSON without yfinance's crumb/rate-limit path."""
    period1 = int(pd.Timestamp(start, tz="UTC").timestamp())
    period2 = int((pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)).timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker, safe='')}"
        f"?period1={period1}&period2={period2}&interval=1d&events=history"
    )
    response = requests.get(url, headers=HTTP_HEADERS, timeout=(5, 15))
    response.raise_for_status()
    result = ((response.json().get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError("Yahoo chart result empty")
    timestamps = result.get("timestamp") or []
    quote_rows = (((result.get("indicators") or {}).get("quote") or [{}])[0])
    closes = quote_rows.get("close") or []
    volumes = quote_rows.get("volume") or []
    if not timestamps or not closes:
        raise RuntimeError("Yahoo chart history empty")
    index = pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(None).normalize()
    frame = pd.DataFrame({"close": pd.to_numeric(closes, errors="coerce")}, index=index)
    if volumes:
        frame["volume"] = pd.to_numeric(volumes, errors="coerce")
    return frame.dropna(subset=["close"]).sort_index().loc[lambda x: ~x.index.duplicated(keep="last")]


def fetch_asset_v21(asset: dict[str, Any], start: str, end: str):
    """Yahoo chart JSON plus Naver latest-close overlay.

    pykrx 1.2.8 can terminate the interpreter on the current KRX schema instead
    of raising a catchable exception, so it is not allowed in the main process.
    """
    errors: list[str] = []
    primary: pd.DataFrame | None = None
    source: str | None = None
    try:
        primary = _yahoo_chart(str(asset["yf"]), start, end)
        source = "Yahoo Finance chart API"
    except Exception as exc:
        errors.append(f"Yahoo: {exc}")

    code = str(asset.get("pykrx") or "")
    if code in {"1001", "2001", "005930", "000660"}:
        try:
            if code == "1001":
                recent = v19._naver_recent_index("KOSPI", pages=3)
            elif code == "2001":
                recent = v19._naver_recent_index("KOSDAQ", pages=3)
            else:
                recent = v19._naver_recent_stock(code, pages=3)
            primary = v19._overlay(primary, recent) if primary is not None else recent
            source = f"{source or 'Naver Finance'} + Naver latest-day overlay"
        except Exception as exc:
            errors.append(f"Naver: {exc}")

    if primary is None or primary.empty:
        raise RuntimeError(" / ".join(errors) or "all price sources failed")
    if errors:
        source = f"{source}; fallback notes: {' | '.join(errors)}"
    return primary, source or "price fallback"


def breadth_v21(date: str, market: str) -> dict[str, Any]:
    """Read Naver's full-market advance/decline counters."""
    krx = {"advancers": None, "decliners": None, "unchanged": None, "ad_ratio": None}
    code = "KOSPI" if market == "KOSPI" else "KOSDAQ"
    url = f"https://finance.naver.com/sise/sise_index.naver?code={code}"
    try:
        response = requests.get(url, headers=HTTP_HEADERS, timeout=(5, 12))
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "euc-kr"
        text = response.text
        patterns = {
            "advancers": r"상승종목수</span>\s*<a[^>]*>\s*<span>([\d,]+)</span>",
            "unchanged": r"보합종목수</span>\s*<a[^>]*>\s*<span>([\d,]+)</span>",
            "decliners": r"하락종목수</span>\s*<a[^>]*>\s*<span>([\d,]+)</span>",
        }
        values = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.S)
            if not match:
                raise RuntimeError(f"{key} counter missing")
            values[key] = int(match.group(1).replace(",", ""))
        values.update({
            "ad_ratio": base.cf(values["advancers"] / values["decliners"]) if values["decliners"] else None,
            "date": date,
            "source": "Naver Finance market advance/decline counters",
            "fallback_from": krx.get("error"),
        })
        return values
    except Exception as exc:
        return {**krx, "source": "KRX/Naver unavailable", "fallback_error": str(exc), "date": date}


base.fetch_asset = fetch_asset_v21
base.breadth = breadth_v21


def _archive_series(path: Path, value_col: str) -> pd.Series:
    frame = pd.read_csv(path)
    frame["date"] = pd.to_datetime(frame.get("date"), errors="coerce")
    frame[value_col] = pd.to_numeric(frame.get(value_col), errors="coerce")
    return (
        frame.dropna(subset=["date", value_col])
        .drop_duplicates("date", keep="last")
        .set_index("date")[value_col]
        .sort_index()
    )


def _individual_flow_safe(start: str, end: str):
    try:
        series = _archive_series(v7.FLOW_ARCHIVE, "individual_net_buy_trn")
        if len(series) >= 20:
            return series.loc[pd.Timestamp(start):pd.Timestamp(end)], "GitHub CSV 개인 순매수 보존자료"
    except Exception:
        pass
    return v7.v3._flow_from_naver()


def _foreign_flow_safe(start: str, end: str):
    errors: list[str] = []
    try:
        recent, source = v10._naver_foreign_net_buy_v10(end)
        recent = recent.loc[pd.Timestamp(start):pd.Timestamp(end)]
        if len(recent) >= 60:
            return recent, source
    except Exception as exc:
        errors.append(str(exc))
    try:
        series = _archive_series(v9.FLOW_ARCHIVE, "daily_net_buy_trn")
        if len(series) >= 20:
            return series.loc[pd.Timestamp(start):pd.Timestamp(end)], "GitHub CSV 외국인 순매수 보존자료"
    except Exception as exc:
        errors.append(str(exc))
    raise RuntimeError(" / ".join(errors) or "foreign-flow sources unavailable")


def _ownership_safe(start: str, end: str, ticker: str) -> pd.Series:
    column = "samsung_pct" if ticker == "005930" else "skhynix_pct"
    try:
        recent, _ = v9._naver_stock_foreign_ownership(ticker)
        recent = recent.loc[pd.Timestamp(start):pd.Timestamp(end)]
        if len(recent) >= 20:
            return recent
    except Exception:
        pass
    series = _archive_series(v9.OWNERSHIP_ARCHIVE, column)
    return series.loc[pd.Timestamp(start):pd.Timestamp(end)]


def _market_snapshot_safe(date: str) -> dict[str, Any]:
    raise RuntimeError("KRX 전종목 표는 스키마 정상화 전까지 이전 확정치만 표시")


# Keep every pykrx call out of the main interpreter. Naver and accumulated CSV
# histories remain independently refreshable when KRX changes its schema.
v7._individual_flow = _individual_flow_safe
v8.foreign_net_buy = _foreign_flow_safe
v8.stock_foreign_ownership = _ownership_safe
v8.market_snapshot = _market_snapshot_safe

ORIGINAL_METRICS = base.metrics
SEOUL = base.SEOUL


def _technical_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    close = pd.to_numeric(out["close"], errors="coerce")
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi14"] = 100 - (100 / (1 + rs))
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    out["macd"] = ema12 - ema26
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()
    out["macd_hist"] = out["macd"] - out["macd_signal"]
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std(ddof=0).replace(0, np.nan)
    out["sigma20"] = (close - sma20) / std20
    return out


def metrics_v21(key: str, frame: pd.DataFrame, source: str):
    result, enriched = ORIGINAL_METRICS(key, frame, source)
    tech = _technical_columns(enriched)
    last = tech.iloc[-1]
    prev = tech.iloc[-2] if len(tech) > 1 else last
    prev2 = tech.iloc[-3] if len(tech) > 2 else prev
    rsi = base.cf(last.get("rsi14"))
    macd = base.cf(last.get("macd"))
    signal = base.cf(last.get("macd_signal"))
    hist = base.cf(last.get("macd_hist"))
    sigma = base.cf(last.get("sigma20"))
    price_up = bool(last.get("close") > prev.get("close"))
    rsi_turn = bool(pd.notna(last.get("rsi14")) and pd.notna(prev.get("rsi14")) and last.get("rsi14") > prev.get("rsi14"))
    macd_turn = bool(
        pd.notna(last.get("macd_hist")) and pd.notna(prev.get("macd_hist"))
        and last.get("macd_hist") > prev.get("macd_hist")
        and (pd.isna(prev2.get("macd_hist")) or prev.get("macd_hist") <= last.get("macd_hist"))
    )
    sigma_turn = bool(pd.notna(last.get("sigma20")) and pd.notna(prev.get("sigma20")) and last.get("sigma20") > prev.get("sigma20"))
    checks = {"price_up": price_up, "rsi_turn": rsi_turn, "macd_hist_turn": macd_turn, "sigma_turn": sigma_turn}
    score = sum(checks.values())
    if score >= 4:
        state = "기술 반등 확인"
    elif score >= 2:
        state = "초기 반등 진행"
    else:
        state = "하락 추세·확인 필요"
    result["technical_rebound"] = {
        "rsi14": rsi,
        "macd": macd,
        "macd_signal": signal,
        "macd_hist": hist,
        "sigma20": sigma,
        "score": score,
        "state": state,
        "checks": checks,
        "note": "일봉 종가 기준. 4개 조건 중 가격·RSI·MACD 히스토그램·Sigma의 동시 개선을 확인",
    }
    if result.get("type") == "global_stock":
        result["disparity_interpretation"] = {
            "zone": state,
            "headline": f"미국 메모리 선행 신호: {state}",
            "summary": f"RSI {rsi}, MACD 히스토그램 {hist}, Sigma(20) {sigma}",
            "action": "Micron·Sandisk의 동시 반등은 한국 메모리주의 다음 거래일 가격 반응을 확인하는 보조 신호입니다.",
        }
    for column in ("rsi14", "macd", "macd_signal", "macd_hist", "sigma20"):
        values = tech[column].tail(520)
        for row, value in zip(result.get("history", [])[-len(values):], values):
            row[column] = base.cf(value)
    return result, tech


base.metrics = metrics_v21


def _previous_weekday(day):
    day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _expected_close_date(asset_key: str, now: datetime):
    # At midnight in Korea, the current US session has not closed. Korean data
    # should represent today's close only after the closing retries begin.
    if asset_key in {"SOX", "NDX", "SPX", "MU", "SNDK"}:
        day = now.date() - timedelta(days=1)
        if now.hour < 7:
            day = _previous_weekday(day)
        elif day.weekday() >= 5:
            while day.weekday() >= 5:
                day = _previous_weekday(day + timedelta(days=1))
        return day
    day = now.date()
    if now.hour < 16:
        day = _previous_weekday(day)
    elif day.weekday() >= 5:
        while day.weekday() >= 5:
            day = _previous_weekday(day + timedelta(days=1))
    return day


def apply_freshness(payload: dict[str, Any]) -> None:
    now = datetime.now(SEOUL)
    status = {}
    delayed = []
    for key, asset in (payload.get("assets") or {}).items():
        raw_date = pd.to_datetime(asset.get("date"), errors="coerce")
        expected = _expected_close_date(key, now)
        age = None if pd.isna(raw_date) else max(0, int(np.busday_count(raw_date.date(), expected)))
        stale = age is None or age > 0
        item = {
            "date": asset.get("date"), "expected_close_date": expected.isoformat(),
            "business_days_late": age, "stale": stale, "source": asset.get("source"),
        }
        asset["freshness"] = item
        status[key] = item
        if stale:
            delayed.append(f"{asset.get('name', key)} {asset.get('date') or '미산출'} (예상 {expected.isoformat()}, {age if age is not None else '?'}거래일 지연)")
    payload["data_freshness"] = {"checked_at": now.isoformat(timespec="seconds"), "assets": status, "delayed": delayed}
    if delayed:
        payload.setdefault("errors", {})["stale_data"] = " / ".join(delayed)


def restore_missing_from_previous(payload: dict[str, Any], previous: dict[str, Any]) -> None:
    """Never replace a usable dashboard with a one-source partial refresh."""
    assets = payload.setdefault("assets", {})
    previous_assets = previous.get("assets") or {}
    restored = []
    for key, old in previous_assets.items():
        if key not in assets and old:
            assets[key] = old
            restored.append(key)
    for key in ("event_studies", "market_psychology"):
        current = payload.get(key)
        empty = not current or (key == "market_psychology" and not current.get("points"))
        if empty and previous.get(key):
            payload[key] = previous[key]
    if restored:
        payload["status"] = "degraded"
        payload.setdefault("errors", {})["restored_last_good"] = (
            "이번 실행에서 조회하지 못해 직전 정상값을 유지한 항목: " + ", ".join(restored)
        )


def persist_complete_history(payload: dict[str, Any]) -> None:
    """Rebuild CSV after last-good restoration so a partial run cannot shrink it."""
    rows = []
    for key, asset in (payload.get("assets") or {}).items():
        for item in asset.get("history") or []:
            rows.append({"asset": key, **item})
    if rows:
        pd.DataFrame(rows).to_csv(base.OUTPUT_CSV, index=False, encoding="utf-8-sig")


def finalise_html_v21() -> None:
    path: Path = base.OUTPUT_HTML
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(<script id="embedded" type="application/json">).*?(</script>)', r'\1{}\2', text, flags=re.S)
    text = re.sub(r'([?&]v=)\d+\b', r'\g<1>21', text)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    try:
        previous_payload = json.loads(base.OUTPUT_JSON.read_text(encoding="utf-8"))
    except Exception:
        previous_payload = {}
    base.main()
    payload = json.loads(base.OUTPUT_JSON.read_text(encoding="utf-8"))
    restore_missing_from_previous(payload, previous_payload)
    payload["cycle_signals"] = v8.build_cycle_signals(payload)
    v12.sanitise_errors(payload)
    v13.apply_event_gated_logic(payload)
    v16.apply_actual_vkospi_snapshot(payload)
    macro = v16.build_macro_context_actual(payload)
    payload["macro_context"] = macro
    v20.enrich_foreign_multi_horizon(payload)
    payload["trend_rebound_gate"] = v20.build_trend_gate_v20(payload, macro)
    v17.adjust_actual_vkospi_gate(payload, macro)
    payload["positioning_analysis"] = v15.build_positioning_analysis(payload)
    payload["mid_cycle_clock"] = v17.build_mid_cycle_clock(payload)
    v19.audit_date_alignment(payload)
    apply_freshness(payload)
    base.OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    persist_complete_history(payload)
    v7.append_archives()
    v9.persist_foreign_archives(payload)
    v13.finalise_html_v13(); v14.finalise_html_v14(); v15.finalise_html_v15()
    v17.finalise_html_v17(); v18.finalise_html_v18(); v19.finalise_html_v19()
    finalise_html_v21()
    print("dashboard v21 technical rebound and freshness checks updated")
