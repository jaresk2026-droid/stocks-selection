"""用 plotly 画带指标的 K 线图（不依赖 Streamlit，便于单独测试）。"""
from __future__ import annotations

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from stock_screener.indicators import add_indicators
from stock_screener.storage import db

_UP = "#e3494f"    # 涨（A 股习惯红涨）
_DOWN = "#22a76b"  # 跌（绿跌）


def build_kline_figure(code: str, period: str = "daily", bars: int = 120,
                       name: str | None = None) -> go.Figure | None:
    """读取某股票某周期 K 线，画「K线+均线 / 成交量 / MACD」三栏图。

    返回 plotly Figure；无数据返回 None。
    """
    kl = db.load_kline(code, period)
    if kl.empty:
        return None
    df = add_indicators(kl).tail(bars).reset_index(drop=True)
    x = df["date"].astype(str)

    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=(f"{code} {name or ''} K线 + 均线", "成交量", "MACD"),
    )

    # --- K 线 + 均线 ---
    fig.add_trace(go.Candlestick(
        x=x, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="K线", increasing_line_color=_UP, decreasing_line_color=_DOWN,
    ), row=1, col=1)
    for ma, color in (("MA5", "#f5a623"), ("MA10", "#4a90d9"), ("MA20", "#9b59b6"), ("MA60", "#7f8c8d")):
        if ma in df.columns:
            fig.add_trace(go.Scatter(x=x, y=df[ma], name=ma, mode="lines",
                                     line=dict(width=1, color=color)), row=1, col=1)

    # --- 成交量 ---
    vol_colors = [_UP if c >= o else _DOWN for o, c in zip(df["open"], df["close"])]
    fig.add_trace(go.Bar(x=x, y=df["volume"], name="成交量",
                         marker_color=vol_colors, showlegend=False), row=2, col=1)

    # --- MACD ---
    hist_colors = [_UP if v >= 0 else _DOWN for v in df["MACD_HIST"]]
    fig.add_trace(go.Bar(x=x, y=df["MACD_HIST"], name="MACD柱",
                         marker_color=hist_colors, showlegend=False), row=3, col=1)
    fig.add_trace(go.Scatter(x=x, y=df["MACD_DIF"], name="DIF", mode="lines",
                             line=dict(width=1, color="#f5a623")), row=3, col=1)
    fig.add_trace(go.Scatter(x=x, y=df["MACD_DEA"], name="DEA", mode="lines",
                             line=dict(width=1, color="#4a90d9")), row=3, col=1)

    fig.update_layout(
        height=720, margin=dict(l=40, r=20, t=40, b=20),
        xaxis_rangeslider_visible=False, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    # 用类目轴去掉非交易日空隙
    fig.update_xaxes(type="category", showticklabels=False, row=1, col=1)
    fig.update_xaxes(type="category", showticklabels=False, row=2, col=1)
    fig.update_xaxes(type="category", nticks=10, row=3, col=1)
    return fig
