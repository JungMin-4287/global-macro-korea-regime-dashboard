#!/usr/bin/env python3
"""Dashboard v10: harden KOSPI foreign net-buy fallback parsing.

Naver's investor table sometimes exposes a two-level header and sometimes keeps
trading dates in the index. v9 relied on header text only; v10 also detects the
date column from values and, when necessary, uses the documented table order
(date, individual, foreign, institution, ...).
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
import update_dashboard_v9 as v9  # applies ownership/market-snapshot fallbacks


DATE_PATTERN = re.compile(r"^\s*\d{2,4}[.\-/]\d{1,2}[.\-/]\d{1,2}\s*$")


def _parse_date(value: Any) -> pd.Timestamp | None:
    text = str(value).strip()
    if not DATE_PATTERN.match(text):
        return None
    for fmt in ("%y.%m.%d", "%Y.%m.%d", "%Y-%m-%d", "%y-%m-%d", "%Y/%m/%d", "%y/%m/%d"):
        try:
            return pd.Timestamp.strptime(text, fmt).normalize()
        except Exception:
            pass
    parsed = pd.to_datetime(text, errors="coerce")
    return pd.Timestamp(parsed).normalize() if pd.notna(parsed) else None


def _date_column(table: pd.DataFrame) -> Any | None:
    for col in table.columns:
        if "날짜" in str(col) or "일자" in str(col):
            return col
    best, count = None, 0
    for col in table.columns:
        hits = sum(_parse_date(v) is not None for v in table[col].head(25))
        if hits > count:
            best, count = col, hits
    return best if count >= 3 else None


def _foreign_column(table: pd.DataFrame, date_col: Any) -> Any | None:
    named = next(
        (c for c in table.columns if "외국인" in str(c) and "보유" not in str(c) and "지분" not in str(c)),
        None,
    )
    if named is not None:
        return named

    # Naver investorDealTrendDay documented order after date:
    # 개인, 외국인, 기관계, 금융투자, 보험, 투신, ...
    cols = list(table.columns)
    try:
        pos = cols.index(date_col)
    except ValueError:
        pos = 0
    if pos + 2 < len(cols):
        return cols[pos + 2]
    return None


def _normalise_table(raw: pd.DataFrame) -> pd.DataFrame:
    table = raw.copy().dropna(how="all").dropna(axis=1, how="all")
    if isinstance(table.columns, pd.MultiIndex):
        table.columns = [
            " ".join(str(x) for x in col if str(x).lower() != "nan").strip()
            for col in table.columns
        ]
    else:
        table.columns = [str(c).strip() for c in table.columns]

    # Dates are often stored as the DataFrame index by read_html.
    if not isinstance(table.index, pd.RangeIndex):
        table = table.reset_index()
        table.columns = [str(c).strip() for c in table.columns]
    return table


def _naver_foreign_net_buy_v10(end: str) -> tuple[pd.Series, str]:
    rows: list[tuple[pd.Timestamp, float]] = []
    end_code = pd.Timestamp(end).strftime("%Y%m%d")
    variants = (
        "https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate={end}&sosok=&page={page}",
        "https://finance.naver.com/sise/investorDealTrendDay.nhn?bizdate={end}&sosok=&page={page}",
        "https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate={end}&sosok=01&page={page}",
    )
    errors: list[str] = []

    for pattern in variants:
        variant_rows: list[tuple[pd.Timestamp, float]] = []
        try:
            for page in range(1, 36):
                url = pattern.format(end=end_code, page=page)
                response = requests.get(url, headers=v9.HEADERS, timeout=20)
                response.raise_for_status()
                response.encoding = response.apparent_encoding or "euc-kr"
                tables = pd.read_html(StringIO(response.text))
                found = False
                for raw in tables:
                    table = _normalise_table(raw)
                    date_col = _date_column(table)
                    if date_col is None:
                        continue
                    foreign_col = _foreign_column(table, date_col)
                    if foreign_col is None:
                        continue
                    found = True
                    for _, row in table.iterrows():
                        date = _parse_date(row.get(date_col))
                        amount = v9._clean_number(row.get(foreign_col))
                        if date is not None and amount is not None:
                            variant_rows.append((date, amount / 10000.0))
                if len({d for d, _ in variant_rows}) >= 260:
                    break
                if not found and page >= 3:
                    break
            if len(variant_rows) >= 10:
                rows = variant_rows
                break
            errors.append(f"{pattern}: {len(variant_rows)} rows")
        except Exception as exc:
            errors.append(f"{pattern}: {exc}")

    if len(rows) < 10:
        raise RuntimeError("Naver foreign flow parser failed: " + " / ".join(errors[-3:]))

    frame = (
        pd.DataFrame(rows, columns=["date", "foreign_net_buy_trn"])
        .drop_duplicates("date", keep="first")
        .set_index("date")
        .sort_index()
    )
    return frame["foreign_net_buy_trn"], "Naver Finance KOSPI 외국인 순매수(억원→조원, 구조 감지 파서)"


def foreign_net_buy_v10(start: str, end: str) -> tuple[pd.Series, str]:
    errors: list[str] = []
    try:
        return v9.ORIGINAL_FOREIGN_NET_BUY(start, end)
    except Exception as exc:
        errors.append(f"KRX: {exc}")
    try:
        s, source = _naver_foreign_net_buy_v10(end)
        start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
        s = s[(s.index >= start_ts) & (s.index <= end_ts)]
        if len(s) >= 10:
            return s, source
        errors.append(f"Naver common period insufficient ({len(s)})")
    except Exception as exc:
        errors.append(f"Naver: {exc}")
    if v9.FLOW_ARCHIVE.exists():
        try:
            old = pd.read_csv(v9.FLOW_ARCHIVE)
            old["date"] = pd.to_datetime(old["date"], errors="coerce")
            s = (
                old.dropna(subset=["date", "daily_net_buy_trn"])
                .drop_duplicates("date", keep="last")
                .set_index("date")["daily_net_buy_trn"]
                .sort_index()
            )
            if len(s) >= 10:
                return s, "GitHub CSV 외국인 순매수 보존자료(원자료 일시 실패)"
        except Exception as exc:
            errors.append(f"archive: {exc}")
    raise RuntimeError(" / ".join(errors))


def make_html_lightweight_v10() -> None:
    path: Path = base.OUTPUT_HTML
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(<script id="embedded" type="application/json">).*?(</script>)', r'\1{}\2', text, flags=re.S)
    text = re.sub(r'href="styles\.css(?:\?v=\d+)?"', 'href="styles.css?v=10"', text)
    for name in ("core", "charts", "panels", "app"):
        text = re.sub(rf'src="js/{name}\.js(?:\?v=\d+)?"', f'src="js/{name}.js?v=10"', text)
    path.write_text(text, encoding="utf-8")


v8.foreign_net_buy = foreign_net_buy_v10


if __name__ == "__main__":
    base.main()
    payload = json.loads(base.OUTPUT_JSON.read_text(encoding="utf-8"))
    payload["cycle_signals"] = v8.build_cycle_signals(payload)
    base.OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    v7.append_archives()
    v9.persist_foreign_archives(payload)
    make_html_lightweight_v10()
    print("dashboard v10 foreign-flow parser updated")
