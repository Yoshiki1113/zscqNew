"""Step test: search Weixin Channels with confirmed fixed coordinates."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


DEFAULT_KEYWORD = "我修仙归来把众神训成了小学生"


async def run() -> None:
    keyword = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_KEYWORD
    escaped = keyword.replace("'", "\\'")

    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[MCP] ready")
            if not await main.connect_device_auto(session):
                print("[x] device connect failed")
                return

            print(f"[search] keyword={keyword}")
            out = await main.run_on_phone(
                session,
                f"""
import time
from ascript.android import action

action.click(540, 100)
time.sleep(0.25)
action.click(885, 180)
time.sleep(0.5)
action.click(300, 210)
time.sleep(0.15)
for _ in range(20):
    action.click(957, 1703)
    time.sleep(0.01)
time.sleep(0.1)
action.input('{escaped}')
time.sleep(0.25)
action.click(950, 215)
time.sleep(1.2)
action.click(302, 350)
time.sleep(1.0)
print("[OK] SEARCH_VIDEO_TAB_READY")
""",
                log_sec=5,
            )
            print(out["log"].strip())
            print("[done] search result video tab should be visible")


if __name__ == "__main__":
    asyncio.run(run())
