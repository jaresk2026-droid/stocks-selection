"""A 股多条件选股 — Streamlit 界面（阶段 2）。

运行：
    .venv/bin/streamlit run app.py
浏览器会自动打开；想分享给朋友，把本程序部署到服务器后访问其地址即可。
"""
from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import streamlit as st

from stock_screener.engine import screen
from stock_screener.engine import catalog
from stock_screener.storage import db
from stock_screener.viz import build_kline_figure

st.set_page_config(page_title="A股多条件选股", layout="wide")

PERIOD_LABELS = {"日线": "daily", "周线": "weekly", "月线": "monthly"}


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
    """在侧边栏按类别渲染条件勾选 + 参数控件，返回选中的条件配置。"""
    selection: dict[str, dict] = {}
    for cat in catalog.categories():
        st.sidebar.markdown(f"**{cat}**")
        for spec in (s for s in catalog.CATALOG if s.category == cat):
            checked = st.sidebar.checkbox(spec.label, key=f"chk_{spec.key}",
                                          help=spec.help or None)
            if not checked:
                continue
            values = {}
            if spec.params:
                cols = st.sidebar.columns(len(spec.params))
                for col, p in zip(cols, spec.params):
                    values[p.key] = col.number_input(
                        p.label, value=float(p.default), min_value=float(p.min),
                        max_value=float(p.max), step=float(p.step),
                        key=f"par_{spec.key}_{p.key}",
                    )
            selection[spec.key] = values
    return selection


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


# ==================== 界面 ====================

st.title("A 股多条件选股")

# --- 侧边栏：周期、逻辑、过滤、条件 ---
st.sidebar.header("筛选设置")
period_label = st.sidebar.selectbox("K 线周期", list(PERIOD_LABELS), index=0)
period = PERIOD_LABELS[period_label]
logic_label = st.sidebar.radio("条件组合", ["全部满足 (AND)", "任一满足 (OR)"], index=0)
logic = "and" if "AND" in logic_label else "or"
exclude_st = st.sidebar.checkbox("剔除 ST 股", value=True)
min_bars = st.sidebar.number_input("最少 K 线根数", value=60, min_value=10, max_value=500, step=10)

st.sidebar.divider()
st.sidebar.subheader("选股条件")
selection = render_condition_picker()
run = st.sidebar.button("开始选股", type="primary", use_container_width=True)

# --- 数据状态提示 ---
n_basic, n_kline = data_status(period)
if n_kline == 0:
    st.warning(
        f"数据库中没有「{period_label}」数据。请先在终端运行：\n\n"
        "```\n"
        ".venv/bin/python scripts/init_data.py --periods daily\n"
        ".venv/bin/python scripts/update_fundamentals.py   # 需要基本面条件时\n"
        "```"
    )
else:
    st.caption(f"数据概况：基础信息 {n_basic} 只 ｜ {period_label}有数据 {n_kline} 只")

# --- 执行选股 ---
if run:
    conditions = catalog.build_conditions(selection)
    if not conditions:
        st.error("请至少勾选一个条件。")
    else:
        names = f" {logic.upper()} ".join(c.name for c in conditions)
        with st.spinner(f"正在按条件筛选：{names}"):
            result = screen(conditions, period=period, logic=logic,
                            exclude_st=exclude_st, min_bars=int(min_bars))
        st.session_state["result"] = result
        st.session_state["cond_names"] = names

# --- 展示结果 ---
result = st.session_state.get("result")
if result is not None:
    st.subheader(f"选股结果：命中 {len(result)} 只")
    st.caption("条件：" + st.session_state.get("cond_names", ""))
    if result.empty:
        st.info("没有符合条件的股票，试试放宽阈值或改用 OR 组合。")
    else:
        st.dataframe(result, use_container_width=True, hide_index=True)

        c1, c2 = st.columns(2)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        c1.download_button("下载 CSV", result.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"screen_{period}_{stamp}.csv", mime="text/csv")
        c2.download_button("下载 Excel", to_excel_bytes(result),
                           file_name=f"screen_{period}_{stamp}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        st.divider()
        st.subheader("个股 K 线")
        options = result["code"].tolist()
        labels = {row["code"]: f'{row["code"]} {row["name"]}' for _, row in result.iterrows()}
        pick = st.selectbox("选择股票", options, format_func=lambda c: labels.get(c, c))
        fig = build_kline_figure(pick, period=period, name=labels.get(pick, "").split(" ")[-1])
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
else:
    st.info("在左侧勾选条件后点击「开始选股」。")
