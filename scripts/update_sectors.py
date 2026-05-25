"""更新行业/概念板块成分（用于板块筛选）。

每个板块单独请求一次成分，板块多、较慢，属偶尔更新（成分变动不频繁）。

用法：
    python scripts/update_sectors.py                 # 行业 + 概念
    python scripts/update_sectors.py --types industry
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stock_screener.config import ensure_dirs
from stock_screener.datasource import sectors_source as ss
from stock_screener.storage import db


def main() -> None:
    ap = argparse.ArgumentParser(description="更新板块成分")
    ap.add_argument("--types", nargs="+", default=["industry", "concept"],
                    choices=["industry", "concept"])
    args = ap.parse_args()

    ensure_dirs()
    db.init_db()

    for board_type in args.types:
        print(f"拉取 {board_type} 板块成分 ...")

        def progress(i, total, name):
            print(f"  [{i}/{total}] {name}", end="\r")

        members = ss.fetch_board_members(board_type, progress=progress)
        n = db.save_boards(members, board_type)
        boards = members["board_name"].nunique() if not members.empty else 0
        print(f"\n{board_type}: {boards} 个板块，{n} 条成分记录")


if __name__ == "__main__":
    main()
