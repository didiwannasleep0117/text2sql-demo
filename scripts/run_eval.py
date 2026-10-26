"""本機評測：一行指令跑完整評測，更新基準和 README 分數區塊（要先開 Ollama）。

  uv run python scripts/run_eval.py                    評 eval/latest.json 記錄的候選（預設 v2b），調整組＋隱藏組都跑
  uv run python scripts/run_eval.py --candidate v4     換候選
  uv run python scripts/run_eval.py --from-existing    不跑模型：用 harness/runs/ 既有的結果重新評分（改了評分規則、或只想更新 README）
  uv run python scripts/run_eval.py --accept           題數改了、或確定接受退步：基準直接換成這次的結果
  uv run python scripts/run_eval.py --from-existing --dry-run   只印出結果和 README 區塊，不寫任何檔案

流程：跑分（同 harness/loop.py probe：結果存 harness/runs/<候選>__<組>.json、記進 scoreboard.csv）
→ 寫 eval/latest.json → 跟 eval/baseline.json 比：沒退步就把基準往上調，退步就不動基準、結束碼 1
→ 改寫 README 最上面 <!-- EVAL:START --> ～ <!-- EVAL:END --> 的分數區塊。
跑完把這些檔案 commit，CI（scripts/check_regression.py）就會檢查。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "harness"), str(ROOT / "eval")]

import loop  # noqa: E402  harness/loop.py（跑分沿用 probe）
import scores  # noqa: E402


def model_ready(model: str) -> str | None:
    """模型伺服器有開、模型也下載了 → None；否則回傳原因。"""
    url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    try:
        r = httpx.get(f"{url}/api/tags", timeout=3)
        r.raise_for_status()
    except httpx.HTTPError as e:
        return f"連不到模型伺服器 {url}（{e.__class__.__name__}）。先開 Ollama，或加 --from-existing 用既有結果"
    if model not in {m.get("name") for m in r.json().get("models", [])}:
        return f"Ollama 裡沒有模型 {model}，先 ollama pull {model}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="本機完整評測（調整組＋隱藏組），更新 eval/latest.json、基準、README 分數區塊")
    ap.add_argument("--candidate", help="候選名稱（harness/candidates/ 底下），預設沿用 eval/latest.json 的候選")
    ap.add_argument("--from-existing", action="store_true", help="不跑模型，用 harness/runs/ 既有的結果重新評分")
    ap.add_argument("--accept", action="store_true", help="基準直接換成這次的結果（題數改了或確定接受退步時用）")
    ap.add_argument("--dry-run", action="store_true", help="不寫 eval/*.json 和 README，只印出來")
    a = ap.parse_args()

    cand = a.candidate or scores.read_json(scores.LATEST).get("candidate", "v2b")
    if not (scores.CANDS / cand).is_dir():
        sys.exit(f"找不到候選 harness/candidates/{cand}")
    if not a.from_existing:
        loop.apply_env(cand)
        why = model_ready(os.getenv("MODEL", "qwen3:8b"))
        if why:
            print("❌", why)
            return 2
        for split in scores.SPLITS:
            loop.cmd_probe(cand, split)

    latest = scores.summarize(cand)
    old_base = scores.read_json(scores.BASELINE)
    fails = [] if a.accept or not old_base else scores.compare(latest, old_base)
    base = scores.raise_baseline(latest, old_base, force=a.accept or not old_base)
    block = scores.render_block(latest, base)

    for split, s in latest["splits"].items():
        print(f"[{cand} / {split}] {s['passed']}/{s['total']}，平均 {s['avg_seconds']} 秒（{s['time']}）")
    for p in fails:
        print("❌", p)
    if base != old_base:
        print("基準更新：", {k: f"{v['passed']}/{v['total']} ({v['candidate']})" for k, v in base["splits"].items()})
    print("\nREADME 分數區塊：\n" + block)

    if a.dry_run:
        print("\n（--dry-run：沒有寫入任何檔案）")
    else:
        scores.write_json(scores.LATEST, latest)
        if base != old_base:
            scores.write_json(scores.BASELINE, base)
        text = scores.read_text(scores.README)
        new = scores.replace_block(text, block)
        if new != text:
            scores.write_text_keep_eol(scores.README, new)
        print("\n已更新 eval/latest.json" + ("、eval/baseline.json" if base != old_base else "") +
              ("、README.md" if new != text else "（README 不用改）"))
    if fails:
        print("有退步：基準沒有更新（同一題每次跑可能 ±1，確定要接受就加 --accept）")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
