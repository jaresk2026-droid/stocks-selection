"""更新基本面数据：估值（PE/PB/市值）+ 财务（ROE/EPS/毛利率/净利同比）+ 行业。

数据源 baostock（稳定、不依赖代理）：估值随股价每日变、财务按季更新，可每日跑。
- 估值/市值来自最近一根日线（peTTM/pbMRQ/股本×价）；
- 财务（ROE/EPS/毛利率/净利润同比）来自季频接口，自动取最近已披露报告期；
- 行业为证监会行业分类，一次性全市场拉取并回填 stock_basic。

注：baostock 无「营收同比」字段（留空，相关条件按缺失判 False）；
    概念板块需东方财富，见 scripts/update_sectors.py（网络好时再跑）。

用法：
    python scripts/update_fundamentals.py                 # 全市场，自动取最近报告期
    python scripts/update_fundamentals.py --limit 50      # 先小范围验证
    python scripts/update_fundamentals.py --year 2025 --quarter 4
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stock_screener.config import ensure_dirs
from stock_screener.datasource import baostock_source as bsrc
from stock_screener.storage import db


def main() -> None:
    ap = argparse.ArgumentParser(description="更新基本面数据（baostock）")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 只股票（0=全部）")
    ap.add_argument("--year", type=int, default=None, help="财报年份（与 --quarter 同用）")
    ap.add_argument("--quarter", type=int, default=None, choices=[1, 2, 3, 4],
                    help="财报季度 1-4（缺省自动取最近已披露）")
    args = ap.parse_args()

    ensure_dirs()
    db.init_db()

    basic = db.load_stock_basic()
    if basic.empty:
        print("stock_basic 为空，请先运行 scripts/init_data.py 拉取股票列表。")
        return
    codes = basic["code"].astype(str).str.zfill(6).tolist()
    if args.limit:
        codes = codes[: args.limit]

    report = (args.year, args.quarter) if args.year and args.quarter else None
    print(f"拉取基本面：{len(codes)} 只（数据源 baostock）...")

    def progress(i, total, code):
        if i % 50 == 0 or i == total:
            print(f"  [{i}/{total}] {code}", end="\r")

    funds, industry = bsrc.fetch_fundamentals(codes, report=report, progress=progress)
    print()

    if funds.empty:
        print("未获取到基本面数据（检查网络）。")
        return

    n = db.save_fundamentals(funds)
    rd = "—"
    if "report_date" in funds and funds["report_date"].notna().any():
        rd = funds["report_date"].dropna().iloc[0]
    print(f"已写入基本面 {n} 条，报告期 {rd}")

    m = db.update_industry(industry)
    print(f"回填行业 {m} 只")


if __name__ == "__main__":
    main()
