"""每日增量更新：拉取最新 K 线追加入库。

每天收盘后运行。对库内每只股票，从已存最新日期的次日拉到今天。
重复日期会被 INSERT OR REPLACE 覆盖，可安全重跑。

用法：
    python scripts/update_daily.py --periods daily
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stock_screener.config import REQUEST_SLEEP, ensure_dirs
from stock_screener.datasource import akshare_source as src
from stock_screener.storage import db


def _next_day(date_str: str) -> str:
    """'YYYY-MM-DD' -> 次日 'YYYYMMDD'。"""
    d = datetime.strptime(date_str[:10], "%Y-%m-%d") + timedelta(days=1)
    return d.strftime("%Y%m%d")


def main() -> None:
    ap = argparse.ArgumentParser(description="每日增量更新")
    ap.add_argument("--periods", nargs="+", default=["daily"],
                    choices=["daily", "weekly", "monthly"])
    args = ap.parse_args()

    ensure_dirs()
    db.init_db()

    # 刷新股票列表（捕捉新股 / 改名 / ST 变动）
    try:
        db.save_stock_basic(src.fetch_stock_list())
    except Exception as e:  # noqa: BLE001
        print("刷新股票列表失败:", e)

    today = datetime.today().strftime("%Y%m%d")
    for period in args.periods:
        codes = db.all_codes_with_data(period)
        print(f"[{period}] 更新 {len(codes)} 只股票 ...")
        total = 0
        for i, code in enumerate(codes, 1):
            last = db.latest_date(code, period)
            start = _next_day(last) if last else None
            if start and start > today:
                continue  # 已是最新
            try:
                df = src.fetch_kline(code, period=period, start_date=start, end_date=today)
                total += db.save_kline(df, period=period)
            except Exception as e:  # noqa: BLE001
                print(f"  [{code}] 失败: {e}")
            time.sleep(REQUEST_SLEEP)
        print(f"[{period}] 完成，新增/更新 {total} 条")


if __name__ == "__main__":
    main()
