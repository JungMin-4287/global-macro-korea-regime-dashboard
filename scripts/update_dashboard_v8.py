#!/usr/bin/env python3
"""Dashboard v8: add continuously updateable cycle-rebound signals from the Meritz study.

Fully automatic
- KOSPI foreign net buying and cumulative flow
- Samsung Electronics / SK hynix foreign ownership rates
- KOSPI aggregate foreign ownership proxy and direct Top2 market-cap share

Event-driven
- EPS estimate snapshot changes from manual_signals.json when a new broker report is entered
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import update_dashboard as base
import update_dashboard_v7 as v7  # noqa: F401 - applies v3~v7 patches

FOREIGN_ARCHIVE = base.DATA_DIR / "foreign_cycle_history.csv"
CONSENSUS_ARCHIVE = base.DATA_DIR / "consensus_snapshot.csv"


def _num(v: Any) -> float | None:
    try:
        x = float(v)
        return None if not np.isfinite(x) else x
    except Exception:
        return None


def _column(df: pd.DataFrame, keywords: tuple[str, ...]) -> str | None:
    for c in df.columns:
        text = str(c)
        if any(k in text for k in keywords):
            return c
    return None


def _merge_archive(path: Path, rows: list[dict[str, Any]], keys: list[str]) -> pd.DataFrame:
    latest = pd.DataFrame(rows)
    if path.exists():
        try:
            old = pd.read_csv(path)
            latest = pd.concat([old, latest], ignore_index=True)
        except Exception:
            pass
    if latest.empty:
        return latest
    latest = latest.dropna(subset=keys).drop_duplicates(keys, keep="last").sort_values(keys)
    latest.to_csv(path, index=False, encoding="utf-8-sig")
    return latest


def foreign_net_buy(start: str, end: str) -> tuple[pd.Series, str]:
    from pykrx import stock

    raw = stock.get_market_trading_value_by_date(
        pd.Timestamp(start).strftime("%Y%m%d"),
        pd.Timestamp(end).strftime("%Y%m%d"),
        "KOSPI",
        on="순매수",
    )
    if raw is None or raw.empty:
        raise RuntimeError("KRX foreign flow empty")
    col = _column(raw, ("외국인합계", "외국인"))
    if col is None:
        raise RuntimeError("KRX foreign column missing")
    s = pd.to_numeric(raw[col], errors="coerce") / 1e12
    s.index = pd.to_datetime(s.index)
    s = s.dropna().sort_index()
    if len(s) < 10:
        raise RuntimeError(f"KRX foreign flow insufficient ({len(s)})")
    return s, "KRX(pykrx) KOSPI 외국인 순매수"


def stock_foreign_ownership(start: str, end: str, ticker: str) -> pd.Series:
    from pykrx import stock

    raw = stock.get_exhaustion_rates_of_foreign_investment(
        pd.Timestamp(start).strftime("%Y%m%d"),
        pd.Timestamp(end).strftime("%Y%m%d"),
        ticker,
    )
    if raw is None or raw.empty:
        raise RuntimeError(f"foreign ownership empty: {ticker}")
    col = _column(raw, ("지분율",))
    if col is None:
        raise RuntimeError(f"foreign ownership column missing: {ticker}")
    s = pd.to_numeric(raw[col], errors="coerce")
    s.index = pd.to_datetime(s.index)
    return s.dropna().sort_index()


def market_snapshot(date: str) -> dict[str, Any]:
    """Return direct Top2 share and a market-cap-weighted KOSPI foreign ownership proxy.

    KRX foreign share counts are confirmed with a delay, so the function walks back
    through recent trading dates until non-zero holdings are available.
    """
    from pykrx import stock

    d = pd.Timestamp(date)
    errors: list[str] = []
    for offset in range(0, 8):
        target = (d - pd.Timedelta(days=offset)).strftime("%Y%m%d")
        try:
            kospi_tickers = set(stock.get_market_ticker_list(target, market="KOSPI"))
            raw = stock.get_market_cap(target)
            if raw is None or raw.empty:
                continue
            raw.index = raw.index.astype(str)
            frame = raw.loc[raw.index.intersection(kospi_tickers)].copy()
            mcap_col = _column(frame, ("시가총액",))
            shares_col = _column(frame, ("상장주식수",))
            foreign_col = _column(frame, ("외국인보유주식수",))
            if mcap_col is None or shares_col is None:
                continue
            mcap = pd.to_numeric(frame[mcap_col], errors="coerce")
            total = float(mcap.sum())
            if not np.isfinite(total) or total <= 0:
                continue
            top2 = float(mcap.reindex(["005930", "000660"]).fillna(0).sum())
            foreign_pct = None
            if foreign_col is not None:
                listed = pd.to_numeric(frame[shares_col], errors="coerce").replace(0, np.nan)
                foreign_shares = pd.to_numeric(frame[foreign_col], errors="coerce")
                foreign_mcap = (mcap / listed * foreign_shares).replace([np.inf, -np.inf], np.nan).sum()
                if foreign_mcap > 0:
                    foreign_pct = foreign_mcap / total * 100
            return {
                "date": pd.Timestamp(target).strftime("%Y-%m-%d"),
                "kospi_market_cap_trn_krw": base.cf(total / 1e12),
                "top2_direct_market_cap_trn_krw": base.cf(top2 / 1e12),
                "top2_direct_market_cap_share_pct": base.cf(top2 / total * 100),
                "kospi_foreign_ownership_mcap_weighted_pct": base.cf(foreign_pct),
                "source": "KRX(pykrx) 종목별 시가총액·외국인보유주식수",
                "note": "외국인 보유주식수는 KRX 확정치 시차가 있어 최신 유효 거래일을 사용",
            }
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("market snapshot failed: " + " / ".join(errors[-3:]))


def _returns(asset: dict[str, Any], n: int) -> float | None:
    h = asset.get("history") or []
    closes = [_num(x.get("close")) for x in h]
    closes = [x for x in closes if x is not None]
    if len(closes) <= n or closes[-n - 1] == 0:
        return None
    return base.cf((closes[-1] / closes[-n - 1] - 1) * 100)


def append_consensus_snapshot(payload: dict[str, Any]) -> pd.DataFrame:
    v = payload.get("valuation") or {}
    ref_date = v.get("reference_date") or payload.get("generated_at", "")[:10]
    rows = []
    for row in v.get("rows") or []:
        rows.append({
            "reference_date": ref_date,
            "company": row.get("key"),
            "name": row.get("name"),
            "eps_2026": row.get("eps_2026"),
            "eps_2027": row.get("eps_2027"),
            "eps_2028": row.get("eps_2028"),
            "source": v.get("source"),
        })
    return _merge_archive(CONSENSUS_ARCHIVE, rows, ["reference_date", "company"])


def estimate_change(archive: pd.DataFrame, company: str) -> dict[str, Any]:
    if archive.empty:
        return {"available": False}
    sub = archive[archive["company"] == company].copy()
    if sub.empty:
        return {"available": False}
    sub["reference_date"] = pd.to_datetime(sub["reference_date"], errors="coerce")
    sub = sub.dropna(subset=["reference_date"]).sort_values("reference_date")
    if len(sub) < 2:
        return {"available": False, "latest_reference_date": sub.iloc[-1]["reference_date"].strftime("%Y-%m-%d")}
    latest, prev = sub.iloc[-1], sub.iloc[-2]
    out: dict[str, Any] = {
        "available": True,
        "latest_reference_date": latest["reference_date"].strftime("%Y-%m-%d"),
        "previous_reference_date": prev["reference_date"].strftime("%Y-%m-%d"),
        "source": latest.get("source"),
    }
    for year in (2026, 2027, 2028):
        a, b = _num(latest.get(f"eps_{year}")), _num(prev.get(f"eps_{year}"))
        out[f"eps_{year}_change_pct"] = base.cf((a / b - 1) * 100) if a is not None and b not in (None, 0) else None
    return out


def build_cycle_signals(payload: dict[str, Any]) -> dict[str, Any]:
    assets = payload.get("assets") or {}
    manual = payload.get("manual") or {}
    ref = manual.get("cycle_rebound_reference") or {}
    date = (assets.get("KOSPI") or {}).get("date") or payload.get("generated_at", "")[:10]
    start = max(pd.Timestamp("2024-01-01"), pd.Timestamp(date) - pd.Timedelta(days=950)).strftime("%Y-%m-%d")
    errors: list[str] = []

    foreign: dict[str, Any] = {"points": [], "ownership": [], "source": None}
    try:
        flow, source = foreign_net_buy(start, date)
        cum = flow.cumsum()
        foreign["points"] = [
            {"date": i.strftime("%Y-%m-%d"), "daily_net_buy_trn": base.cf(flow.loc[i]), "cumulative_net_buy_trn": base.cf(cum.loc[i])}
            for i in flow.index
        ]
        foreign["source"] = source
        foreign["latest_daily_net_buy_trn"] = base.cf(flow.iloc[-1])
        foreign["cumulative_net_buy_trn"] = base.cf(cum.iloc[-1])
        foreign["net_buy_5d_trn"] = base.cf(flow.tail(5).sum())
        foreign["net_buy_20d_trn"] = base.cf(flow.tail(20).sum())
    except Exception as exc:
        errors.append(f"foreign flow: {exc}")

    ownership_rows: dict[str, pd.Series] = {}
    for ticker, key in (("005930", "samsung"), ("000660", "skhynix")):
        try:
            ownership_rows[key] = stock_foreign_ownership(start, date, ticker)
        except Exception as exc:
            errors.append(f"{key} ownership: {exc}")
    if ownership_rows:
        idx = sorted(set().union(*[set(s.index) for s in ownership_rows.values()]))
        foreign["ownership"] = [{
            "date": pd.Timestamp(i).strftime("%Y-%m-%d"),
            "samsung_pct": base.cf(ownership_rows.get("samsung", pd.Series(dtype=float)).get(i)),
            "skhynix_pct": base.cf(ownership_rows.get("skhynix", pd.Series(dtype=float)).get(i)),
        } for i in idx]
        for key, s in ownership_rows.items():
            foreign[f"{key}_foreign_ownership_pct"] = base.cf(s.iloc[-1]) if len(s) else None
            foreign[f"{key}_foreign_ownership_20d_change_pp"] = base.cf(s.iloc[-1] - s.iloc[-21]) if len(s) > 21 else None

    snapshot: dict[str, Any] = {}
    try:
        snapshot = market_snapshot(date)
    except Exception as exc:
        errors.append(str(exc))

    history_rows = []
    if snapshot:
        history_rows.append({
            "date": snapshot.get("date"),
            "kospi_foreign_ownership_mcap_weighted_pct": snapshot.get("kospi_foreign_ownership_mcap_weighted_pct"),
            "top2_direct_market_cap_share_pct": snapshot.get("top2_direct_market_cap_share_pct"),
            "kospi_market_cap_trn_krw": snapshot.get("kospi_market_cap_trn_krw"),
            "top2_direct_market_cap_trn_krw": snapshot.get("top2_direct_market_cap_trn_krw"),
            "source": snapshot.get("source"),
            "generated_at": payload.get("generated_at"),
        })
    history = _merge_archive(FOREIGN_ARCHIVE, history_rows, ["date"])
    if not history.empty:
        foreign["market_snapshot_history"] = history.tail(520).replace({np.nan: None}).to_dict("records")
    foreign["market_snapshot"] = snapshot

    if foreign.get("net_buy_20d_trn") is not None and foreign.get("samsung_foreign_ownership_20d_change_pp") is not None:
        flow_good = foreign["net_buy_20d_trn"] > 0
        own_good = foreign["samsung_foreign_ownership_20d_change_pp"] > 0 or (foreign.get("skhynix_foreign_ownership_20d_change_pp") or 0) > 0
        foreign["signal"] = "수급 회복 확인" if flow_good and own_good else "순매수 반전 관찰" if flow_good else "외국인 매도 압력 지속"
    else:
        foreign["signal"] = "데이터 축적 중"

    cons = append_consensus_snapshot(payload)
    earnings_rows = []
    for key in ("SAMSUNG", "SKHYNIX"):
        revision = estimate_change(cons, key)
        r5, r20 = _returns(assets.get(key) or {}, 5), _returns(assets.get(key) or {}, 20)
        revision["key"] = key
        revision["name"] = (assets.get(key) or {}).get("name", key)
        revision["price_return_5d_pct"] = r5
        revision["price_return_20d_pct"] = r20
        rev = revision.get("eps_2027_change_pct")
        if rev is None:
            status = "컨센서스 스냅샷 축적 중"
        elif rev < 0 and (r5 or -999) >= -2:
            status = "하향 조정에 둔감: 이익 신뢰 회복 후보"
        elif rev < 0 and (r5 or 0) <= -5:
            status = "하향 조정에 민감: 피크아웃 우려 지속"
        elif rev >= 0 and (r5 or 0) < 0:
            status = "상향에도 주가 약세: 호재 불반응 경고"
        else:
            status = "중립"
        revision["status"] = status
        earnings_rows.append(revision)

    top2 = {
        "current_direct_market_cap_share_pct": snapshot.get("top2_direct_market_cap_share_pct") if snapshot else None,
        "current_reference_date": snapshot.get("date") if snapshot else None,
        "reported_market_cap_share_pct": ref.get("reported_top2_market_cap_share_pct"),
        "reported_12m_net_income_share_pct": ref.get("reported_top2_12m_net_income_share_pct"),
        "house_12m_net_income_share_pct": ref.get("house_top2_12m_net_income_share_pct"),
        "reported_gap_pp": base.cf((ref.get("reported_top2_12m_net_income_share_pct") or 0) - (ref.get("reported_top2_market_cap_share_pct") or 0)),
        "method_note": ref.get("reported_share_method"),
        "source": ref.get("source"),
        "reference_date": ref.get("reference_date"),
    }

    return {
        "foreign": foreign,
        "top2_share_gap": top2,
        "earnings_trust": {
            "rows": earnings_rows,
            "historical_rule": ref.get("historical_rule"),
            "update_note": ref.get("update_note"),
            "source": ref.get("source"),
            "reference_date": ref.get("reference_date"),
        },
        "errors": errors,
    }


def make_html_lightweight_v8() -> None:
    path: Path = base.OUTPUT_HTML
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(<script id="embedded" type="application/json">).*?(</script>)', r'\1{}\2', text, flags=re.S)
    text = re.sub(r'href="styles\.css(?:\?v=\d+)?"', 'href="styles.css?v=8"', text)
    for name in ("core", "charts", "panels", "app"):
        text = re.sub(rf'src="js/{name}\.js(?:\?v=\d+)?"', f'src="js/{name}.js?v=8"', text)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    base.main()
    payload = json.loads(base.OUTPUT_JSON.read_text(encoding="utf-8"))
    payload["cycle_signals"] = build_cycle_signals(payload)
    base.OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    v7.append_archives()
    make_html_lightweight_v8()
    print("dashboard v8 cycle signals updated")
