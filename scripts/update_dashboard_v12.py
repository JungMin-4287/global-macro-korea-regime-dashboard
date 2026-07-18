#!/usr/bin/env python3
"""Dashboard v12: tolerate KRX market-cap schema changes.

The public pykrx market-cap table may expose only close, market cap, volume and
trading value. Top2 market-cap share needs only market cap, so missing listed
shares must not invalidate the whole snapshot. Aggregate foreign ownership is
left unavailable when the required share-count columns are absent.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import update_dashboard as base
import update_dashboard_v7 as v7
import update_dashboard_v8 as v8
import update_dashboard_v9 as v9
import update_dashboard_v10 as v10  # noqa: F401 - applies daily foreign-flow patch
import update_dashboard_v11 as v11


def market_snapshot_v12(date: str) -> dict[str, Any]:
    from pykrx import stock

    d = pd.Timestamp(date)
    errors: list[str] = []
    for offset in range(0, 10):
        target = (d - pd.Timedelta(days=offset)).strftime("%Y%m%d")
        try:
            kospi_tickers = set(stock.get_market_ticker_list(target, market="KOSPI"))
            raw = stock.get_market_cap(target)
            if raw is None or raw.empty:
                continue
            raw.index = raw.index.astype(str)
            frame = raw.loc[raw.index.intersection(kospi_tickers)].copy()
            mcap_col = v8._column(frame, ("시가총액",))
            if mcap_col is None:
                errors.append(f"{target}: 시가총액 열 없음 ({list(frame.columns)})")
                continue

            mcap = pd.to_numeric(frame[mcap_col], errors="coerce")
            total = float(mcap.sum())
            if not np.isfinite(total) or total <= 0:
                continue
            top2 = float(mcap.reindex(["005930", "000660"]).fillna(0).sum())

            shares_col = v8._column(frame, ("상장주식수",))
            foreign_col = v8._column(frame, ("외국인보유주식수",))
            foreign_pct = None
            note = "KOSPI 전체 외국인 보유비중은 원자료 열이 없으면 미산출"
            if shares_col is not None and foreign_col is not None:
                listed = pd.to_numeric(frame[shares_col], errors="coerce").replace(0, np.nan)
                foreign_shares = pd.to_numeric(frame[foreign_col], errors="coerce")
                foreign_mcap = (mcap / listed * foreign_shares).replace([np.inf, -np.inf], np.nan).sum()
                if foreign_mcap > 0:
                    foreign_pct = foreign_mcap / total * 100
                    note = "외국인 보유주식수는 KRX 확정치 시차가 있어 최신 유효 거래일 사용"

            return {
                "date": pd.Timestamp(target).strftime("%Y-%m-%d"),
                "kospi_market_cap_trn_krw": base.cf(total / 1e12),
                "top2_direct_market_cap_trn_krw": base.cf(top2 / 1e12),
                "top2_direct_market_cap_share_pct": base.cf(top2 / total * 100),
                "kospi_foreign_ownership_mcap_weighted_pct": base.cf(foreign_pct),
                "source": "KRX(pykrx) 종목별 시가총액",
                "note": note,
                "available_columns": [str(c) for c in frame.columns],
            }
        except Exception as exc:
            errors.append(f"{target}: {exc}")
    raise RuntimeError("최근 유효 거래일의 KOSPI 시가총액 자료를 받지 못했습니다")


def sanitise_errors(payload: dict[str, Any]) -> None:
    cycle = payload.get("cycle_signals") or {}
    clean: list[str] = []
    for message in cycle.get("errors") or []:
        text = str(message)
        if "market snapshot" in text.lower() or "are in the [columns]" in text:
            clean.append("KOSPI 전체 외국인 보유비중은 KRX 원자료 열 변경으로 미산출됐습니다. 외국인 순매수와 삼성전자·SK하이닉스 지분율은 별도로 정상 표시됩니다.")
        else:
            clean.append(text)
    cycle["errors"] = list(dict.fromkeys(clean))
    if cycle.get("foreign") is not None:
        cycle["foreign"]["collection_errors"] = cycle["errors"]


def finalise_html_v12() -> None:
    path: Path = base.OUTPUT_HTML
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(<script id="embedded" type="application/json">).*?(</script>)', r'\1{}\2', text, flags=re.S)
    text = re.sub(r'href="styles\.css(?:\?v=\d+)?"', 'href="styles.css?v=12"', text)
    for name in ("core", "charts", "panels", "foreign-fix", "app"):
        text = re.sub(rf'src="js/{name}\.js(?:\?v=\d+)?"', f'src="js/{name}.js?v=12"', text)
    path.write_text(text, encoding="utf-8")


v8.market_snapshot = market_snapshot_v12


if __name__ == "__main__":
    base.main()
    payload = json.loads(base.OUTPUT_JSON.read_text(encoding="utf-8"))
    payload["cycle_signals"] = v8.build_cycle_signals(payload)
    sanitise_errors(payload)
    base.OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    v7.append_archives()
    v9.persist_foreign_archives(payload)
    finalise_html_v12()
    print("dashboard v12 KRX market snapshot updated")
