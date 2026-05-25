"""选股条件库。

每个条件是一个 Condition：有名字 + 一个判断函数 predicate(df)->bool，
predicate 在「已追加指标、按日期升序」的 K 线 DataFrame 上评估，判断最新一根 K 线是否满足。
条件用工厂函数生成，方便带参数（阈值、周期等）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

Predicate = Callable[[pd.DataFrame], bool]


@dataclass
class Condition:
    name: str
    predicate: Predicate

    def __call__(self, df: pd.DataFrame) -> bool:
        try:
            return bool(self.predicate(df))
        except Exception:  # noqa: BLE001 - 个股数据异常不应中断整轮选股
            return False


def _last(df: pd.DataFrame, col: str, i: int = -1) -> float:
    return df[col].iloc[i]


# ---------------- MACD ----------------

def macd_golden_cross() -> Condition:
    """MACD 金叉：DIF 上穿 DEA。"""
    def p(df: pd.DataFrame) -> bool:
        if len(df) < 2:
            return False
        return _last(df, "MACD_DIF", -2) <= _last(df, "MACD_DEA", -2) and \
            _last(df, "MACD_DIF") > _last(df, "MACD_DEA")
    return Condition("MACD金叉", p)


def macd_above_zero() -> Condition:
    """MACD 在零轴上方（DIF>0）。"""
    return Condition("MACD零轴上", lambda df: _last(df, "MACD_DIF") > 0)


# ---------------- RSI ----------------

def rsi_below(threshold: float = 30) -> Condition:
    return Condition(f"RSI<{threshold:g}", lambda df: _last(df, "RSI") < threshold)


def rsi_between(low: float, high: float) -> Condition:
    return Condition(f"RSI∈[{low:g},{high:g}]",
                     lambda df: low <= _last(df, "RSI") <= high)


# ---------------- KDJ ----------------

def kdj_golden_cross() -> Condition:
    """KDJ 金叉：K 上穿 D。"""
    def p(df: pd.DataFrame) -> bool:
        if len(df) < 2:
            return False
        return _last(df, "KDJ_K", -2) <= _last(df, "KDJ_D", -2) and \
            _last(df, "KDJ_K") > _last(df, "KDJ_D")
    return Condition("KDJ金叉", p)


# ---------------- 均线 / 趋势 ----------------

def ma_bullish() -> Condition:
    """均线多头排列：MA5 > MA10 > MA20。"""
    return Condition("均线多头",
                     lambda df: _last(df, "MA5") > _last(df, "MA10") > _last(df, "MA20"))


def price_above_ma(window: int = 20) -> Condition:
    return Condition(f"价格>MA{window}",
                     lambda df: _last(df, "close") > _last(df, f"MA{window}"))


def new_high(window: int = 60) -> Condition:
    """创 N 日新高（收盘价为近 window 日最高收盘）。"""
    def p(df: pd.DataFrame) -> bool:
        if len(df) < 2:
            return False
        recent = df["close"].tail(window)
        return _last(df, "close") >= recent.max()
    return Condition(f"创{window}日新高", p)


# ---------------- 成交量 ----------------

def volume_ratio_above(threshold: float = 1.5) -> Condition:
    return Condition(f"量比>{threshold:g}", lambda df: _last(df, "VOL_RATIO") > threshold)


def volume_price_up() -> Condition:
    """量价齐升：收盘较昨日上涨且成交量较昨日放大。"""
    def p(df: pd.DataFrame) -> bool:
        if len(df) < 2:
            return False
        return _last(df, "close") > _last(df, "close", -2) and \
            _last(df, "volume") > _last(df, "volume", -2)
    return Condition("量价齐升", p)
