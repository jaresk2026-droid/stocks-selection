"""baostock 备份数据源：日/周/月 K 线（前复权）。

当主源 akshare（东方财富）网络不稳定时作为回退。baostock 有独立服务器、
不走系统代理，连通性更稳，但仅覆盖沪深，**不含北交所**，也没有基本面/板块数据。

关键差异（务必对齐主源 schema）：
- baostock 成交量 volume 单位是「股」，akshare 是「手」→ 这里统一 /100 转成「手」；
- baostock 代码需带市场前缀（sh./sz.），日期用 YYYY-MM-DD。
"""
from __future__ import annotations

import atexit

import baostock as bs
import pandas as pd

from stock_screener.config import HISTORY_START

# 内部周期 -> baostock frequency
_FREQ = {"daily": "d", "weekly": "w", "monthly": "m"}

_logged_in = False


def _ensure_login() -> None:
    """首次使用时登录 baostock，进程退出时自动登出。"""
    global _logged_in
    if _logged_in:
        return
    res = bs.login()
    if res.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {res.error_code} {res.error_msg}")
    _logged_in = True
    atexit.register(_logout)


def _logout() -> None:
    global _logged_in
    if _logged_in:
        bs.logout()
        _logged_in = False


def _to_bs_code(code: str) -> str | None:
    """6 位代码 -> baostock 带前缀代码。不支持的市场（北交所）返回 None。"""
    code = str(code).zfill(6)
    head = code[0]
    if head in ("6", "9"):          # 沪市主板/科创板/B股
        return f"sh.{code}"
    if head in ("0", "2", "3"):     # 深市主板/创业板/B股
        return f"sz.{code}"
    return None                      # 4/8 北交所等：baostock 不支持


def _fmt_date(yyyymmdd: str) -> str:
    """YYYYMMDD -> YYYY-MM-DD；已是带横线格式则原样返回。"""
    s = str(yyyymmdd)
    return s if "-" in s else f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def fetch_kline(code: str, period: str = "daily", start_date: str | None = None,
                end_date: str | None = None) -> pd.DataFrame:
    """获取单只股票日/周/月 K 线（前复权），返回内部 schema。

    列：code, date, open, high, low, close, volume(手), amount(元)。
    """
    if period not in _FREQ:
        raise ValueError(f"日/周/月周期错误 {period!r}")
    bs_code = _to_bs_code(code)
    if bs_code is None:
        raise ValueError(f"baostock 不支持的市场: {code}")

    _ensure_login()
    start = _fmt_date(start_date or HISTORY_START)
    end = _fmt_date(end_date or pd.Timestamp.today().strftime("%Y%m%d"))
    rs = bs.query_history_k_data_plus(
        bs_code,
        "date,open,high,low,close,volume,amount",
        start_date=start,
        end_date=end,
        frequency=_FREQ[period],
        adjustflag="2",  # 2=前复权
    )
    if rs.error_code != "0":
        raise RuntimeError(f"baostock 查询失败 {code}: {rs.error_code} {rs.error_msg}")

    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    cols = ["date", "open", "high", "low", "close", "volume", "amount"]
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        return pd.DataFrame(
            columns=["code", "date", "open", "high", "low", "close", "volume", "amount"])

    df["code"] = str(code).zfill(6)
    num = ["open", "high", "low", "close", "volume", "amount"]
    df[num] = df[num].apply(pd.to_numeric, errors="coerce")
    df["volume"] = df["volume"] / 100.0  # 股 -> 手，对齐 akshare
    keep = ["code", "date", "open", "high", "low", "close", "volume", "amount"]
    return df[keep].dropna(subset=["close"]).reset_index(drop=True)


# ==================== 基本面（估值 + 财务 + 行业） ====================
# baostock 没有「全市场快照」接口，估值/财务都按个股查询；行业可一次拉全市场。
# 注意单位：baostock 的 roeAvg/gpMargin/npMargin/YOYxx 都是「小数」，
# 这里统一 ×100 转成「百分数」，对齐 conditions.py 里 ROE>10、毛利率>30 的比较口径。

def _rs_to_dicts(rs) -> list[dict]:
    """baostock ResultData -> list[dict]（按 rs.fields 命名）。"""
    fields = rs.fields
    out = []
    while rs.error_code == "0" and rs.next():
        out.append(dict(zip(fields, rs.get_row_data())))
    return out


def _f(d: dict, key: str, scale: float = 1.0):
    """从 dict 取数值，空串/缺失返回 None，可乘系数（如百分数 ×100）。"""
    v = d.get(key)
    if v is None or v == "":
        return None
    try:
        return float(v) * scale
    except (TypeError, ValueError):
        return None


def fetch_industry_all() -> pd.DataFrame:
    """一次性拉全市场行业分类（证监会行业）。返回 code, industry。"""
    _ensure_login()
    rs = bs.query_stock_industry()
    rows = _rs_to_dicts(rs)
    if not rows:
        return pd.DataFrame(columns=["code", "industry"])
    df = pd.DataFrame(rows)
    df["code"] = df["code"].str.split(".").str[-1].str.zfill(6)
    df = df.rename(columns={"industry": "industry"})[["code", "industry"]]
    return df[df["industry"].astype(str) != ""].reset_index(drop=True)


# 报告期探测用的候选 (year, quarter)，由近及远
def _report_candidates(n: int = 6) -> list[tuple[int, int]]:
    today = pd.Timestamp.today()
    cands = []
    y, q = today.year, (today.month - 1) // 3 + 1
    for _ in range(n):
        q -= 1
        if q == 0:
            q = 4
            y -= 1
        cands.append((y, q))
    return cands


def detect_report(sample_code: str = "600000") -> tuple[int, int] | None:
    """用一只样本股探测「最近已披露」的报告期 (year, quarter)。"""
    _ensure_login()
    bs_code = _to_bs_code(sample_code) or "sh.600000"
    for year, quarter in _report_candidates():
        rs = bs.query_profit_data(code=bs_code, year=year, quarter=quarter)
        if _rs_to_dicts(rs):
            return year, quarter
    return None


def _fetch_valuation_one(bs_code: str) -> dict:
    """取单只最新估值：close, pe, pb, bps（来自最近一根日线）。

    market_cap 不在日线里——股本(totalShare/liqaShare)来自财务接口，
    由 fetch_fundamentals 用 close × 股本算市值。
    """
    end = pd.Timestamp.today()
    start = end - pd.Timedelta(days=20)
    rs = bs.query_history_k_data_plus(
        bs_code,
        "date,close,peTTM,pbMRQ",  # 日线仅有这些估值字段
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
        frequency="d", adjustflag="3",  # 估值用不复权价（市值口径）
    )
    rows = _rs_to_dicts(rs)
    if not rows:
        return {}
    last = rows[-1]
    close = _f(last, "close")
    pb = _f(last, "pbMRQ")
    return {
        "close": close,
        "pe": _f(last, "peTTM"),
        "pb": pb,
        "bps": close / pb if close and pb else None,  # 每股净资产 = 价/市净率
    }


def fetch_fundamentals(codes: list[str], report: tuple[int, int] | None = None,
                       progress=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """逐只拉取 baostock 基本面，组装为对齐 db.FUNDAMENTAL_COLUMNS 的表。

    返回 (fundamentals_df, industry_df)。
    - report: (year, quarter)，缺省自动探测最近已披露报告期；
    - revenue_yoy（营收同比）baostock 无对应字段，留空。
    """
    _ensure_login()
    industry_df = fetch_industry_all()

    if report is None:
        report = detect_report()
    year, quarter = report if report else (None, None)
    report_date = None
    rows = []
    total = len(codes)
    for i, code in enumerate(codes, 1):
        bs_code = _to_bs_code(code)
        if bs_code is None:  # 北交所等：baostock 不支持，跳过
            if progress:
                progress(i, total, code)
            continue
        rec = {"code": str(code).zfill(6)}
        close = None
        try:
            val = _fetch_valuation_one(bs_code)
            close = val.pop("close", None)
            rec.update(val)  # pe, pb, bps
        except Exception:  # noqa: BLE001 - 个股失败不中断
            pass
        if year:
            try:
                prof = _rs_to_dicts(bs.query_profit_data(code=bs_code, year=year, quarter=quarter))
                if prof:
                    p = prof[0]
                    rec["roe"] = _f(p, "roeAvg", 100)          # 小数 -> %
                    rec["gross_margin"] = _f(p, "gpMargin", 100)
                    rec["eps"] = _f(p, "epsTTM")
                    rec["profit"] = _f(p, "netProfit")
                    rec["revenue"] = _f(p, "MBRevenue")        # 主营收入
                    # 市值 = 最新收盘 × 股本（股本来自财务接口）
                    ts, ls = _f(p, "totalShare"), _f(p, "liqaShare")
                    if close and ts:
                        rec["total_mv"] = close * ts
                    if close and ls:
                        rec["circ_mv"] = close * ls
                    if report_date is None and p.get("statDate"):
                        report_date = p["statDate"].replace("-", "")
                    rec["report_date"] = p.get("statDate", "").replace("-", "") or None
                grow = _rs_to_dicts(bs.query_growth_data(code=bs_code, year=year, quarter=quarter))
                if grow:
                    rec["profit_yoy"] = _f(grow[0], "YOYNI", 100)  # 净利润同比 小数 -> %
            except Exception:  # noqa: BLE001
                pass
        rows.append(rec)
        if progress:
            progress(i, total, code)

    funds = pd.DataFrame(rows)
    # 营收同比 baostock 无 -> 占位空列，保证 schema 完整
    for col in ("revenue_yoy",):
        if col not in funds.columns:
            funds[col] = None
    return funds, industry_df
