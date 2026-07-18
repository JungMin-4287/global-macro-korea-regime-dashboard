#!/usr/bin/env python3
"""Dashboard v7.

- Keep the public HTML lightweight: load market_data.json at runtime instead of
  embedding the complete history in every HTML rebuild.
- Append deduplicated daily asset and investor-flow archives.
- Add a KOSPI drawdown vs cumulative individual net-buy correction map.
- Preserve the v6 VKOSPI history enhancements and data-source fallbacks.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import update_dashboard as base
import update_dashboard_v6 as v6  # noqa: F401 - applies v5/v6 patches
import update_dashboard_v3 as v3

ARCHIVE = base.DATA_DIR / "daily_archive.csv"
FLOW_ARCHIVE = base.DATA_DIR / "investor_flow_history.csv"
CORRECTION_ARCHIVE = base.DATA_DIR / "correction_flow_map.csv"
ORIGINAL_PSYCHOLOGY = base.psychology


def _individual_flow(start: str, end: str) -> tuple[pd.Series, str]:
    errors: list[str] = []
    try:
        return v3._flow_from_pykrx(start, end)
    except Exception as exc:
        errors.append(f"KRX: {exc}")
    try:
        return v3._flow_from_naver()
    except Exception as exc:
        errors.append(f"Naver: {exc}")
    raise RuntimeError(" / ".join(errors))


def correction_flow_map(start: str, end: str, kospi: pd.DataFrame) -> dict[str, Any]:
    """Plot drawdown from each new high against cumulative retail net buying.

    The cumulative flow resets when KOSPI makes a new high. This turns the chart
    into a map of how aggressively individuals absorb supply during corrections.
    """
    individual, source = _individual_flow(start, end)
    frame = pd.concat(
        [kospi["close"].rename("close"), individual.rename("individual_net_buy_trn")],
        axis=1,
    ).dropna().tail(550)
    if len(frame) < 20:
        raise RuntimeError(f"가격·수급 공통 관측치 부족 ({len(frame)})")

    peak = float(frame["close"].iloc[0])
    peak_date = frame.index[0]
    cumulative = 0.0
    points: list[dict[str, Any]] = []
    for date, row in frame.iterrows():
        close = float(row["close"])
        flow = float(row["individual_net_buy_trn"])
        if close >= peak:
            peak = close
            peak_date = date
            cumulative = 0.0
        else:
            cumulative += flow
        drawdown = (close / peak - 1.0) * 100.0
        if drawdown <= -0.5:
            points.append({
                "date": date.strftime("%Y-%m-%d"),
                "peak_date": pd.Timestamp(peak_date).strftime("%Y-%m-%d"),
                "x": base.cf(cumulative),
                "y": base.cf(drawdown),
                "close": base.cf(close),
                "daily_individual_net_buy_trn": base.cf(flow),
            })

    if len(points) < 10:
        raise RuntimeError(f"조정구간 관측치 부족 ({len(points)})")

    xs = np.array([float(p["x"]) for p in points])
    ys = np.array([float(p["y"]) for p in points])
    slope, intercept = np.polyfit(xs, ys, 1)
    latest = points[-1]

    selected: list[dict[str, Any]] = [dict(latest)]
    for candidate in sorted(points[:-1], key=lambda p: float(p["y"])):
        dt = pd.Timestamp(candidate["date"])
        if all(abs((dt - pd.Timestamp(item["date"])).days) >= 20 for item in selected):
            selected.append(dict(candidate))
        if len(selected) >= 5:
            break
    for item in selected:
        dt = pd.Timestamp(item["date"])
        item["label"] = dt.strftime("%-m/%-d")

    cumulative_now = float(latest["x"])
    drawdown_now = float(latest["y"])
    if drawdown_now <= -20 and cumulative_now > 5:
        zone = "개인 대규모 저가매수에도 깊은 낙폭"
        interpretation = "개인이 누적으로 크게 매수했지만 지수 낙폭이 깊습니다. 외국인·기관 매도 압력이 개인 매수보다 강해 청산이 끝났다고 보기 어렵습니다."
    elif drawdown_now <= -20 and cumulative_now <= 0:
        zone = "개인 투매 동반 극단 공포"
        interpretation = "깊은 조정에서 개인까지 누적 순매도로 전환했습니다. 매도 고갈 후보지만 다음 거래일 저점 방어와 VKOSPI 하락 전환이 필요합니다."
    elif drawdown_now <= -10 and cumulative_now > 0:
        zone = "개인 저가매수 누적 중"
        interpretation = "조정이 깊어질수록 개인이 물량을 받아내고 있습니다. 외국인 수급과 시장 폭이 돌아서기 전까지는 바닥 확인보다 매물 소화 과정으로 봅니다."
    else:
        zone = "일반 조정 범위"
        interpretation = "현재 낙폭과 개인 누적매수는 최근 관측 범위 안에 있습니다. 회귀선에서 크게 벗어나는지 확인합니다."

    x_min, x_max = float(xs.min()), float(xs.max())
    return {
        "points": points,
        "regression": [
            {"x": base.cf(x_min), "y": base.cf(slope * x_min + intercept)},
            {"x": base.cf(x_max), "y": base.cf(slope * x_max + intercept)},
        ],
        "highlights": selected,
        "latest": latest,
        "zone": zone,
        "interpretation": interpretation,
        "source": source,
        "window": "최근 최대 550일, 신고가에서 누적 순매수 재설정",
    }


def psychology_v7(start: str, end: str, kospi: pd.DataFrame) -> dict[str, Any]:
    result = ORIGINAL_PSYCHOLOGY(start, end, kospi)
    try:
        result["correction_map"] = correction_flow_map(start, end, kospi)
    except Exception as exc:
        result["correction_map"] = {
            "points": [],
            "error": str(exc),
            "interpretation": "고점 이후 누적 개인순매수와 KOSPI 낙폭 데이터를 만들지 못했습니다.",
        }
    return result


def _merge_archive(path: Path, rows: list[dict[str, Any]], keys: list[str]) -> None:
    if not rows:
        return
    latest = pd.DataFrame(rows)
    if path.exists():
        try:
            latest = pd.concat([pd.read_csv(path), latest], ignore_index=True)
        except Exception:
            pass
    latest = latest.dropna(subset=keys)
    latest = latest.drop_duplicates(keys, keep="last").sort_values(keys)
    latest.to_csv(path, index=False, encoding="utf-8-sig")


def append_archives() -> None:
    payload = json.loads(base.OUTPUT_JSON.read_text(encoding="utf-8"))
    generated_at = payload.get("generated_at")
    asset_rows = []
    for key, asset in (payload.get("assets") or {}).items():
        asset_rows.append({
            "date": asset.get("date"), "asset": key, "name": asset.get("name"),
            "close": asset.get("close"), "change_pct": asset.get("change_pct"),
            "ratio30": asset.get("ratio30"), "ratio50": asset.get("ratio50"),
            "ratio60": asset.get("ratio60"), "ratio100": asset.get("ratio100"),
            "ratio120": asset.get("ratio120"), "ratio200": asset.get("ratio200"),
            "current_drawdown_pct": asset.get("current_drawdown_pct"),
            "mdd_252_pct": asset.get("mdd_252_pct"), "source": asset.get("source"),
            "generated_at": generated_at,
        })
    _merge_archive(ARCHIVE, asset_rows, ["date", "asset"])

    psychology = payload.get("market_psychology") or {}
    flow_rows = [{
        "date": p.get("date"),
        "individual_net_buy_trn": p.get("x"),
        "kospi_return_pct": p.get("y"),
        "source": psychology.get("source"),
        "generated_at": generated_at,
    } for p in psychology.get("points") or []]
    _merge_archive(FLOW_ARCHIVE, flow_rows, ["date"])

    correction = psychology.get("correction_map") or {}
    correction_rows = [{**p, "source": correction.get("source"), "generated_at": generated_at}
                       for p in correction.get("points") or []]
    _merge_archive(CORRECTION_ARCHIVE, correction_rows, ["date"])


def make_html_lightweight() -> None:
    path: Path = base.OUTPUT_HTML
    text = path.read_text(encoding="utf-8")
    text = re.sub(
        r'(<script id="embedded" type="application/json">).*?(</script>)',
        r'\1{}\2', text, flags=re.S,
    )
    replacements = {
        'href="styles.css"': 'href="styles.css?v=7',
        'href="styles.css?v=6"': 'href="styles.css?v=7',
        'src="js/core.js"': 'src="js/core.js?v=7',
        'src="js/core.js?v=6"': 'src="js/core.js?v=7',
        'src="js/charts.js"': 'src="js/charts.js?v=7',
        'src="js/charts.js?v=6"': 'src="js/charts.js?v=7',
        'src="js/panels.js"': 'src="js/panels.js?v=7',
        'src="js/panels.js?v=6"': 'src="js/panels.js?v=7',
        'src="js/app.js"': 'src="js/app.js?v=7',
        'src="js/app.js?v=6"': 'src="js/app.js?v=7',
    }
    # Use fixed v7 cache keys; correct any accidental duplicate replacement.
    replacements = {k: v + '"' for k, v in replacements.items()}
    for old, new in replacements.items():
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


base.psychology = psychology_v7

if __name__ == "__main__":
    base.main()
    append_archives()
    make_html_lightweight()
