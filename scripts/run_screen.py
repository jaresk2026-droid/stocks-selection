"""阶段 1 MVP 选股：用一个内置策略筛选全市场，打印并导出 Excel。

内置策略（示例，可在下方 build_conditions 中修改）：
    MACD 金叉 + 量比 > 1.5 + 均线多头排列

用法：
    python scripts/run_screen.py
    python scripts/run_screen.py --period daily --logic and
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from stock_screener.config import OUTPUT_DIR, ensure_dirs
from stock_screener.engine import conditions as C
from stock_screener.engine import screen


def build_conditions() -> list:
    """在这里定义/修改你的选股条件（技术面 + 基本面可混合）。"""
    return [
        # 技术面
        C.macd_golden_cross(),
        C.volume_ratio_above(1.5),
        C.ma_bullish(),
        # 基本面（需先运行 update_fundamentals.py；未拉基本面时这些条件恒为 False）
        C.roe_above(10),
        C.profit_yoy_above(20),
        C.pe_below(50),
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description="运行选股")
    ap.add_argument("--period", default="daily", choices=["daily", "weekly", "monthly"])
    ap.add_argument("--logic", default="and", choices=["and", "or"])
    ap.add_argument("--top", type=int, default=50, help="控制台预览前 N 条")
    args = ap.parse_args()

    ensure_dirs()
    conds = build_conditions()
    print("选股条件:", " {} ".format(args.logic.upper()).join(c.name for c in conds))

    result = screen(conds, period=args.period, logic=args.logic)
    print(f"\n命中 {len(result)} 只股票")
    if result.empty:
        print("无符合条件的股票（或数据库为空，请先运行 init_data.py）。")
        return

    with pd.option_context("display.max_rows", args.top, "display.width", 200):
        print(result.head(args.top).to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"screen_{args.period}_{stamp}.xlsx"
    result.to_excel(out, index=False)
    print("\n已导出:", out)


if __name__ == "__main__":
    main()
