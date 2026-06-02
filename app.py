"""A 股多条件选股 — Streamlit 界面（交互融合版）。

运行：
    .venv/bin/streamlit run app.py
浏览器会自动打开；想分享给朋友，把本程序部署到服务器后访问其地址即可。
"""
from __future__ import annotations

import html
import io
from datetime import datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from stock_screener.engine import screen
from stock_screener.engine import catalog
from stock_screener.engine import conditions as C
from stock_screener.storage import db
from stock_screener.viz import (
    build_chart_payload,
    latest_quote,
    range_presets,
    recommend_indicators,
    render_chart_html,
)

st.set_page_config(page_title="A股多条件选股", layout="wide")

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

PERIOD_LABELS = {"日线": "daily", "周线": "weekly", "月线": "monthly"}


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


@st.cache_data(show_spinner=False)
def data_status(period: str) -> tuple[int, int]:
    """返回 (基础信息股票数, 该周期有K线的股票数)。带缓存避免重复查库。"""
    try:
        basic = len(db.load_stock_basic())
        kl = len(db.all_codes_with_data(period))
    except Exception:
        return 0, 0
    return basic, kl


def render_condition_picker() -> dict[str, dict]:
    """在侧边栏按类别渲染条件勾选 + 参数控件，返回选中的条件配置。

    需在 ``with st.sidebar:`` 上下文里调用，所有控件用普通 ``st.*`` 即可落入侧栏。
    """
    selection: dict[str, dict] = {}
    for cat in catalog.categories():
        st.markdown(f"**{cat}**")
        for spec in (s for s in catalog.CATALOG if s.category == cat):
            checked = st.checkbox(spec.label, key=f"chk_{spec.key}", help=spec.help or None)
            if not checked:
                continue
            values = {}
            if spec.params:
                cols = st.columns(len(spec.params))
                for col, p in zip(cols, spec.params):
                    values[p.key] = col.number_input(
                        p.label, value=float(p.default), min_value=float(p.min),
                        max_value=float(p.max), step=float(p.step),
                        key=f"par_{spec.key}_{p.key}",
                    )
            selection[spec.key] = values
    return selection


@st.cache_data(show_spinner=False)
def sector_options() -> tuple[list[str], list[str]]:
    """行业列表（stock_basic）与板块列表（stock_boards），供下拉。"""
    try:
        return db.list_industries(), db.list_boards()
    except Exception:
        return [], []


def render_sector_picker() -> tuple[list[str], list[str]]:
    """渲染行业 / 板块多选，返回 (选中的行业, 选中的板块)。

    需在 ``with st.sidebar:`` 上下文里调用。
    """
    industries, boards = sector_options()
    pick_ind, pick_board = [], []
    if industries:
        pick_ind = st.multiselect("行业（来自财报分类）", industries,
                                  help="需先运行 update_fundamentals.py 回填行业")
    if boards:
        pick_board = st.multiselect("板块（行业+概念）", boards,
                                    help="需先运行 update_sectors.py")
    if not industries and not boards:
        st.caption("（运行 update_fundamentals / update_sectors 后可按行业/板块筛选）")
    return pick_ind, pick_board


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


# ==================== 侧边栏 ====================

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

# --- 数据状态提示 ---
n_basic, n_kline = data_status(period)

# --- 执行选股 ---
if run:
    conditions = catalog.build_conditions(selection)
    if pick_industries:
        conditions.append(C.industry_in(pick_industries))
    if pick_boards:
        conditions.append(C.board_in(pick_boards))
    if not conditions:
        st.error("请至少勾选一个条件（或选择行业/板块）。")
    elif n_kline == 0:
        st.warning(
            f"数据库中没有「{period_label}」数据。请先在终端运行：\n\n"
            "```\n"
            ".venv/bin/python scripts/init_data.py --periods daily\n"
            ".venv/bin/python scripts/update_fundamentals.py   # 需要基本面条件时\n"
            "```"
        )
    else:
        names = f" {logic.upper()} ".join(c.name for c in conditions)
        frames = catalog.needed_periods(selection)
        with st.spinner(f"正在按条件筛选：{names}"):
            result = screen(conditions, period=period, logic=logic,
                            exclude_st=exclude_st, min_bars=int(min_bars), frames=frames)
        st.session_state["result"] = result
        st.session_state["cond_names"] = names
        st.session_state["selection_snapshot"] = list(selection)
        st.session_state["screen_period"] = period
        st.session_state["condition_count"] = len(conditions)
        for key in ("detail_code", "detail_period", "detail_period_label", "detail_indicators"):
            st.session_state.pop(key, None)

# ==================== 主区 ====================

result = st.session_state.get("result")

if result is None:
    st.markdown("# 📊 A 股多条件选股")
    st.markdown("组合技术指标、基本面条件和行业板块，筛选后直接查看个股 K 线与指标图。")
    st.warning("本工具仅供学习和研究，不构成任何投资建议。")
    if n_kline == 0:
        st.info(
            f"当前数据库还没有「{period_label}」数据。先在终端运行 "
            "`scripts/init_data.py --periods daily` 拉取行情后即可选股。"
        )
    else:
        st.caption(f"数据概况：基础信息 {n_basic} 只 ｜ {period_label}有数据 {n_kline} 只")
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
else:
    st.markdown(f"## 选股结果 · 命中 {len(result)} 只")
    st.caption("条件：" + st.session_state.get("cond_names", ""))
    c1, c2, c3 = st.columns(3)
    with c1:
        metric_card("命中股票", str(len(result)), "#1677ff")
    with c2:
        metric_card(
            "筛选周期",
            next(label for label, value in PERIOD_LABELS.items()
                 if value == st.session_state.get("screen_period", period)),
            "#52c41a",
        )
    with c3:
        metric_card(
            "已选条件",
            str(st.session_state.get("condition_count", len(st.session_state.get("selection_snapshot", [])))),
            "#fa8c16",
        )

    if result.empty:
        st.info("没有符合条件的股票，试试放宽阈值或改用 OR 组合。")
    else:
        divider()
        st.dataframe(result, use_container_width=True, hide_index=True)

        cdl, cxl = st.columns(2)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screen_period = st.session_state.get("screen_period", period)
        cdl.download_button("下载 CSV", result.to_csv(index=False).encode("utf-8-sig"),
                            file_name=f"screen_{screen_period}_{stamp}.csv", mime="text/csv")
        cxl.download_button("下载 Excel", to_excel_bytes(result),
                            file_name=f"screen_{screen_period}_{stamp}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        divider("个股详情")
        options = result["code"].tolist()
        labels = {row["code"]: f'{row["code"]} {row["name"]}' for _, row in result.iterrows()}
        pick = st.selectbox("选择股票", options, format_func=lambda code: labels.get(code, code), key="detail_code")

        if "detail_period" not in st.session_state:
            st.session_state["detail_period"] = screen_period
        detail_labels = list(PERIOD_LABELS)
        default_period_index = list(PERIOD_LABELS.values()).index(st.session_state["detail_period"])
        detail_period_label = st.radio(
            "图表周期",
            detail_labels,
            index=default_period_index,
            horizontal=True,
            key="detail_period_label",
        )
        detail_period = PERIOD_LABELS[detail_period_label]
        st.session_state["detail_period"] = detail_period

        presets = range_presets(detail_period)
        range_label = st.radio("时间范围", [label for label, _ in presets],
                               index=min(2, len(presets) - 1), horizontal=True,
                               key=f"detail_range_{detail_period}")
        bars = dict(presets)[range_label]

        if "detail_indicators" not in st.session_state:
            st.session_state["detail_indicators"] = recommend_indicators(
                st.session_state.get("selection_snapshot", []))
        detail_indicators = st.multiselect(
            "指标副图",
            ["MACD", "RSI", "KDJ"],
            key="detail_indicators",
            help="默认根据本次筛选条件自动选择；可以多选展开更多副图。",
        )
        if not detail_indicators:
            st.info("至少保留一个指标副图。本次图表先按默认 MACD 展示。")
        chart_indicators = detail_indicators or ["MACD"]

        detail_df = db.load_kline(pick, detail_period)
        if detail_df.empty:
            st.warning(f"{labels.get(pick, pick)} 暂无{detail_period_label}数据，请切换其他周期。")
        else:
            quote = latest_quote(detail_df.tail(bars))
            color = "#e3494f" if quote["change"] >= 0 else "#22a76b"
            sign = "+" if quote["change"] >= 0 else ""
            stock_label = html.escape(labels.get(pick, pick))
            st.markdown(
                f"<h3 style='margin-bottom:4px'>{stock_label}</h3>"
                f"<div style='color:{color};font-size:13px'>"
                f"{quote['close']:.2f}　{sign}{quote['change']:.2f} ({sign}{quote['pct']:.2f}%)　"
                f"开 {quote['open']:.2f}　高 {quote['high']:.2f}　低 {quote['low']:.2f}　量 {quote['volume']:.0f}</div>",
                unsafe_allow_html=True,
            )
            st.caption("拖动平移 · 滚轮或双指缩放 · 十字光标查看 OHLC")
            try:
                payload = build_chart_payload(detail_df, chart_indicators, bars=bars)
                components.html(render_chart_html(payload), height=payload["height"], scrolling=False)
            except Exception as exc:
                st.error(f"图表加载失败：{exc}")
