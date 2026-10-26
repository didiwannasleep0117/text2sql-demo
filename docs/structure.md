# 目錄結構

[← 回到 README](../README.md)

```
src/text2sql_demo/
  linker.py     代碼／日期對照（程式）
  schema.py     給模型看的資料表說明、指標公式、內建範例
  agent.py      主流程：產生 SQL → 改寫 → 試跑／修正 → 摘要 → 數字檢查 → 圖表
  db.py         唯讀連線、authorizer、逾時、列數上限
  cli.py        命令列
  mcp_server.py MCP 伺服器（ask_metrics、describe_schema、resolve_entities、run_sql、calculate）
  calc.py       安全計算機
prompts/        正式版 prompt 與範例（＝改進循環選出的 v2b）
app/            Streamlit 介面
eval/           tune.yaml（28 題）、holdout.yaml（17 題）、grade.py、scores.py、latest.json（最新分數）、baseline.json（CI 基準）
harness/        loop.py、candidates/、runs/、scoreboard.csv、EXPERIENCE.md
scripts/        make_fake_db.py、take_screenshots.py、run_eval.py（本機評測）、check_regression.py（CI 回歸檢查）
tests/          單元測試（評分、回歸檢查、安全檢查…；MCP 測試沒開伺服器就跳過）
.github/        workflows/eval-ci.yml（CI）
```
