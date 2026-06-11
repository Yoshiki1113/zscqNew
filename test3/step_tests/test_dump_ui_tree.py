"""
单步测试：在当前页面 dump 完整 UI 树
用法: python test_dump_ui_tree.py
"""
import asyncio, json, os, re, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(encoding='utf-8')

PHONE_IP = "172.16.1.139"
PHONE_PORT = 9096


async def get_ui_tree(session):
    r = await session.call_tool("dump_ui_tree", {"mode": 0})
    for item in r.content:
        if item.type == "text":
            return json.loads(item.text)
    return {}


def print_ui_tree(nodes, depth=0, max_depth=8, max_nodes=500):
    printed = [0]
    def _print(n, d):
        if d > max_depth or printed[0] >= max_nodes:
            return
        printed[0] += 1
        indent = "  " * d
        t = n.get("text", "") or ""
        i = n.get("id", "") or ""
        ty = n.get("type", "") or ""
        c = n.get("clickable", False)
        cx = n.get("center_x")
        cy = n.get("center_y")
        bx = n.get("bounds")
        info = []
        if t: info.append(f'text="{t}"')
        if i: info.append(f'id="{i}"')
        if ty: info.append(f'type={ty}')
        info.append(f'clickable={c}')
        if cx is not None: info.append(f'x={cx},y={cy}')
        if bx: info.append(f'bounds={bx}')
        print(f"{indent}|- {' | '.join(info)}")
        for child in n.get("childs", []):
            _print(child, d + 1)
    for node in nodes:
        _print(node, depth)


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

            print("[调试] 正在 dump UI 树...")
            ui = await get_ui_tree(session)
            root_views = ui.get('data', {}).get('views', [])
            print(f"[调试] UI 树根节点数量: {len(root_views)}\n")

            print("=" * 70)
            print("完整 UI 树（前 8 层，最多 500 个节点）：")
            print("=" * 70)
            print_ui_tree(root_views, max_depth=8, max_nodes=500)
            print("=" * 70)
            print("\n[完成] UI 树输出完毕")


if __name__ == "__main__":
    asyncio.run(main())
