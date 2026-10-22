# v2a：Compose（v1a prompt ＋ v1b 對照／查無資料自檢）＋ 程式修整數相除

父候選：v1a（prompt）＋ v1b（LINKER_V2、EMPTY_RETRY）

## 改了什麼
- 合併 v1a、v1b
- `SQL_FIXUPS=1`：程式把 `SUM(a) / SUM(b)` 改寫成 `1.0 * SUM(a) / SUM(b)`

## 為什麼
- v1a（22）、v1b（23）修好的題目不同：v1a 修好沒提日期的題目，v1b 修好活動名稱和版本上線日
- 兩個都沒修好整數相除：v1a 在 prompt 寫了「要乘 1.0」，模型照樣抄範例和公式寫 SUM/SUM → 留存率全是 0。prompt 叮嚀沒用，改用程式直接改寫 SQL
