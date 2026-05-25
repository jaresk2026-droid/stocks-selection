"""行业/概念板块采集：板块列表 + 各板块成分股（来自东方财富）。

注意：每个板块要单独请求一次成分，板块多（行业约 80+、概念约 400+），
全量拉取较慢，属于「偶尔更新」操作，不必每天跑。
"""
from __future__ import annotations

import time

import akshare as ak
import pandas as pd

from stock_screener.config import REQUEST_SLEEP
from stock_screener.datasource.akshare_source import _retry

# 板块类型 -> (列表函数, 成分函数)
_BOARD_API = {
    "industry": (ak.stock_board_industry_name_em, ak.stock_board_industry_cons_em),
    "concept": (ak.stock_board_concept_name_em, ak.stock_board_concept_cons_em),
}


def fetch_board_list(board_type: str) -> pd.DataFrame:
    """获取板块列表。返回含「板块名称」列的 DataFrame。"""
    list_fn, _ = _BOARD_API[board_type]
    return _retry(list_fn)


def fetch_board_members(board_type: str, sleep: float = REQUEST_SLEEP,
                        progress=None) -> pd.DataFrame:
    """遍历某类型所有板块，拉取成分股。

    返回列：code, board_name（board_type 由调用方写库时附加）。
    progress: 可选回调 progress(i, total, board_name)。
    """
    _, cons_fn = _BOARD_API[board_type]
    boards = fetch_board_list(board_type)
    names = boards["板块名称"].tolist()
    frames = []
    total = len(names)
    for i, name in enumerate(names, 1):
        try:
            cons = _retry(cons_fn, symbol=name)
            code_col = "代码" if "代码" in cons.columns else cons.columns[1]
            sub = pd.DataFrame({"code": cons[code_col].astype(str).str.zfill(6),
                                "board_name": name})
            frames.append(sub)
        except Exception:  # noqa: BLE001 - 个别板块失败跳过
            pass
        if progress:
            progress(i, total, name)
        time.sleep(sleep)
    if not frames:
        return pd.DataFrame(columns=["code", "board_name"])
    return pd.concat(frames, ignore_index=True)
