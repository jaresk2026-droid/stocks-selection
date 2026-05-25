"""选股条件库。

每个条件是一个 Condition：有名字 + 判断函数 predicate(ctx)->bool。
ctx 是 Context，同时持有：
    ctx.df   —— 已追加指标、按日期升序的 K 线 DataFrame（技术面）
    ctx.fund —— 该股票的基本面字段 dict（估值/财务），可能为空
技术面条件读 ctx.df 的最新一根 K 线；基本面条件读 ctx.fund。
条件用工厂函数生成，方便带参数（阈值、周期等）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd


@dataclass
class Context:
    df: pd.DataFrame                      # K 线 + 指标
    fund: dict = field(default_factory=dict)  # 基本面字段


Predicate = Callable[[Context], bool]


@dataclass
class Condition:
    name: str
    predicate: Predicate

    def __call__(self, ctx: Context) -> bool:
        try:
            return bool(self.predicate(ctx))
        except Exception:  # noqa: BLE001 - 个股数据异常不应中断整轮选股
            return False


def _last(ctx: Context, col: str, i: int = -1) -> float:
    return ctx.df[col].iloc[i]


def _fund(ctx: Context, key: str) -> float | None:
    """取基本面字段，缺失或 NaN 返回 None。"""
    v = ctx.fund.get(key)
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return v


# ==================== 技术面条件 ====================

# ---------------- MACD ----------------

def macd_golden_cross() -> Condition:
    """MACD 金叉：DIF 上穿 DEA。"""
    def p(ctx: Context) -> bool:
        if len(ctx.df) < 2:
            return False
        return _last(ctx, "MACD_DIF", -2) <= _last(ctx, "MACD_DEA", -2) and \
            _last(ctx, "MACD_DIF") > _last(ctx, "MACD_DEA")
    return Condition("MACD金叉", p)


def macd_above_zero() -> Condition:
    """MACD 在零轴上方（DIF>0）。"""
    return Condition("MACD零轴上", lambda ctx: _last(ctx, "MACD_DIF") > 0)


# ---------------- RSI ----------------

def rsi_below(threshold: float = 30) -> Condition:
    return Condition(f"RSI<{threshold:g}", lambda ctx: _last(ctx, "RSI") < threshold)


def rsi_between(low: float, high: float) -> Condition:
    return Condition(f"RSI∈[{low:g},{high:g}]",
                     lambda ctx: low <= _last(ctx, "RSI") <= high)


# ---------------- KDJ ----------------

def kdj_golden_cross() -> Condition:
    """KDJ 金叉：K 上穿 D。"""
    def p(ctx: Context) -> bool:
        if len(ctx.df) < 2:
            return False
        return _last(ctx, "KDJ_K", -2) <= _last(ctx, "KDJ_D", -2) and \
            _last(ctx, "KDJ_K") > _last(ctx, "KDJ_D")
    return Condition("KDJ金叉", p)


# ---------------- 均线 / 趋势 ----------------

def ma_bullish() -> Condition:
    """均线多头排列：MA5 > MA10 > MA20。"""
    return Condition("均线多头",
                     lambda ctx: _last(ctx, "MA5") > _last(ctx, "MA10") > _last(ctx, "MA20"))


def price_above_ma(window: int = 20) -> Condition:
    return Condition(f"价格>MA{window}",
                     lambda ctx: _last(ctx, "close") > _last(ctx, f"MA{window}"))


def new_high(window: int = 60) -> Condition:
    """创 N 日新高（收盘价为近 window 日最高收盘）。"""
    def p(ctx: Context) -> bool:
        if len(ctx.df) < 2:
            return False
        recent = ctx.df["close"].tail(window)
        return _last(ctx, "close") >= recent.max()
    return Condition(f"创{window}日新高", p)


# ---------------- 成交量 ----------------

def volume_ratio_above(threshold: float = 1.5) -> Condition:
    return Condition(f"量比>{threshold:g}", lambda ctx: _last(ctx, "VOL_RATIO") > threshold)


def volume_price_up() -> Condition:
    """量价齐升：收盘较昨日上涨且成交量较昨日放大。"""
    def p(ctx: Context) -> bool:
        if len(ctx.df) < 2:
            return False
        return _last(ctx, "close") > _last(ctx, "close", -2) and \
            _last(ctx, "volume") > _last(ctx, "volume", -2)
    return Condition("量价齐升", p)


# ==================== 基本面条件 ====================
# 注：基本面字段缺失（未拉取基本面数据）时，相关条件一律判 False。

# ---------------- 估值 ----------------

def pe_between(low: float = 0, high: float = 30) -> Condition:
    """市盈率（动态）在区间内。亏损股 PE 为负，默认 low=0 可顺带排除。"""
    def p(ctx: Context) -> bool:
        pe = _fund(ctx, "pe")
        return pe is not None and low <= pe <= high
    return Condition(f"PE∈[{low:g},{high:g}]", p)


def pe_below(threshold: float = 30, positive_only: bool = True) -> Condition:
    def p(ctx: Context) -> bool:
        pe = _fund(ctx, "pe")
        if pe is None:
            return False
        if positive_only and pe <= 0:
            return False
        return pe < threshold
    return Condition(f"PE<{threshold:g}", p)


def pb_below(threshold: float = 3) -> Condition:
    def p(ctx: Context) -> bool:
        pb = _fund(ctx, "pb")
        return pb is not None and 0 < pb < threshold
    return Condition(f"PB<{threshold:g}", p)


def market_cap_between(low_yi: float = 0, high_yi: float = 1e9) -> Condition:
    """总市值区间，单位「亿元」。"""
    def p(ctx: Context) -> bool:
        mv = _fund(ctx, "total_mv")
        return mv is not None and low_yi * 1e8 <= mv <= high_yi * 1e8
    return Condition(f"市值∈[{low_yi:g},{high_yi:g}]亿", p)


# ---------------- 盈利能力 ----------------

def roe_above(threshold: float = 10) -> Condition:
    """净资产收益率（%）大于阈值。"""
    def p(ctx: Context) -> bool:
        roe = _fund(ctx, "roe")
        return roe is not None and roe > threshold
    return Condition(f"ROE>{threshold:g}%", p)


def eps_above(threshold: float = 0) -> Condition:
    """每股收益大于阈值（默认 >0，即盈利）。"""
    def p(ctx: Context) -> bool:
        eps = _fund(ctx, "eps")
        return eps is not None and eps > threshold
    return Condition(f"EPS>{threshold:g}", p)


def gross_margin_above(threshold: float = 30) -> Condition:
    """销售毛利率（%）大于阈值。"""
    def p(ctx: Context) -> bool:
        gm = _fund(ctx, "gross_margin")
        return gm is not None and gm > threshold
    return Condition(f"毛利率>{threshold:g}%", p)


# ---------------- 成长性 ----------------

def revenue_yoy_above(threshold: float = 20) -> Condition:
    """营收同比增长（%）大于阈值。"""
    def p(ctx: Context) -> bool:
        v = _fund(ctx, "revenue_yoy")
        return v is not None and v > threshold
    return Condition(f"营收同比>{threshold:g}%", p)


def profit_yoy_above(threshold: float = 20) -> Condition:
    """净利润同比增长（%）大于阈值。"""
    def p(ctx: Context) -> bool:
        v = _fund(ctx, "profit_yoy")
        return v is not None and v > threshold
    return Condition(f"净利同比>{threshold:g}%", p)
