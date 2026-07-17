#!/usr/bin/env python3
"""Robust data fallbacks for dashboard v2.

- KRX individual net-buy: recent-window query, then Naver Finance fallback
- VKOSPI: actual KRX series first, then transparent KOSPI 20-day realized-vol proxy
"""
from __future__ import annotations

import math
import re
from io import StringIO
from typing import Any

import numpy as np
import pandas as pd
import requests

import update_dashboard as base
import update_dashboard_v2 as v2


def fetch_vkospi_v3(start: str, end: str):
    try:
        frame, source = v2.ORIGINAL_FETCH_VKOSPI(start, end)
        if frame is not None and len(frame.dropna()) >= 60:
            return frame, source
    except Exception:
        pass

    kospi = v2.KOSPI_FRAME
    if kospi is None or kospi.empty:
        kospi, _ = v2.ORIGINAL_FETCH_ASSET(base.ASSETS["KOSPI"], start, end)

    proxy = kospi["close"].pct_change().rolling(20, min_periods=15).std() * math.sqrt(252) * 100
    frame = pd.DataFrame({"close": proxy}).dropna()
    if frame.empty:
        raise RuntimeError("VKOSPI and realized-volatility proxy unavailable")
    return frame, "KOSPI 20일 실현변동성 대체지표"


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [" ".join(str(x) for x in col if str(x) != "nan").strip() for col in out.columns]
    else:
        out.columns = [str(c).strip() for c in out.columns]
    return out


def _normalise_flow(raw: pd.DataFrame, divisor: float, source: str) -> tuple[pd.Series, str]:
    if raw is None or raw.empty:
        raise RuntimeError(f"{source}: empty response")
    raw = _flatten_columns(raw)
    personal_col = next((c for c in raw.columns if "개인" in c), None)
    if personal_col is None:
        raise RuntimeError(f"{source}: 개인 column missing")
    idx = pd.to_datetime(raw.index, errors="coerce")
    values = pd.to_numeric(raw[personal_col], errors="coerce")
    flow = pd.Series(values.to_numpy() / divisor, index=idx, name="x").dropna()
    flow = flow[~flow.index.isna()].sort_index()
    if len(flow) < 10:
        raise RuntimeError(f"{source}: insufficient observations ({len(flow)})")
    return flow, source


def _flow_from_pykrx(start: str, end: str) -> tuple[pd.Series, str]:
    from pykrx import stock

    end_ts = pd.Timestamp(end)
    recent_start = max(pd.Timestamp(start), end_ts - pd.Timedelta(days=550)).strftime("%Y%m%d")
    end_s = end_ts.strftime("%Y%m%d")
    errors: list[str] = []
    for kwargs in (
        {"on": "순매수"},
        {},
        {"on": "순매수", "etf": True, "etn": True, "elw": True},
    ):
        try:
            raw = stock.get_market_trading_value_by_date(recent_start, end_s, "KOSPI", **kwargs)
            return _normalise_flow(raw, 1e12, "KRX(pykrx) 개인 순매수")
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError(" / ".join(errors))


def _parse_number(value: Any) -> float | None:
    text = str(value).strip().replace(",", "").replace("+", "")
    text = re.sub(r"[^0-9.\-]", "", text)
    if text in ("", "-", ".", "-."):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _flow_from_naver() -> tuple[pd.Series, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Referer": "https://finance.naver.com/sise/sise_trans_style.naver?sosok=01",
    }
    rows: list[tuple[pd.Timestamp, float]] = []
    for page in range(1, 25):
        url = f"https://finance.naver.com/sise/investorDealTrendDay.naver?sosok=01&page={page}"
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "euc-kr"
        found = False
        for table in pd.read_html(StringIO(response.text)):
            table = _flatten_columns(table)
            date_col = next((c for c in table.columns if "날짜" in c or "일자" in c), None)
            personal_col = next((c for c in table.columns if "개인" in c), None)
            if date_col is None or personal_col is None:
                continue
            found = True
            for _, row in table.iterrows():
                date = pd.to_datetime(str(row[date_col]).strip(), errors="coerce")
                amount = _parse_number(row[personal_col])
                if pd.notna(date) and amount is not None:
                    rows.append((pd.Timestamp(date).normalize(), amount / 10000.0))
        if len({d for d, _ in rows}) >= 220:
            break
        if not found and page >= 3:
            break

    if len(rows) < 10:
        raise RuntimeError(f"Naver Finance: insufficient observations ({len(rows)})")
    frame = pd.DataFrame(rows, columns=["date", "x"]).drop_duplicates("date", keep="first").set_index("date").sort_index()
    return frame["x"], "Naver Finance 개인 순매수(억원→조원)"


def psychology_v3(start: str, end: str, kospi: pd.DataFrame) -> dict[str, Any]:
    errors: list[str] = []
    individual: pd.Series | None = None
    source = ""

    try:
        individual, source = _flow_from_pykrx(start, end)
    except Exception as exc:
        errors.append(str(exc))

    if individual is None:
        try:
            individual, source = _flow_from_naver()
        except Exception as exc:
            errors.append(str(exc))

    if individual is None:
        return {
            "points": [], "regression": [], "zone": "미산출",
            "source": " / ".join(errors), "error": " / ".join(errors),
            "interpretation": "KRX와 네이버 금융에서 개인 순매수 데이터를 모두 받지 못했습니다. 다음 자동 실행에서 재시도합니다.",
        }

    returns = kospi["close"].pct_change() * 100
    frame = pd.concat([individual.rename("x"), returns.rename("y")], axis=1).dropna().tail(180)
    if len(frame) < 10:
        return {
            "points": [], "regression": [], "zone": "미산출", "source": source,
            "error": f"가격과 수급의 공통 날짜 부족 ({len(frame)})",
            "interpretation": "가격과 수급 데이터의 기준일이 일치하지 않아 산점도를 만들지 못했습니다.",
        }

    slope, intercept = np.polyfit(frame.x, frame.y, 1)
    latest_x, latest_y = float(frame.x.iloc[-1]), float(frame.y.iloc[-1])
    residual = latest_y - (slope * latest_x + intercept)

    if latest_x > 0 and latest_y < 0:
        zone = "개인 저가매수·지수 하락"
        text = "개인이 외국인·기관 매물을 받아냈지만 지수는 하락했습니다. 레버리지와 매도 압력이 아직 해소되지 않았을 가능성이 큽니다."
    elif latest_x < 0 and latest_y > 0:
        zone = "외국인·기관 주도 상승"
        text = "개인 매도에도 지수가 상승했습니다. 외국인·기관이 가격을 끌어올리는 비교적 건전한 수급입니다."
    elif latest_x > 0 and latest_y > 0:
        zone = "동반 매수·탐욕 관찰"
        text = "개인 순매수와 지수 상승이 함께 나타났습니다. 추세 강화일 수 있지만 급격한 추격매수라면 과열을 경계합니다."
    else:
        zone = "공포·위험 축소"
        text = "개인 순매도와 지수 하락이 동시에 나타났습니다. 투매가 매도 고갈로 이어지는지 다음 거래일 회복을 확인합니다."

    if residual < -1:
        text += " 과거 회귀관계보다 지수 반응이 약해 수급 스트레스가 큽니다."
    elif residual > 1:
        text += " 과거 회귀관계보다 지수 반응이 강해 수급 개선 가능성이 있습니다."

    x_min, x_max = float(frame.x.min()), float(frame.x.max())
    return {
        "points": [{"date": idx.strftime("%Y-%m-%d"), "x": base.cf(row.x), "y": base.cf(row.y)} for idx, row in frame.iterrows()],
        "regression": [
            {"x": base.cf(x_min), "y": base.cf(slope * x_min + intercept)},
            {"x": base.cf(x_max), "y": base.cf(slope * x_max + intercept)},
        ],
        "latest": {
            "date": frame.index[-1].strftime("%Y-%m-%d"),
            "x": base.cf(latest_x), "y": base.cf(latest_y), "residual": base.cf(residual),
        },
        "correlation": base.cf(frame.corr().iloc[0, 1]),
        "zone": zone, "source": source, "interpretation": text,
    }


base.fetch_vkospi = fetch_vkospi_v3
base.psychology = psychology_v3

if __name__ == "__main__":
    base.main()
