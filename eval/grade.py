"""評分：比對「執行結果」，不比對 SQL 字串（同一個答案有很多種寫法）。

- 列數要一樣
- 標準答案的每一個數字欄，模型的結果裡要有一欄數值相同（排序後逐一比，容許四捨五入誤差；比率也接受 ×100 的百分比）
- 標準答案的名稱欄（App、國家、管道…）也要對得上；日期／月份欄只看列數，不比格式（'2026-08' 和 '08' 都算）
- compare: first → 只比模型結果的第一列（「哪個最高」這類題目）
"""
from __future__ import annotations

import re
import sqlite3

from text2sql_demo.db import DB_PATH

_DATEISH = re.compile(r"^\d{4}(-\d{2}){0,2}$|^\d{1,2}$")


def gold_result(sql: str):
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    try:
        cur = con.execute(sql)
        return [c[0] for c in cur.description], [list(r) for r in cur.fetchall()]
    finally:
        con.close()


def _names() -> dict[str, str]:
    """代碼 → 名稱（'US' → '美國'、'SPN' → '芽芽記帳'、短網址 → 活動名稱）。回答代碼也算答對。"""
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    try:
        return dict(con.execute("SELECT country_code, country_name FROM countries UNION ALL SELECT app_id, app_name FROM apps "
                                "UNION ALL SELECT short_code, campaign_name FROM ad_campaigns"))
    finally:
        con.close()


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.011, abs(b) * 0.002)


def _num_col_match(g: list, p: list) -> bool:
    if any(not isinstance(v, (int, float)) for v in p if v is not None):
        return False
    gs, ps = sorted(float(v or 0) for v in g), sorted(float(v or 0) for v in p)
    return all(_close(a, b) for a, b in zip(ps, gs)) or all(_close(a, b * 100) for a, b in zip(ps, gs))


def compare(item: dict, cols, rows) -> tuple[bool, str]:
    gcols, grows = gold_result(item["gold"])
    if item.get("compare") == "first":
        rows = rows[:1]
    if len(rows) != len(grows):
        return False, f"列數不同（模型 {len(rows)}，標準 {len(grows)}）"
    if not rows:
        return True, "都沒有資料"
    pcols = list(zip(*rows))
    for j, gc in enumerate(zip(*grows)):
        gc = list(gc)
        if all(isinstance(v, (int, float)) or v is None for v in gc):
            if not any(_num_col_match(gc, list(pc)) for pc in pcols):
                return False, f"數值欄 {gcols[j]} 對不上（標準 {gc[:3]}…）"
        elif all(isinstance(v, str) and _DATEISH.match(v) for v in gc):
            continue
        else:
            target = sorted(map(str, gc))
            nm = _names()
            if not any(sorted(nm.get(str(v), str(v)) for v in pc) == target for pc in pcols):
                return False, f"名稱欄 {gcols[j]} 對不上（標準 {target[:3]}…）"
    return True, "結果一致"


def grade(item: dict, res: dict) -> tuple[bool, str]:
    kind = item.get("kind", "sql")
    act = res.get("action")
    if kind == "refuse":
        return act == "refuse", f"應拒答（實際 {act}）"
    if kind == "clarify":
        ok = act in ("clarify", "empty")
        return ok, f"應追問或說明查不到（實際 {act}）"
    if kind == "empty":
        ok = act in ("empty", "clarify")
        return ok, f"應回查無資料（實際 {act}）"
    if act != "sql":
        return False, f"應查詢（實際 {act}：{res.get('answer', '')[:40]}）"
    ok, why = compare(item, res["columns"], res["rows"])
    if ok and res.get("summary_fallback"):
        why += "（摘要被擋，只給表格）"
    return ok, why
