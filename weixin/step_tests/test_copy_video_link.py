"""Step test: on the playback page, copy the current video link from the share sheet."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402
from core.collector import copy_video_link  # noqa: E402
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


async def run() -> None:
    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[MCP] ready")
            if not await main.connect_device_auto(session):
                print("[x] device connect failed")
                return

            print("[flow] playback page -> share -> swipe tray -> copy link")
            link = await copy_video_link(session)
            print(f"[flow] copied link: {link!r}")


if __name__ == "__main__":
    asyncio.run(run())
