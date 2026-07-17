#!/usr/bin/env python3
"""Dashboard v5.

- Use Investing.com KOSPI Volatility as the preferred current VKOSPI source.
- Merge it with KRX history when available; never merge with a realized-volatility proxy.
- Add a volatility-specific interpretation and summary fields.
- Highlight recent and statistically unusual investor-flow observations.
"""
from __future__ import annotations

from io import BytesIO
import re
from typing import Any

import numpy as np
import pandas as pd
import requests

import update_dashboard as base
import update_dashboard_v4 as v4  # noqa: F401 - loads the v4 investor-flow engine

ORIGINAL_FETCH_VKOSPI = base.fetch_vkospi
ORIGINAL_METRICS = base.metrics
ORIGINAL_PSYCHOLOGY = base.psychology


def _frame_from_investing_text(text: str) -> pd.DataFrame:
    rows: list[tuple[pd.Timestamp, float]] = []
    patterns = [
        r"(?mi)^\s*\|?\s*([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})\s*\|\s*([0-9,]+(?:\.\d+)?)",
        r"(?m)^\s*\|?\s*(\d{4}년\s+\d{1,2}월\s+\d{1,2}일)\s*\|\s*([0-9,]+(?:\.\d+)?)",
        r"(?m)^\s*\|?\s*(\d{1,2}-\d{1,2}-\d{4})\s*\|\s*([0-9,]+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        for raw_date, raw_price in re.findall(pattern, text):
            normalized = re.sub(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", r"\1-\2-\3", raw_date)
            date = pd.to_datetime(normalized, errors="coerce", dayfirst="-" in normalized and normalized[:2].isdigit())
            price = pd.to_numeric(raw_price.replace(",", ""), errors="coerce")
            if pd.notna(date) and pd.notna(price):
                rows.append((pd.Timestamp(date).normalize(), float(price)))
    if len(rows) < 10:
        raise RuntimeError(f"text parser found only {len(rows)} observations")
    frame = pd.DataFrame(rows, columns=["date", "close"]).drop_duplicates("date", keep="first").set_index("date").sort_index()
    return frame


def _frame_from_investing_html(content: bytes) -> pd.DataFrame:
    tables = pd.read_html(BytesIO(content))
    for table in tables:
        columns = {str(c).strip().lower(): c for c in table.columns}
        date_col = next((orig for low, orig in columns.items() if low in {"date", "날짜"}), None)
        price_col = next((orig for low, orig in columns.items() if low in {"price", "종가", "last"}), None)
        if date_col is None or price_col is None:
            continue
        dates = pd.to_datetime(table[date_col], errors="coerce")
        prices = pd.to_numeric(
            table[price_col].astype(str).str.replace(",", "", regex=False).str.replace("−", "-", regex=False),
            errors="coerce",
        )
        frame = pd.DataFrame({"close": prices.to_numpy()}, index=dates).dropna().sort_index()
        frame = frame[~frame.index.duplicated(keep="last")]
        if len(frame) >= 10:
            return frame
    raise RuntimeError("historical table not found")


def _investing_vkospi() -> tuple[pd.DataFrame, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
        "Referer": "https://www.investing.com/indices/kospi-volatility",
    }
    errors: list[str] = []
    direct_urls = [
        "https://www.investing.com/indices/kospi-volatility-historical-data",
        "https://kr.investing.com/indices/kospi-volatility-historical-data",
    ]
    for url in direct_urls:
        try:
            response = requests.get(url, headers=headers, timeout=25)
            response.raise_for_status()
            try:
                return _frame_from_investing_html(response.content), "Investing.com KOSPI Volatility (KSVKOSPI)"
            except Exception:
                return _frame_from_investing_text(response.text), "Investing.com KOSPI Volatility (KSVKOSPI)"
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    # Investing sometimes blocks cloud runners. Jina Reader is a text mirror of the same public page.
    reader_urls = [
        "https://r.jina.ai/http://www.investing.com/indices/kospi-volatility-historical-data",
        "https://r.jina.ai/http://kr.investing.com/indices/kospi-volatility-historical-data",
    ]
    for url in reader_urls:
        try:
            response = requests.get(url, headers={"User-Agent": headers["User-Agent"]}, timeout=35)
            response.raise_for_status()
            frame = _frame_from_investing_text(response.text)
            return frame, "Investing.com KOSPI Volatility via Jina Reader"
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError(" / ".join(errors))


def fetch_vkospi_v5(start: str, end: str):
    investing_frame: pd.DataFrame | None = None
    investing_source: str | None = None
    underlying_frame: pd.DataFrame | None = None
    underlying_source: str | None = None
    errors: list[str] = []

    try:
        investing_frame, investing_source = _investing_vkospi()
    except Exception as exc:
        errors.append(f"Investing.com: {exc}")

    try:
        underlying_frame, underlying_source = ORIGINAL_FETCH_VKOSPI(start, end)
    except Exception as exc:
        errors.append(f"KRX/proxy: {exc}")

    if investing_frame is not None and underlying_frame is not None and "대체" not in str(underlying_source):
        combined = pd.concat([underlying_frame[["close"]], investing_frame[["close"]]])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        return combined, f"{investing_source} · 장기이력 {underlying_source}"

    if investing_frame is not None:
        return investing_frame, investing_source or "Investing.com KOSPI Volatility"

    if underlying_frame is not None:
        return underlying_frame, underlying_source or "VKOSPI fallback"

    raise RuntimeError(" / ".join(errors))


def metrics_v5(key: str, df: pd.DataFrame, source: str):
    m, out = ORIGINAL_METRICS(key, df, source)
    if key != "VKOSPI":
        return m, out

    level = m.get("close")
    m["sma20"] = base.cf(out["sma20"].iloc[-1]) if "sma20" in out else None
    m["level_percentile_3y"] = base.percentile(out["close"], 756)
    year = out["close"].tail(252)
    m["low_52w"] = base.cf(year.min()) if not year.empty else None
    m["high_52w"] = base.cf(year.max()) if not year.empty else None
    m["is_proxy"] = "대체" in source

    if level is None:
        zone = "미산출"
        action = "변동성 데이터를 확인할 때까지 과매도 매수 비중을 제한합니다."
    elif level < 20:
        zone = "안정 구간"
        action = "변동성은 안정적입니다. 다만 지나친 안도와 주가 과열 여부는 별도로 확인합니다."
    elif level < 30:
        zone = "경계 구간"
        action = "변동성이 평시보다 높습니다. 지수 반등과 VKOSPI 하락이 함께 나오는지 확인합니다."
    elif level < 50:
        zone = "고변동성 구간"
        action = "가격 급변 가능성이 높습니다. 분할매수만 허용하고 전저점 방어를 확인합니다."
    elif level < 75:
        zone = "시장 위기 구간"
        action = "강제청산과 레버리지 축소 가능성이 큽니다. VKOSPI 고점 통과 전까지 매수 비중을 제한합니다."
    else:
        zone = "극단적 공포·강제청산 구간"
        action = "역사적 극단 구간입니다. 공포 자체는 반등 후보지만 최소 2거래일 하락 전환과 시장 폭 회복이 필요합니다."

    percentile = m.get("level_percentile_3y")
    summary = f"VKOSPI {level:.2f}" if level is not None else "VKOSPI 미산출"
    if m.get("sma20") is not None:
        summary += f", 20일 평균 {m['sma20']:.2f}"
    if m.get("sma50") is not None:
        summary += f", 50일 평균 {m['sma50']:.2f}"
    if percentile is not None:
        summary += f", 3년 수준 백분위 {percentile:.1f}%"
    if m["is_proxy"]:
        summary += ". 실제 VKOSPI가 아닌 실현변동성 대체치"

    m["disparity_interpretation"] = {
        "zone": zone,
        "headline": f"현재 구간: {zone}",
        "summary": summary,
        "action": action,
    }
    return m, out


def psychology_v5(start: str, end: str, kospi: pd.DataFrame) -> dict[str, Any]:
    result = ORIGINAL_PSYCHOLOGY(start, end, kospi)
    points = result.get("points") or []
    if len(points) < 5:
        result["highlights"] = []
        return result

    slope = result.get("slope")
    intercept = result.get("intercept")
    if slope is None or intercept is None:
        x = np.array([float(p["x"]) for p in points])
        y = np.array([float(p["y"]) for p in points])
        slope, intercept = np.polyfit(x, y, 1)

    enriched = []
    for p in points:
        residual = float(p["y"]) - (float(slope) * float(p["x"]) + float(intercept))
        enriched.append({**p, "residual": residual})

    selected: list[dict[str, Any]] = [enriched[-1]]
    for candidate in sorted(enriched[:-1], key=lambda p: abs(p["residual"]), reverse=True):
        if all(candidate["date"] != item["date"] for item in selected):
            selected.append(candidate)
        if len(selected) >= 4:
            break

    for item in selected:
        dt = pd.to_datetime(item["date"], errors="coerce")
        item["label"] = dt.strftime("%-m/%-d") if pd.notna(dt) else item["date"]
    result["highlights"] = selected
    result["highlight_note"] = "최신 거래일과 회귀선에서 가장 크게 벗어난 주요 변곡일을 자동 표시합니다."
    return result


base.fetch_vkospi = fetch_vkospi_v5
base.metrics = metrics_v5
base.psychology = psychology_v5

if __name__ == "__main__":
    base.main()
