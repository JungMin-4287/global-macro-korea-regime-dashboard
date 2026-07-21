#!/usr/bin/env python3
"""Dashboard v19: prevent the newest Korean trading day from disappearing.

KRX/pykrx or Yahoo can occasionally lag by one trading day while Naver's
investor-flow table already contains the new session. The psychology charts use
an inner date join, so the newest flow observation was silently dropped.

This version overlays recent Naver daily closes for KOSPI, KOSDAQ, Samsung
Electronics and SK hynix on top of the long KRX/Yahoo histories. It also records
an explicit alignment warning instead of silently hiding a newer flow date.
"""
from __future__ import annotations

import json
import re
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests

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

ORIGINAL_FETCH_ASSET = base.fetch_asset
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Referer": "https://finance.naver.com/",
}


def _flatten_columns(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [" ".join(str(x) for x in col if str(x).lower() != "nan").strip() for col in out.columns]
    else:
        out.columns = [str(col).strip() for col in out.columns]
    return out


def _pick_table(html: str, required: tuple[str, ...]) -> pd.DataFrame:
    tables = pd.read_html(StringIO(html))
    for raw in tables:
        frame = _flatten_columns(raw)
        joined = "|".join(frame.columns)
        if all(token in joined for token in required):
            return frame
    raise RuntimeError(f"Naver table not found: {required}")


def _clean_daily_table(frame: pd.DataFrame, close_tokens: tuple[str, ...]) -> pd.DataFrame:
    date_col = next((c for c in frame.columns if "날짜" in c), None)
    close_col = next((c for c in frame.columns if any(token in c for token in close_tokens)), None)
    volume_col = next((c for c in frame.columns if "거래량" in c), None)
    if date_col is None or close_col is None:
        raise RuntimeError(f"date/close columns missing: {list(frame.columns)}")

    out = pd.DataFrame()
    out["date"] = pd.to_datetime(frame[date_col], errors="coerce")
    out["close"] = pd.to_numeric(
        frame[close_col].astype(str).str.replace(",", "", regex=False), errors="coerce"
    )
    if volume_col is not None:
        out["volume"] = pd.to_numeric(
            frame[volume_col].astype(str).str.replace(",", "", regex=False), errors="coerce"
        )
    return out.dropna(subset=["date", "close"]).drop_duplicates("date", keep="last").set_index("date").sort_index()


def _naver_recent_index(code: str, pages: int = 20) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for page in range(1, pages + 1):
        url = f"https://finance.naver.com/sise/sise_index_day.naver?code={code}&page={page}"
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "euc-kr"
        table = _pick_table(response.text, ("날짜", "체결가"))
        frames.append(_clean_daily_table(table, ("체결가", "종가")))
    if not frames:
        raise RuntimeError("Naver index history empty")
    return pd.concat(frames).sort_index().loc[lambda x: ~x.index.duplicated(keep="last")]


def _naver_recent_stock(code: str, pages: int = 20) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for page in range(1, pages + 1):
        url = f"https://finance.naver.com/item/sise_day.naver?code={code}&page={page}"
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "euc-kr"
        table = _pick_table(response.text, ("날짜", "종가"))
        frames.append(_clean_daily_table(table, ("종가",)))
    if not frames:
        raise RuntimeError("Naver stock history empty")
    return pd.concat(frames).sort_index().loc[lambda x: ~x.index.duplicated(keep="last")]


def _overlay(primary: pd.DataFrame, recent: pd.DataFrame) -> pd.DataFrame:
    if primary is None or primary.empty:
        return recent.copy()
    columns = sorted(set(primary.columns).union(recent.columns))
    left = primary.reindex(columns=columns)
    right = recent.reindex(columns=columns)
    combined = pd.concat([left, right]).sort_index()
    # Recent Naver observations are appended last and therefore replace a stale
    # or conflicting record for the same trading date.
    return combined.loc[~combined.index.duplicated(keep="last")].dropna(subset=["close"])


def fetch_asset_v19(asset: dict[str, Any], start: str, end: str):
    primary, source = ORIGINAL_FETCH_ASSET(asset, start, end)
    code = str(asset.get("pykrx") or "")
    try:
        recent = None
        if asset.get("type") == "index" and code in {"1001", "2001"}:
            recent = _naver_recent_index("KOSPI" if code == "1001" else "KOSDAQ")
        elif asset.get("type") == "stock" and code in {"005930", "000660"}:
            recent = _naver_recent_stock(code)
        if recent is None or recent.empty:
            return primary, source

        before = pd.Timestamp(primary.index.max()) if not primary.empty else None
        merged = _overlay(primary, recent)
        after = pd.Timestamp(merged.index.max()) if not merged.empty else before
        if before is None or (after is not None and after > before):
            source = f"{source} + Naver Finance latest-day overlay"
        return merged, source
    except Exception as exc:
        # Never discard the long primary history merely because the recent
        # overlay failed. The alignment audit below exposes any remaining lag.
        return primary, f"{source}; Naver overlay failed: {exc}"


def _latest_flow_date() -> pd.Timestamp | None:
    try:
        flow, _ = v7._individual_flow("2025-01-01", pd.Timestamp.now(tz="Asia/Seoul").strftime("%Y-%m-%d"))
        if flow is not None and len(flow):
            return pd.Timestamp(flow.dropna().index.max()).tz_localize(None)
    except Exception:
        pass
    try:
        archive = pd.read_csv(v7.FLOW_ARCHIVE)
        dates = pd.to_datetime(archive.get("date"), errors="coerce").dropna()
        return pd.Timestamp(dates.max()) if len(dates) else None
    except Exception:
        return None


def audit_date_alignment(payload: dict[str, Any]) -> None:
    kospi_date = pd.to_datetime((payload.get("assets") or {}).get("KOSPI", {}).get("date"), errors="coerce")
    flow_date = _latest_flow_date()
    audit = {
        "kospi_price_date": kospi_date.strftime("%Y-%m-%d") if pd.notna(kospi_date) else None,
        "individual_flow_date": flow_date.strftime("%Y-%m-%d") if flow_date is not None else None,
        "aligned": bool(flow_date is None or (pd.notna(kospi_date) and kospi_date >= flow_date)),
    }
    if not audit["aligned"]:
        audit["warning"] = (
            f"개인 순매수는 {audit['individual_flow_date']}까지 있으나 KOSPI 가격은 "
            f"{audit['kospi_price_date']}까지여서 최신 수급점이 차트에서 제외될 수 있습니다."
        )
        payload.setdefault("errors", {})["date_alignment"] = audit["warning"]
    payload["date_alignment"] = audit


def finalise_html_v19() -> None:
    path: Path = base.OUTPUT_HTML
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(<script id="embedded" type="application/json">).*?(</script>)', r'\1{}\2', text, flags=re.S)
    text = re.sub(r'([?&]v=)18\b', r'\g<1>19', text)
    # Catch older cache keys left by compatibility finalisers.
    text = re.sub(r'([?&]v=)\d+\b', r'\g<1>19', text)
    path.write_text(text, encoding="utf-8")


base.fetch_asset = fetch_asset_v19


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
    audit_date_alignment(payload)
    base.OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    v7.append_archives()
    v9.persist_foreign_archives(payload)
    v13.finalise_html_v13()
    v14.finalise_html_v14()
    v15.finalise_html_v15()
    v17.finalise_html_v17()
    v18.finalise_html_v18()
    finalise_html_v19()
    print("dashboard v19 latest Korean trading-day alignment updated")
