"""akshare 数据采集封装。

负责：股票列表、日/周/月 K 线、分钟 K 线。
统一把 akshare 的中文列名转换成项目内部 schema（见 storage.db.KLINE_COLUMNS）。
"""
from __future__ import annotations

import time

import akshare as ak
import pandas as pd

from stock_screener.config import ADJUST, HISTORY_START, REQUEST_SLEEP

# akshare 中文列 -> 内部列
_KLINE_RENAME = {
    "日期": "date",
    "时间": "date",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
    "成交额": "amount",
}

# akshare period 参数（日/周/月用 stock_zh_a_hist）
_PERIOD_ARG = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}


def _retry(func, *args, retries: int = 3, **kwargs):
    """简单重试，应对 akshare 偶发网络/限频失败。"""
    last_err = None
    for i in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 - 数据源异常种类多，统一兜底重试
            last_err = e
            time.sleep(REQUEST_SLEEP * (i + 1) * 2)
    raise last_err


def fetch_stock_list() -> pd.DataFrame:
    """获取全部 A 股代码与名称。

    返回列：code, name, list_date, is_st, industry
    （list_date / industry 此处留空，由后续板块/数据补全。）

    先用交易所列表接口；失败则回退东方财富全 A 快照（更稳但更重）。
    """
    try:
        df = _retry(ak.stock_info_a_code_name)
        df = df.rename(columns={"code": "code", "name": "name"})
    except Exception:  # noqa: BLE001 - 回退到东财快照
        spot = _retry(ak.stock_zh_a_spot_em)
        df = spot.rename(columns={"代码": "code", "名称": "name"})[["code", "name"]]
    df["code"] = df["code"].astype(str).str.zfill(6)
    # 名称含 ST / *ST 视为风险股
    df["is_st"] = df["name"].str.upper().str.contains("ST").astype(int)
    df["list_date"] = None
    df["industry"] = None
    return df[["code", "name", "list_date", "is_st", "industry"]]


def _standardize_kline(df: pd.DataFrame, code: str) -> pd.DataFrame:
    """把 akshare K 线 DataFrame 转为内部 schema。"""
    if df is None or df.empty:
        return pd.DataFrame(columns=["code", "date", "open", "high", "low", "close", "volume", "amount"])
    df = df.rename(columns=_KLINE_RENAME)
    df["code"] = code
    # 日期统一成 YYYY-MM-DD 字符串（分钟线含时分秒也保留）
    df["date"] = df["date"].astype(str)
    keep = ["code", "date", "open", "high", "low", "close", "volume", "amount"]
    for col in keep:
        if col not in df.columns:
            df[col] = None
    out = df[keep].copy()
    num_cols = ["open", "high", "low", "close", "volume", "amount"]
    out[num_cols] = out[num_cols].apply(pd.to_numeric, errors="coerce")
    return out.dropna(subset=["close"]).reset_index(drop=True)


def fetch_kline(code: str, period: str = "daily", start_date: str | None = None,
                end_date: str | None = None) -> pd.DataFrame:
    """获取单只股票的日/周/月 K 线（前复权）。

    start_date / end_date 格式 YYYYMMDD；缺省用 config.HISTORY_START ~ 今天。
    """
    if period not in _PERIOD_ARG:
        raise ValueError(f"日/周/月周期错误 {period!r}")
    start = start_date or HISTORY_START
    end = end_date or pd.Timestamp.today().strftime("%Y%m%d")
    df = _retry(
        ak.stock_zh_a_hist,
        symbol=code,
        period=_PERIOD_ARG[period],
        start_date=start,
        end_date=end,
        adjust=ADJUST,
    )
    return _standardize_kline(df, code)


def fetch_kline_min(code: str, period: str = "60", start_date: str | None = None,
                    end_date: str | None = None) -> pd.DataFrame:
    """获取单只股票的分钟 K 线（60/15/5，前复权）。

    日期列含 'YYYY-MM-DD HH:MM:SS'。
    """
    start = (start_date or HISTORY_START)
    # 分钟接口要求 'YYYY-MM-DD HH:MM:SS' 形式
    start_fmt = f"{start[:4]}-{start[4:6]}-{start[6:8]} 09:30:00" if len(start) == 8 else start
    end = end_date or f"{pd.Timestamp.today().strftime('%Y-%m-%d')} 15:00:00"
    df = _retry(
        ak.stock_zh_a_hist_min_em,
        symbol=code,
        period=str(period),
        start_date=start_fmt,
        end_date=end,
        adjust=ADJUST,
    )
    return _standardize_kline(df, code)
