# 自動改進循環（仿 Harness²，`harness/`）

[← 回到 README](../README.zh-TW.md)

跟 [policy-agent-demo](https://github.com/didiwannasleep0117/policy-agent-demo) 同一套做法：每個候選是一個資料夾（`sql_system.md`、`summary_system.md`、`fewshots.yaml`、`env.yaml` 開關、`PROPOSAL.md` 說明），`loop.py` 跑分、比較，結果和教訓寫進 `harness/EXPERIENCE.md`。只看調整組的錯題，隱藏組最後才跑。

| 候選 | 改了什麼 | 調整組 28 題 |
|---|---|---|
| v0 | 第一版 | 19 |
| v1a | Prompt：比率乘 1.0、沒提日期不加日期、JOIN 用同義欄位 | 23 |
| v1b | 程式：活動名稱／版本上線日／「到 N 月底」對照、沒提日期明講查全期間、查無資料先自檢 | 23 |
| v2a | 合併 v1a＋v1b，**程式改寫整數相除** | 27 |
| **v2b** | v2a ＋ 換範例（示範地區 JOIN、比率乘 1.0；範例題不取自調整組） | **27** |
| v3 | v2b ＋ prompt 補「每日平均只 GROUP BY date」 | 27（沒修好，淘汰） |

v2b 已複製成預設設定（`prompts/`、程式預設開關）。

**最有意思的發現**：「比率要乘 1.0」寫在 prompt 裡，8B 模型完全不理，因為它照抄範例和公式說明裡的 `SUM/SUM`。改成程式直接改寫 SQL，4 題一次修好。範例的影響力比規則文字大，所以 v2b 是換範例，不是加規則。

```bash
python harness/loop.py new v4 --from v2b          # 複製候選
python harness/loop.py probe v4 --split tune      # 跑分
python harness/loop.py fails v4                   # 看錯題（隱藏組不給看）
python harness/loop.py diff v2b v4                # 哪些修好、哪些弄壞
python harness/loop.py rescore v4 --split tune    # 評分規則修正後重評（不重跑模型）
```
