# Stock Screener Interaction Fusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `D:\Investment` 的非认证交互体验融入当前 A 股选股器，并用本地内嵌的 `lightweight-charts` 提供可切换周期、可缩放、带十字光标和智能多副图的个股详情。

**Architecture:** 保留现有筛选引擎和 SQLite 数据读取。新增纯 Python 图表数据模块，将 K 线、均线、成交量和 `MACD / RSI / KDJ` 转换为 JSON payload；新增独立 HTML 模板，通过 `streamlit.components.v1.html` 渲染本地内嵌图表运行时。`app.py` 只负责页面编排和 session state，不承载大型 JavaScript。

**Tech Stack:** Python 3、pandas、Streamlit、SQLite、标准库 `unittest`、TradingView `lightweight-charts` 4.2.0 本地运行时。

---

## File Map

- Create: `tests/__init__.py`
  - 让标准库 `unittest` 可以按模块运行新增测试。
- Create: `tests/test_lightweight.py`
  - 覆盖智能副图默认值、周期范围、payload 序列化、行情摘要和 HTML 渲染。
- Create: `stock_screener/viz/lightweight.py`
  - 提供纯 Python payload 构建、指标推荐、行情摘要和 HTML 渲染接口。
- Create: `stock_screener/viz/lightweight_template.html`
  - 保存 `lightweight-charts` 页面模板和 JavaScript 交互逻辑。
- Create: `static/lightweight-charts.js`
  - 从 `D:\Investment\static\lightweight-charts.js` 复制本地图表运行时。
- Modify: `stock_screener/viz/__init__.py`
  - 对外导出新的图表构建接口，同时保留原 Plotly 接口作为回退能力。
- Modify: `app.py`
  - 融合视觉样式、空状态、结果摘要、详情状态、周期切换、范围切换和副图多选。
- Modify: `README.md`
  - 更新图形界面说明和新增验证命令。

## Task 1: Build The Pure Python Chart Model

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_lightweight.py`
- Create: `stock_screener/viz/lightweight.py`

- [ ] **Step 1: Create the test package**

Create an empty file:

```python
# tests/__init__.py
```

- [ ] **Step 2: Write failing tests for indicator recommendation and range presets**

Create `tests/test_lightweight.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
python -m unittest tests.test_lightweight -v
```

Expected: `ModuleNotFoundError: No module named 'stock_screener.viz.lightweight'`.

- [ ] **Step 4: Implement recommendation, ranges, payload serialization, and quote summary**

Create `stock_screener/viz/lightweight.py` with these public interfaces and constants:

```python
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
        raise ValueError(f"未知周期 {period!r}") from exc


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
        raise ValueError("K 线数据为空")
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
        raise ValueError("K 线数据为空")
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
```

- [ ] **Step 5: Add payload and quote assertions**

Append to `LightweightChartModelTests`:

```python
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
```

- [ ] **Step 6: Run model tests**

Run:

```powershell
python -m unittest tests.test_lightweight -v
```

Expected: all six tests pass.

- [ ] **Step 7: Commit the pure model**

```powershell
git add tests/__init__.py tests/test_lightweight.py stock_screener/viz/lightweight.py
git commit -m "feat: add lightweight chart data model"
```

## Task 2: Add The Local Lightweight Charts Renderer

**Files:**
- Create: `static/lightweight-charts.js`
- Create: `stock_screener/viz/lightweight_template.html`
- Modify: `stock_screener/viz/lightweight.py`
- Modify: `tests/test_lightweight.py`
- Modify: `stock_screener/viz/__init__.py`

- [ ] **Step 1: Copy the reviewed local runtime from the reference project**

Run:

```powershell
New-Item -ItemType Directory -Force -Path static | Out-Null
Copy-Item -LiteralPath 'D:\Investment\static\lightweight-charts.js' -Destination 'static\lightweight-charts.js'
Get-Item -LiteralPath 'static\lightweight-charts.js' | Select-Object Length
```

Expected: file exists with length `163558`.

- [ ] **Step 2: Write failing HTML renderer tests**

Add imports:

```python
from stock_screener.viz.lightweight import render_chart_html
```

Append tests:

```python
    def test_html_renderer_inlines_runtime_and_payload(self):
        payload = build_chart_payload(self.df, ["MACD", "RSI"])
        html = render_chart_html(payload, runtime_js="window.LightweightCharts = {};")
        self.assertIn("window.LightweightCharts = {};", html)
        self.assertIn('"key": "MACD"', html)
        self.assertIn('"key": "RSI"', html)
        self.assertIn("oscillator-0", html)
        self.assertIn("oscillator-1", html)

    def test_html_renderer_fails_clearly_when_runtime_is_missing(self):
        with self.assertRaisesRegex(FileNotFoundError, "lightweight-charts"):
            render_chart_html({"candles": [], "volume": [], "overlays": [], "oscillators": [], "height": 500}, runtime_path="missing.js")
```

- [ ] **Step 3: Run the renderer tests to verify failure**

Run:

```powershell
python -m unittest tests.test_lightweight.LightweightChartModelTests.test_html_renderer_inlines_runtime_and_payload -v
```

Expected: fail because `render_chart_html` does not exist.

- [ ] **Step 4: Create the standalone HTML template**

Create `stock_screener/viz/lightweight_template.html`. The template must:

- use placeholders `__RUNTIME_JS__`, `__PAYLOAD_JSON__`, and `__OSCILLATOR_SECTIONS__`;
- create one main chart with candles, fixed volume, and MA overlays;
- create one independent chart per item in `PAYLOAD.oscillators`;
- synchronize visible logical ranges in both directions;
- synchronize crosshair positions from the main chart to each oscillator;
- show OHLC, percentage change, and MA values in the main tooltip;
- use red for rising candles and green for falling candles;
- show an in-frame error box if initialization throws.

Use this exact HTML skeleton and JavaScript contract:

```html
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<style>
html, body { margin:0; padding:0; height:100%; background:#fff; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; }
#wrap { position:relative; width:100%; height:100%; display:flex; flex-direction:column; }
#main-chart { position:relative; flex:1 1 auto; min-height:320px; }
.oscillator { position:relative; height:145px; border-top:1px solid #f0f0f0; }
.oscillator-chart { width:100%; height:100%; }
.oscillator-title, #legend { position:absolute; z-index:5; background:rgba(255,255,255,.88); border-radius:4px; padding:3px 7px; font-size:11px; color:#595959; }
.oscillator-title { top:4px; left:8px; }
#legend { top:8px; right:10px; max-width:70%; }
#tooltip { display:none; position:absolute; top:8px; left:10px; z-index:10; min-width:210px; padding:6px 10px; background:rgba(255,255,255,.94); border:1px solid #e5e5e5; border-radius:6px; font-size:12px; line-height:1.5; pointer-events:none; }
#chart-error { display:none; padding:16px; background:#fffbe6; border:1px solid #ffe58f; color:#874d00; font-size:13px; }
</style>
</head>
<body>
<div id="wrap">
  <div id="chart-error">图表初始化失败，请刷新页面重试。</div>
  <div id="main-chart"><div id="tooltip"></div><div id="legend"></div></div>
  __OSCILLATOR_SECTIONS__
</div>
<script>__RUNTIME_JS__</script>
<script>
const PAYLOAD = __PAYLOAD_JSON__;
const UP = '#ef5350', DOWN = '#26a69a';
function createOptions(showTimeScale) {
  return {
    autoSize:true,
    layout:{background:{color:'#fff'},textColor:'#333'},
    grid:{vertLines:{color:'#f5f5f5'},horzLines:{color:'#f5f5f5'}},
    timeScale:{visible:showTimeScale,borderColor:'#e0e0e0',rightOffset:4},
    rightPriceScale:{borderColor:'#e0e0e0'},
    crosshair:{mode:1},
    localization:{dateFormat:'yyyy-MM-dd',locale:'zh-CN'},
    handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:false},
    handleScale:{axisPressedMouseMove:true,mouseWheel:true,pinch:true},
  };
}
function addLine(chart, item) {
  const series = chart.addLineSeries({color:item.color,lineWidth:2,priceLineVisible:false,lastValueVisible:false});
  series.setData(item.data);
  return series;
}
try {
  const main = LightweightCharts.createChart(document.getElementById('main-chart'), createOptions(PAYLOAD.oscillators.length === 0));
  const candles = main.addCandlestickSeries({upColor:UP,downColor:DOWN,wickUpColor:UP,wickDownColor:DOWN,borderUpColor:UP,borderDownColor:DOWN});
  candles.setData(PAYLOAD.candles);
  const volume = main.addHistogramSeries({priceFormat:{type:'volume'},priceScaleId:'volume'});
  volume.setData(PAYLOAD.volume);
  main.priceScale('volume').applyOptions({scaleMargins:{top:.78,bottom:0}});
  const overlaySeries = PAYLOAD.overlays.map(item => ({item, series:addLine(main, item)}));
  document.getElementById('legend').innerHTML = PAYLOAD.overlays.map(item => '<span style="margin-left:8px;color:'+item.color+'">'+item.label+'</span>').join('');
  const oscCharts = PAYLOAD.oscillators.map((osc, index) => {
    const chart = LightweightCharts.createChart(document.getElementById('oscillator-'+index), createOptions(index === PAYLOAD.oscillators.length - 1));
    const series = osc.series.map(item => {
      if (item.type !== 'histogram') return addLine(chart, item);
      const histogram = chart.addHistogramSeries({priceLineVisible:false,lastValueVisible:false});
      histogram.setData(item.data.map(point => ({...point,color:point.value >= 0 ? 'rgba(239,83,80,.60)' : 'rgba(38,166,154,.60)'})));
      return histogram;
    });
    (osc.referenceLines || []).forEach(line => series[0].createPriceLine({price:line.value,color:line.color,lineWidth:1,lineStyle:2,axisLabelVisible:true,title:line.label}));
    return {chart, series};
  });
  let syncing = false;
  const syncRange = (source, targets) => source.timeScale().subscribeVisibleLogicalRangeChange(range => {
    if (syncing || !range) return;
    syncing = true;
    targets.forEach(target => target.timeScale().setVisibleLogicalRange(range));
    syncing = false;
  });
  syncRange(main, oscCharts.map(item => item.chart));
  oscCharts.forEach(item => syncRange(item.chart, [main, ...oscCharts.filter(other => other !== item).map(other => other.chart)]));
  const previous = Object.fromEntries(PAYLOAD.candles.map(item => [item.time, item.prevClose]));
  main.subscribeCrosshairMove(param => {
    if (!param.time || !param.point) { document.getElementById('tooltip').style.display='none'; return; }
    const value = param.seriesData.get(candles);
    if (!value) return;
    const pct = (value.close - previous[param.time]) / previous[param.time] * 100;
    const extra = overlaySeries.map(({item,series}) => {
      const point = param.seriesData.get(series);
      return point ? '<div style="color:'+item.color+'">'+item.label+' '+point.value.toFixed(2)+'</div>' : '';
    }).join('');
    const tooltip = document.getElementById('tooltip');
    tooltip.innerHTML = '<div>'+param.time+'</div><b>开 '+value.open.toFixed(2)+' 高 '+value.high.toFixed(2)+' 低 '+value.low.toFixed(2)+' 收 '+value.close.toFixed(2)+' ('+(pct >= 0 ? '+' : '')+pct.toFixed(2)+'%)</b>'+extra;
    tooltip.style.display='block';
    oscCharts.forEach(item => item.series[0] && item.chart.setCrosshairPosition(NaN, param.time, item.series[0]));
  });
  main.timeScale().fitContent();
  oscCharts.forEach(item => item.chart.timeScale().fitContent());
} catch (error) {
  console.error(error);
  document.getElementById('chart-error').style.display='block';
}
</script>
</body>
</html>
```

- [ ] **Step 5: Add the renderer implementation**

Append to `stock_screener/viz/lightweight.py`:

```python
def render_chart_html(payload: dict, runtime_js: str | None = None, runtime_path: str | Path = RUNTIME_PATH) -> str:
    if runtime_js is None:
        runtime_js = Path(runtime_path).read_text(encoding="utf-8")
    sections = "".join(
        f'<div class="oscillator"><div class="oscillator-title">{item["title"]}</div>'
        f'<div class="oscillator-chart" id="oscillator-{index}"></div></div>'
        for index, item in enumerate(payload["oscillators"])
    )
    return (
        TEMPLATE_PATH.read_text(encoding="utf-8")
        .replace("__RUNTIME_JS__", runtime_js)
        .replace("__PAYLOAD_JSON__", json.dumps(payload, ensure_ascii=False))
        .replace("__OSCILLATOR_SECTIONS__", sections)
    )
```

- [ ] **Step 6: Export the new interfaces**

Replace `stock_screener/viz/__init__.py` with:

```python
"""可视化：K 线图与 lightweight-charts 详情组件。"""
from stock_screener.viz.charts import build_kline_figure
from stock_screener.viz.lightweight import (
    build_chart_payload,
    latest_quote,
    range_presets,
    recommend_indicators,
    render_chart_html,
)

__all__ = [
    "build_chart_payload",
    "build_kline_figure",
    "latest_quote",
    "range_presets",
    "recommend_indicators",
    "render_chart_html",
]
```

- [ ] **Step 7: Run renderer and model tests**

Run:

```powershell
python -m unittest tests.test_lightweight -v
python -m compileall -q stock_screener tests
```

Expected: all tests pass and compile command exits `0`.

- [ ] **Step 8: Commit the renderer**

```powershell
git add static/lightweight-charts.js stock_screener/viz/lightweight_template.html stock_screener/viz/lightweight.py stock_screener/viz/__init__.py tests/test_lightweight.py
git commit -m "feat: add local lightweight charts renderer"
```

## Task 3: Fuse The Streamlit Interaction Design

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Confirm the non-auth boundary before editing**

Run:

```powershell
rg -n "auth|login|register|cookie|redeem|pro|rate_limit" app.py stock_screener
```

Expected: no matches. Do not copy `D:\Investment\auth.py`, `rate_limit.py`, account sidebar calls, or paid-plan states into this project.

- [ ] **Step 2: Replace the visualization imports**

Add:

```python
import streamlit.components.v1 as components

from stock_screener.viz import (
    build_chart_payload,
    latest_quote,
    range_presets,
    recommend_indicators,
    render_chart_html,
)
```

Remove the `build_kline_figure` import from `app.py`. Keep `stock_screener/viz/charts.py` unchanged as a fallback module.

- [ ] **Step 3: Add the global visual shell**

Immediately after `st.set_page_config(...)`, add:

```python
st.markdown(
    """
    <style>
    html, body, [class*="css"] {
        font-family: -apple-system, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif;
    }
    .block-container { padding-top: 2rem; padding-bottom: 1rem; }
    footer { visibility: hidden; }
    [data-testid="stSidebar"] > div:first-child { background: #f5f5f5 !important; }
    [data-testid="stAppViewContainer"] { background: #ffffff !important; }
    .stButton > button { border-radius: 6px !important; }
    @media (max-width: 768px) {
        .block-container { padding: 3rem .6rem 1rem !important; }
        h1 { font-size: 1.2rem !important; }
        h2 { font-size: 1.1rem !important; }
        h3 { font-size: 1rem !important; }
        [data-testid="column"] { padding: 0 2px !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def divider(label: str = "") -> None:
    if label:
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:8px;margin:14px 0 6px'>"
            f"<span style='font-size:13px;font-weight:600;color:#8c8c8c;white-space:nowrap'>{label}</span>"
            f"<span style='flex:1;height:1px;background:#e8e8e8'></span></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown("<hr style='margin:12px 0;border:none;border-top:1px solid #e8e8e8'>", unsafe_allow_html=True)


def metric_card(label: str, value: str, color: str) -> None:
    st.markdown(
        f"<div style='background:#fff;border:1px solid #e8e8e8;border-top:3px solid {color};"
        f"border-radius:8px;padding:12px;text-align:center'>"
        f"<div style='color:#8c8c8c;font-size:12px'>{label}</div>"
        f"<div style='color:{color};font-size:22px;font-weight:700;margin-top:5px'>{value}</div></div>",
        unsafe_allow_html=True,
    )
```

- [ ] **Step 4: Reorganize the sidebar**

Use the current controls and condition rendering, but wrap them in this order:

```python
with st.sidebar:
    st.markdown("## 📊 A 股多条件选股")
    st.caption("本地行情数据库 · 收盘后更新")
    divider("筛选范围")
    period_label = st.selectbox("K 线周期", list(PERIOD_LABELS), index=0)
    period = PERIOD_LABELS[period_label]
    logic_label = st.radio("条件组合", ["全部满足 (AND)", "任一满足 (OR)"], index=0)
    logic = "and" if "AND" in logic_label else "or"
    exclude_st = st.checkbox("剔除 ST 股", value=True)
    min_bars = st.number_input("最少 K 线根数", value=60, min_value=10, max_value=500, step=10)
    divider("选股条件")
    selection = render_condition_picker()
    divider("行业 / 板块")
    pick_industries, pick_boards = render_sector_picker()
    run = st.button("开始选股", type="primary", use_container_width=True)
    divider("帮助")
    with st.expander("❓ 指标和筛选规则说明"):
        st.markdown("**MACD / RSI / KDJ** 用于技术指标筛选。详情图中的副图会根据本次筛选条件自动展开，也可以手动切换。")
        st.caption("详情中的图表周期切换只影响当前股票，不会重新扫描全市场。")
```

Update `render_condition_picker()` and `render_sector_picker()` to use `st.markdown`, `st.checkbox`, `st.columns`, `st.multiselect`, and `st.caption` because they are now called inside `with st.sidebar:`.

- [ ] **Step 5: Persist the screening snapshot and reset detail state**

After a successful call to `screen(...)`, replace the existing state writes with:

```python
        st.session_state["result"] = result
        st.session_state["cond_names"] = names
        st.session_state["selection_snapshot"] = list(selection)
        st.session_state["screen_period"] = period
        for key in ("detail_code", "detail_period", "detail_indicators"):
            st.session_state.pop(key, None)
```

- [ ] **Step 6: Replace the empty state**

When `result is None`, render:

```python
st.markdown("# 📊 A 股多条件选股")
st.markdown("组合技术指标、基本面条件和行业板块，筛选后直接查看个股 K 线与指标图。")
st.warning("本工具仅供学习和研究，不构成任何投资建议。")
divider("🚀 快速开始")
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown("### 1. 配置条件")
    st.caption("在左侧选择周期、指标、阈值和行业板块。")
with c2:
    st.markdown("### 2. 开始选股")
    st.caption("点击按钮后扫描数据库并生成命中列表。")
with c3:
    st.markdown("### 3. 查看图表")
    st.caption("选择股票，切换周期和指标副图。")
```

- [ ] **Step 7: Add result summary cards**

Before the existing result table, add the cards below. Keep the current result DataFrame, CSV download button, and Excel download button unchanged:

```python
st.markdown(f"## 选股结果 · 命中 {len(result)} 只")
st.caption("条件：" + st.session_state.get("cond_names", ""))
c1, c2, c3 = st.columns(3)
with c1:
    metric_card("命中股票", str(len(result)), "#1677ff")
with c2:
    metric_card("筛选周期", next(label for label, value in PERIOD_LABELS.items() if value == st.session_state.get("screen_period", period)), "#52c41a")
with c3:
    metric_card("已选条件", str(len(st.session_state.get("selection_snapshot", []))), "#fa8c16")
```

- [ ] **Step 8: Replace the Plotly detail block with the lightweight detail block**

After the downloads, replace the existing `build_kline_figure` block with:

```python
divider("个股详情")
options = result["code"].tolist()
labels = {row["code"]: f'{row["code"]} {row["name"]}' for _, row in result.iterrows()}
pick = st.selectbox("选择股票", options, format_func=lambda code: labels.get(code, code), key="detail_code")

screen_period = st.session_state.get("screen_period", period)
if "detail_period" not in st.session_state:
    st.session_state["detail_period"] = screen_period
detail_labels = list(PERIOD_LABELS)
default_period_index = list(PERIOD_LABELS.values()).index(st.session_state["detail_period"])
detail_period_label = st.radio("图表周期", detail_labels, index=default_period_index, horizontal=True)
detail_period = PERIOD_LABELS[detail_period_label]
st.session_state["detail_period"] = detail_period

presets = range_presets(detail_period)
range_label = st.radio("时间范围", [label for label, _ in presets], index=min(2, len(presets) - 1), horizontal=True, key=f"detail_range_{detail_period}")
bars = dict(presets)[range_label]

if "detail_indicators" not in st.session_state:
    st.session_state["detail_indicators"] = recommend_indicators(st.session_state.get("selection_snapshot", []))
detail_indicators = st.multiselect(
    "指标副图",
    ["MACD", "RSI", "KDJ"],
    key="detail_indicators",
    help="默认根据本次筛选条件自动选择；可以多选展开更多副图。",
)
if not detail_indicators:
    st.info("至少保留一个指标副图。已恢复默认 MACD。")
    detail_indicators = ["MACD"]
    st.session_state["detail_indicators"] = detail_indicators

detail_df = db.load_kline(pick, detail_period).tail(bars).reset_index(drop=True)
if detail_df.empty:
    st.warning(f"{labels.get(pick, pick)} 暂无{detail_period_label}数据，请切换其他周期。")
else:
    quote = latest_quote(detail_df)
    color = "#e3494f" if quote["change"] >= 0 else "#22a76b"
    sign = "+" if quote["change"] >= 0 else ""
    st.markdown(
        f"<h3 style='margin-bottom:4px'>{labels.get(pick, pick)}</h3>"
        f"<div style='color:{color};font-size:13px'>"
        f"{quote['close']:.2f}　{sign}{quote['change']:.2f} ({sign}{quote['pct']:.2f}%)　"
        f"开 {quote['open']:.2f}　高 {quote['high']:.2f}　低 {quote['low']:.2f}　量 {quote['volume']:.0f}</div>",
        unsafe_allow_html=True,
    )
    st.caption("拖动平移 · 滚轮或双指缩放 · 十字光标查看 OHLC")
    try:
        payload = build_chart_payload(detail_df, detail_indicators)
        components.html(render_chart_html(payload), height=payload["height"], scrolling=False)
    except Exception as exc:
        st.error(f"图表加载失败：{exc}")
```

- [ ] **Step 9: Compile the app**

Run:

```powershell
python -m compileall -q app.py stock_screener tests
```

Expected: exits `0`.

- [ ] **Step 10: Run unit tests**

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 11: Re-check the non-auth boundary**

Run:

```powershell
rg -n "from auth|import auth|rate_limit|render_sidebar_auth|redeem|登录|注册|Pro" app.py stock_screener
```

Expected: no matches.

- [ ] **Step 12: Commit the Streamlit integration**

```powershell
git add app.py
git commit -m "feat: fuse screener interaction design"
```

## Task 4: Document And Verify The Finished Workflow

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the GUI documentation**

In the README graphical interface section, document:

```markdown
- 结果页显示命中数量、筛选周期和已选条件摘要。
- 选择命中股票后，可在结果表下方展开个股详情。
- 个股详情使用 lightweight-charts：支持拖动、缩放和十字光标 OHLC 提示。
- 图表周期（日 / 周 / 月）与侧栏筛选周期相互独立；切换详情周期不会重新执行全市场筛选。
- 成交量固定展示；MACD、RSI、KDJ 副图根据筛选条件智能展开，也可手动多选。
```

Add verification commands:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app.py stock_screener tests
streamlit run app.py
```

- [ ] **Step 2: Run the automated verification**

Run:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app.py stock_screener tests
git diff --check
```

Expected: tests pass, compile exits `0`, and `git diff --check` emits no whitespace errors.

- [ ] **Step 3: Start Streamlit for browser verification**

Run:

```powershell
Start-Process -FilePath '.venv\Scripts\streamlit.exe' -ArgumentList 'run','app.py','--server.headless=true','--server.port=8501' -WorkingDirectory 'D:\Stocks_selection' -WindowStyle Hidden
```

Expected: `http://localhost:8501` responds.

- [ ] **Step 4: Verify the UI with the Browser plugin**

Use the `browser:control-in-app-browser` skill and verify:

1. The initial empty state shows the quick-start cards and non-investment-advice message.
2. The sidebar shows grouped sections and no login or registration UI.
3. After a screen run with available local data, summary cards, result table, downloads, and stock selector appear.
4. Changing detail period updates only the current stock chart.
5. The main chart displays candles, volume, MA overlays, drag, zoom, and crosshair tooltip.
6. RSI, MACD, and KDJ can be selected together and render as separate synchronized副图.
7. A narrow viewport remains usable.

- [ ] **Step 5: Commit documentation**

```powershell
git add README.md
git commit -m "docs: describe enhanced screener charts"
```

- [ ] **Step 6: Perform final repository verification**

Run:

```powershell
git status --short
git log --oneline -n 8
```

Expected: only pre-existing unrelated local files such as `.claude/` remain untracked; the implementation commits are visible.

- [ ] **Step 7: Push the implementation branch**

Run:

```powershell
git push
```

Expected: the remote branch updates successfully and draft PR `#3` contains the implementation.
