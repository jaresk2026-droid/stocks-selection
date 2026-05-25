"""首次全量初始化：建库 + 拉取股票列表 + 历史 K 线。

用法示例：
    # 先小范围验证（只拉前 20 只的日线）
    python scripts/init_data.py --limit 20 --periods daily
    # 全量日/周/月线
    python scripts/init_data.py --periods daily weekly monthly
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stock_screener.config import REQUEST_SLEEP, ensure_dirs
from stock_screener.datasource import akshare_source as src
from stock_screener.storage import db


def main() -> None:
    ap = argparse.ArgumentParser(description="全量初始化历史数据")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 只股票（0=全部）")
    ap.add_argument("--periods", nargs="+", default=["daily"],
                    choices=["daily", "weekly", "monthly"], help="要拉取的周期")
    args = ap.parse_args()

    ensure_dirs()
    db.init_db()

    print("获取股票列表 ...")
    stock_list = src.fetch_stock_list()
    db.save_stock_basic(stock_list)
    codes = stock_list["code"].tolist()
    if args.limit:
        codes = codes[: args.limit]
    print(f"共 {len(codes)} 只股票，周期 {args.periods}")

    for i, code in enumerate(codes, 1):
        for period in args.periods:
            try:
                df = src.fetch_kline(code, period=period)
                n = db.save_kline(df, period=period)
            except Exception as e:  # noqa: BLE001
                print(f"  [{code}] {period} 失败: {e}")
                n = 0
            if period == args.periods[-1]:
                print(f"[{i}/{len(codes)}] {code} {period} {n} 条")
        time.sleep(REQUEST_SLEEP)

    print("初始化完成。数据库:", db.DB_PATH)


if __name__ == "__main__":
    main()
