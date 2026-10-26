"""評分程式（eval/grade.py）的單元測試：不需要模型，直接拿 SQL 在假資料庫上執行，當作「模型的回答」。

uv run python -m pytest -q tests/test_grade.py
"""
import sys
from pathlib import Path

import pytest
import yaml

from text2sql_demo import db

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))

from grade import gold_result, grade  # noqa: E402

GOLD_REV = ("SELECT a.app_name, ROUND(SUM(m.revenue_usd), 2) FROM daily_app_metrics m JOIN apps a USING(app_id) "
            "WHERE date BETWEEN '2026-08-01' AND '2026-08-31' GROUP BY a.app_name")
GOLD_CTR = ("SELECT 1.0 * SUM(clicks) / SUM(impressions) FROM campaign_daily JOIN ad_campaigns USING(campaign_id) "
            "WHERE channel='TikTok'")
GOLD_TOP = ("SELECT c.country_name, SUM(revenue_usd) / SUM(dau) AS v FROM daily_app_metrics JOIN countries c "
            "USING(country_code) WHERE date BETWEEN '2026-08-01' AND '2026-08-31' GROUP BY c.country_name "
            "ORDER BY v DESC LIMIT 1")
GOLD_DAILY = ("SELECT date, SUM(new_installs) FROM daily_app_metrics WHERE app_id='SFT' "
              "AND date BETWEEN '2026-09-24' AND '2026-09-30' GROUP BY date")


def model(sql: str) -> dict:
    """模擬 agent.ask() 成功查詢的回傳。"""
    cols, rows, _ = db.run(sql)
    return {"action": "sql", "sql": sql, "columns": cols, "rows": [list(r) for r in rows]}


def g(gold: str, sql: str, **item) -> bool:
    return grade({"q": "測試", "gold": gold, **item}, model(sql))[0]


@pytest.mark.parametrize("sql", [
    # 欄位順序、別名、排序都不同
    "SELECT ROUND(SUM(m.revenue_usd), 2) AS rev, a.app_name AS app FROM daily_app_metrics AS m JOIN apps AS a "
    "ON a.app_id = m.app_id WHERE m.date >= '2026-08-01' AND m.date <= '2026-08-31' GROUP BY a.app_name ORDER BY rev DESC",
    # 用 App 代碼代替名稱、沒有 ROUND（四捨五入誤差內）
    "SELECT app_id, SUM(revenue_usd) FROM daily_app_metrics WHERE strftime('%Y-%m', date) = '2026-08' GROUP BY app_id",
    # 多一欄也沒關係（例如順便給 DAU）
    "SELECT app_id, SUM(dau), SUM(revenue_usd) FROM daily_app_metrics WHERE date LIKE '2026-08-%' GROUP BY app_id",
])
def test_equivalent_sql_graded_correct(sql):
    assert g(GOLD_REV, sql)


def test_ratio_as_percentage_graded_correct():
    assert g(GOLD_CTR, "SELECT ROUND(100.0 * SUM(cd.clicks) / SUM(cd.impressions), 2) AS ctr_pct FROM campaign_daily cd "
                       "JOIN ad_campaigns ac ON ac.campaign_id = cd.campaign_id WHERE ac.channel = 'TikTok'")


def test_date_column_format_ignored():
    assert g(GOLD_DAILY, "SELECT substr(date, 6) AS d, SUM(new_installs) FROM daily_app_metrics WHERE app_id='SFT' "
                         "AND date >= '2026-09-24' GROUP BY date ORDER BY date DESC")


@pytest.mark.parametrize("sql", [
    # 日期範圍錯（7 月）
    "SELECT a.app_name, ROUND(SUM(m.revenue_usd), 2) FROM daily_app_metrics m JOIN apps a USING(app_id) "
    "WHERE date BETWEEN '2026-07-01' AND '2026-07-31' GROUP BY a.app_name",
    # 列數不同（沒分 App）
    "SELECT ROUND(SUM(revenue_usd), 2) FROM daily_app_metrics WHERE date BETWEEN '2026-08-01' AND '2026-08-31'",
    # 名稱對、數字錯（錯欄位）
    "SELECT a.app_name, SUM(m.dau) FROM daily_app_metrics m JOIN apps a USING(app_id) "
    "WHERE date BETWEEN '2026-08-01' AND '2026-08-31' GROUP BY a.app_name",
    # 數字對、名稱欄錯（分組變成平台）
    "SELECT platform, ROUND(SUM(revenue_usd), 2) FROM daily_app_metrics WHERE date BETWEEN '2026-08-01' AND '2026-08-31' "
    "GROUP BY platform",
])
def test_wrong_result_graded_wrong(sql):
    assert not g(GOLD_REV, sql)


def test_integer_division_zero_graded_wrong():
    # SQLite 整數相除 → 0，這正是 v0 的錯
    assert not g(GOLD_CTR, "SELECT SUM(clicks) / SUM(impressions) FROM campaign_daily JOIN ad_campaigns USING(campaign_id) "
                           "WHERE channel='TikTok'")


def test_compare_first_only_checks_first_row():
    top_all = ("SELECT c.country_name, SUM(revenue_usd) / SUM(dau) AS v FROM daily_app_metrics JOIN countries c "
               "USING(country_code) WHERE date BETWEEN '2026-08-01' AND '2026-08-31' GROUP BY c.country_name ORDER BY v DESC")
    assert g(GOLD_TOP, top_all, compare="first")
    assert not g(GOLD_TOP, top_all.replace("DESC", "ASC"), compare="first")  # 排反了 → 第一名錯
    assert not g(GOLD_TOP, top_all)  # 沒有 compare: first → 列數不同


def test_both_empty_graded_correct():
    empty = "SELECT SUM(revenue_usd) FROM daily_app_metrics WHERE app_id='SCM' AND date < '2026-06-01' GROUP BY app_id"
    assert g(empty, empty)


def test_model_sql_error_graded_wrong():
    # 模型的 SQL 修正後還是失敗 → agent 回 action=error，沒有結果
    with pytest.raises(db.SQLError):
        db.run("SELECT no_such_col FROM apps")
    ok, why = grade({"q": "x", "gold": GOLD_REV}, {"action": "error", "sql": "SELECT no_such_col FROM apps",
                                                   "answer": "抱歉，這題我產生的查詢一直失敗"})
    assert not ok and "error" in why


def test_non_numeric_column_not_matched_as_number():
    res = {"action": "sql", "columns": ["app", "rev"], "rows": [["芽芽記帳", "很多"]]}
    assert not grade({"q": "x", "gold": "SELECT app_name, 1.5 FROM apps WHERE app_id='SPN'"}, res)[0]


@pytest.mark.parametrize("kind,action,want", [
    ("refuse", "refuse", True), ("refuse", "sql", False), ("refuse", "clarify", False),
    ("clarify", "clarify", True), ("clarify", "empty", True), ("clarify", "sql", False),
    ("empty", "empty", True), ("empty", "clarify", True), ("empty", "sql", False),
    ("sql", "clarify", False), ("sql", "refuse", False),
])
def test_kinds(kind, action, want):
    assert grade({"q": "x", "kind": kind, "gold": GOLD_REV}, {"action": action, "answer": ""})[0] is want


def test_invalid_gold_sql_raises():
    # 標準答案寫錯要大聲失敗，不能默默算模型錯
    with pytest.raises(Exception):
        gold_result("SELECT FROM WHERE")


@pytest.mark.parametrize("split", ["tune", "holdout"])
def test_every_gold_sql_runs_and_self_grades(split):
    items = yaml.safe_load((ROOT / "eval" / f"{split}.yaml").read_text(encoding="utf-8"))
    assert items and len({i["q"] for i in items}) == len(items), "題目不能重複（結果檔用題目當 key）"
    for it in items:
        if it.get("kind", "sql") != "sql":
            continue
        cols, rows = gold_result(it["gold"])
        assert grade(it, {"action": "sql", "columns": cols, "rows": rows})[0], it["q"]
