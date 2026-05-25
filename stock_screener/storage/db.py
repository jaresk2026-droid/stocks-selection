"""SQLite 读写：基础信息、行业板块、日/周/月 K 线。

设计要点：
- K 线表用 (code, date) 作主键，重复写入自动覆盖（INSERT OR REPLACE），
  因此增量更新可以安全地重跑当天数据。
- 周期 daily / weekly / monthly 共用同一套表结构，按表名区分。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

import pandas as pd

from stock_screener.config import DB_PATH, ensure_dirs

# K 线周期 -> 表名
KLINE_TABLES = {"daily": "kline_daily", "weekly": "kline_weekly", "monthly": "kline_monthly"}

# K 线表统一列
KLINE_COLUMNS = ["code", "date", "open", "high", "low", "close", "volume", "amount"]


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """打开数据库连接（自动建目录、提交、关闭）。"""
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """创建所有表（已存在则跳过）。"""
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_basic (
                code       TEXT PRIMARY KEY,   -- 6 位代码，如 000001
                name       TEXT,
                list_date  TEXT,               -- 上市日期 YYYYMMDD
                is_st      INTEGER DEFAULT 0,   -- 1=ST/退市风险
                industry   TEXT                 -- 所属行业（来自板块映射）
            )
            """
        )
        for table in KLINE_TABLES.values():
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    code   TEXT NOT NULL,
                    date   TEXT NOT NULL,       -- YYYY-MM-DD
                    open   REAL,
                    high   REAL,
                    low    REAL,
                    close  REAL,
                    volume REAL,                -- 成交量（手）
                    amount REAL,                -- 成交额（元）
                    PRIMARY KEY (code, date)
                )
                """
            )
            cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_date ON {table}(date)")


def _table_for(period: str) -> str:
    if period not in KLINE_TABLES:
        raise ValueError(f"未知周期 {period!r}，可选 {list(KLINE_TABLES)}")
    return KLINE_TABLES[period]


# ---------------- 基础信息 ----------------

def save_stock_basic(df: pd.DataFrame) -> int:
    """写入/更新股票基础信息表。df 需含列：code,name,list_date,is_st,industry。"""
    cols = ["code", "name", "list_date", "is_st", "industry"]
    df = df.reindex(columns=cols)
    with connect() as conn:
        df.to_sql("_tmp_basic", conn, if_exists="replace", index=False)
        conn.execute(
            f"""
            INSERT INTO stock_basic ({','.join(cols)})
            SELECT {','.join(cols)} FROM _tmp_basic
            WHERE true
            ON CONFLICT(code) DO UPDATE SET
                name=excluded.name,
                list_date=excluded.list_date,
                is_st=excluded.is_st,
                industry=excluded.industry
            """
        )
        conn.execute("DROP TABLE _tmp_basic")
    return len(df)


def load_stock_basic() -> pd.DataFrame:
    """读取股票基础信息表。"""
    with connect() as conn:
        return pd.read_sql("SELECT * FROM stock_basic", conn)


# ---------------- K 线 ----------------

def save_kline(df: pd.DataFrame, period: str = "daily") -> int:
    """写入 K 线（重复 (code,date) 覆盖）。df 需含 KLINE_COLUMNS。"""
    table = _table_for(period)
    df = df.reindex(columns=KLINE_COLUMNS)
    if df.empty:
        return 0
    rows = [tuple(r) for r in df.itertuples(index=False, name=None)]
    placeholders = ",".join(["?"] * len(KLINE_COLUMNS))
    with connect() as conn:
        conn.executemany(
            f"INSERT OR REPLACE INTO {table} ({','.join(KLINE_COLUMNS)}) VALUES ({placeholders})",
            rows,
        )
    return len(rows)


def load_kline(code: str, period: str = "daily") -> pd.DataFrame:
    """读取单只股票某周期的全部 K 线，按日期升序。"""
    table = _table_for(period)
    with connect() as conn:
        df = pd.read_sql(
            f"SELECT * FROM {table} WHERE code=? ORDER BY date ASC",
            conn,
            params=(code,),
        )
    return df


def latest_date(code: str, period: str = "daily") -> Optional[str]:
    """返回某股票某周期已存的最新日期（YYYY-MM-DD），无数据返回 None。"""
    table = _table_for(period)
    with connect() as conn:
        cur = conn.execute(f"SELECT MAX(date) FROM {table} WHERE code=?", (code,))
        row = cur.fetchone()
    return row[0] if row and row[0] else None


def all_codes_with_data(period: str = "daily") -> list[str]:
    """返回某周期表中已有数据的股票代码列表。"""
    table = _table_for(period)
    with connect() as conn:
        cur = conn.execute(f"SELECT DISTINCT code FROM {table}")
        return [r[0] for r in cur.fetchall()]
