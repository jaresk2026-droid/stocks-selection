from __future__ import annotations

import math
import unittest

import pandas as pd

from stock_screener.indicators import add_indicators
from stock_screener.viz.lightweight import (
    TEMPLATE_PATH,
    _line_data,
    build_chart_payload,
    latest_quote,
    range_presets,
    recommend_indicators,
    render_chart_html,
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

    def test_range_presets_returns_a_fresh_list(self):
        presets = range_presets("daily")
        presets.append(("mutated", 1))

        self.assertNotIn(("mutated", 1), range_presets("daily"))

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

    def test_payload_trims_after_computing_indicators_on_full_history(self):
        long_df = pd.DataFrame(
            [
                {
                    "code": "600519",
                    "date": date,
                    "open": close - 0.2,
                    "high": close + 0.5,
                    "low": close - 0.5,
                    "close": close,
                    "volume": 100.0 + index,
                    "amount": 1000.0 + index,
                }
                for index, date in enumerate(pd.date_range("2026-04-01", periods=30))
                for close in [10.0 + index * 0.4]
            ]
        )
        expected = float(add_indicators(long_df).tail(3).iloc[0]["MACD_DIF"])
        cold_start = float(add_indicators(long_df.tail(3)).iloc[0]["MACD_DIF"])

        payload = build_chart_payload(long_df, ["MACD"], bars=3)
        visible_dif = payload["oscillators"][0]["series"][0]["data"][0]["value"]

        self.assertEqual(len(payload["candles"]), 3)
        self.assertNotAlmostEqual(expected, cold_start)
        self.assertAlmostEqual(visible_dif, expected)

    def test_latest_quote_sorts_unsorted_input(self):
        quote = latest_quote(self.df.iloc[[2, 0, 1]])

        self.assertEqual(quote["date"], "2026-05-29")
        self.assertAlmostEqual(quote["change"], 0.5)
        self.assertAlmostEqual(quote["pct"], 0.5 / 11.5 * 100)

    def test_invalid_market_rows_are_omitted_from_payload_and_quote(self):
        invalid_rows = pd.DataFrame(
            [
                {"code": "600519", "date": "2026-05-30", "open": 12.0, "high": 13.0, "low": 11.5, "close": float("inf"), "volume": 130.0, "amount": 1500.0},
                {"code": "600519", "date": "invalid", "open": 12.0, "high": 13.0, "low": 11.5, "close": 12.5, "volume": 130.0, "amount": 1500.0},
                {"code": "600519", "date": "2026-05-31", "open": 12.0, "high": 13.0, "low": 11.5, "close": 12.5, "volume": "invalid", "amount": 1500.0},
            ]
        )
        dirty_df = pd.concat([self.df, invalid_rows], ignore_index=True)

        payload = build_chart_payload(dirty_df, ["MACD", "RSI", "KDJ"])
        quote = latest_quote(dirty_df)

        self.assertEqual([item["time"] for item in payload["candles"]], ["2026-05-27", "2026-05-28", "2026-05-29"])
        self.assertEqual(quote["date"], "2026-05-29")
        self._assert_finite_numbers(payload)
        self._assert_finite_numbers(quote)

    def test_all_invalid_market_rows_raise_value_error(self):
        invalid_df = pd.DataFrame(
            [
                {"date": "invalid", "open": float("inf"), "high": 11.0, "low": 9.5, "close": 10.5, "volume": 100.0},
            ]
        )

        with self.assertRaisesRegex(ValueError, "No valid K-line rows remain"):
            build_chart_payload(invalid_df, ["MACD"])
        with self.assertRaisesRegex(ValueError, "No valid K-line rows remain"):
            latest_quote(invalid_df)

    def test_line_data_omits_non_finite_indicator_values(self):
        indicator_df = pd.DataFrame(
            [
                {"date": "2026-05-27", "TEST": float("inf")},
                {"date": "2026-05-28", "TEST": float("-inf")},
                {"date": "2026-05-29", "TEST": 12.5},
            ]
        )

        self.assertEqual(_line_data(indicator_df, "TEST"), [{"time": "2026-05-29", "value": 12.5}])

    def test_render_chart_html_injects_runtime_payload_and_oscillator_sections(self):
        payload = build_chart_payload(self.df, ["MACD", "RSI"])

        html = render_chart_html(payload, runtime_js="window.LightweightCharts = {};")

        self.assertIn("window.LightweightCharts = {};", html)
        self.assertIn('"key": "MACD"', html)
        self.assertIn('"key": "RSI"', html)
        self.assertIn("oscillator-0", html)
        self.assertIn("oscillator-1", html)
        self.assertNotIn("__RUNTIME_JS__", html)
        self.assertNotIn("__PAYLOAD_JSON__", html)
        self.assertNotIn("__OSCILLATOR_SECTIONS__", html)

    def test_render_chart_html_raises_when_runtime_file_is_missing(self):
        payload = {"candles": [], "volume": [], "overlays": [], "oscillators": [], "height": 500}

        with self.assertRaisesRegex(FileNotFoundError, "lightweight-charts"):
            render_chart_html(payload, runtime_path="missing.js")

    def test_render_chart_html_script_escapes_payload_and_html_escapes_oscillator_titles(self):
        attacker = "</script><script>window.bad=1</script>"
        payload = {
            "candles": [],
            "volume": [],
            "overlays": [],
            "oscillators": [{"title": attacker + "\"'&", "series": []}],
            "height": 650,
            "marker": ">&\u2028\u2029",
        }

        html = render_chart_html(payload, runtime_js="window.LightweightCharts = {};")

        self.assertNotIn(attacker, html)
        self.assertIn("\\u003c/script\\u003e\\u003cscript\\u003ewindow.bad=1\\u003c/script\\u003e", html)
        self.assertIn("&lt;/script&gt;&lt;script&gt;window.bad=1&lt;/script&gt;&quot;&#x27;&amp;", html)
        self.assertIn('"marker": "\\u003e\\u0026\\u2028\\u2029"', html)

    def test_render_chart_html_rejects_nan_payload_values(self):
        payload = {"candles": [], "volume": [], "overlays": [], "oscillators": [], "height": float("nan")}

        with self.assertRaises(ValueError):
            render_chart_html(payload, runtime_js="window.LightweightCharts = {};")

    def test_render_chart_html_preserves_placeholder_text_inside_payload_json(self):
        payload = {
            "candles": [],
            "volume": [],
            "overlays": [],
            "oscillators": [],
            "height": 500,
            "marker": "__OSCILLATOR_SECTIONS__",
        }

        html = render_chart_html(payload, runtime_js="window.LightweightCharts = {};")

        self.assertIn('"marker": "__OSCILLATOR_SECTIONS__"', html)

    def test_template_uses_safe_dom_text_and_guards_zero_previous_close(self):
        template = TEMPLATE_PATH.read_text(encoding="utf-8")

        self.assertIn("const previousClose = previous[param.time];", template)
        self.assertIn("const pct = previousClose ? (value.close - previousClose) / previousClose * 100 : 0.0;", template)
        self.assertNotIn(".innerHTML", template)

    def _assert_finite_numbers(self, value):
        if isinstance(value, dict):
            for item in value.values():
                self._assert_finite_numbers(item)
        elif isinstance(value, list):
            for item in value:
                self._assert_finite_numbers(item)
        elif isinstance(value, float):
            self.assertTrue(math.isfinite(value), repr(value))
