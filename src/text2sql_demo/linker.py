"""實體與日期對照：由程式把口語換成資料庫代碼和明確日期，不讓 LLM 自己猜。

例如「上個月」「記帳」「抖音」「美區」→ 2026-08-01~2026-08-31、SPN、TikTok、US。
代碼從資料庫讀，資料庫多了新 App 或國家不用改程式。
"""
from __future__ import annotations

import os
import re
from datetime import date, timedelta
from functools import lru_cache

from .db import connect

TODAY = date.fromisoformat(os.getenv("TODAY", "2026-09-30"))  # 示範用：資料最新日期當作「今天」


def _v2() -> bool:
    # LINKER_V2（改進循環 v1b 加的）：活動名稱對照、版本附上線日、「到 N 月底」、沒提日期就明說查全期間
    return os.getenv("LINKER_V2", "1") == "1"

APP_ALIASES = {"記帳": "SPN", "健身": "SFT", "單字": "SWD", "相機": "SCM"}
COUNTRY_ALIASES = {"臺灣": "TW", "南韓": "KR", "美區": "US", "美区": "US", "大馬": "MY", "港區": "HK"}
CHANNEL_ALIASES = {"facebook": "Facebook", "fb": "Facebook", "臉書": "Facebook", "meta": "Facebook",
                   "google": "Google", "谷歌": "Google", "tiktok": "TikTok", "抖音": "TikTok", "line": "LINE"}
PLATFORM_ALIASES = {"ios": "iOS", "iphone": "iOS", "蘋果": "iOS", "android": "Android", "安卓": "Android"}
_CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
       "十一": 11, "十二": 12, "兩": 2}


@lru_cache
def _db_entities():
    con = connect()
    try:
        apps = con.execute("SELECT app_id, app_name FROM apps").fetchall()
        countries = con.execute("SELECT country_code, country_name FROM countries").fetchall()
        regions = [r[0] for r in con.execute("SELECT DISTINCT region FROM countries")]
        codes = {r[0]: r[1] for r in con.execute("SELECT short_code, campaign_name FROM ad_campaigns")}
        versions = con.execute("SELECT app_id, version, release_date FROM app_versions").fetchall()
        campaigns = con.execute("SELECT campaign_name, short_code, campaign_id FROM ad_campaigns").fetchall()
        rng = con.execute("SELECT MIN(date), MAX(date) FROM daily_app_metrics").fetchone()
    finally:
        con.close()
    return apps, countries, regions, codes, versions, rng, campaigns


def _num(s: str) -> int:
    return int(s) if s.isdigit() else _CN.get(s, 0)


def _month(y: int, m: int) -> tuple[date, date]:
    start = date(y, m, 1)
    end = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    return start, end


def resolve_dates(q: str) -> list[tuple[str, date, date]]:
    out = []
    y = TODAY.year
    n = r"(\d{1,2}|十[一二]?|[一二兩三四五六七八九])"
    if m := re.search(rf"{n}\s*月?\s*(?:到|至|~|－|-)\s*{n}\s*月", q):
        a, b = _num(m.group(1)), _num(m.group(2))
        if 1 <= a <= b <= 12:
            out.append((m.group(0), _month(y, a)[0], _month(y, b)[1]))
            q = q.replace(m.group(0), " ")
    for m in re.finditer(rf"(?<![\d/])(\d{{1,2}})\s*[/月]\s*(\d{{1,2}})\s*[日號]?", q):
        try:
            d = date(y, int(m.group(1)), int(m.group(2)))
            out.append((m.group(0), d, d))
        except ValueError:
            pass
    q2 = re.sub(r"(?<![\d/])\d{1,2}\s*[/月]\s*\d{1,2}\s*[日號]?", " ", q)
    rel = {
        "上個月": _month(*(lambda d: (d.year, d.month))(TODAY.replace(day=1) - timedelta(days=1))),
        "上月": _month(*(lambda d: (d.year, d.month))(TODAY.replace(day=1) - timedelta(days=1))),
        "這個月": _month(y, TODAY.month), "本月": _month(y, TODAY.month),
        "昨天": (TODAY - timedelta(days=1),) * 2, "今天": (TODAY, TODAY),
        "上週": (TODAY - timedelta(days=TODAY.weekday() + 7), TODAY - timedelta(days=TODAY.weekday() + 1)),
        "上禮拜": (TODAY - timedelta(days=TODAY.weekday() + 7), TODAY - timedelta(days=TODAY.weekday() + 1)),
        "這週": (TODAY - timedelta(days=TODAY.weekday()), TODAY),
        "上半年": (date(y, 1, 1), date(y, 6, 30)), "下半年": (date(y, 7, 1), date(y, 12, 31)),
    }
    for k, (a, b) in rel.items():
        if k in q2:
            out.append((k, a, b))
    for m in re.finditer(r"(?:最近|近|過去)\s*(\d+|[一二兩三四五六七八九十]+)\s*(天|日|週|周|個月)", q2):
        k = _num(m.group(1))
        days = {"天": k, "日": k, "週": 7 * k, "周": 7 * k}.get(m.group(2))
        if m.group(2) == "個月":
            s = date(TODAY.year, TODAY.month, 1)
            for _ in range(k - 1):
                s = (s - timedelta(days=1)).replace(day=1)
            out.append((m.group(0), s, TODAY))
        elif days:
            out.append((m.group(0), TODAY - timedelta(days=days - 1), TODAY))
    for m in re.finditer(r"(?:第\s*([一二三四1-4])\s*季|Q([1-4]))", q2, re.I):
        k = _num(m.group(1) or m.group(2))
        out.append((m.group(0), _month(y, 3 * k - 2)[0], _month(y, 3 * k)[1]))
    if not any(k in q2 for k, *_ in out):
        for m in re.finditer(rf"(?<![\d.]){n}\s*月(?!份?\s*(?:到|至))", q2):
            k = _num(m.group(1))
            if 1 <= k <= 12 and not q2[m.end():m.end() + 1].isdigit():
                out.append((m.group(0), *_month(y, k)))
    return out


def link(question: str) -> list[str]:
    """回傳給模型看的對照提示（每行一條）。"""
    q = question
    ql = q.lower()
    apps, countries, regions, codes, versions, rng, campaigns = _db_entities()
    hints = []
    for aid, name in apps:
        if name in q or re.search(rf"\b{aid}\b", q) or any(k in q and v == aid for k, v in APP_ALIASES.items()):
            hints.append(f"App「{name}」→ app_id = '{aid}'")
    for cc, name in countries:
        if name in q or re.search(rf"\b{cc}\b", q) or any(k in q and v == cc for k, v in COUNTRY_ALIASES.items()):
            hints.append(f"國家「{name}」→ country_code = '{cc}'")
    for r in regions:
        if r in q:
            ccs = [c for c, _ in countries if _region(c) == r]
            hints.append(f"地區「{r}」→ countries.region = '{r}'（{', '.join(ccs)}）")
    for k, v in CHANNEL_ALIASES.items():
        if re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", ql) and f"'{v}'" not in " ".join(hints):
            hints.append(f"廣告管道「{k}」→ ad_campaigns.channel = '{v}'")
    for k, v in PLATFORM_ALIASES.items():
        if k in ql and f"'{v}'" not in " ".join(hints):
            hints.append(f"平台「{k}」→ platform = '{v}'")
    for code in re.findall(r"sp-[a-z0-9-]+", ql):
        if code in codes:
            hints.append(f"短網址「{code}」→ ad_campaigns.short_code = '{code}'（{codes[code]}）")
        else:
            hints.append(f"短網址「{code}」在資料庫裡不存在")
    for v in re.findall(r"\d+\.\d+(?:\.\d+)?", q):
        hit = [(a, ver, rd) for a, ver, rd in versions if ver == v or ver.startswith(v + ".")]
        if hit and _v2():
            hints += [f"版本「{v}」→ {a} 的 {ver} 版，上線日 {rd}" for a, ver, rd in hit]
        elif hit:
            hints.append(f"版本「{v}」→ app_versions.version（{', '.join(sorted({h[0] for h in hit}))}）")
    if _v2():
        for name, code, cid in campaigns:
            if name in q:
                hints.append(f"廣告活動「{name}」→ campaign_id = {cid}（short_code = '{code}'）")
        if m := re.search(r"到\s*(\d{1,2})\s*月底", q):
            end = _month(TODAY.year, int(m.group(1)))[1]
            hints.append(f"日期「{m.group(0)}」→ 結束日 {end}")
            q = q.replace(m.group(0), " ")
    dates = resolve_dates(q)
    q_chk = re.sub(r"每(個)?(月|天|日|週|周|季|年)|上線當天|上架以來", "", q)  # 「每個月」是分組，不是日期條件
    has_date_hint = any("上線日" in h or "結束日" in h for h in hints)
    if _v2() and not dates and not has_date_hint and not re.search(r"\d{4}\s*年|月|日|天|週|周|季|年", q_chk):
        hints.append(f"問題沒有指定日期 → 查整個資料期間（{rng[0]} ~ {rng[1]}），SQL 不要加日期條件")
    for text, a, b in dates:
        note = ""
        if b.isoformat() < rng[0] or a.isoformat() > rng[1]:
            note = f"（超出資料期間 {rng[0]} ~ {rng[1]}）"
        hints.append(f"日期「{text.strip()}」→ {a} ~ {b}{note}")
    return hints


@lru_cache
def _regions():
    con = connect()
    try:
        return dict(con.execute("SELECT country_code, region FROM countries").fetchall())
    finally:
        con.close()


def _region(cc: str) -> str:
    return _regions().get(cc, "")
