"""資料庫：唯讀連線、只准 SELECT、逾時中止、限制回傳列數。"""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("DB_PATH", ROOT / "data" / "sprout_metrics.db"))
MAX_ROWS = int(os.getenv("MAX_ROWS", "500"))
TIMEOUT_SEC = float(os.getenv("SQL_TIMEOUT_SEC", "5"))

_ALLOWED = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}


def _authorizer(action, *_):
    # 第二道防線：就算 SQL 騙過字串檢查，資料庫層也只允許讀取
    return sqlite3.SQLITE_OK if action in _ALLOWED else sqlite3.SQLITE_DENY


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True, check_same_thread=False)
    con.set_authorizer(_authorizer)
    return con


class SQLError(Exception):
    pass


def check_sql(sql: str) -> str:
    s = sql.strip().rstrip(";").strip()
    if ";" in s:
        raise SQLError("一次只能執行一條 SQL")
    head = s.split(None, 1)[0].upper() if s else ""
    if head not in ("SELECT", "WITH"):
        raise SQLError("只允許 SELECT 查詢")
    return s


def run(sql: str) -> tuple[list[str], list[tuple], bool]:
    """回傳 (欄位, 資料列, 是否被截斷)。錯誤會丟 SQLError（訊息會回饋給模型修正）。"""
    s = check_sql(sql)
    con = connect()
    deadline = time.monotonic() + TIMEOUT_SEC
    con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
    try:
        cur = con.execute(s)
        cols = [c[0] for c in cur.description or []]
        rows = cur.fetchmany(MAX_ROWS + 1)
    except sqlite3.Error as e:
        msg = str(e)
        if "interrupted" in msg:
            msg = f"查詢超過 {TIMEOUT_SEC:g} 秒被中止，請縮小範圍或改用彙總"
        raise SQLError(msg) from None
    finally:
        con.close()
    return cols, rows[:MAX_ROWS], len(rows) > MAX_ROWS
