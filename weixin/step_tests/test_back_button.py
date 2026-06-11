"""
单步测试：定位并点击左上角返回按钮，验证页面是否返回上一级
用法: python test_back_button.py
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

            # 第一步：查找左上角返回按钮候选
            print("=" * 60)
            print("【步骤 1】查找左上角返回按钮候选...")
            print("=" * 60)
            ui = await get_ui_tree(session)
            views = ui.get("data", {}).get("views", [])

            candidates = []
            def walk(nodes):
                for n in nodes:
                    nid = n.get("id", "") or ""
                    if "systemui" in nid:
                        continue
                    if n.get("clickable", False):
                        cx = n.get("center_x")
                        cy = n.get("center_y")
                        if cx is not None and cy is not None and cy < 300 and cx < 300:
                            candidates.append({
                                "id": nid,
                                "type": n.get("type", ""),
                                "x": cx,
                                "y": cy,
                                "text": n.get("text", "") or "",
                            })
                    walk(n.get("childs", []))
            walk(views)
            candidates.sort(key=lambda c: c["y"])

            print(f"      找到 {len(candidates)} 个候选节点（clickable=True, y<300, x<300）：")
            for idx, c in enumerate(candidates[:10], 1):
                print(f"      [{idx}] ({c['x']}, {c['y']}) type={c['type']} id={c['id']!r} text={c['text']!r}")

            if not candidates:
                print("[✗] 没有找到候选节点")
                # 兜底
                bx, by = 90, 200
                print(f"      使用兜底坐标: ({bx}, {by})")
            else:
                target = candidates[0]
                bx, by = target["x"], target["y"]
                print(f"\n[返回] 选择最靠上的节点: ({bx}, {by})")

            # 第二步：点击
            print("\n" + "=" * 60)
            print("【步骤 2】点击返回按钮...")
            print("=" * 60)
            out = await run_on_phone(session, f"""
import time
from ascript.android import action
action.click({bx}, {by})
time.sleep(1.0)
print("[OK] BACK_CLICKED")
""", log_sec=3)
            print(f"      日志: {out['log'].strip()}")
            print("      等待页面切换...")
            await asyncio.sleep(1.5)

            # 第三步：验证返回后页面
            print("\n" + "=" * 60)
            print("【步骤 3】返回后页面（前20个节点）...")
            print("=" * 60)
            ui2 = await get_ui_tree(session)
            views2 = ui2.get("data", {}).get("views", [])

            printed = [0]
            def _print(nodes, d=0):
                for n in nodes:
                    if printed[0] >= 20:
                        return
                    printed[0] += 1
                    t = n.get("text", "") or ""
                    i = n.get("id", "") or ""
                    ty = n.get("type", "") or ""
                    cx = n.get("center_x")
                    cy = n.get("center_y")
                    info = []
                    if t: info.append(f'text="{t}"')
                    if i: info.append(f'id="{i}"')
                    if ty: info.append(f'type={ty}')
                    if cx is not None: info.append(f'x={cx},y={cy}')
                    print(f"{'  '*d}|- {' | '.join(info)}")
                    _print(n.get("childs", []), d + 1)
            _print(views2)
            print("=" * 60)

            print("\n[完成] 请检查手机屏幕确认返回是否生效")


if __name__ == "__main__":
    asyncio.run(main())
