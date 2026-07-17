#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DATA_DIR = DOCS / "data"
TEMPLATE = ROOT / "templates" / "index.template.html"
MANUAL = DATA_DIR / "manual_signals.json"
OUTPUT_JSON = DATA_DIR / "market_data.json"
OUTPUT_CSV = DATA_DIR / "market_history.csv"
OUTPUT_HTML = DOCS / "index.html"

ASSETS = {
    "KOSPI": {"name": "KOSPI", "type": "index", "pykrx": "1001", "yf": "^KS11"},
    "KOSDAQ": {"name": "KOSDAQ", "type": "index", "pykrx": "2001", "yf": "^KQ11"},
    "SAMSUNG": {"name": "삼성전자", "type": "stock", "pykrx": "005930", "yf": "005930.KS"},
    "SKHYNIX": {"name": "SK하이닉스", "type": "stock", "pykrx": "000660", "yf": "000660.KS"},
}

SEOUL = timezone(timedelta(hours=9))


def clean_float(value: Any) -> float | None:
    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return round(number, 4)
    except (TypeError, ValueError):
        return None


def fetch_with_pykrx(asset: dict[str, str], start: str, end: str) -> pd.DataFrame:
    from pykrx import stock
    if asset["type"] == "index":
        raw = stock.get_index_ohlcv_by_date(start, end, asset["pykrx"])
    else:
        raw = stock.get_market_ohlcv_by_date(start, end, asset["pykrx"])
    if raw is None or raw.empty or "종가" not in raw.columns:
        raise RuntimeError("pykrx returned no closing-price data")
    df = pd.DataFrame(index=pd.to_datetime(raw.index))
    df["close"] = pd.to_numeric(raw["종가"], errors="coerce")
    if "거래량" in raw.columns:
        df["volume"] = pd.to_numeric(raw["거래량"], errors="coerce")
    return df.dropna(subset=["close"]).sort_index()


def fetch_with_yfinance(asset: dict[str, str], start: str, end: str) -> pd.DataFrame:
    import yfinance as yf
    raw = yf.download(asset["yf"], start=start, end=end, auto_adjust=False, progress=False)
    if raw is None or raw.empty:
        raise RuntimeError("yfinance returned no data")
    close = raw["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    df = pd.DataFrame(index=pd.to_datetime(close.index))
    df["close"] = pd.to_numeric(close, errors="coerce")
    if "Volume" in raw:
        volume = raw["Volume"]
        if isinstance(volume, pd.DataFrame):
            volume = volume.iloc[:, 0]
        df["volume"] = pd.to_numeric(volume, errors="coerce")
    return df.dropna(subset=["close"]).sort_index()


def fetch_asset(asset: dict[str, str], start: str, end: str) -> tuple[pd.DataFrame, str]:
    errors = []
    try:
        return fetch_with_pykrx(asset, start.replace("-", ""), end.replace("-", "")), "KRX(pykrx)"
    except Exception as exc:
        errors.append(f"pykrx: {exc}")
    try:
        return fetch_with_yfinance(asset, start, end), "Yahoo Finance fallback"
    except Exception as exc:
        errors.append(f"yfinance: {exc}")
    raise RuntimeError(" / ".join(errors))


def percentile_of_last(series: pd.Series, window: int = 756) -> float | None:
    s = series.dropna().tail(window)
    if len(s) < 20:
        return None
    return clean_float(s.rank(pct=True).iloc[-1] * 100)


def current_and_mdd(close: pd.Series, window: int = 252) -> tuple[float | None, float | None]:
    s = close.dropna().tail(window)
    if s.empty:
        return None, None
    dd = (s / s.cummax() - 1.0) * 100
    return clean_float(dd.iloc[-1]), clean_float(dd.min())


def classify_index(metrics: dict[str, Any]) -> tuple[str, int, list[str]]:
    score = 0
    reasons: list[str] = []
    ratio50 = metrics.get("ratio50")
    p50 = metrics.get("ratio50_percentile_3y")
    p120 = metrics.get("ratio120_percentile_3y")
    dd = metrics.get("current_drawdown_pct")
    rebound = metrics.get("rebound_3d", False)
    if p50 is not None and p50 <= 20:
        score += 1
        reasons.append(f"50일 이격도 지수의 3년 백분위가 {p50:.1f}%")
    if p120 is not None and p120 <= 20:
        score += 1
        reasons.append(f"120일 이격도 지수의 3년 백분위가 {p120:.1f}%")
    if dd is not None and dd <= -20:
        score += 2
        reasons.append(f"252일 고점 대비 {dd:.1f}% 조정")
    elif dd is not None and dd <= -10:
        score += 1
        reasons.append(f"252일 고점 대비 {dd:.1f}% 조정")
    if rebound:
        score += 1
        reasons.append("최근 3거래일 저점 방어·종가 회복")
    if ratio50 is not None and ratio50 < 90 and not rebound:
        return "낙하 중·확인 필요", score, reasons
    if score >= 4 and rebound:
        return "반등 확인", score, reasons
    if score >= 3:
        return "과매도 접근", score, reasons
    if ratio50 is not None and ratio50 < 100:
        return "추세 훼손", score, reasons
    return "중립", score, reasons


def classify_stock(key: str, metrics: dict[str, Any], index_context: dict[str, Any]) -> tuple[str, int, list[str]]:
    score = 0
    reasons: list[str] = []
    ratio30 = metrics.get("ratio30")
    ratio50 = metrics.get("ratio50")
    dd = metrics.get("current_drawdown_pct")
    rebound = metrics.get("rebound_3d", False)
    rs5 = metrics.get("relative_strength_5d_pct")
    if ratio30 is not None:
        if 98 <= ratio30 <= 103:
            score += 2
            reasons.append(f"30일 이격도 지수 {ratio30:.1f}: 전술적 매수 관찰 구간")
        elif ratio30 < 98:
            score += 1
            reasons.append(f"30일선 하회({ratio30:.1f}): 과매도이나 낙하 확인 필요")
        elif ratio30 >= 115:
            score -= 2
            reasons.append(f"30일 이격도 지수 {ratio30:.1f}: 조정 후에도 과열 잔존")
        elif ratio30 >= 110:
            score -= 1
            reasons.append(f"30일 이격도 지수 {ratio30:.1f}: 확장 구간")
    threshold = -25 if key == "SAMSUNG" else -30
    if dd is not None and dd <= threshold:
        score += 1
        reasons.append(f"MDD {dd:.1f}%: 과거 급락 비교 구간 진입")
    if ratio50 is not None and ratio50 <= 100:
        score += 1
        reasons.append("50일선 이하로 밸류에이션·수급 조정 진행")
    if rebound:
        score += 1
        reasons.append("최근 3거래일 저점 방어·종가 반전")
    if rs5 is not None and rs5 > 0:
        score += 1
        reasons.append(f"KOSPI 대비 5일 상대강도 +{rs5:.1f}%p")
    market_signal = index_context.get("signal")
    if market_signal == "반등 확인":
        score += 1
        reasons.append("KOSPI 반등 확인 동반")
    elif market_signal == "낙하 중·확인 필요":
        score -= 1
        reasons.append("KOSPI 낙하 국면")
    if score >= 5 and rebound:
        return "강한 트레이딩 바이", score, reasons
    if score >= 3:
        return "1차 분할매수", score, reasons
    if score >= 1 and ratio30 is not None and ratio30 <= 103:
        return "실적 전 탐색매수", score, reasons
    if ratio30 is not None and ratio30 >= 110:
        return "관망", score, reasons
    return "매수 보류", score, reasons


def make_history(df: pd.DataFrame, limit: int = 260) -> list[dict[str, Any]]:
    columns = ["close", "sma30", "sma50", "sma120", "ratio30", "ratio50", "ratio120", "drawdown"]
    rows = []
    for idx, row in df.tail(limit).iterrows():
        item = {"date": idx.strftime("%Y-%m-%d")}
        for col in columns:
            if col in df.columns:
                item[col] = clean_float(row.get(col))
        rows.append(item)
    return rows


def build_asset_metrics(key: str, df: pd.DataFrame, source: str) -> dict[str, Any]:
    out = df.copy()
    for window in (5, 30, 50, 120):
        out[f"sma{window}"] = out["close"].rolling(window).mean()
    for window in (30, 50, 120):
        out[f"ratio{window}"] = out["close"] / out[f"sma{window}"] * 100
    out["drawdown"] = (out["close"] / out["close"].rolling(252, min_periods=20).max() - 1) * 100
    latest = out.dropna(subset=["close"]).iloc[-1]
    previous = out.dropna(subset=["close"]).iloc[-2] if len(out.dropna(subset=["close"])) >= 2 else latest
    current_dd, mdd = current_and_mdd(out["close"], 252)
    close_3 = out["close"].dropna().tail(3)
    rebound = len(close_3) >= 3 and close_3.iloc[-1] > close_3.iloc[0] and close_3.iloc[-1] > close_3.min()
    metrics: dict[str, Any] = {
        "name": ASSETS[key]["name"], "type": ASSETS[key]["type"],
        "date": out.index[-1].strftime("%Y-%m-%d"), "source": source,
        "close": clean_float(latest["close"]),
        "change_pct": clean_float((latest["close"] / previous["close"] - 1) * 100),
        "current_drawdown_pct": current_dd, "mdd_252_pct": mdd, "rebound_3d": bool(rebound),
    }
    for window in (30, 50, 120):
        metrics[f"sma{window}"] = clean_float(latest.get(f"sma{window}"))
        metrics[f"ratio{window}"] = clean_float(latest.get(f"ratio{window}"))
        ratio = metrics[f"ratio{window}"]
        metrics[f"dev{window}"] = clean_float(ratio - 100) if ratio is not None else None
        metrics[f"ratio{window}_percentile_3y"] = percentile_of_last(out[f"ratio{window}"])
    metrics["history"] = make_history(out)
    return metrics


def fetch_breadth(date_yyyymmdd: str, market: str) -> dict[str, Any]:
    try:
        from pykrx import stock
        raw = stock.get_market_ohlcv_by_ticker(date_yyyymmdd, market=market)
        if raw is None or raw.empty:
            raise RuntimeError("empty")
        ret = pd.to_numeric(raw["등락률"], errors="coerce").dropna() if "등락률" in raw.columns else pd.Series(dtype=float)
        adv, dec, flat = int((ret > 0).sum()), int((ret < 0).sum()), int((ret == 0).sum())
        return {"advancers": adv, "decliners": dec, "unchanged": flat, "ad_ratio": clean_float(adv / dec) if dec else None}
    except Exception as exc:
        return {"advancers": None, "decliners": None, "unchanged": None, "ad_ratio": None, "error": str(exc)}


def load_manual() -> dict[str, Any]:
    try:
        return json.loads(MANUAL.read_text(encoding="utf-8")) if MANUAL.exists() else {}
    except Exception:
        return {}


def write_csv(payload: dict[str, Any]) -> None:
    rows = []
    for key, asset in payload["assets"].items():
        for item in asset.get("history", []):
            rows.append({"asset": key, **item})
    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")


def render_html(payload: dict[str, Any]) -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    embedded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    OUTPUT_HTML.write_text(template.replace("__EMBEDDED_DATA__", embedded), encoding="utf-8")


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    end_dt = datetime.now(SEOUL) + timedelta(days=1)
    start_dt = end_dt - timedelta(days=1200)
    start, end = start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")
    assets, frames, errors = {}, {}, {}
    for key, config in ASSETS.items():
        try:
            frame, source = fetch_asset(config, start, end)
            frames[key] = frame
            assets[key] = build_asset_metrics(key, frame, source)
        except Exception as exc:
            errors[key] = str(exc)
    if "KOSPI" in assets:
        kospi = assets["KOSPI"]
        label, score, reasons = classify_index(kospi)
        kospi.update(signal=label, score=score, reasons=reasons)
        for key in ("SAMSUNG", "SKHYNIX"):
            if key in assets and key in frames:
                rs5 = frames[key]["close"].pct_change(5).iloc[-1] - frames["KOSPI"]["close"].pct_change(5).iloc[-1]
                assets[key]["relative_strength_5d_pct"] = clean_float(rs5 * 100)
                label, score, reasons = classify_stock(key, assets[key], kospi)
                assets[key].update(signal=label, score=score, reasons=reasons)
    if "KOSDAQ" in assets:
        label, score, reasons = classify_index(assets["KOSDAQ"])
        assets["KOSDAQ"].update(signal=label, score=score, reasons=reasons)
    latest_date = max((v["date"] for v in assets.values()), default=datetime.now(SEOUL).strftime("%Y-%m-%d"))
    payload = {
        "generated_at": datetime.now(SEOUL).isoformat(timespec="seconds"),
        "status": "ok" if assets else "error",
        "methodology": {
            "disparity_ratio": "현재가 ÷ 이동평균 × 100",
            "deviation_pct": "이격도 지수 - 100",
            "index_windows": [50, 120], "stock_tactical_window": 30, "drawdown_window": 252,
            "principles": [
                "지수는 50일·120일 이격도 지수를 기본으로 본다.",
                "삼성전자·SK하이닉스는 30일 이격도 지수로 단기 과열·눌림을 판단하고 50·120일선과 MDD로 중기 위치를 보강한다.",
                "호재에도 하락하면 사이클 고점 경고, 악재에도 저점을 지키면 바닥 선행 신호로 본다.",
                "단순 호실적보다 금리 안정과 자본 공급자 안심 이벤트를 반등 트리거로 가중한다."
            ]
        },
        "assets": assets,
        "breadth": {
            "KOSPI": fetch_breadth(latest_date.replace("-", ""), "KOSPI"),
            "KOSDAQ": fetch_breadth(latest_date.replace("-", ""), "KOSDAQ")
        },
        "manual": load_manual(), "errors": errors,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(payload)
    render_html(payload)
    print(f"Updated {OUTPUT_HTML} / {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
