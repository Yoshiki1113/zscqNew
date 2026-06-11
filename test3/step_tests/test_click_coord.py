"""
单步测试：点击指定坐标并验证页面变化
用法: python test_click_coord.py
"""
import asyncio, json, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(encoding='utf-8')

PHONE_IP = "172.16.1.139"
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


def has_node(nodes, id_sub):
    def walk(nlist):
        for n in nlist:
            if id_sub in (n.get("id", "") or ""):
                return True
            if walk(n.get("childs", [])):
                return True
        return False
    return walk(nodes)


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
                import re
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

            # 点击指定坐标
            bx, by = 1159, 1055
            print(f"\n[点击] 坐标: ({bx}, {by})")
            out = await run_on_phone(session, f"""
import time
from ascript.android import action
action.click({bx}, {by})
time.sleep(1.0)
print("[OK] CLICKED")
""", log_sec=3)
            print(f"[点击] 日志: {out['log'].strip()}")

            print("[点击] 等待页面切换...")
            await asyncio.sleep(1.5)

            # dump UI 树验证
            print("\n" + "=" * 60)
            print("【验证】点击后页面 UI 树（前30行）")
            print("=" * 60)
            ui = await get_ui_tree(session)
            views = ui.get('data', {}).get('views', [])

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
            _print(views)
            print("=" * 60)

            if has_node(views, "user_name_text_view"):
                print("\n[判断] 已回到视频播放页")
            elif has_node(views, "user_name_tv"):
                print("\n[判断] 仍在博主主页")
            else:
                print("\n[判断] 页面已变化，请从 UI 树确认")

            print("\n[完成]")


if __name__ == "__main__":
    asyncio.run(main())
