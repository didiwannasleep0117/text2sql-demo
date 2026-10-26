# MCP 伺服器（`src/text2sql_demo/mcp_server.py`）

[← 回到 README](../README.md)

讓外部 Agent（n8n、Claude、Hermes…）也能查數據。`uv run text2sql-mcp` → `http://127.0.0.1:8002/mcp`（Streamable HTTP）。

| 工具 | 給誰用 | 說明 |
|---|---|---|
| `ask_metrics(question)` | 不想自己寫 SQL 的呼叫端 | 整條本地流程（對照 → 本機 8B 產生 SQL → 試跑修正 → 摘要數字檢查），回傳摘要＋SQL＋表格 |
| `describe_schema()` | 自己寫 SQL 的外部模型 | 資料表、欄位意義、指標公式、資料期間 |
| `resolve_entities(question)` | 同上 | 程式做的代碼／日期對照（跟本地流程用同一套），避免外部模型猜代碼 |
| `run_sql(sql)` | 同上 | 唯讀、只准單一 SELECT、5 秒逾時、最多 500 列；只回原始表格，不做摘要 |
| `calculate(expression)` | 所有呼叫端 | 安全計算機。成長率、差額、佔比交給它算，不要讓模型心算 |

**分工的想法**：比較強的外部模型負責「理解問題、寫 SQL、寫摘要」，容易出錯的部分交給工具：代碼對照、執行防護、計算。

⚠️ **資料敏感度**：低階工具的查詢結果會進到外部模型。示範用假資料沒問題；真實資料要先決定哪些表能給外部模型看（例如只開彙總表、不開明細和個資），敏感的問題走 `ask_metrics` 留在本機模型。

`tests/test_mcp_client.py`：伺服器有啟動時，實際用 MCP client 測工具清單、低階查詢流程、寫入被擋、計算機（共 4 題，沒啟動就跳過）。
