"""不用 LLM 的測試：SQL 安全檢查、日期對照、摘要數字檢查、圖表判斷。

uv run python -m pytest -q tests
"""
from datetime import date

import pytest

from text2sql_demo import db
from text2sql_demo.agent import chart_spec, fix_int_division, unsupported_numbers
from text2sql_demo.linker import link, resolve_dates


@pytest.mark.parametrize("sql", [
    "UPDATE daily_app_metrics SET revenue_usd = 0",
    "DELETE FROM apps",
    "DROP TABLE apps",
    "SELECT 1; DROP TABLE apps",
    "ATTACH DATABASE 'x.db' AS x",
    "PRAGMA writable_schema = 1",
])
def test_write_sql_blocked(sql):
    with pytest.raises(db.SQLError):
        db.run(sql)


def test_cte_with_write_blocked_by_authorizer():
    # 字串檢查只看開頭是 WITH，真正擋寫入的是資料庫層的 authorizer ＋ 唯讀連線
    with pytest.raises(db.SQLError):
        db.run("WITH x AS (SELECT 1) DELETE FROM apps")


def test_select_ok():
    cols, rows, trunc = db.run("SELECT app_id FROM apps ORDER BY app_id")
    assert cols == ["app_id"] and len(rows) == 4 and not trunc


def test_dates():
    d = {t.strip(): (a, b) for t, a, b in resolve_dates("上個月跟最近 7 天、第三季、6 月到 8 月")}
    assert d["上個月"] == (date(2026, 8, 1), date(2026, 8, 31))
    assert d["最近 7 天"] == (date(2026, 9, 24), date(2026, 9, 30))
    assert d["第三季"] == (date(2026, 7, 1), date(2026, 9, 30))
    assert d["6 月到 8 月"] == (date(2026, 6, 1), date(2026, 8, 31))


def test_link_aliases():
    h = " ".join(link("抖音廣告在美區的花費，記帳 App"))
    assert "'TikTok'" in h and "'US'" in h and "'SPN'" in h


def test_summary_number_check():
    rows = [["芽芽記帳", 12345.67], ["星芽健身", 0.0345]]
    assert unsupported_numbers("芽芽記帳營收 12,345.67 美元，健身 3.45%", "", "", rows) == []
    assert unsupported_numbers("芽芽記帳約 12,346 美元", "", "", rows) == []  # 四捨五入版本放過
    assert unsupported_numbers("兩款合計 99,999 美元", "", "", rows) == ["99,999"]


def test_chart_spec():
    assert chart_spec(["date", "v"], [["2026-09-01", 1], ["2026-09-02", 2]])["type"] == "line"
    assert chart_spec(["app", "v"], [["A", 1], ["B", 2]])["type"] == "bar"
    assert chart_spec(["v"], [[1]]) is None


@pytest.mark.parametrize("src,want", [
    ("SELECT ROUND(SUM(a) / SUM(b), 4)", "SELECT ROUND(1.0 * SUM(a) / SUM(b), 4)"),
    ("SELECT 1.0 * SUM(a) / SUM(b)", "SELECT 1.0 * SUM(a) / SUM(b)"),
    ("SELECT SUM(a) * 1.0 / SUM(b)", "SELECT SUM(a) * 1.0 / SUM(b)"),
])
def test_fix_int_division(src, want):
    assert fix_int_division(src) == want
    cols, rows, _ = db.run("SELECT " + fix_int_division("SUM(d1_retained) / SUM(cohort_size)") + " FROM retention")
    assert 0.2 < rows[0][0] < 0.6
