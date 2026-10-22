"""MCP 端到端：要先啟動 uv run text2sql-mcp。沒啟動就跳過。

uv run python -m pytest -q tests/test_mcp_client.py
"""
import asyncio
import json

import httpx
import pytest

URL = "http://127.0.0.1:8002/mcp"


def _up() -> bool:
    try:
        httpx.get(URL, timeout=2)
        return True
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _up(), reason="text2sql-mcp 沒有啟動")


async def _call(tool: str, args: dict) -> str:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    async with streamablehttp_client(URL) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool(tool, args)
            return res.content[0].text


def call(tool, **args):
    return asyncio.run(_call(tool, args))


def test_tools_listed():
    async def _list():
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        async with streamablehttp_client(URL) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return sorted(t.name for t in (await s.list_tools()).tools)
    assert asyncio.run(_list()) == ["ask_metrics", "calculate", "describe_schema", "resolve_entities", "run_sql"]


def test_low_level_flow():
    hints = call("resolve_entities", question="抖音廣告上個月的花費")
    assert "'TikTok'" in hints and "2026-08-01" in hints
    out = json.loads(call("run_sql", sql="SELECT ROUND(SUM(spend_usd), 2) FROM campaign_daily JOIN ad_campaigns "
                                         "USING(campaign_id) WHERE channel='TikTok' AND date BETWEEN '2026-08-01' AND '2026-08-31'"))
    assert out["row_count"] == 1 and out["rows"][0][0] > 0


def test_run_sql_blocks_writes():
    assert "error" in json.loads(call("run_sql", sql="DELETE FROM apps"))
    assert "error" in json.loads(call("run_sql", sql="WITH x AS (SELECT 1) DELETE FROM apps"))


def test_calculate():
    assert call("calculate", expression="(5210.79 - 7560.95) / 7560.95 * 100").endswith("= -31.082867")
