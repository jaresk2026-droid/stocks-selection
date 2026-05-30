from __future__ import annotations

import unittest

import pandas as pd

from stock_screener.viz.lightweight import (
    build_chart_payload,
    latest_quote,
    range_presets,
    recommend_indicators,
)


class LightweightChartModelTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame(
            [
                {"code": "600519", "date": "2026-05-27", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 100.0, "amount": 1000.0},
                {"code": "600519", "date": "2026-05-28", "open": 10.5, "high": 12.0, "low": 10.0, "close": 11.5, "volume": 140.0, "amount": 1500.0},
                {"code": "600519", "date": "2026-05-29", "open": 11.5, "high": 12.5, "low": 11.0, "close": 12.0, "volume": 120.0, "amount": 1450.0},
            ]
        )

    def test_recommend_indicators_uses_selected_condition_families(self):
        self.assertEqual(
            recommend_indicators(["rsi_below", "weekly_macd_above_zero", "kdj_golden_cross"]),
            ["MACD", "RSI", "KDJ"],
        )

    def test_recommend_indicators_defaults_to_macd(self):
        self.assertEqual(recommend_indicators(["ma_bullish"]), ["MACD"])

    def test_range_presets_are_period_specific(self):
        self.assertEqual(range_presets("daily")[2], ("1 年", 250))
        self.assertEqual(range_presets("weekly")[1], ("1 年", 52))
        self.assertEqual(range_presets("monthly")[0], ("1 年", 12))

    def test_range_presets_reject_unknown_period(self):
        with self.assertRaises(ValueError):
            range_presets("minute")

    def test_payload_contains_candles_volume_overlays_and_multiple_oscillators(self):
        payload = build_chart_payload(self.df, ["RSI", "MACD", "KDJ"])
        self.assertEqual(payload["candles"][1]["prevClose"], 10.5)
        self.assertEqual(payload["volume"][0]["color"], "rgba(239,83,80,0.50)")
        self.assertEqual([item["label"] for item in payload["overlays"]], ["MA5", "MA10", "MA20", "MA60"])
        self.assertEqual([item["key"] for item in payload["oscillators"]], ["MACD", "RSI", "KDJ"])
        self.assertEqual(payload["height"], 950)

    def test_latest_quote_uses_previous_close(self):
        quote = latest_quote(self.df)
        self.assertEqual(quote["date"], "2026-05-29")
        self.assertAlmostEqual(quote["change"], 0.5)
        self.assertAlmostEqual(quote["pct"], 0.5 / 11.5 * 100)
