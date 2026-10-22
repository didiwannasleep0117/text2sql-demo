"""改進循環（仿 Harness²）：候選 = 一個資料夾（prompt 檔 ＋ env.yaml 開關 ＋ PROPOSAL.md）。

  python harness/loop.py new v1 --from v0          複製候選
  python harness/loop.py probe v1 --split tune     跑分，結果存 harness/runs/，成績記進 scoreboard.csv
  python harness/loop.py fails v1                  看調整組錯題（隱藏組不給看）
  python harness/loop.py diff v0 v1                逐題比較：哪些修好、哪些弄壞
  python harness/loop.py rescore v1 --split tune   評分規則修正後，用存下的結果重新評分（不重跑模型）
  python harness/loop.py board                     成績表
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CANDS, RUNS, BOARD = ROOT / "harness" / "candidates", ROOT / "harness" / "runs", ROOT / "harness" / "scoreboard.csv"
SPLITS = {"tune": ROOT / "eval" / "tune.yaml", "holdout": ROOT / "eval" / "holdout.yaml"}
sys.path.insert(0, str(ROOT / "eval"))
sys.stdout.reconfigure(encoding="utf-8")


def apply_env(name: str) -> None:
    c = CANDS / name
    for k, v in (yaml.safe_load((c / "env.yaml").read_text(encoding="utf-8")) or {}).items():
        v = str(v)
        os.environ[k] = str(c / v) if (k.endswith("_FILE") and v) else v  # *_FILE 是候選資料夾裡的檔案（空字串＝不用）


def cmd_new(name: str, src: str) -> None:
    shutil.copytree(CANDS / src, CANDS / name)
    (CANDS / name / "PROPOSAL.md").write_text(f"# {name}\n\n父候選：{src}\n\n## 改了什麼\n\n## 為什麼（根據哪些調整組錯題）\n",
                                              encoding="utf-8")
    print("建立", CANDS / name)


def cmd_probe(name: str, split: str) -> None:
    apply_env(name)
    from grade import grade
    from text2sql_demo.agent import ask
    items = yaml.safe_load(SPLITS[split].read_text(encoding="utf-8"))
    out = []
    for it in items:
        hist = []
        for prev in it.get("before", []):
            r0 = ask(prev)
            hist.append({"question": prev, "sql": r0.get("sql")})
        try:
            r = ask(it["q"], history=hist or None)
            ok, why = grade(it, r)
        except Exception as e:  # noqa: BLE001
            r, ok, why = {"action": "crash", "seconds": 0, "answer": repr(e)}, False, f"程式錯誤 {e!r}"
        print(f"{'✅' if ok else '❌'} {it['q']}  ({r.get('seconds', 0)}s)  {why}", flush=True)
        out.append({"q": it["q"], "ok": ok, "why": why, "seconds": r.get("seconds", 0), "action": r.get("action"),
                    "sql": r.get("sql"), "columns": r.get("columns"), "rows": (r.get("rows") or [])[:40],
                    "answer": r.get("answer"), "hints": r.get("hints"), "errors": r.get("errors"),
                    "repairs": r.get("repairs"), "summary_retry": r.get("summary_retry"),
                    "summary_fallback": r.get("summary_fallback")})
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / f"{name}__{split}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    passed = sum(r["ok"] for r in out)
    avg = round(sum(r["seconds"] for r in out) / len(out), 1)
    new = not BOARD.exists()
    with BOARD.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "candidate", "split", "passed", "total", "avg_seconds"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M"), name, split, passed, len(out), avg])
    print(f"[{name} / {split}] 通過 {passed}/{len(out)}，平均 {avg} 秒")


def load(name: str, split: str) -> list[dict]:
    return json.loads((RUNS / f"{name}__{split}.json").read_text(encoding="utf-8"))


def cmd_fails(name: str, split: str) -> None:
    if split.startswith("holdout"):
        sys.exit("隱藏組的錯題不給看（看了就不再是隱藏組）")
    for r in load(name, split):
        if not r["ok"]:
            print(f"## {r['q']}\n  判定：{r['why']}  動作：{r['action']}  修正次數：{r.get('repairs')}")
            print(f"  對照：{r.get('hints')}")
            if r.get("errors"):
                print(f"  SQL 錯誤：{r['errors']}")
            print(f"  SQL：{(r.get('sql') or '').replace(chr(10), ' ')}")
            print(f"  結果：{r.get('columns')} {str(r.get('rows'))[:200]}")
            print(f"  回答：{(r.get('answer') or '')[:150]}\n")


def cmd_diff(a: str, b: str, split: str) -> None:
    ra, rb = {r["q"]: r for r in load(a, split)}, {r["q"]: r for r in load(b, split)}
    for q in ra:
        if q in rb and ra[q]["ok"] != rb[q]["ok"]:
            print(f"{'修好 ❌→✅' if rb[q]['ok'] else '弄壞 ✅→❌'} {q}")
    print(f"{a} {sum(r['ok'] for r in ra.values())} → {b} {sum(r['ok'] for r in rb.values())}")


def cmd_rescore(name: str, split: str) -> None:
    from grade import grade
    items = {i["q"]: i for i in yaml.safe_load(SPLITS[split].read_text(encoding="utf-8"))}
    res = load(name, split)
    for r in res:
        r["ok"], r["why"] = grade(items[r["q"]], r)
    (RUNS / f"{name}__{split}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{name} / {split}] 重新評分：{sum(r['ok'] for r in res)}/{len(res)}")


def cmd_board() -> None:
    print(BOARD.read_text(encoding="utf-8"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new"); p.add_argument("name"); p.add_argument("--from", dest="src", default="v0")
    for c in ("probe", "fails", "rescore"):
        p = sub.add_parser(c); p.add_argument("name"); p.add_argument("--split", default="tune", choices=SPLITS)
    p = sub.add_parser("diff"); p.add_argument("a"); p.add_argument("b"); p.add_argument("--split", default="tune")
    sub.add_parser("board")
    a = ap.parse_args()
    {"new": lambda: cmd_new(a.name, a.src), "probe": lambda: cmd_probe(a.name, a.split),
     "fails": lambda: cmd_fails(a.name, a.split), "diff": lambda: cmd_diff(a.a, a.b, a.split),
     "rescore": lambda: cmd_rescore(a.name, a.split), "board": cmd_board}[a.cmd]()
