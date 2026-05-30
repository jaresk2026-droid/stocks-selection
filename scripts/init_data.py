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
from stock_screener.datasource import baostock_source as bsrc
from stock_screener.storage import db


def main() -> None:
    ap = argparse.ArgumentParser(description="全量初始化历史数据")
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 只股票（0=全部）")
    ap.add_argument("--periods", nargs="+", default=["daily"],
                    choices=["daily", "weekly", "monthly"], help="要拉取的周期")
    ap.add_argument("--source", default="baostock", choices=["baostock", "akshare"],
                    help="K线数据源：baostock 直连稳定(默认)；akshare 走东方财富(本机不可用)+baostock 回退")
    ap.add_argument("--use-db", action="store_true",
                    help="跳过 akshare 股票列表拉取，直接用库里 stock_basic（避免 akshare 内部 multiprocessing 派生子进程导致 baostock 并发死锁）")
    ap.add_argument("--skip-existing", action="store_true",
                    help="跳过该周期已有数据的股票（断点续传，重新启动不浪费时间）")
    args = ap.parse_args()
    # 东方财富在本机不可用，默认直接用 baostock，避免逐只先失败再回退的长时间等待
    fetch_kline = bsrc.fetch_kline if args.source == "baostock" else src.fetch_kline

    ensure_dirs()
    db.init_db()

    if args.use_db:
        print("使用库内 stock_basic（跳过 akshare 列表拉取）...")
        basic = db.load_stock_basic()
        if basic.empty:
            print("stock_basic 为空，去掉 --use-db 重新跑以拉股票列表。")
            return
        codes = basic["code"].astype(str).str.zfill(6).tolist()
    else:
        print("获取股票列表 ...")
        stock_list = src.fetch_stock_list()
        db.save_stock_basic(stock_list)
        codes = stock_list["code"].tolist()
    if args.limit:
        codes = codes[: args.limit]
    print(f"共 {len(codes)} 只股票，周期 {args.periods}")

    # 断点续传：先建好每个周期"已有数据的 code 集合"，循环里 O(1) 跳过
    existing = {p: set(db.all_codes_with_data(p)) for p in args.periods} if args.skip_existing else {}

    for i, code in enumerate(codes, 1):
        for period in args.periods:
            if args.skip_existing and code in existing.get(period, set()):
                if period == args.periods[-1]:
                    print(f"[{i}/{len(codes)}] {code} {period} 跳过(已存在)")
                continue
            try:
                df = fetch_kline(code, period=period)
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
