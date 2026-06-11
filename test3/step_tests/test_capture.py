"""
单步测试：截取当前屏幕并保存到本地
用法: python test_capture.py
"""
import asyncio, base64, json, os, re, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(encoding='utf-8')

PHONE_IP = "172.16.1.139"
PHONE_PORT = 9096
SCREENSHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


async def capture_to_local(session, prefix="test_capture"):
    shot = await session.call_tool("screen_capture", {})
    for item in shot.content:
        if item.type == "image":
            data = base64.b64decode(item.data)
            ts = int(asyncio.get_event_loop().time() * 1000) % 10000
            filename = f"{prefix}_{ts}.png"
            path = os.path.join(SCREENSHOT_DIR, filename)
            with open(path, "wb") as f:
                f.write(data)
            print(f"[截图] 已保存 {filename} ({len(data):,} bytes)")
            return filename
    print("[截图] 未收到图片数据")
    return None


async def connect_device_auto(session):
    print(f"[连接] 尝试直连 {PHONE_IP}:{PHONE_PORT} ...")
    r = await session.call_tool("connect_device", {
        "ip": PHONE_IP, "port": PHONE_PORT, "connection_mode": "LocalIP",
    })
    ok = False
    for item in r.content:
        if item.type == "text":
            if "失败" not in item.text and "fail" not in item.text.lower():
                ok = True
    if ok:
        print("[连接] 直连成功")
        return True

    print("[连接] 直连失败，开始扫描设备...")
    r = await session.call_tool("scan_devices", {"port": PHONE_PORT})
    for item in r.content:
        if item.type == "text":
            for line in item.text.split("\n"):
                m = re.search(r"IP:\s*([\d.]+):(\d+)", line)
                if m:
                    ip2, port2 = m.group(1), int(m.group(2))
                    await session.call_tool("connect_device", {
                        "ip": ip2, "port": port2, "connection_mode": "LocalIP",
                    })
                    print(f"[连接] 扫描发现设备 {ip2}:{port2}")
                    return True
    return False


async def main():
    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[MCP] 服务端已启动\n")

            if not await connect_device_auto(session):
                print("[✗] 未找到设备")
                return

            print("[截图] 正在截取当前屏幕...")
            filename = await capture_to_local(session, prefix="test_capture")
            if filename:
                print(f"\n[完成] 截图已保存: {SCREENSHOT_DIR}/{filename}")
            else:
                print("\n[✗] 截图失败")


if __name__ == "__main__":
    asyncio.run(main())
