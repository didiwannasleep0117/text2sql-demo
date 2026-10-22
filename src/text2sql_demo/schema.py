"""給模型看的資料表說明。欄位意義、指標公式寫清楚，模型才不會自己發明算法。"""

SCHEMA = """\
資料庫：星芽科技（虛構）App 營運數據，SQLite。資料期間 2026-04-01 ~ 2026-09-30。日期欄位都是 'YYYY-MM-DD' 文字。

apps(app_id, app_name, category, launch_date)
  -- 4 款 App：SPN 芽芽記帳、SFT 星芽健身、SWD 芽語單字、SCM 星芽相機（2026-06-01 才上架）
countries(country_code, country_name, region, language)
  -- region：東亞、北美、東南亞；language 例如 zh-TW、ja、en
app_versions(app_id, version, release_date)
daily_app_metrics(date, app_id, country_code, platform, new_installs, dau, sessions, revenue_usd)
  -- 每天 × App × 國家 × 平台（'iOS' / 'Android'）一列
  -- dau 是當天活躍人數，跨天加總沒有意義：「某段期間的 DAU」要用 AVG(每日 DAU 總和)
  -- revenue_usd 是美元
ad_campaigns(campaign_id, short_code, app_id, channel, campaign_name, start_date, end_date)
  -- channel：Facebook、Google、TikTok、LINE；short_code 是廣告短網址代碼（例如 sp-fit-tt01）
campaign_daily(date, campaign_id, country_code, impressions, clicks, installs, spend_usd)
retention(cohort_date, app_id, country_code, cohort_size, d1_retained, d7_retained)
  -- 某天新安裝的人（cohort_size）中，隔天、第 7 天還回來的人數

指標公式（比率一律先加總再相除，不要平均每天的比率）：
  ARPDAU = SUM(revenue_usd) / SUM(dau)
  每日平均 DAU = 先 GROUP BY date 加總 dau，再取 AVG
  CTR 點擊率 = SUM(clicks) / SUM(impressions)
  CPI 單次安裝成本 = SUM(spend_usd) / SUM(installs)
  CVR 轉換率 = SUM(installs) / SUM(clicks)
  D1 留存率 = SUM(d1_retained) / SUM(cohort_size)；D7 同理
  ROAS 這類需要歸因收入的指標：資料庫沒有，不能算
"""

FEW_SHOTS = [
    ("芽芽記帳 8 月在台灣的營收是多少？",
     "SELECT ROUND(SUM(revenue_usd), 2) AS revenue_usd FROM daily_app_metrics\n"
     "WHERE app_id = 'SPN' AND country_code = 'TW' AND date BETWEEN '2026-08-01' AND '2026-08-31'"),
    ("各 App 上個月的每日平均 DAU",
     "SELECT a.app_name, ROUND(AVG(t.dau), 0) AS avg_daily_dau FROM (\n"
     "  SELECT date, app_id, SUM(dau) AS dau FROM daily_app_metrics\n"
     "  WHERE date BETWEEN '2026-08-01' AND '2026-08-31' GROUP BY date, app_id) t\n"
     "JOIN apps a USING (app_id) GROUP BY a.app_name ORDER BY avg_daily_dau DESC"),
    ("TikTok 廣告的 CPI 是多少？",
     "SELECT ROUND(SUM(d.spend_usd) / SUM(d.installs), 3) AS cpi_usd FROM campaign_daily d\n"
     "JOIN ad_campaigns c USING (campaign_id) WHERE c.channel = 'TikTok'"),
]
