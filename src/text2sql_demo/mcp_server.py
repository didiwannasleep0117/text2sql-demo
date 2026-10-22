"""MCP 伺服器：讓外部 Agent（n8n、Claude、Hermes…）查星芽營運數據。

兩種用法：
  高階：ask_metrics(question)  → 整條本地流程（代碼對照 → 本機 8B 產生 SQL → 試跑修正 → 摘要數字檢查）
  低階：describe_schema / resolve_entities / run_sql / calculate
        → 給比較強的外部模型自己寫 SQL。run_sql 一樣唯讀、只准 SELECT、有逾時和列數上限，
          只回原始表格，不做摘要（摘要交給呼叫端，數字請用 calculate 算，不要心算）

啟動：uv run text2sql-mcp   → http://127.0.0.1:8002/mcp（Streamable HTTP）

⚠️ 資料敏感度：用低階工具時，查詢結果會進到外部模型。示範用的是假資料所以沒關係；
   真實公司資料要先確認哪些表可以給外部模型看（例如只開彙總表、不開明細和個資）。
"""
from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

from . import db
from .agent import ask
from .calc import calculate as _calculate
from .linker import TODAY, link
from .schema import SCHEMA

mcp = FastMCP(
    "sprout-metrics",
    instructions="星芽科技（虛構）App 營運數據。問數字先用 resolve_entities 取得代碼和日期，再用 run_sql 查；"
                 "任何計算或比較請用 calculate。不想自己寫 SQL 就用 ask_metrics。",
    host=os.getenv("HOST", "0.0.0.0"),
    port=int(os.getenv("PORT", "8002")),
)


def _rows_json(cols, rows, truncated) -> str:
    return json.dumps({"columns": cols, "rows": rows, "row_count": len(rows), "truncated": truncated},
                      ensure_ascii=False, default=str)


@mcp.tool()
def describe_schema() -> str:
    """回傳資料表、欄位意義、指標公式（ARPDAU、CTR、CPI、留存率…）和資料期間。寫 SQL 前先看這個。"""
    return SCHEMA + f"\n今天日期（資料最新日期）：{TODAY}"


@mcp.tool()
def resolve_entities(question: str) -> str:
    """把問題裡的口語換成資料庫代碼和明確日期（例：記帳→app_id 'SPN'、抖音→channel 'TikTok'、上個月→2026-08-01~2026-08-31）。
    寫 SQL 時請照這些對照用，不要自己猜代碼。"""
    hints = link(question)
    return "\n".join(f"- {h}" for h in hints) if hints else "（問題裡沒有可對照的 App、國家、管道、日期）"


@mcp.tool()
def run_sql(sql: str) -> str:
    """執行一條 SQLite SELECT 查詢，回傳 JSON（columns、rows、row_count、truncated）。
    唯讀；只允許單一 SELECT/WITH；5 秒逾時；最多 500 列。
    注意：SQLite 整數相除會變 0，比率請寫 1.0 * SUM(a) / SUM(b)。"""
    try:
        return _rows_json(*db.run(sql))
    except db.SQLError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def calculate(expression: str) -> str:
    """安全計算機：四則運算、次方、比較、round/min/max/abs。例：(5210.79 - 7560.95) / 7560.95 * 100。
    成長率、差額、佔比這類數字請用它算，不要心算。"""
    return _calculate(expression)


@mcp.tool()
def ask_metrics(question: str) -> str:
    """用中文問營運數據，由伺服器端的本機流程完成：代碼對照 → 產生 SQL → 試跑（出錯自動修正）→ 摘要（數字必須出現在結果裡）。
    回傳 JSON：answer（摘要）、sql、columns、rows、action（sql / clarify / refuse / empty / error）。"""
    r = ask(question)
    return json.dumps({k: r.get(k) for k in ("answer", "action", "sql", "columns", "rows", "hints", "seconds")},
                      ensure_ascii=False, default=str)


# ---------- 一般 HTTP 端點（給 n8n 的 HTTP Request 節點用，不必走 MCP） ----------
_SESSIONS: dict[str, list[dict]] = {}  # sessionId → 最近一題（追問用）


def to_markdown(r: dict, max_rows: int = 15) -> str:
    """把 ask() 的結果排成聊天視窗看得懂的 Markdown：摘要 → 表格 → SQL。"""
    out = [r.get("answer") or ""]
    cols, rows = r.get("columns") or [], r.get("rows") or []
    if rows:
        fmt = lambda v: f"{v:,.4f}".rstrip("0").rstrip(".") if isinstance(v, float) else (  # noqa: E731
            f"{v:,}" if isinstance(v, int) else str(v))
        out.append("| " + " | ".join(cols) + " |\n|" + "---|" * len(cols))
        out[-1] += "".join("\n| " + " | ".join(fmt(v) for v in row) + " |" for row in rows[:max_rows])
        if len(rows) > max_rows:
            out.append(f"（共 {len(rows)} 列，只列前 {max_rows} 列）")
    if r.get("sql"):
        out.append(f"```sql\n{r['sql']}\n```")
    return "\n\n".join(out)


@mcp.custom_route("/ask", methods=["POST"])
async def http_ask(request):
    import anyio
    from starlette.responses import JSONResponse
    body = await request.json()
    q, sid = str(body.get("question", "")).strip(), str(body.get("sessionId", ""))
    hist = _SESSIONS.get(sid) if sid else None
    r = await anyio.to_thread.run_sync(lambda: ask(q, history=hist))
    if sid and r.get("sql"):
        _SESSIONS[sid] = [{"question": q, "sql": r["sql"]}]
    r["markdown"] = to_markdown(r)
    return JSONResponse({k: r.get(k) for k in ("markdown", "answer", "action", "sql", "columns", "rows", "seconds")})


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
