"""常用技术指标的纯 pandas 实现。

为什么不用 pandas-ta / TA-Lib：
- TA-Lib 需要编译 C 库，非程序员安装易踩坑；
- 这些指标公式简单且固定，自己实现零依赖、可读、好维护。

所有函数都接收一个按日期升序排列的 K 线 DataFrame（含 open/high/low/close/volume），
返回追加了指标列的新 DataFrame。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD：DIF、DEA、柱(MACD_HIST)。柱 = (DIF-DEA)*2（A 股习惯）。"""
    dif = ema(close, fast) - ema(close, slow)
    dea = ema(dif, signal)
    hist = (dif - dea) * 2
    return pd.DataFrame({"MACD_DIF": dif, "MACD_DEA": dea, "MACD_HIST": hist})


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI（Wilder 平滑）。"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.fillna(100)  # 全程上涨时 loss=0 -> RSI=100


def kdj(high: pd.Series, low: pd.Series, close: pd.Series,
        n: int = 9, k_period: int = 3, d_period: int = 3) -> pd.DataFrame:
    """KDJ：K、D、J。RSV 用 n 日最高/最低，K/D 用递推平滑。"""
    low_n = low.rolling(n, min_periods=1).min()
    high_n = high.rolling(n, min_periods=1).max()
    rsv = (close - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    rsv = rsv.fillna(50)
    k = rsv.ewm(alpha=1 / k_period, adjust=False).mean()
    d = k.ewm(alpha=1 / d_period, adjust=False).mean()
    j = 3 * k - 2 * d
    return pd.DataFrame({"KDJ_K": k, "KDJ_D": d, "KDJ_J": j})


def moving_averages(close: pd.Series, windows: tuple[int, ...] = (5, 10, 20, 60)) -> pd.DataFrame:
    return pd.DataFrame({f"MA{w}": close.rolling(w, min_periods=1).mean() for w in windows})


def volume_ratio(volume: pd.Series, period: int = 5) -> pd.Series:
    """量比 = 当日成交量 / 过去 period 日平均成交量（不含当日）。"""
    avg_prev = volume.shift(1).rolling(period, min_periods=1).mean()
    return volume / avg_prev.replace(0, np.nan)


def add_indicators(df: pd.DataFrame, ma_windows: tuple[int, ...] = (5, 10, 20, 60)) -> pd.DataFrame:
    """对一只股票的 K 线追加全部指标列。要求按日期升序。"""
    if df.empty:
        return df
    df = df.sort_values("date").reset_index(drop=True)
    out = df.copy()
    out = pd.concat([out, macd(df["close"])], axis=1)
    out["RSI"] = rsi(df["close"])
    out = pd.concat([out, kdj(df["high"], df["low"], df["close"])], axis=1)
    out = pd.concat([out, moving_averages(df["close"], ma_windows)], axis=1)
    out["VOL_RATIO"] = volume_ratio(df["volume"])
    return out
