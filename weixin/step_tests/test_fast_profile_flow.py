"""Fast step test: video page -> profile info -> back to video page."""
from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

import main  # noqa: E402
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

            print("[flow] avatar -> dots -> more info")
            await main.run_on_phone(
                session,
                """
import time
from ascript.android import action
action.click(140, 2140)
time.sleep(1.0)
action.click(970, 835)
time.sleep(1.3)
action.click(540, 2050)
time.sleep(1.5)
print("FAST_PROFILE_INFO_DONE")
""",
                log_sec=6,
            )

            adb = main.find_adb()
            info_path = ROOT / "screenshots" / "weixin_fast_flow_info.png"
            back_path = ROOT / "screenshots" / "weixin_fast_flow_back.png"

            print("[flow] screenshot profile info")
            subprocess.run([adb, "shell", "screencap", "-p", "/sdcard/weixin_fast_flow_info.png"], check=False)
            subprocess.run([adb, "pull", "/sdcard/weixin_fast_flow_info.png", str(info_path)], check=False)

            print("[flow] adb back x2")
            subprocess.run([adb, "shell", "input", "keyevent", "4"], check=False)
            time.sleep(0.6)
            subprocess.run([adb, "shell", "input", "keyevent", "4"], check=False)
            time.sleep(0.8)

            print("[flow] screenshot back page")
            subprocess.run([adb, "shell", "screencap", "-p", "/sdcard/weixin_fast_flow_back.png"], check=False)
            subprocess.run([adb, "pull", "/sdcard/weixin_fast_flow_back.png", str(back_path)], check=False)
            print(f"[flow] info screenshot: {info_path}")
            print(f"[flow] back screenshot: {back_path}")
            print("[flow] done")


if __name__ == "__main__":
    asyncio.run(run())
