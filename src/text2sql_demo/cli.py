"""命令列：text2sql-ask 上個月各 App 的總營收"""
import sys

from .agent import ask


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    r = ask(" ".join(sys.argv[1:]) or "上個月各 App 的總營收", verbose=True)
    print("對照：", r["hints"])
    print("SQL：", r["sql"])
    for row in [r["columns"], *r["rows"][:20]]:
        print("  ", row)
    print("回答：", r["answer"], f"（{r['seconds']} 秒）")
