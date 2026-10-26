# 自動評測「拆成兩半」：實作報告

分支：`eval-ci`（本機，**沒有 push**、沒改 repo 可見度、沒建 release）。基底是 `master` 的 88aa6ff。

## 做了什麼

**CI 這一半（GitHub Actions，不跑模型、不需要 API 金鑰）**

- `.github/workflows/eval-ci.yml`：push／PR 都會跑。`actions/checkout@v4` → `astral-sh/setup-uv@v6`（開 cache）→ `uv sync --locked` → `uv run python -m pytest -q tests` → `uv run python scripts/check_regression.py`。權限只有 `contents: read`。
- `tests/test_grade.py`（新，28 個測試案例）：評分程式本身的測試，「模型的回答」是直接在假資料庫上執行的 SQL
  - 算對：欄位順序／別名／排序不同、用 App 代碼代替名稱、沒 ROUND（誤差內）、多一欄、比率寫成百分比、日期欄格式不同、`compare: first`、兩邊都查無資料
  - 算錯：日期範圍錯、列數不同、數字欄錯、名稱欄錯、整數相除變 0、`compare: first` 排反、數值欄放文字
  - 無效 SQL：模型 SQL 執行失敗（agent 回 `action=error`）算錯；標準答案 SQL 寫錯會直接丟例外（不會默默算成模型錯）
  - 題型：refuse／clarify／empty／sql 的 11 種組合
  - 題庫：tune、holdout 每一題的標準 SQL 都能執行，而且「標準答案自己評自己」會通過；題目不能重複（結果檔用題目當 key）
- `tests/test_regression.py`（新，7 個測試）：退步判定、`allowed_drop`、題數改變／少一組、基準只升不降、README 區塊插入與取代（說明文字裡用反引號提到標記不會被誤認）、以及「commit 進來的結果通過回歸檢查」（跟 CI 同一個檢查）
- `scripts/check_regression.py`（新）：
  1. 用現在的 `eval/grade.py` 和題庫重新評分 `eval/latest.json` 那個候選在 `harness/runs/` 的結果，要跟 `latest.json` 的分數一樣；題庫跟結果檔題目不一致也會失敗
  2. `latest.json` 每組答對題數 ≥ `eval/baseline.json` 的基準 − `allowed_drop`（預設 0）
  3. README 分數區塊要跟 `latest.json` 一致
- 既有 `tests/test_offline.py`（15 個）不需要模型，照跑；`tests/test_mcp_client.py`（4 個）沒有 MCP 伺服器會自動 skip，CI 上也一樣。

**本機這一半**

- `scripts/run_eval.py`（新）：一行指令 `uv run python scripts/run_eval.py`
  - 先檢查 Ollama 有沒有開、模型有沒有下載（沒開 → 印原因、結束碼 2）
  - 跑調整組＋隱藏組（直接沿用 `harness/loop.py` 的 `apply_env`／`cmd_probe`，結果存 `harness/runs/`、記進 `scoreboard.csv`）
  - 寫 `eval/latest.json`；跟基準比，沒退步就把基準往上調（只升不降），退步就不動基準、結束碼 1
  - 改寫 README 最上面 `<!-- EVAL:START -->`～`<!-- EVAL:END -->` 的區塊（每組分數、百分比、平均秒數、日期、模型、候選、CI 基準）
  - 參數：`--candidate`（預設沿用 latest.json 的候選，現在是 v2b）、`--from-existing`（不跑模型，用既有結果重新評分）、`--accept`（強制把基準設成這次結果）、`--dry-run`（不寫檔）
- `eval/scores.py`（新）：上面兩支腳本共用的邏輯（重新評分、比較、基準、README 區塊）。寫回 README 時保留原本的換行格式。
- `eval/latest.json`、`eval/baseline.json`（新）：用 `--from-existing --candidate v2b` 從既有 `harness/runs/v2b__*.json` 產生：調整組 27/28、隱藏組 17/17（跟 README 原本寫的一致）。

**文件**

- `README.md`：最上面加自動產生的分數區塊；新增「自動評測：CI 檢查 ＋ 本機跑模型」一節（CI 檢查什麼、為什麼 CI 不跑模型、本機怎麼跑、每個分數的意思）；「快速開始」「目錄」補上新指令和檔案。
- 本報告 `docs/eval_ci_report.md`。

沒有刪除或改動任何既有的 `harness/runs/`、`scoreboard.csv`、候選、題庫、`eval/grade.py`。

## 實際執行的指令與輸出

全部在 Windows 本機、repo 根目錄、`eval-ci` 分支：

```
$ uv sync --locked
Resolved 59 packages in 1ms
Checked 58 packages in 3ms

$ uv run python -m pytest -q tests
50 passed, 4 skipped in 2.65s        # 4 skipped = MCP 測試（伺服器沒開）

$ uv run python -m pytest -q tests/test_grade.py tests/test_regression.py
35 passed in 0.20s

$ uv run python scripts/check_regression.py
[v2b / tune] 重新評分 27/28（latest.json 記錄 27/28）
[v2b / holdout] 重新評分 17/17（latest.json 記錄 17/17）
[基準 / tune] 27/28（v2b，2026-10-22 01:24，容許少 0 題）
[基準 / holdout] 17/17（v2b，2026-10-22 01:28，容許少 0 題）
✅ 沒有退步                            # exit=0

$ uv run python scripts/run_eval.py --from-existing     # 第二次跑
已更新 eval/latest.json（README 不用改）                 # 內容不變，README 不動
```

**故意弄壞，確認回歸檢查會擋**（每次都用備份還原）：

| 動作 | 結果 |
|---|---|
| `latest.json` 調整組 27 改成 26 | exit 1：重新評分不一致、調整組退步、README 不一致（3 項） |
| 手改 README 區塊 17/17 → 16/17 | exit 1：README 分數區塊跟 latest.json 不一致 |
| `grade.py` 誤差容許改成 0 | exit 1：重新評分 tune 18/28、holdout 13/17，跟記錄不一致 |
| `tune.yaml` 加一題 | exit 1：題庫跟結果檔不一致（結果檔少 1 題） |
| `OLLAMA_URL=http://127.0.0.1:9 run_eval.py` | exit 2：連不到模型伺服器（ConnectError），提示用 `--from-existing` |

**真的跑了一次模型**（本機 Ollama 有開、有 qwen3:8b）：為了不覆蓋已 commit 的 `harness/runs/v2b__*.json`，在暫存 git worktree 裡跑，跑完就刪掉 worktree，**結果沒有 commit**：

```
$ uv run python scripts/run_eval.py        # 在暫存 worktree
[v2b / tune] 27/28，平均 4.4 秒（2026-10-26 19:29）
[v2b / holdout] 17/17，平均 3.3 秒（2026-10-26 19:30）
已更新 eval/latest.json、eval/baseline.json、README.md
real 3m14.773s        # exit=0

$ uv run python scripts/check_regression.py   # 同一個 worktree，跑完後
✅ 沒有退步                                    # exit=0；pytest 50 passed, 4 skipped
```

分數跟 10/22 的記錄一樣（調整組 27/28、隱藏組 17/17），調整組平均秒數 4.4（10/22 是 3.5，可能是機器當下負載）。

## 沒有驗證到的

- **GitHub Actions 本身沒跑過**：依規定沒有 push。workflow 的 YAML 有用 PyYAML 解析檢查，裡面的指令都在本機（Windows）跑過同樣的命令，但沒在 ubuntu runner 上實跑。可能的差異：Linux 上 uv 會自己下載 Python 3.11（`.python-version`），依賴裡有 streamlit／pandas，第一次安裝大約 1～2 分鐘。
- `astral-sh/setup-uv@v6` 是我寫的版本號，push 前可以確認一下是不是要換成更新的大版本。

## 想請滴滴決定的事

1. **容許浮動（`allowed_drop`）**：目前是 0（最嚴格）。同一題每次跑可能 ±1，基準又只升不降，運氣好跑出高分後，下一次正常浮動就會讓 CI 變紅。要不要改成 1？（改 `eval/baseline.json` 的 `allowed_drop` 就好）
2. **跑模型會覆蓋結果檔**：`run_eval.py` 跟 `loop.py probe` 一樣，會覆寫 `harness/runs/<候選>__<組>.json`（舊版留在 git 歷史裡，`scoreboard.csv` 是累加的）。如果想保留每次的完整結果，可以改成另存帶日期的檔名。
3. **CI 費用**：repo 是 private，GitHub Actions 在免費額度內（每月 2000 分鐘）不用錢；這個 job 大概 1～3 分鐘。公開之後就完全免費。
4. **觸發條件**：現在是所有分支的 push ＋ PR（PR 會跟 push 各跑一次）。要不要只限 `master` 的 push ＋ PR？
5. README 上面原本的「改善前後差異」表格是手寫的（v0 vs v2b），沒有改成自動產生；自動區塊只顯示目前候選的最新分數。
