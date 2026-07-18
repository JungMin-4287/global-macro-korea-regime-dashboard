#!/usr/bin/env python3
"""Dashboard v9: robust foreign-flow and foreign-ownership collection.

Why v9 exists
- KRX occasionally blocks or returns empty data in GitHub Actions.
- The v8 panel depended only on KRX, so the foreign-flow card could be blank.

Fallback order
1. KRX/pykrx
2. Naver Finance public tables
3. Previously accumulated GitHub CSV archive
"""
from __future__ import annotations

import json
import re
from io import StringIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

import update_dashboard as base
import update_dashboard_v3 as v3
import update_dashboard_v7 as v7
import update_dashboard_v8 as v8  # imports the v3~v8 patches

FLOW_ARCHIVE = base.DATA_DIR / "foreign_net_buy_history.csv"
OWNERSHIP_ARCHIVE = base.DATA_DIR / "foreign_ownership_history.csv"

ORIGINAL_FOREIGN_NET_BUY = v8.foreign_net_buy
ORIGINAL_STOCK_FOREIGN_OWNERSHIP = v8.stock_foreign_ownership
ORIGINAL_MARKET_SNAPSHOT = v8.market_snapshot

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Referer": "https://finance.naver.com/",
}


def _clean_number(value: Any) -> float | None:
    text = str(value).strip().replace(",", "").replace("+", "")
    text = re.sub(r"[^0-9.\-]", "", text)
    if text in ("", "-", ".", "-."):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _flatten(df: pd.DataFrame) -> pd.DataFrame:
    return v3._flatten_columns(df)


def _naver_foreign_net_buy() -> tuple[pd.Series, str]:
    """Naver KOSPI investor trend: amounts are displayed in KRW 100m units."""
    rows: list[tuple[pd.Timestamp, float]] = []
    for page in range(1, 31):
        url = f"https://finance.naver.com/sise/investorDealTrendDay.naver?sosok=01&page={page}"
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "euc-kr"
        page_found = False
        for table in pd.read_html(StringIO(response.text)):
            table = _flatten(table)
            date_col = next((c for c in table.columns if "날짜" in c or "일자" in c), None)
            foreign_col = next(
                (c for c in table.columns if "외국인" in c and "보유" not in c and "지분" not in c),
                None,
            )
            if date_col is None or foreign_col is None:
                continue
            page_found = True
            for _, row in table.iterrows():
                date = pd.to_datetime(str(row[date_col]).strip(), errors="coerce")
                amount = _clean_number(row[foreign_col])
                if pd.notna(date) and amount is not None:
                    # Naver table unit: 억원. 10,000억원 = 1조원.
                    rows.append((pd.Timestamp(date).normalize(), amount / 10000.0))
        if len({d for d, _ in rows}) >= 260:
            break
        if not page_found and page >= 3:
            break
    if len(rows) < 10:
        raise RuntimeError(f"Naver foreign flow insufficient ({len(rows)})")
    frame = (
        pd.DataFrame(rows, columns=["date", "foreign_net_buy_trn"])
        .drop_duplicates("date", keep="first")
        .set_index("date")
        .sort_index()
    )
    return frame["foreign_net_buy_trn"], "Naver Finance KOSPI 외국인 순매수(억원→조원)"


def foreign_net_buy_v9(start: str, end: str) -> tuple[pd.Series, str]:
    errors: list[str] = []
    try:
        return ORIGINAL_FOREIGN_NET_BUY(start, end)
    except Exception as exc:
        errors.append(f"KRX: {exc}")
    try:
        s, source = _naver_foreign_net_buy()
        start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
        s = s[(s.index >= start_ts) & (s.index <= end_ts)]
        if len(s) >= 10:
            return s, source
        errors.append(f"Naver common period insufficient ({len(s)})")
    except Exception as exc:
        errors.append(f"Naver: {exc}")
    if FLOW_ARCHIVE.exists():
        try:
            old = pd.read_csv(FLOW_ARCHIVE)
            old["date"] = pd.to_datetime(old["date"], errors="coerce")
            s = old.dropna(subset=["date", "daily_net_buy_trn"]).drop_duplicates("date", keep="last").set_index("date")["daily_net_buy_trn"].sort_index()
            if len(s) >= 10:
                return s, "GitHub CSV 외국인 순매수 보존자료(원자료 일시 실패)"
        except Exception as exc:
            errors.append(f"archive: {exc}")
    raise RuntimeError(" / ".join(errors))


def _naver_stock_foreign_ownership(ticker: str) -> tuple[pd.Series, str]:
    rows: list[tuple[pd.Timestamp, float]] = []
    for page in range(1, 31):
        url = f"https://finance.naver.com/item/frgn.naver?code={ticker}&page={page}"
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "euc-kr"
        page_found = False
        for table in pd.read_html(StringIO(response.text)):
            table = _flatten(table)
            date_col = next((c for c in table.columns if "날짜" in c or "일자" in c), None)
            pct_col = next((c for c in table.columns if "보유율" in c or "지분율" in c), None)
            if date_col is None or pct_col is None:
                continue
            page_found = True
            for _, row in table.iterrows():
                date = pd.to_datetime(str(row[date_col]).strip(), errors="coerce")
                pct = _clean_number(row[pct_col])
                if pd.notna(date) and pct is not None and 0 <= pct <= 100:
                    rows.append((pd.Timestamp(date).normalize(), pct))
        if len({d for d, _ in rows}) >= 260:
            break
        if not page_found and page >= 3:
            break
    if len(rows) < 10:
        raise RuntimeError(f"Naver ownership insufficient ({ticker}: {len(rows)})")
    frame = (
        pd.DataFrame(rows, columns=["date", "foreign_ownership_pct"])
        .drop_duplicates("date", keep="first")
        .set_index("date")
        .sort_index()
    )
    return frame["foreign_ownership_pct"], f"Naver Finance {ticker} 외국인 보유율"


def stock_foreign_ownership_v9(start: str, end: str, ticker: str) -> pd.Series:
    errors: list[str] = []
    try:
        return ORIGINAL_STOCK_FOREIGN_OWNERSHIP(start, end, ticker)
    except Exception as exc:
        errors.append(f"KRX: {exc}")
    try:
        s, _ = _naver_stock_foreign_ownership(ticker)
        start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
        s = s[(s.index >= start_ts) & (s.index <= end_ts)]
        if len(s) >= 10:
            return s
        errors.append(f"Naver common period insufficient ({len(s)})")
    except Exception as exc:
        errors.append(f"Naver: {exc}")
    if OWNERSHIP_ARCHIVE.exists():
        try:
            old = pd.read_csv(OWNERSHIP_ARCHIVE)
            old["date"] = pd.to_datetime(old["date"], errors="coerce")
            col = "samsung_pct" if ticker == "005930" else "skhynix_pct"
            s = old.dropna(subset=["date", col]).drop_duplicates("date", keep="last").set_index("date")[col].sort_index()
            if len(s) >= 10:
                return s
        except Exception as exc:
            errors.append(f"archive: {exc}")
    raise RuntimeError(" / ".join(errors))


def _krx_market_snapshot(date: str) -> dict[str, Any]:
    """Use the KRX all-ticker foreign-exhaustion table, not get_market_cap columns."""
    from pykrx import stock

    d = pd.Timestamp(date)
    errors: list[str] = []
    for offset in range(0, 10):
        target = (d - pd.Timedelta(days=offset)).strftime("%Y%m%d")
        try:
            cap = stock.get_market_cap(target)
            foreign = stock.get_exhaustion_rates_of_foreign_investment(target, "KOSPI")
            tickers = set(stock.get_market_ticker_list(target, market="KOSPI"))
            if cap is None or cap.empty or foreign is None or foreign.empty or not tickers:
                continue
            cap.index = cap.index.astype(str)
            foreign.index = foreign.index.astype(str)
            common = cap.index.intersection(foreign.index).intersection(list(tickers))
            if len(common) < 100:
                continue
            cap = cap.loc[common]
            foreign = foreign.loc[common]
            mcap_col = next((c for c in cap.columns if "시가총액" in str(c)), None)
            pct_col = next((c for c in foreign.columns if "지분율" in str(c)), None)
            if mcap_col is None or pct_col is None:
                continue
            mcap = pd.to_numeric(cap[mcap_col], errors="coerce")
            pct = pd.to_numeric(foreign[pct_col], errors="coerce")
            valid = pd.concat([mcap.rename("mcap"), pct.rename("pct")], axis=1).dropna()
            total = float(valid.mcap.sum())
            if total <= 0:
                continue
            top2 = float(mcap.reindex(["005930", "000660"]).fillna(0).sum())
            weighted_foreign = float((valid.mcap * valid.pct / 100.0).sum() / total * 100.0)
            return {
                "date": pd.Timestamp(target).strftime("%Y-%m-%d"),
                "kospi_market_cap_trn_krw": base.cf(total / 1e12),
                "top2_direct_market_cap_trn_krw": base.cf(top2 / 1e12),
                "top2_direct_market_cap_share_pct": base.cf(top2 / total * 100),
                "kospi_foreign_ownership_mcap_weighted_pct": base.cf(weighted_foreign),
                "source": "KRX(pykrx) 시가총액 + 외국인 보유율 전종목 표",
                "note": "외국인 지분율은 장개시 시점 기준 전일 확정치",
            }
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("KRX market snapshot failed: " + " / ".join(errors[-3:]))


def market_snapshot_v9(date: str) -> dict[str, Any]:
    first: dict[str, Any] = {}
    errors: list[str] = []
    try:
        first = ORIGINAL_MARKET_SNAPSHOT(date)
        if first.get("kospi_foreign_ownership_mcap_weighted_pct") is not None:
            return first
    except Exception as exc:
        errors.append(str(exc))
    try:
        second = _krx_market_snapshot(date)
        if first:
            second.setdefault("top2_direct_market_cap_share_pct", first.get("top2_direct_market_cap_share_pct"))
        return second
    except Exception as exc:
        errors.append(str(exc))
    if first:
        first["note"] = (first.get("note") or "") + " · KOSPI 외국인 보유 비중은 미산출"
        return first
    raise RuntimeError(" / ".join(errors))


def _merge(path: Path, rows: list[dict[str, Any]], keys: list[str]) -> pd.DataFrame:
    latest = pd.DataFrame(rows)
    if path.exists():
        try:
            latest = pd.concat([pd.read_csv(path), latest], ignore_index=True)
        except Exception:
            pass
    if latest.empty:
        return latest
    latest = latest.dropna(subset=keys).drop_duplicates(keys, keep="last").sort_values(keys)
    latest.to_csv(path, index=False, encoding="utf-8-sig")
    return latest


def persist_foreign_archives(payload: dict[str, Any]) -> None:
    foreign = (payload.get("cycle_signals") or {}).get("foreign") or {}
    generated_at = payload.get("generated_at")
    flow_rows = [
        {
            "date": row.get("date"),
            "daily_net_buy_trn": row.get("daily_net_buy_trn"),
            "cumulative_net_buy_trn": row.get("cumulative_net_buy_trn"),
            "source": foreign.get("source"),
            "generated_at": generated_at,
        }
        for row in foreign.get("points") or []
    ]
    _merge(FLOW_ARCHIVE, flow_rows, ["date"])

    ownership_rows = [
        {
            "date": row.get("date"),
            "samsung_pct": row.get("samsung_pct"),
            "skhynix_pct": row.get("skhynix_pct"),
            "source": "KRX 또는 Naver Finance 외국인 보유율",
            "generated_at": generated_at,
        }
        for row in foreign.get("ownership") or []
    ]
    _merge(OWNERSHIP_ARCHIVE, ownership_rows, ["date"])


def make_html_lightweight_v9() -> None:
    path: Path = base.OUTPUT_HTML
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(<script id="embedded" type="application/json">).*?(</script>)', r'\1{}\2', text, flags=re.S)
    text = re.sub(r'href="styles\.css(?:\?v=\d+)?"', 'href="styles.css?v=9"', text)
    for name in ("core", "charts", "panels", "app"):
        text = re.sub(rf'src="js/{name}\.js(?:\?v=\d+)?"', f'src="js/{name}.js?v=9"', text)
    path.write_text(text, encoding="utf-8")


v8.foreign_net_buy = foreign_net_buy_v9
v8.stock_foreign_ownership = stock_foreign_ownership_v9
v8.market_snapshot = market_snapshot_v9


if __name__ == "__main__":
    base.main()
    payload = json.loads(base.OUTPUT_JSON.read_text(encoding="utf-8"))
    payload["cycle_signals"] = v8.build_cycle_signals(payload)
    base.OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    v7.append_archives()
    persist_foreign_archives(payload)
    make_html_lightweight_v9()
    print("dashboard v9 foreign-flow fallbacks updated")
