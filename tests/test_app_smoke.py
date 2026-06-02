from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"


class AppSmokeTests(unittest.TestCase):
    def test_detail_chart_computes_indicators_before_trimming_visible_bars(self) -> None:
        source = APP.read_text(encoding="utf-8")

        self.assertIn("detail_df = db.load_kline(pick, detail_period)", source)
        self.assertIn(
            "build_chart_payload(detail_df, chart_indicators, bars=bars)",
            source,
        )
        self.assertNotIn("db.load_kline(pick, detail_period).tail", source)

    def test_app_source_keeps_authentication_out_of_scope(self) -> None:
        source = APP.read_text(encoding="utf-8").lower()

        for forbidden in ("login", "register", "authentication", "登录", "注册"):
            self.assertNotIn(forbidden, source)

    def test_empty_indicator_selection_does_not_mutate_widget_state(self) -> None:
        source = APP.read_text(encoding="utf-8")

        self.assertIn('chart_indicators = detail_indicators or ["MACD"]', source)
        self.assertNotIn(
            'st.session_state["detail_indicators"] = detail_indicators',
            source,
        )

    def test_initial_empty_state_runs_without_database(self) -> None:
        at = AppTest.from_file(str(APP)).run(timeout=20)

        self.assertEqual(len(at.exception), 0)
        rendered = "\n".join(
            getattr(node, "value", "")
            for node in [*at.markdown, *at.warning, *at.info, *at.caption]
        )
        self.assertIn("A 股多条件选股", rendered)
        self.assertIn("快速开始", rendered)


if __name__ == "__main__":
    unittest.main()
