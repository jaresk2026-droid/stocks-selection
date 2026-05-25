"""全市场选股：遍历库内股票，逐条评估条件，返回命中列表。"""
from __future__ import annotations

from typing import Sequence

import pandas as pd

from stock_screener.engine.conditions import Condition, Context
from stock_screener.indicators import add_indicators
from stock_screener.storage import db

# 结果中展示的技术面快照列
_TECH_SNAPSHOT = ["close", "MACD_DIF", "MACD_DEA", "RSI", "KDJ_K", "KDJ_D",
                  "MA5", "MA20", "VOL_RATIO"]
# 结果中展示的基本面快照列
_FUND_SNAPSHOT = ["pe", "pb", "roe", "revenue_yoy", "profit_yoy", "gross_margin"]


def screen(conditions: Sequence[Condition], period: str = "daily",
           logic: str = "and", exclude_st: bool = True,
           min_bars: int = 60) -> pd.DataFrame:
    """对全市场执行选股。

    参数：
        conditions: 条件列表（技术面 + 基本面混合）。
        period:     周期（daily/weekly/monthly）。
        logic:      'and'=全部满足，'or'=任一满足。
        exclude_st: 是否剔除 ST 股。
        min_bars:   K 线根数不足则跳过（指标不可靠）。
    返回：命中股票 DataFrame（含代码、名称、行业、命中条件、技术面 + 基本面快照）。
    """
    basic = db.load_stock_basic().set_index("code")
    fundamentals = db.load_fundamentals()
    codes = db.all_codes_with_data(period)
    rows = []
    for code in codes:
        if exclude_st and code in basic.index and basic.loc[code, "is_st"] == 1:
            continue
        kl = db.load_kline(code, period)
        if len(kl) < min_bars:
            continue
        ctx = Context(df=add_indicators(kl), fund=fundamentals.get(code, {}))
        matched = [c.name for c in conditions if c(ctx)]
        hit = (len(matched) == len(conditions)) if logic == "and" else (len(matched) > 0)
        if not hit:
            continue
        last = ctx.df.iloc[-1]
        rec = {
            "code": code,
            "name": basic.loc[code, "name"] if code in basic.index else "",
            "industry": basic.loc[code, "industry"] if code in basic.index else "",
            "date": last["date"],
            "命中条件": "+".join(matched),
        }
        for col in _TECH_SNAPSHOT:
            rec[col] = round(float(last[col]), 3) if pd.notna(last.get(col)) else None
        for col in _FUND_SNAPSHOT:
            v = ctx.fund.get(col)
            rec[col] = round(float(v), 3) if v is not None and pd.notna(v) else None
        rows.append(rec)

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values("VOL_RATIO", ascending=False).reset_index(drop=True)
    return result
