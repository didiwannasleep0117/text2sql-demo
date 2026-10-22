"""截 Streamlit 畫面（需先啟動：uv run streamlit run app/streamlit_app.py --server.port 8501 --server.headless true）。

用法：python scripts/take_screenshots.py 問題1 問題2 ...   （用裝了 playwright 的 Python 跑）
每題開新對話、截一張 docs/screenshots/chat_N.png
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
QUESTIONS = sys.argv[1:] or ["上個月各 App 的總營收"]
URL = "http://localhost:8501"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 900, "height": 1000}, device_scale_factor=2)
    for i, q in enumerate(QUESTIONS, 1):
        page.goto(URL)  # 每題開新的對話，截圖只有一問一答
        page.wait_for_selector("textarea", timeout=60000)
        page.wait_for_timeout(1500)
        n_before = 0
        page.locator("textarea").fill(q)
        page.keyboard.press("Enter")
        log("送出", q)
        # 回答完成的訊號：出現「查詢細節」展開區（每個有 SQL 的回答都有）
        page.wait_for_selector('[data-testid="stExpander"]', timeout=240000)
        page.wait_for_timeout(2500)
        page.add_style_tag(content='header[data-testid="stHeader"] { display: none !important; }')
        # 展開最新一則的「查詢細節」
        exp = page.locator('[data-testid="stExpander"] summary').last
        if exp.count():
            exp.click()
            page.wait_for_timeout(800)
        page.locator('[data-testid="stChatMessage"]').last.scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / f"chat_{i}.png"), full_page=True)
        log("截圖", f"chat_{i}.png")
    b.close()
