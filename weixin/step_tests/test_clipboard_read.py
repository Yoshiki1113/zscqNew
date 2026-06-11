"""Test whether AScript can read the Android clipboard."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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

            out = await main.run_on_phone(
                session,
                """
try:
    from ascript.android.system import Clipboard
    print("CLIPBOARD1:" + str(Clipboard.get()))
except Exception as e:
    print("ERR1:" + repr(e))

try:
    from ascript.android import system
    print("CLIPBOARD2:" + str(system.get_clipboard()))
except Exception as e:
    print("ERR2:" + repr(e))

try:
    from android.content import Context
    from com.aojoy.airscript import Globals
    ctx = Globals.getContext()
    cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE)
    clip = cm.getPrimaryClip()
    txt = ""
    if clip and clip.getItemCount() > 0:
        txt = str(clip.getItemAt(0).coerceToText(ctx))
    print("CLIPBOARD3:" + txt)
except Exception as e:
    print("ERR3:" + repr(e))
""",
                log_sec=5,
            )
            print(out["log"])


if __name__ == "__main__":
    asyncio.run(run())
