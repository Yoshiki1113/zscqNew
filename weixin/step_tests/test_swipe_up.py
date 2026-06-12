"""
Step test: swipe up on a Weixin playback page and verify whether the next video loaded.

Usage:
    python weixin/step_tests/test_swipe_up.py
"""
import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from main import find_adb  # noqa: E402


PHONE_IP = "172.16.1.216"
PHONE_PORT = 9096


def adb_swipe_up() -> tuple[bool, str]:
    proc = subprocess.run(
        [find_adb(), "shell", "input", "swipe", "540", "2100", "540", "500", "300"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        return False, proc.stderr.strip()
    return True, proc.stdout.strip()


async def get_ui_tree(session):
    result = await session.call_tool("dump_ui_tree", {"mode": 0})
    for item in result.content:
        if item.type == "text":
            return json.loads(item.text)
    return {}


def tool_call_succeeded(result) -> bool:
    texts = [item.text for item in result.content if item.type == "text"]
    merged = "\n".join(texts).lower()
    if not merged.strip():
        return False
    if any(token in merged for token in ("fail", "error", "失败", "错误", "未连接")):
        return False
    return any(token in merged for token in ("success", "connected", "成功", "已连接", "本地端口"))


async def connect_device_auto(session):
    print(f"[connect] try direct LocalIP {PHONE_IP}:{PHONE_PORT} ...")
    result = await session.call_tool(
        "connect_device",
        {"ip": PHONE_IP, "port": PHONE_PORT, "connection_mode": "LocalIP"},
    )
    if tool_call_succeeded(result):
        print("[connect] direct LocalIP connected")
        return True

    print("[connect] direct LocalIP failed, scanning devices ...")
    result = await session.call_tool("scan_devices", {"port": PHONE_PORT})
    for item in result.content:
        if item.type != "text":
            continue
        for line in item.text.splitlines():
            if "USB(ADB)" in line:
                prefix = line.split("USB(ADB)", 1)[0]
                serial_match = re.search(r":\s*([A-Za-z0-9._:-]+)\s*$", prefix)
                if serial_match:
                    serial = serial_match.group(1)
                    print(f"[connect] try USB ADB serial {serial} ...")
                    adb_result = await session.call_tool(
                        "connect_device",
                        {"ip": serial, "connection_mode": "ADB"},
                    )
                    if tool_call_succeeded(adb_result):
                        print(f"[connect] USB ADB connected: {serial}")
                        return True

            lan_match = re.search(r"IP:\s*([\d.]+):(\d+)", line)
            if not lan_match:
                continue
            ip2, port2 = lan_match.group(1), int(lan_match.group(2))
            print(f"[connect] try scanned LocalIP {ip2}:{port2} ...")
            lan_result = await session.call_tool(
                "connect_device",
                {"ip": ip2, "port": port2, "connection_mode": "LocalIP"},
            )
            if tool_call_succeeded(lan_result):
                print(f"[connect] scanned LocalIP connected: {ip2}:{port2}")
                return True
    return False


def collect_visible_texts(ui_tree: dict) -> list[dict]:
    views = ui_tree.get("data", {}).get("views", [])
    visible = []

    def walk(nodes):
        for node in nodes:
            text = (node.get("text", "") or "").strip()
            cy = node.get("center_y")
            if text and len(text) > 1 and cy and 300 < cy < 2800:
                visible.append({"text": text, "y": cy, "id": node.get("id", "")})
            walk(node.get("childs", []))

    walk(views)
    visible.sort(key=lambda item: item["y"])
    return visible


def top_snapshot(items: list[dict], limit: int = 12) -> list[str]:
    return [item["text"] for item in items[:limit]]


async def main():
    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[MCP] server started\n")

            if not await connect_device_auto(session):
                print("[x] device not connected")
                return

            print("=" * 50)
            print("[step 1] capture visible texts before swipe")
            print("=" * 50)
            before_items = collect_visible_texts(await get_ui_tree(session))
            for item in before_items[:15]:
                print(f"  y={item['y']:4d} text={item['text']!r} id={item['id']!r}")
            before_snapshot = top_snapshot(before_items)

            print("\n" + "=" * 50)
            print("[step 2] swipe up with adb")
            print("=" * 50)
            ok, detail = adb_swipe_up()
            if not ok:
                print(f"[result] adb swipe failed: {detail}")
                return
            print("[swipe] adb swipe sent")
            await asyncio.sleep(2.5)

            print("\n" + "=" * 50)
            print("[step 3] capture visible texts after swipe")
            print("=" * 50)
            after_items = collect_visible_texts(await get_ui_tree(session))
            for item in after_items[:15]:
                print(f"  y={item['y']:4d} text={item['text']!r} id={item['id']!r}")
            after_snapshot = top_snapshot(after_items)

            print("\n" + "=" * 50)
            print("[judge] swipe result")
            print("=" * 50)
            changed = [index for index, (a, b) in enumerate(zip(before_snapshot, after_snapshot)) if a != b]
            if before_snapshot == after_snapshot:
                print("[result] no visible text change detected; likely still on the same video")
            else:
                print(f"[result] visible text changed at indexes: {changed}")
                print(f"[result] before top texts: {before_snapshot[:6]}")
                print(f"[result] after  top texts: {after_snapshot[:6]}")

            print("\n[done] swipe test finished")


if __name__ == "__main__":
    asyncio.run(main())
