"""Step test: from playback page, open the free-series traffic subject and collect subject info."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402
from core.collector import collect_traffic_info  # noqa: E402
from db.models import EvidenceRecord  # noqa: E402
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

            print("[flow] playback page -> free-series traffic subject -> more info")
            record = EvidenceRecord(search_keyword="traffic_test")
            await collect_traffic_info(session, record, "traffic_test")
            print("[flow] traffic info:")
            print(json.dumps(record.traffic_info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(run())
