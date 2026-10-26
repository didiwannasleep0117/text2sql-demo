# 評測與 CI

[← 回到 README](../README.md)

## 評測：比對「執行結果」，不比對 SQL 字串

同一個答案有很多種 SQL 寫法，所以評分是**把標準 SQL 和模型 SQL 都執行一次，比結果**（`eval/grade.py`）：

- 列數要一樣；標準答案的每個數值欄，模型結果裡要有一欄數值相同（容許四捨五入，比率也接受 ×100 的百分比）
- 名稱欄要對得上（代碼和名稱都算：'US' = 美國、短網址 = 活動名稱）；日期欄只看列數，不管格式
- 「哪個最高」只比第一列；另外有應追問（clarify）、應拒答（refuse）、應回查無資料（empty）三種題型
- 有追問題：`before:` 先問前一題，前一題的 SQL 當作對話紀錄

`tests/test_offline.py`（不需要模型，15 題）測 SQL 安全檢查、日期對照、摘要數字檢查、整數相除改寫、圖表判斷。

## 自動評測：CI 檢查 ＋ 本機跑模型

模型跑在自己電腦上（Ollama），GitHub 的 CI 機器上沒有模型；為了 CI 去呼叫付費 API 也不划算，而且換了模型分數就不是同一個東西了。所以評測拆成兩半：**CI 只做不需要模型的檢查，真正跑模型的評測在本機做，分數跟著 commit 進來，再由 CI 把關。**

### CI（GitHub Actions：`.github/workflows/eval-ci.yml`）

push 到 master、對 master 開 PR 時自動跑（也可在 Actions 頁面手動觸發），不呼叫模型、不需要 API 金鑰：

1. **單元測試** `uv run python -m pytest -q tests`
   - `tests/test_grade.py`：評分程式本身對不對。SQL 寫法不同（欄位順序、別名、排序、用代碼代替名稱、比率寫成百分比）但結果一樣 → 算對；日期範圍錯、列數不同、數字錯 → 算錯；模型產生的 SQL 執行失敗（`error`）→ 算錯；追問／拒答／查無資料題型；題庫每一題的標準 SQL 都能執行
   - `tests/test_regression.py`：回歸檢查和 README 分數區塊的邏輯
   - `tests/test_offline.py`：SQL 安全檢查、日期對照等（見上面）
   - `tests/test_mcp_client.py` 要有 MCP 伺服器，CI 上自動跳過
2. **回歸檢查** `uv run python scripts/check_regression.py`
   - 用**現在的**評分規則和題庫，重新評分已 commit 的結果（`harness/runs/<候選>__tune.json`、`__holdout.json`），分數要跟 `eval/latest.json` 一樣。改了 `eval/grade.py` 或題目、讓分數變了，一定會被抓到
   - `eval/latest.json` 每一組答對的題數，不能低於基準 `eval/baseline.json`
   - README 最上面的分數區塊要跟 `eval/latest.json` 一致（不會出現 README 寫的分數跟實際結果對不上）

要注意：CI 不知道模型「現在」會怎麼回答。它檢查的是「commit 進來的分數有沒有退步、用現在的評分規則算不算得出來」。改了 prompt 或程式流程，要在本機重跑評測，CI 才會看到新分數。

### 本機：一行指令跑完整評測

```bash
# 先開 Ollama（預設 http://127.0.0.1:11434，可用環境變數 OLLAMA_URL 改），並 ollama pull qwen3:8b
uv run python scripts/run_eval.py                    # 評目前的候選（eval/latest.json 裡記的，現在是 v2b），調整組＋隱藏組都跑，約 3 分鐘
uv run python scripts/run_eval.py --candidate v4     # 換候選（harness/candidates/v4）
uv run python scripts/run_eval.py --from-existing    # 不跑模型：用 harness/runs/ 既有的結果重新評分（改了評分規則、或只想更新 README）
uv run python scripts/run_eval.py --accept           # 題數改了、或確定接受分數下降：基準直接換成這次的結果
```

它會依序：

1. 跑調整組和隱藏組（跟 `harness/loop.py probe` 一樣：結果存 `harness/runs/`、記進 `harness/scoreboard.csv`）
2. 寫 `eval/latest.json`（候選、模型、每組分數、平均秒數、時間）
3. 跟基準 `eval/baseline.json` 比：**沒退步就把基準往上調**（基準只升不降）；退步就不動基準，結束碼 1
4. 改寫 README 最上面 `<!-- EVAL:START -->` ～ `<!-- EVAL:END -->` 之間的分數區塊（不要手動改這段）

跑完把 `harness/runs/`、`harness/scoreboard.csv`、`eval/latest.json`、`eval/baseline.json`、`README.md` 一起 commit。如果分數退步又沒有 `--accept`，CI 會失敗，提醒你這次改動讓分數變差。

### 分數怎麼看

- **調整組 tune（28 題）**：改進時看得到錯題，有被「針對」過，分數偏樂觀
- **隱藏組 holdout（17 題）**：不拿來調整，比較接近真實表現；錯題不給看（`loop.py fails` 會拒絕）
- **答對**：`sql` 題是模型 SQL 的執行結果跟標準答案一致（規則見上一節）；追問、拒答、查無資料題是看模型的動作對不對
- **平均秒數**：每題從問問題到回答完成的時間，跟電腦的 GPU 有關，只能在同一台電腦上比較
- **CI 基準**：每組最少要答對幾題。同一題每次跑可能有 ±1 題的浮動，`eval/baseline.json` 的 `allowed_drop` 設定容許少幾題（目前設 1：少 1 題算正常浮動，少 2 題以上 CI 才會失敗）
