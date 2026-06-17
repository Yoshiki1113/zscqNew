"""Step test: capture the current playback page and crop the traffic-marker region."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402
from core.collector import capture_single  # noqa: E402
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


LEFT = 66
TOP = 1635
RIGHT = 666
BOTTOM = 1721


def crop_region(src_path: str, dst_path: str) -> bool:
    img = cv2.imread(src_path)
    if img is None:
        return False
    region = img[TOP:BOTTOM, LEFT:RIGHT]
    if region.size == 0:
        return False
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    return bool(cv2.imwrite(dst_path, region))


async def run() -> None:
    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[MCP] ready")
            if not await main.connect_device_auto(session):
                print("[x] device connect failed")
                return

            full_path = os.path.join(main.SCREENSHOT_DIR, "traffic_region_debug_full.png")
            region_path = os.path.join(main.SCREENSHOT_DIR, "traffic_region_debug_crop.png")

            print("[flow] capture current screen")
            ok = await capture_single(session, full_path)
            print(f"[flow] full screenshot ok={ok} path={full_path}")
            if not ok:
                return

            crop_ok = crop_region(full_path, region_path)
            print(f"[flow] crop region ok={crop_ok} path={region_path}")
            print(f"[flow] region bounds=({LEFT},{TOP})-({RIGHT},{BOTTOM})")


if __name__ == "__main__":
    asyncio.run(run())
