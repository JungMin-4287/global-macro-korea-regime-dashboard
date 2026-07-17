#!/usr/bin/env python3
"""Dashboard v4: repair Naver investor-flow fallback endpoint."""
from __future__ import annotations

from io import BytesIO

import pandas as pd
import requests

import update_dashboard as base
import update_dashboard_v3 as v3


def flow_from_naver_legacy():
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Referer": "https://finance.naver.com/sise/sise_trans_style.naver",
    }
    rows: list[tuple[pd.Timestamp, float]] = []
    bizdate = pd.Timestamp.now(tz="Asia/Seoul").strftime("%Y%m%d")

    for page in range(1, 30):
        url = f"https://finance.naver.com/sise/investorDealTrendDay.nhn?bizdate={bizdate}&sosok=&page={page}"
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()

        tables = pd.read_html(BytesIO(response.content))
        if not tables:
            continue
        table = tables[0].dropna(how="all")
        if table.empty or table.shape[1] < 2:
            continue

        for _, row in table.iterrows():
            raw_date = str(row.iloc[0]).strip()
            date = pd.to_datetime(raw_date, format="%y.%m.%d", errors="coerce")
            if pd.isna(date):
                date = pd.to_datetime(raw_date, errors="coerce")
            amount = pd.to_numeric(row.iloc[1], errors="coerce")
            if pd.notna(date) and pd.notna(amount):
                # Naver table unit is KRW 100 million; convert to KRW trillion.
                rows.append((pd.Timestamp(date).normalize(), float(amount) / 10000.0))

        if len({d for d, _ in rows}) >= 220:
            break

    if len(rows) < 10:
        raise RuntimeError(f"Naver legacy endpoint: insufficient observations ({len(rows)})")

    frame = (
        pd.DataFrame(rows, columns=["date", "x"])
        .drop_duplicates("date", keep="first")
        .set_index("date")
        .sort_index()
    )
    return frame["x"], "Naver Finance 개인 순매수(억원→조원)"


v3._flow_from_naver = flow_from_naver_legacy
base.psychology = v3.psychology_v3

if __name__ == "__main__":
    base.main()
