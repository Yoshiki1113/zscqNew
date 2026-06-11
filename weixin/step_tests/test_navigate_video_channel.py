"""
单步测试：在微信发现页中点击"视频号"入口，验证是否成功进入视频号
用法: python test_navigate_video_channel.py
"""
import asyncio, json, re, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(encoding='utf-8')

PHONE_IP = "172.16.1.216"
PHONE_PORT = 9096


async def run_on_phone(session, code, log_sec=5):
    r = await session.call_tool("deploy_and_run", {
        "project_name": "zscqAndroid",
        "code": code,
        "log_seconds": log_sec,
    })
    out = {"log": "", "images": []}
    for item in r.content:
        if item.type == "text":
            out["log"] += item.text + "\n"
        elif item.type == "image":
            out["images"].append(item.data)
    return out


async def get_ui_tree(session):
    r = await session.call_tool("dump_ui_tree", {"mode": 0})
    for item in r.content:
        if item.type == "text":
            return json.loads(item.text)
    return {}


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

            # 假定手机当前已在微信发现页
            # 第一步：dump UI 树，查找"视频号"入口
            print("=" * 60)
            print("【步骤 1】在发现页查找'视频号'入口...")
            print("=" * 60)
            ui = await get_ui_tree(session)
            views = ui.get("data", {}).get("views", [])

            channel_nodes = []
            def walk(nodes):
                for n in nodes:
                    t = n.get("text", "") or ""
                    i = n.get("id", "") or ""
                    cx = n.get("center_x")
                    cy = n.get("center_y")
                    c = n.get("clickable", False)
                    if "视频号" in t and cy is not None and 300 < cy < 2500:
                        channel_nodes.append({"text": t, "id": i, "x": cx, "y": cy, "clickable": c})
                    walk(n.get("childs", []))
            walk(views)

            print(f"      找到 {len(channel_nodes)} 个含'视频号'的节点：")
            for idx, node in enumerate(channel_nodes[:10], 1):
                print(f"      [{idx}] ({node['x']}, {node['y']}) text={node['text']!r} id={node['id']!r} clickable={node['clickable']}")

            if channel_nodes:
                target = channel_nodes[0]
                cx, cy = target["x"], target["y"]
                print(f"\n[点击] 取第一个: ({cx}, {cy})")
            else:
                cx, cy = 620, 980
                print(f"\n[点击] 未找到，兜底坐标: ({cx}, {cy})")

            # 第二步：点击"视频号"
            print("\n" + "=" * 60)
            print("【步骤 2】点击'视频号'入口...")
            print("=" * 60)
            out = await run_on_phone(session, f"""
import time
from ascript.android import action
action.click({cx}, {cy})
time.sleep(1.5)
print("[OK] VIDEO_CHANNEL_CLICKED")
""", log_sec=4)
            print(f"      日志: {out['log'].strip()}")
            print("      等待页面加载...")
            await asyncio.sleep(2.0)

            # 第三步：验证是否进入视频号
            print("\n" + "=" * 60)
            print("【步骤 3】验证页面（前30个节点）...")
            print("=" * 60)
            ui2 = await get_ui_tree(session)
            views2 = ui2.get("data", {}).get("views", [])

            printed = [0]
            def _print(nodes, d=0):
                for n in nodes:
                    if printed[0] >= 30:
                        return
                    printed[0] += 1
                    t = n.get("text", "") or ""
                    i = n.get("id", "") or ""
                    ty = n.get("type", "") or ""
                    c = n.get("clickable", False)
                    cx = n.get("center_x")
                    cy = n.get("center_y")
                    info = []
                    if t: info.append(f'text="{t}"')
                    if i: info.append(f'id="{i}"')
                    if ty: info.append(f'type={ty}')
                    info.append(f'clickable={c}')
                    if cx is not None: info.append(f'x={cx},y={cy}')
                    print(f"{'  '*d}|- {' | '.join(info)}")
                    _print(n.get("childs", []), d + 1)
            _print(views2)
            print("=" * 60)

            print("\n[完成] 测试结束，请检查手机屏幕是否已进入视频号页面")


if __name__ == "__main__":
    asyncio.run(main())
