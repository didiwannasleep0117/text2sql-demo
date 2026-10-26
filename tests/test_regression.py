"""回歸檢查和 README 分數區塊的邏輯（eval/scores.py、scripts/check_regression.py），不需要模型。

uv run python -m pytest -q tests/test_regression.py
"""
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "eval"), str(ROOT / "scripts")]

import scores  # noqa: E402


def latest(tune=27, holdout=17, total=(28, 17)):
    return {"candidate": "vX", "model": "qwen3:8b", "splits": {
        "tune": {"passed": tune, "total": total[0], "avg_seconds": 3.5, "time": "2026-10-22 01:24"},
        "holdout": {"passed": holdout, "total": total[1], "avg_seconds": 3.3, "time": "2026-10-22 01:28"}}}


BASE = scores.raise_baseline(latest(), {}, force=True)


def test_no_regression():
    assert scores.compare(latest(), BASE) == []
    assert scores.compare(latest(tune=28), BASE) == []


def test_drop_fails_each_split():
    assert len(scores.compare(latest(tune=26), BASE)) == 1
    assert len(scores.compare(latest(holdout=16), BASE)) == 1
    assert len(scores.compare(latest(tune=26, holdout=15), BASE)) == 2


def test_allowed_drop():
    assert scores.compare(latest(tune=26), {**BASE, "allowed_drop": 1}) == []
    assert scores.compare(latest(tune=25), {**BASE, "allowed_drop": 1}) != []


def test_total_changed_or_split_missing_fails():
    assert scores.compare(latest(total=(29, 17)), BASE) != []
    only_tune = latest()
    del only_tune["splits"]["holdout"]
    assert scores.compare(only_tune, BASE) != []


def test_baseline_only_goes_up():
    assert scores.raise_baseline(latest(tune=26), BASE)["splits"]["tune"]["passed"] == 27
    up = scores.raise_baseline(latest(tune=28, holdout=16), BASE)
    assert up["splits"]["tune"]["passed"] == 28 and up["splits"]["holdout"]["passed"] == 17
    assert scores.raise_baseline(latest(tune=20), BASE, force=True)["splits"]["tune"]["passed"] == 20
    assert scores.raise_baseline(latest(), {**BASE, "allowed_drop": 1})["allowed_drop"] == 1


def test_readme_block_insert_and_replace():
    block = scores.render_block(latest(), BASE)
    assert "27/28" in block and "17/17" in block and "100%" in block and "96.4%" in block
    text = "# 標題\n\n> ⚠️ 示範專案\n\n![圖](x.png)\n\n說明：`<!-- EVAL:START -->` ～ `<!-- EVAL:END -->` 之間自動產生\n"
    assert scores.readme_block(text) is None  # 說明文字裡提到標記，不算區塊
    once = scores.replace_block(text, block)
    assert once.index(block) > once.index("示範專案") and once.index(block) < once.index("![圖]")
    assert once.endswith(text[text.index("![圖]"):])  # 說明文字原封不動
    again = scores.replace_block(once, scores.render_block(latest(tune=28), BASE))
    assert again.count(scores.START + "\n") == 1 and "28/28" in again and "27/28" not in again
    assert scores.readme_block(again) == scores.render_block(latest(tune=28), BASE)


def test_committed_results_pass_regression_check():
    # 跟 CI 跑的是同一個檢查：commit 進來的 latest.json／baseline.json／README／harness/runs 要一致、沒有退步
    check_regression = importlib.import_module("check_regression")
    assert check_regression.check() == []
