"""更新基本面数据：估值（PE/PB/市值）+ 业绩（ROE/EPS/营收净利同比/毛利率）。

估值随股价每日变化、业绩按季度更新，因此可每日运行（业绩自动取最近已发布报告期）。
顺带把业绩里的「所处行业」回填到 stock_basic.industry。

用法：
    python scripts/update_fundamentals.py                 # 自动取最近报告期
    python scripts/update_fundamentals.py --report 20240331
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stock_screener.config import ensure_dirs
from stock_screener.datasource import akshare_source as src
from stock_screener.storage import db


def main() -> None:
    ap = argparse.ArgumentParser(description="更新基本面数据")
    ap.add_argument("--report", default=None, help="财报报告期 YYYYMMDD（缺省自动取最近）")
    args = ap.parse_args()

    ensure_dirs()
    db.init_db()

    print("拉取基本面（估值 + 业绩）...")
    funds, industry = src.fetch_fundamentals(report_date=args.report)
    if funds.empty:
        print("未获取到基本面数据（检查网络或报告期）。")
        return

    n = db.save_fundamentals(funds)
    rd = funds["report_date"].dropna().iloc[0] if "report_date" in funds and funds["report_date"].notna().any() else "—"
    print(f"已写入基本面 {n} 条，报告期 {rd}")

    m = db.update_industry(industry)
    print(f"回填行业 {m} 只")


if __name__ == "__main__":
    main()
