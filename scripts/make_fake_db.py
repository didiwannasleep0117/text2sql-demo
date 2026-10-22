"""產生假的 App 營運資料庫（SQLite）。所有公司、App、數字都是虛構的。

星芽科技（虛構）經營 4 款 App，資料期間 2026-04-01 ~ 2026-09-30。
固定亂數種子，每次產生的資料都一樣（評測的標準答案才會穩定）。

用法：python scripts/make_fake_db.py  → data/sprout_metrics.db
"""
from __future__ import annotations

import math
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sprout_metrics.db"
START, END = date(2026, 4, 1), date(2026, 9, 30)

APPS = [  # app_id, 名稱, 類別, 上架日, 規模, ARPDAU(USD)
    ("SPN", "芽芽記帳", "理財", "2024-03-01", 1.0, 0.020),
    ("SFT", "星芽健身", "健康", "2025-01-15", 0.6, 0.035),
    ("SWD", "芽語單字", "教育", "2023-09-10", 0.8, 0.015),
    ("SCM", "星芽相機", "攝影", "2026-06-01", 0.5, 0.010),  # 6 月才上架
]
COUNTRIES = [  # code, 中文名, 地區, 語系, 規模
    ("TW", "台灣", "東亞", "zh-TW", 1.0),
    ("HK", "香港", "東亞", "zh-HK", 0.35),
    ("JP", "日本", "東亞", "ja", 0.7),
    ("KR", "韓國", "東亞", "ko", 0.4),
    ("US", "美國", "北美", "en", 0.6),
    ("TH", "泰國", "東南亞", "th", 0.45),
    ("VN", "越南", "東南亞", "vi", 0.3),
    ("MY", "馬來西亞", "東南亞", "ms", 0.25),
]
PLATFORMS = ["iOS", "Android"]
CHANNELS = ["Facebook", "Google", "TikTok", "LINE"]
CAMPAIGNS = [  # campaign_id, 短網址代碼, app, 管道, 名稱, 開始, 結束
    (1, "sp-acct-fb01", "SPN", "Facebook", "記帳春季推廣", "2026-04-01", "2026-05-31"),
    (2, "sp-acct-gg01", "SPN", "Google", "記帳關鍵字", "2026-04-01", "2026-09-30"),
    (3, "sp-fit-tt01", "SFT", "TikTok", "健身挑戰短影音", "2026-05-01", "2026-08-31"),
    (4, "sp-fit-fb01", "SFT", "Facebook", "健身新手方案", "2026-04-15", "2026-09-30"),
    (5, "sp-wd-line1", "SWD", "LINE", "單字每日一句", "2026-04-01", "2026-09-30"),
    (6, "sp-wd-gg01", "SWD", "Google", "考試季關鍵字", "2026-06-01", "2026-07-31"),
    (7, "sp-cam-tt01", "SCM", "TikTok", "相機上架首發", "2026-06-01", "2026-07-15"),
    (8, "sp-cam-fb01", "SCM", "Facebook", "相機濾鏡活動", "2026-08-01", "2026-09-30"),
]
CAMPAIGN_COUNTRIES = {1: ["TW", "HK"], 2: ["TW", "HK", "US"], 3: ["TW", "TH", "VN", "MY"], 4: ["TW", "JP"],
                      5: ["TW", "JP", "TH"], 6: ["TW", "KR"], 7: ["TW", "JP", "KR", "US"], 8: ["TW", "TH"]}
VERSIONS = {"SPN": [("3.4.0", "2026-03-20"), ("3.5.0", "2026-06-10"), ("3.6.0", "2026-09-01")],
            "SFT": [("2.1.0", "2026-02-01"), ("2.2.0", "2026-07-01")],
            "SWD": [("5.0.2", "2026-01-05"), ("5.1.0", "2026-05-15"), ("5.2.0", "2026-08-20")],
            "SCM": [("1.0.0", "2026-06-01"), ("1.1.0", "2026-08-01")]}


def days():
    d = START
    while d <= END:
        yield d
        d += timedelta(days=1)


def main() -> None:
    rnd = random.Random(20260930)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.unlink(missing_ok=True)
    db = sqlite3.connect(OUT)
    db.executescript("""
    CREATE TABLE apps (app_id TEXT PRIMARY KEY, app_name TEXT, category TEXT, launch_date TEXT);
    CREATE TABLE countries (country_code TEXT PRIMARY KEY, country_name TEXT, region TEXT, language TEXT);
    CREATE TABLE app_versions (app_id TEXT, version TEXT, release_date TEXT);
    CREATE TABLE daily_app_metrics (
        date TEXT, app_id TEXT, country_code TEXT, platform TEXT,
        new_installs INTEGER, dau INTEGER, sessions INTEGER, revenue_usd REAL,
        PRIMARY KEY (date, app_id, country_code, platform));
    CREATE TABLE ad_campaigns (campaign_id INTEGER PRIMARY KEY, short_code TEXT, app_id TEXT, channel TEXT,
        campaign_name TEXT, start_date TEXT, end_date TEXT);
    CREATE TABLE campaign_daily (date TEXT, campaign_id INTEGER, country_code TEXT,
        impressions INTEGER, clicks INTEGER, installs INTEGER, spend_usd REAL,
        PRIMARY KEY (date, campaign_id, country_code));
    CREATE TABLE retention (cohort_date TEXT, app_id TEXT, country_code TEXT,
        cohort_size INTEGER, d1_retained INTEGER, d7_retained INTEGER,
        PRIMARY KEY (cohort_date, app_id, country_code));
    """)
    db.executemany("INSERT INTO apps VALUES (?,?,?,?)", [a[:4] for a in APPS])
    db.executemany("INSERT INTO countries VALUES (?,?,?,?)", [c[:4] for c in COUNTRIES])
    db.executemany("INSERT INTO app_versions VALUES (?,?,?)",
                   [(a, v, d) for a, vs in VERSIONS.items() for v, d in vs])
    rows, ret = [], []
    for d in days():
        ds = d.isoformat()
        season = 1 + 0.15 * math.sin((d - START).days / 30)
        weekend = 1.12 if d.weekday() >= 5 else 1.0
        for app_id, _, _, launch, scale, arpdau in APPS:
            if ds < launch:
                continue
            age = (d - date.fromisoformat(launch)).days
            ramp = min(1.0, 0.3 + age / 60) if age < 60 else 1.0
            for cc, _, _, _, cscale in COUNTRIES:
                for pf in PLATFORMS:
                    pscale = 0.45 if pf == "iOS" else 0.55
                    base = 4000 * scale * cscale * pscale * season * weekend * ramp
                    dau = int(base * rnd.uniform(0.9, 1.1))
                    inst = int(dau * rnd.uniform(0.03, 0.06) * (2.0 if age < 30 else 1.0))
                    sess = int(dau * rnd.uniform(2.2, 3.4))
                    pay = arpdau * (1.6 if pf == "iOS" else 1.0) * (1.4 if cc in ("JP", "US") else 1.0)
                    rev = round(dau * pay * rnd.uniform(0.8, 1.2), 2)
                    rows.append((ds, app_id, cc, pf, inst, dau, sess, rev))
                cohort = sum(r[4] for r in rows[-2:])
                d1 = int(cohort * rnd.uniform(0.32, 0.45))
                d7 = int(d1 * rnd.uniform(0.35, 0.55))
                ret.append((ds, app_id, cc, cohort, d1, d7))
    db.executemany("INSERT INTO daily_app_metrics VALUES (?,?,?,?,?,?,?,?)", rows)
    db.executemany("INSERT INTO retention VALUES (?,?,?,?,?,?)", ret)
    db.executemany("INSERT INTO ad_campaigns VALUES (?,?,?,?,?,?,?)", CAMPAIGNS)
    crow = []
    cpc = {"Facebook": 0.18, "Google": 0.25, "TikTok": 0.12, "LINE": 0.20}
    for d in days():
        ds = d.isoformat()
        for cid, _, _, ch, _, s, e in CAMPAIGNS:
            if not (s <= ds <= e):
                continue
            for cc in CAMPAIGN_COUNTRIES[cid]:
                imp = int(rnd.uniform(8000, 30000) * (1.5 if cc == "TW" else 1.0))
                clk = int(imp * rnd.uniform(0.008, 0.025))
                ins = int(clk * rnd.uniform(0.08, 0.2))
                spend = round(clk * cpc[ch] * rnd.uniform(0.85, 1.15), 2)
                crow.append((ds, cid, cc, imp, clk, ins, spend))
    db.executemany("INSERT INTO campaign_daily VALUES (?,?,?,?,?,?,?)", crow)
    db.commit()
    for t in ["apps", "countries", "app_versions", "daily_app_metrics", "ad_campaigns", "campaign_daily", "retention"]:
        print(t, db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    db.close()


if __name__ == "__main__":
    main()
