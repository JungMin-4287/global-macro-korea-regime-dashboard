#!/usr/bin/env python3
"""Feature layer for the Korea market dashboard.

It reuses the stable data engine in update_dashboard.py and adds:
- explicit, shareable interpretations for every disparity chart
- a robust VKOSPI -> realized-volatility proxy fallback
- richer KOSPI return / individual net-buy psychology diagnostics
- the v2 modular HTML template
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import update_dashboard as base

ORIGINAL_FETCH_ASSET = base.fetch_asset
ORIGINAL_FETCH_VKOSPI = base.fetch_vkospi
ORIGINAL_METRICS = base.metrics
KOSPI_FRAME: pd.DataFrame | None = None


def interpret(key: str, m: dict[str, Any]) -> dict[str, str]:
    rebound = bool(m.get("rebound_3d"))
    dd = m.get("current_drawdown_pct")

    if key in ("KOSPI", "KOSDAQ"):
        r50, r60, r120 = m.get("ratio50"), m.get("ratio60"), m.get("ratio120")
        if r50 is None:
            return {"zone": "미산출", "headline": "이동평균 데이터 부족", "summary": "데이터가 충분히 쌓인 뒤 계산됩니다.", "action": "판정 보류"}
        zone = ("극단적 과매도·낙하 위험" if not rebound else "극단적 과매도 후 반전 시도") if r50 < 90 else "강한 과매도" if r50 < 95 else "조정 국면" if r50 < 100 else "중립·추세선 부근" if r50 < 105 else "상승 추세 확장" if r50 < 110 else "단기 과열"
        long_trend = "120일선 위로 중기 추세는 유지" if r120 is not None and r120 >= 100 else "120일선 아래로 중기 추세도 훼손"
        summary = f"50일 이격도 {r50:.1f}({r50-100:+.1f}%)"
        if r120 is not None:
            summary += f", 120일 이격도 {r120:.1f}({r120-100:+.1f}%). {long_trend}."
        if key == "KOSPI" and r60 is not None:
            summary += f" 60일 이격도는 {r60:.1f}로 장표상 과거 극단 구간 90과 비교합니다."
        if r50 < 95 and not rebound:
            action = "수치만으로 매수하지 말고 전저점 방어, A/D 개선, VKOSPI 하락 전환을 확인해야 합니다."
        elif r50 < 100 and rebound:
            action = "과매도 반등이 시작됐지만 5·20일선 회복과 외국인 수급 반전이 추가 확인 조건입니다."
        elif r50 >= 110:
            action = "추격매수보다 이격 축소를 기다리는 구간입니다."
        else:
            action = "추세와 시장 폭이 같은 방향인지 확인하는 중립 구간입니다."
        return {"zone": zone, "headline": f"현재 구간: {zone}", "summary": summary, "action": action}

    if key in ("SAMSUNG", "SKHYNIX"):
        r30, r50, r120 = m.get("ratio30"), m.get("ratio50"), m.get("ratio120")
        if r30 is None:
            return {"zone": "미산출", "headline": "30일 이격도 미산출", "summary": "가격 이력이 부족합니다.", "action": "판정 보류"}
        zone = "극단적 과매도·투매권" if r30 < 90 else "강한 조정" if r30 < 98 else "전술적 눌림 관찰" if r30 <= 103 else "상승 추세" if r30 < 110 else "추세 확장·과열 경계" if r30 < 115 else "고과열·이격 축소 필요"
        summary = f"30일 이격도 {r30:.1f}({r30-100:+.1f}%)"
        if None not in (r50, r120):
            summary += f", 50일 {r50:.1f}({r50-100:+.1f}%), 120일 {r120:.1f}({r120-100:+.1f}%)"
        if dd is not None:
            summary += f". 252일 고점 대비 {dd:.1f}%"
        if r30 < 98 and not rebound:
            action = "과매도여도 낙하 중입니다. 갭하락 회복, 전저점 방어, 외국인 순매수 전환 전에는 탐색매수만 허용합니다."
        elif 98 <= r30 <= 103 and rebound:
            action = "눌림 후 반전 조건에 근접했습니다. 5·20일선 회복과 SOX 상대강도 개선 시 1차 분할매수 후보입니다."
        elif r30 >= 110:
            action = "조정 후에도 이격이 높아 추격매수보다 리스크 관리가 우선입니다."
        else:
            action = "가격 반응과 수급을 함께 확인해야 하며 이격도 단독으로 매수하지 않습니다."
        return {"zone": zone, "headline": f"현재 구간: {zone}", "summary": summary, "action": action}

    if key == "SOX":
        r50, r100, r200 = m.get("ratio50"), m.get("ratio100"), m.get("ratio200")
        if r100 is None:
            return {"zone": "미산출", "headline": "SOX 100일선 미산출", "summary": "데이터 부족", "action": "판정 보류"}
        zone = "심각한 약세장·꼬리위험" if dd is not None and dd <= -30 else "기술적 약세장" if dd is not None and dd <= -20 else "100일선 하회·추가 조정 위험" if r100 < 100 else "50일선 하회 조정" if r50 is not None and r50 < 100 else "중기 상승 추세"
        summary = f"고점 대비 {dd:.1f}%, 50일 이격도 {r50:.1f}, 100일 {r100:.1f}, 200일 {r200:.1f}." if None not in (dd, r50, r100, r200) else "SOX 기술 지표 일부 미산출."
        return {"zone": zone, "headline": f"현재 구간: {zone}", "summary": summary, "action": "-20%는 역사적 반등 후보지만 -30% 전이 사례도 있어 이벤트 스터디와 포지셔닝을 함께 봅니다."}

    if key == "NDX":
        r100 = m.get("ratio100")
        if r100 is None:
            return {"zone": "미산출", "headline": "100일선 미산출", "summary": "데이터 부족", "action": "판정 보류"}
        zone = "강한 위험회피" if r100 < 95 else "100일선 하회 조정" if r100 < 100 else "중립·추세선 부근" if r100 < 105 else "중기 상승 추세"
        return {"zone": zone, "headline": f"현재 구간: {zone}", "summary": f"나스닥100 100일 이격도 {r100:.1f}({r100-100:+.1f}%).", "action": "100일선 아래면 한국 반도체 반등의 신뢰도를 낮춥니다."}

    if key == "VKOSPI":
        value, pct = m.get("close"), m.get("ratio50_percentile_3y")
        if value is None:
            return {"zone": "미산출", "headline": "변동성 미산출", "summary": "데이터 조회 실패", "action": "판정 보류"}
        zone = "극단적 공포·강제청산 위험" if value >= 35 else "고변동성 경계" if value >= 25 else "불안 확대" if value >= 18 else "안정"
        proxy = " 실제 VKOSPI가 아닌 KOSPI 20일 실현변동성 대체치입니다." if "대체" in str(m.get("source", "")) else ""
        summary = f"현재 {value:.1f}" + (f", 3년 백분위 {pct:.1f}%." if pct is not None else ".") + proxy
        action = "변동성 고점 통과와 2거래일 연속 하락 전에는 과매도 매수 비중을 제한합니다." if value >= 25 else "지수 반등과 변동성 하락이 동시에 나오는지 확인합니다." if value >= 18 else "변동성은 안정적이나 과도한 안도 구간에서는 주가 과열을 별도 점검합니다."
        return {"zone": zone, "headline": f"현재 구간: {zone}", "summary": summary, "action": action}

    return {"zone": "관찰", "headline": "현재 구간: 관찰", "summary": "", "action": ""}


def fetch_asset_v2(asset: dict[str, str], start: str, end: str):
    global KOSPI_FRAME
    frame, source = ORIGINAL_FETCH_ASSET(asset, start, end)
    if asset.get("name") == "KOSPI":
        KOSPI_FRAME = frame.copy()
    return frame, source


def fetch_vkospi_v2(start: str, end: str):
    try:
        return ORIGINAL_FETCH_VKOSPI(start, end)
    except Exception:
        if KOSPI_FRAME is None:
            raise
        proxy = KOSPI_FRAME["close"].pct_change().rolling(20).std() * math.sqrt(252) * 100
        frame = pd.DataFrame({"close": proxy}).dropna()
        if frame.empty:
            raise RuntimeError("VKOSPI and realized-volatility proxy unavailable")
        return frame, "KOSPI 20일 실현변동성 대체지표"


def metrics_v2(key: str, df: pd.DataFrame, source: str):
    m, out = ORIGINAL_METRICS(key, df, source)
    m["disparity_interpretation"] = interpret(key, m)
    m["is_proxy"] = key == "VKOSPI" and "대체" in source
    return m, out


def psychology_v2(start: str, end: str, kospi: pd.DataFrame) -> dict[str, Any]:
    try:
        from pykrx import stock

        raw = stock.get_market_trading_value_by_date(start.replace("-", ""), end.replace("-", ""), "KOSPI")
        personal_col = next(col for col in raw.columns if "개인" in str(col))
        individual = pd.to_numeric(raw[personal_col], errors="coerce") / 1e12
        returns = kospi["close"].pct_change() * 100
        frame = pd.concat([individual.rename("x"), returns.rename("y")], axis=1).dropna().tail(180)
        if len(frame) < 10:
            raise RuntimeError("insufficient observations")
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
            "regression": [{"x": base.cf(x_min), "y": base.cf(slope * x_min + intercept)}, {"x": base.cf(x_max), "y": base.cf(slope * x_max + intercept)}],
            "latest": {"date": frame.index[-1].strftime("%Y-%m-%d"), "x": base.cf(latest_x), "y": base.cf(latest_y), "residual": base.cf(residual)},
            "correlation": base.cf(frame.corr().iloc[0, 1]),
            "zone": zone,
            "interpretation": text,
        }
    except Exception as exc:
        return {"points": [], "regression": [], "zone": "미산출", "error": str(exc), "interpretation": "개인 순매수 데이터 미산출"}


base.fetch_asset = fetch_asset_v2
base.fetch_vkospi = fetch_vkospi_v2
base.metrics = metrics_v2
base.psychology = psychology_v2
base.TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "index.v2.html"

if __name__ == "__main__":
    base.main()
