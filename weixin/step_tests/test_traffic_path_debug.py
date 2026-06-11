"""Step test: debug the traffic-subject path with screenshots after each step."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


TRAFFIC_MARKER_X = 192
TRAFFIC_MARKER_Y = 1693
FIRST_EPISODE_X = 130
FIRST_EPISODE_Y = 1342
AVATAR_X = 140
AVATAR_Y = 2140
MORE_BUTTON_X = 975
MORE_BUTTON_Y = 834
MORE_INFO_X = 517
MORE_INFO_Y = 2063


def adb_capture(name: str) -> str:
    adb = main.find_adb()
    remote = f"/sdcard/{name}.png"
    local = os.path.join(main.SCREENSHOT_DIR, f"{name}.png")
    subprocess.run([adb, "shell", "screencap", "-p", remote], check=False)
    subprocess.run([adb, "pull", remote, local], check=False)
    return local


async def phone_tap(session, x: int, y: int, wait_s: float, label: str) -> None:
    print(f"[tap] {label}: ({x}, {y})")
    await main.run_on_phone(
        session,
        f"""
import time
from ascript.android import action
action.click({x}, {y})
time.sleep({wait_s})
print("[OK] TAP_DONE")
""",
        log_sec=max(4, int(wait_s) + 2),
    )


async def dump_ocr(session, label: str) -> list[dict]:
    items = await main.ocr_recognize(session)
    print(f"[ocr] {label}: {len(items)} items")
    for item in sorted(items, key=lambda x: (x.get("y", 0), x.get("x", 0)))[:40]:
        text = (item.get("text", "") or "").strip()
        if text:
            print(f"  ({item.get('x', 0)}, {item.get('y', 0)}) {text}")
    return items


async def run() -> None:
    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[MCP] ready")
            if not await main.connect_device_auto(session):
                print("[x] device connect failed")
                return

            captures = []

            print("[flow] capture starting playback page")
            captures.append(adb_capture("traffic_debug_0_start"))
            await dump_ocr(session, "start")

            await phone_tap(session, TRAFFIC_MARKER_X, TRAFFIC_MARKER_Y, 1.8, "traffic marker")
            captures.append(adb_capture("traffic_debug_1_after_marker"))
            await dump_ocr(session, "after marker")

            await phone_tap(session, FIRST_EPISODE_X, FIRST_EPISODE_Y, 3.0, "first episode")
            captures.append(adb_capture("traffic_debug_2_after_episode"))
            await dump_ocr(session, "after episode")

            await phone_tap(session, AVATAR_X, AVATAR_Y, 1.8, "avatar")
            captures.append(adb_capture("traffic_debug_3_after_avatar"))
            await dump_ocr(session, "after avatar")

            await phone_tap(session, MORE_BUTTON_X, MORE_BUTTON_Y, 1.8, "more button")
            captures.append(adb_capture("traffic_debug_4_after_more_button"))
            await dump_ocr(session, "after more button")

            await phone_tap(session, MORE_INFO_X, MORE_INFO_Y, 2.2, "more info")
            captures.append(adb_capture("traffic_debug_5_after_more_info"))
            info_items = await dump_ocr(session, "after more info")

            print("[flow] captures:")
            print(json.dumps(captures, ensure_ascii=False, indent=2))
            print("[flow] final_ocr_count:", len(info_items))


if __name__ == "__main__":
    asyncio.run(run())
