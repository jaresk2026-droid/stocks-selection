from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from stock_screener.indicators import add_indicators

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = Path(__file__).with_name("lightweight_template.html")
RUNTIME_PATH = PROJECT_ROOT / "static" / "lightweight-charts.js"

INDICATOR_ORDER = ("MACD", "RSI", "KDJ")
RANGE_PRESETS = {
    "daily": [("3 个月", 60), ("半年", 120), ("1 年", 250), ("2 年", 500)],
    "weekly": [("半年", 26), ("1 年", 52), ("2 年", 104), ("3 年", 156)],
    "monthly": [("1 年", 12), ("2 年", 24), ("3 年", 36), ("5 年", 60)],
}
MA_SPECS = (
    ("MA5", "#f5a623"),
    ("MA10", "#4a90d9"),
    ("MA20", "#9b59b6"),
    ("MA60", "#7f8c8d"),
)


def range_presets(period: str) -> list[tuple[str, int]]:
    try:
        return RANGE_PRESETS[period]
    except KeyError as exc:
        raise ValueError(f"Unknown period {period!r}") from exc


def recommend_indicators(selection_keys: Iterable[str]) -> list[str]:
    keys = tuple(selection_keys)
    picked = {
        "MACD": any("macd" in key for key in keys),
        "RSI": any("rsi" in key for key in keys),
        "KDJ": any("kdj" in key for key in keys),
    }
    out = [name for name in INDICATOR_ORDER if picked[name]]
    return out or ["MACD"]


def normalize_indicators(indicators: Iterable[str]) -> list[str]:
    selected = set(indicators)
    return [name for name in INDICATOR_ORDER if name in selected] or ["MACD"]


def _time_text(value) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _line_data(df: pd.DataFrame, column: str) -> list[dict]:
    return [
        {"time": _time_text(row.date), "value": float(getattr(row, column))}
        for row in df.itertuples(index=False)
        if pd.notna(getattr(row, column))
    ]


def latest_quote(raw_df: pd.DataFrame) -> dict:
    if raw_df.empty:
        raise ValueError("K-line data is empty")
    latest = raw_df.iloc[-1]
    previous_close = float(raw_df.iloc[-2]["close"]) if len(raw_df) > 1 else float(latest["open"])
    close = float(latest["close"])
    change = close - previous_close
    pct = change / previous_close * 100 if previous_close else 0.0
    return {
        "date": _time_text(latest["date"]),
        "open": float(latest["open"]),
        "high": float(latest["high"]),
        "low": float(latest["low"]),
        "close": close,
        "volume": float(latest["volume"]),
        "change": change,
        "pct": pct,
    }


def build_chart_payload(raw_df: pd.DataFrame, indicators: Iterable[str]) -> dict:
    if raw_df.empty:
        raise ValueError("K-line data is empty")
    df = add_indicators(raw_df.copy()).reset_index(drop=True)
    selected = normalize_indicators(indicators)
    candles = []
    for index, row in df.iterrows():
        candles.append(
            {
                "time": _time_text(row["date"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "prevClose": float(df.iloc[index - 1]["close"]) if index else float(row["open"]),
            }
        )
    volume = [
        {
            "time": _time_text(row["date"]),
            "value": float(row["volume"]),
            "color": "rgba(239,83,80,0.50)" if row["close"] >= row["open"] else "rgba(38,166,154,0.50)",
        }
        for _, row in df.iterrows()
    ]
    overlays = [
        {"label": column, "color": color, "data": _line_data(df, column)}
        for column, color in MA_SPECS
        if column in df.columns
    ]
    oscillators = []
    if "MACD" in selected:
        oscillators.append(
            {
                "key": "MACD",
                "title": "MACD",
                "series": [
                    {"label": "DIF", "type": "line", "color": "#f5a623", "data": _line_data(df, "MACD_DIF")},
                    {"label": "DEA", "type": "line", "color": "#4a90d9", "data": _line_data(df, "MACD_DEA")},
                    {"label": "MACD", "type": "histogram", "color": "#8c8c8c", "data": _line_data(df, "MACD_HIST")},
                ],
                "referenceLines": [{"value": 0, "label": "0", "color": "#bdbdbd"}],
            }
        )
    if "RSI" in selected:
        oscillators.append(
            {
                "key": "RSI",
                "title": "RSI",
                "series": [{"label": "RSI", "type": "line", "color": "#722ed1", "data": _line_data(df, "RSI")}],
                "referenceLines": [
                    {"value": 30, "label": "30", "color": "#52c41a"},
                    {"value": 70, "label": "70", "color": "#f5222d"},
                ],
            }
        )
    if "KDJ" in selected:
        oscillators.append(
            {
                "key": "KDJ",
                "title": "KDJ",
                "series": [
                    {"label": "K", "type": "line", "color": "#1677ff", "data": _line_data(df, "KDJ_K")},
                    {"label": "D", "type": "line", "color": "#fa8c16", "data": _line_data(df, "KDJ_D")},
                    {"label": "J", "type": "line", "color": "#722ed1", "data": _line_data(df, "KDJ_J")},
                ],
                "referenceLines": [
                    {"value": 20, "label": "20", "color": "#52c41a"},
                    {"value": 80, "label": "80", "color": "#f5222d"},
                ],
            }
        )
    return {
        "candles": candles,
        "volume": volume,
        "overlays": overlays,
        "oscillators": oscillators,
        "height": 500 + 150 * len(oscillators),
    }
