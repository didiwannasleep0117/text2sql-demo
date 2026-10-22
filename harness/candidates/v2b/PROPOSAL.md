# v2b：v2a ＋ 換範例（few-shot）

父候選：v2a

## 改了什麼
- `FEWSHOT_FILE=fewshots.yaml`：原本 3 個範例，加上「地區 × 每日平均」（北美 6 月 sessions，不是調整組的題目）和「比率乘 1.0」範例，CPI 範例也改成乘 1.0

## 為什麼
- 「東南亞上個月每日平均 DAU」：模型照抄範例 2 的「GROUP BY date, app_id」，再用錯的欄位 JOIN countries。範例裡沒有地區 JOIN 的寫法
- 模型會照抄範例裡的公式（v1a 的觀察），所以範例本身就要示範乘 1.0
