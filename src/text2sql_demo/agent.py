"""Text-to-SQL 查詢流程（每一步都可以用環境變數開關，方便改進循環比較）。

問題 → ① 代碼／日期對照（程式）→ ② 產生 SQL（LLM）→ ③ 安全檢查＋試跑（程式）
     → 有錯：把錯誤訊息回饋給 LLM 修正（最多 REPAIR_TRIES 次）
     → 查無資料：不回答 0，請使用者確認條件
     → ④ 摘要（LLM）→ ⑤ 摘要數字檢查：摘要裡的數字必須出現在查詢結果，否則重寫或只給表格
     → ⑥ 圖表（程式依欄位型態決定）
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import httpx

from . import db
from .linker import TODAY, link
from .schema import FEW_SHOTS, SCHEMA

ROOT = Path(__file__).resolve().parents[2]
OLLAMA = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.getenv("MODEL", "qwen3:8b")


def _env(k: str, d: str) -> str:
    return os.getenv(k, d)


def cfg() -> dict:
    """每次呼叫重新讀環境變數，改進循環換候選時不用重啟。"""
    return {
        "LINKER": _env("LINKER", "1") == "1",
        "FEWSHOT": _env("FEWSHOT", "1") == "1",
        "REPAIR_TRIES": int(_env("REPAIR_TRIES", "2")),
        "EMPTY_CHECK": _env("EMPTY_CHECK", "1") == "1",
        "EMPTY_RETRY": _env("EMPTY_RETRY", "1") == "1",
        "SUMMARY_CHECK": _env("SUMMARY_CHECK", "1") == "1",
        "THINK": _env("THINK", "0") == "1",
        "SQL_FIXUPS": _env("SQL_FIXUPS", "1") == "1",
        "FEWSHOT_FILE": _env("FEWSHOT_FILE", str(ROOT / "prompts" / "fewshots.yaml")),
        "SQL_PROMPT": Path(_env("SQL_PROMPT_FILE", str(ROOT / "prompts" / "sql_system.md"))).read_text(encoding="utf-8"),
        "SUM_PROMPT": Path(_env("SUMMARY_PROMPT_FILE", str(ROOT / "prompts" / "summary_system.md"))).read_text(encoding="utf-8"),
    }


_SQL_FORMAT = {"type": "object", "properties": {
    "action": {"type": "string", "enum": ["sql", "clarify", "refuse"]},
    "sql": {"type": "string"}, "message": {"type": "string"}}, "required": ["action"]}


def _chat(messages: list[dict], think: bool, fmt=None, timeout=180) -> str:
    body = {"model": MODEL, "messages": messages, "stream": False, "think": think,
            "options": {"temperature": 0, "num_ctx": 8192}}
    if fmt:
        body["format"] = fmt
    r = httpx.post(f"{OLLAMA}/api/chat", json=body, timeout=timeout)
    r.raise_for_status()
    return r.json()["message"]["content"]


def _parse(txt: str) -> dict:
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", txt, re.S)
        return json.loads(m.group(0)) if m else {"action": "clarify", "message": txt.strip()}


def _table_md(cols, rows, limit=30) -> str:
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join("" if v is None else str(v) for v in r) + " |" for r in rows[:limit]]
    if len(rows) > limit:
        out.append(f"（共 {len(rows)} 列，只列前 {limit} 列）")
    return "\n".join(out)


# ---------- SQL 改寫（程式修，不靠模型記得） ----------
_INT_DIV = re.compile(r"(?<![\d.]\s\*\s)(?<!1\.0\*)(?<!\* )\b(SUM|COUNT)\(([^()]*)\)\s*/\s*(?=(?:SUM|COUNT)\()", re.I)


def fix_int_division(sql: str) -> str:
    """SQLite 整數相除會無條件捨去成 0：SUM(a) / SUM(b) → 1.0 * SUM(a) / SUM(b)。已經乘過 1.0 的不重複改。"""
    return _INT_DIV.sub(lambda m: f"1.0 * {m.group(1)}({m.group(2)}) / ", sql)


# ---------- 摘要數字檢查 ----------
_NUM = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?%?")


def _allowed_values(question: str, sql: str, rows) -> list[float]:
    vals = []
    for r in rows:
        for v in r:
            if isinstance(v, (int, float)):
                vals += [float(v), float(v) * 100]  # 比率可以寫成百分比
            elif isinstance(v, str):
                vals += [float(x) for x in re.findall(r"\d+(?:\.\d+)?", v)]
    vals += [float(x) for x in re.findall(r"\d+(?:\.\d+)?", question + " " + sql)]
    return vals


def unsupported_numbers(summary: str, question: str, sql: str, rows) -> list[str]:
    """摘要裡每個數字都要能在結果（或問題、SQL）找到，容許照顯示的位數四捨五入。"""
    vals = _allowed_values(question, sql, rows)
    bad = []
    for tok in _NUM.findall(summary):
        n = tok.replace(",", "").rstrip("%")
        try:
            f = float(n)
        except ValueError:
            continue
        if f.is_integer() and (abs(f) <= 12 or f in (2025, 2026)):  # 月份、名次、年份這類小數字放過
            continue
        dec = len(n.split(".")[1]) if "." in n else 0
        tol = 0.5 * 10 ** -dec + 1e-9
        if not any(abs(abs(f) - abs(v)) <= tol for v in vals):
            bad.append(tok)
    return bad


# ---------- 圖表 ----------
_DATE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")


def chart_spec(cols, rows) -> dict | None:
    if len(rows) < 2 or len(cols) < 2:
        return None
    num = [i for i, c in enumerate(cols) if all(isinstance(r[i], (int, float)) or r[i] is None for r in rows)]
    txt = [i for i in range(len(cols)) if i not in num]
    if not num or not txt:
        return None
    x = txt[0]
    if all(isinstance(r[x], str) and _DATE.match(r[x]) for r in rows):
        return {"type": "line", "x": cols[x], "y": [cols[i] for i in num], "series": [cols[i] for i in txt[1:2]]}
    if len(rows) <= 30:
        return {"type": "bar", "x": cols[x], "y": [cols[i] for i in num[:2]], "series": [cols[i] for i in txt[1:2]]}
    return None


# ---------- 主流程 ----------
def ask(question: str, history: list[dict] | None = None, verbose: bool = False) -> dict:
    c = cfg()
    t0 = time.time()
    res = {"question": question, "hints": [], "sql": None, "columns": [], "rows": [], "truncated": False,
           "action": None, "answer": "", "chart": None, "errors": [], "repairs": 0,
           "summary_retry": False, "summary_fallback": False}
    hints = link(question) if c["LINKER"] else []
    res["hints"] = hints
    user = [f"今天日期：{TODAY}（資料最新日期）"]
    if hints:
        user.append("代碼與日期對照（程式查好的，照用）：\n" + "\n".join(f"- {h}" for h in hints))
    if history:
        last = history[-1]
        user.append(f"上一題：{last['question']}\n上一題的 SQL：\n{last.get('sql') or '（無）'}\n"
                    "這一題可能是追問，沒提到的條件沿用上一題。")
    user.append(f"問題：{question}")
    sys_msg = c["SQL_PROMPT"] + "\n\n資料表：\n" + SCHEMA
    if c["FEWSHOT"]:
        shots = FEW_SHOTS
        if c["FEWSHOT_FILE"]:
            import yaml
            shots = [(x["q"], x["sql"]) for x in yaml.safe_load(Path(c["FEWSHOT_FILE"]).read_text(encoding="utf-8"))]
        sys_msg += "\n範例：\n" + "\n\n".join(f"問：{q}\nSQL：\n{s}" for q, s in shots)
    msgs = [{"role": "system", "content": sys_msg}, {"role": "user", "content": "\n\n".join(user)}]

    out = _parse(_chat(msgs, c["THINK"], _SQL_FORMAT))
    for attempt in range(c["REPAIR_TRIES"] + 2):
        res["action"] = out.get("action")
        if out.get("action") != "sql" or not out.get("sql"):
            res["answer"] = out.get("message") or ("抱歉，我只能回答星芽科技的營運數據問題。" if out.get("action") == "refuse"
                                                  else "這個問題需要更多條件才能查，可以再說清楚一點嗎？")
            if out.get("action") == "sql":
                res["action"] = "clarify"
            break
        res["sql"] = out["sql"].strip()
        if c["SQL_FIXUPS"]:
            fixed = fix_int_division(res["sql"])
            if fixed != res["sql"]:
                res["fixups"] = res.get("fixups", 0) + 1
                res["sql"] = fixed
        try:
            cols, rows, trunc = db.run(res["sql"])
        except db.SQLError as e:
            res["errors"].append(str(e))
            if verbose:
                print("  SQL 錯誤：", e)
            if res["repairs"] >= c["REPAIR_TRIES"]:
                res["action"] = "error"
                res["answer"] = "抱歉，這題我產生的查詢一直失敗，可以換個說法再問一次嗎？"
                break
            res["repairs"] += 1
            msgs += [{"role": "assistant", "content": json.dumps(out, ensure_ascii=False)},
                     {"role": "user", "content": f"這條 SQL 執行失敗：{e}\n請修正後重新輸出 JSON。"}]
            out = _parse(_chat(msgs, c["THINK"], _SQL_FORMAT))
            continue
        res.update(columns=cols, rows=[list(r) for r in rows], truncated=trunc)
        empty = not rows or all(v is None for r in rows for v in r)
        if empty and c["EMPTY_RETRY"] and not res.get("empty_retry"):
            # 查無資料先別急著回「沒資料」：請模型檢查一次 JOIN 和條件（常見錯：JOIN 錯欄位、自己加了問題沒說的日期）
            res["empty_retry"] = True
            msgs += [{"role": "assistant", "content": json.dumps(out, ensure_ascii=False)},
                     {"role": "user", "content": "這條 SQL 查無資料（結果是空的或 NULL）。請逐一檢查：JOIN 的欄位是否對應正確、"
                                                 "有沒有加了問題沒提到的條件（例如日期）、代碼是否照對照表。"
                                                 "有錯就輸出修正後的 JSON；確定條件都正確，就輸出同一條 SQL。"}]
            out2 = _parse(_chat(msgs, c["THINK"], _SQL_FORMAT))
            if out2.get("action") == "sql" and out2.get("sql") and out2["sql"].strip() != res["sql"]:
                out = out2
                continue
        if empty and c["EMPTY_CHECK"]:
            res["action"] = "empty"
            res["answer"] = ("查無資料。可能是條件太窄（例如該 App 那段期間還沒上架、廣告沒有投放在那個國家），"
                             "可以確認一下 App、國家和日期嗎？資料期間是 2026-04-01 ~ 2026-09-30。")
            break
        res["answer"] = _summarize(c, question, res, verbose)
        res["chart"] = chart_spec(cols, rows)
        break
    if not res["answer"]:
        res["action"] = "error"
        res["answer"] = "抱歉，這題我查不出可靠的結果，可以換個說法再問一次嗎？"
    res["seconds"] = round(time.time() - t0, 1)
    return res


def _summarize(c: dict, question: str, res: dict, verbose: bool) -> str:
    table = _table_md(res["columns"], res["rows"])
    msgs = [{"role": "system", "content": c["SUM_PROMPT"]},
            {"role": "user", "content": f"問題：{question}\n\n查詢結果：\n{table}"}]
    s = _chat(msgs, False).strip()
    if not c["SUMMARY_CHECK"]:
        return s
    bad = unsupported_numbers(s, question, res["sql"] or "", res["rows"])
    if bad:
        if verbose:
            print("  摘要有表格沒有的數字：", bad)
        res["summary_retry"] = True
        msgs += [{"role": "assistant", "content": s},
                 {"role": "user", "content": f"摘要裡的 {', '.join(bad)} 在查詢結果表格裡找不到。"
                                             "請重寫，只能用表格裡出現的數字。"}]
        s = _chat(msgs, False).strip()
        if unsupported_numbers(s, question, res["sql"] or "", res["rows"]):
            res["summary_fallback"] = True
            s = "查詢結果如下表。"
    return s
