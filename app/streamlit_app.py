"""Streamlit 聊天介面：問題 → 摘要 ＋ 表格 ＋ 圖表 ＋ 可展開的 SQL。

uv run streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from text2sql_demo.agent import ask

st.set_page_config(page_title="星芽數據小幫手", page_icon="📊", layout="centered")
st.title("📊 星芽數據小幫手")
st.caption("示範用虛構公司「星芽科技」，所有數據皆為假資料 · 本機 Qwen3-8B · 資料期間 2026-04-01 ~ 2026-09-30")

if "turns" not in st.session_state:
    st.session_state.turns = []

EXAMPLES = ["上個月各 App 的總營收", "抖音廣告 6 月到 8 月每個月的花費", "各 App 第三季的 D1 留存率"]


def render(r: dict) -> None:
    st.markdown(r["answer"])
    if r.get("rows"):
        df = pd.DataFrame(r["rows"], columns=r["columns"])
        ch = r.get("chart")
        if ch:
            x, ys = ch["x"], ch["y"]
            if ch.get("series"):
                piv = df.pivot_table(index=x, columns=ch["series"][0], values=ys[0], aggfunc="sum")
            else:
                piv = df.set_index(x)[ys]
            (st.line_chart if ch["type"] == "line" else st.bar_chart)(piv, height=260)
        st.dataframe(df, hide_index=True, use_container_width=True)
        if r.get("truncated"):
            st.caption("結果太多，只顯示前 500 列")
    meta = []
    if r.get("hints"):
        meta.append("**代碼／日期對照（程式）**\n" + "\n".join(f"- {h}" for h in r["hints"]))
    if r.get("sql"):
        meta.append(f"**SQL**\n```sql\n{r['sql']}\n```")
    if r.get("repairs"):
        meta.append(f"試跑失敗後自動修正 {r['repairs']} 次：{r['errors']}")
    if r.get("summary_retry"):
        meta.append("摘要數字檢查：第一版摘要有表格沒有的數字，已重寫" + ("（仍不通過，只給表格）" if r.get("summary_fallback") else ""))
    if meta:
        with st.expander(f"查詢細節 · {r.get('seconds', 0)} 秒"):
            st.markdown("\n\n".join(meta))


for t in st.session_state.turns:
    with st.chat_message("user"):
        st.markdown(t["question"])
    with st.chat_message("assistant"):
        render(t)

if not st.session_state.turns:
    st.markdown("可以試試：" + "、".join(f"「{e}」" for e in EXAMPLES))

q = st.chat_input("例如：上個月各 App 的總營收")
if q:
    with st.chat_message("user"):
        st.markdown(q)
    with st.chat_message("assistant"):
        with st.spinner("查詢中…"):
            hist = [{"question": t["question"], "sql": t.get("sql")} for t in st.session_state.turns[-1:]]
            r = ask(q, history=hist or None)
        render(r)
    st.session_state.turns.append(r)
