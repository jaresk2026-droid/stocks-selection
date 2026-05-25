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


# ---------------- 基本面 ----------------

# stock_zh_a_spot_em 估值列 -> 内部列
_VALUATION_RENAME = {
    "代码": "code", "市盈率-动态": "pe", "市净率": "pb",
    "总市值": "total_mv", "流通市值": "circ_mv",
}

# stock_yjbb_em 业绩报表列 -> 内部列
_PERF_RENAME = {
    "股票代码": "code", "每股收益": "eps", "每股净资产": "bps",
    "净资产收益率": "roe", "营业总收入-营业总收入": "revenue",
    "营业总收入-同比增长": "revenue_yoy", "净利润-净利润": "profit",
    "净利润-同比增长": "profit_yoy", "销售毛利率": "gross_margin",
    "所处行业": "industry",
}


def fetch_valuation() -> pd.DataFrame:
    """全市场估值快照：code, pe, pb, total_mv, circ_mv（来自东方财富）。"""
    spot = _retry(ak.stock_zh_a_spot_em)
    cols = {k: v for k, v in _VALUATION_RENAME.items() if k in spot.columns}
    df = spot.rename(columns=cols)[list(cols.values())].copy()
    df["code"] = df["code"].astype(str).str.zfill(6)
    for c in ["pe", "pb", "total_mv", "circ_mv"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def latest_report_dates(n: int = 4) -> list[str]:
    """返回最近 n 个财报报告期（YYYYMMDD），由近及远。"""
    today = pd.Timestamp.today()
    ends = []
    year = today.year
    for y in (year, year - 1):
        for md in ("1231", "0930", "0630", "0331"):
            d = f"{y}{md}"
            if d <= today.strftime("%Y%m%d"):
                ends.append(d)
    return sorted(set(ends), reverse=True)[:n]


def fetch_performance(report_date: str | None = None) -> pd.DataFrame:
    """全市场业绩报表（来自东方财富）。

    report_date 为报告期 YYYYMMDD；缺省自动尝试最近几个报告期，取第一个有数据的。
    返回列：code, eps, bps, roe, revenue, revenue_yoy, profit, profit_yoy,
            gross_margin, industry, report_date
    """
    candidates = [report_date] if report_date else latest_report_dates()
    for rd in candidates:
        try:
            df = _retry(ak.stock_yjbb_em, date=rd)
        except Exception:  # noqa: BLE001 - 该报告期可能尚未发布，换下一个
            continue
        if df is None or df.empty:
            continue
        cols = {k: v for k, v in _PERF_RENAME.items() if k in df.columns}
        out = df.rename(columns=cols)[list(cols.values())].copy()
        out["code"] = out["code"].astype(str).str.zfill(6)
        num = ["eps", "bps", "roe", "revenue", "revenue_yoy", "profit",
               "profit_yoy", "gross_margin"]
        for c in num:
            if c in out.columns:
                out[c] = pd.to_numeric(out[c], errors="coerce")
        out["report_date"] = rd
        return out
    return pd.DataFrame()


def fetch_fundamentals(report_date: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """合并估值 + 业绩为基本面表。

    返回 (fundamentals_df, industry_df)：
        fundamentals_df 含 db.FUNDAMENTAL_COLUMNS；
        industry_df 含 code, industry（用于回填 stock_basic）。
    """
    perf = fetch_performance(report_date)
    val = fetch_valuation()
    if perf.empty:
        merged = val.copy()
        merged["report_date"] = None
    else:
        merged = perf.merge(val, on="code", how="outer")
    industry_df = (perf[["code", "industry"]].copy()
                   if "industry" in perf.columns else pd.DataFrame(columns=["code", "industry"]))
    if "industry" in merged.columns:
        merged = merged.drop(columns=["industry"])
    return merged, industry_df


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
