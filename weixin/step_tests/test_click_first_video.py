"""
单步测试：在视频号搜索结果页点击第一个视频卡片
用法: python test_click_first_video.py
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

            # 第一步：dump 搜索结果的 UI 树，列出所有 clickable 节点
            print("=" * 60)
            print("【步骤 1】dump UI 树，列出所有 clickable 节点...")
            print("=" * 60)
            ui = await get_ui_tree(session)
            views = ui.get("data", {}).get("views", [])

            clickable_nodes = []
            def walk(nodes):
                for n in nodes:
                    if n.get("clickable", False):
                        cx = n.get("center_x")
                        cy = n.get("center_y")
                        t = n.get("text", "") or ""
                        i = n.get("id", "") or ""
                        ty = n.get("type", "") or ""
                        if cx and cy:
                            clickable_nodes.append({"x": cx, "y": cy, "text": t, "id": i, "type": ty})
                    walk(n.get("childs", []))
            walk(views)
            clickable_nodes.sort(key=lambda n: n["y"])

            print(f"      共 {len(clickable_nodes)} 个 clickable 节点（按 y 排序）：")
            for idx, n in enumerate(clickable_nodes[:20], 1):
                print(f"      [{idx}] ({n['x']}, {n['y']}) text={n['text']!r} id={n['id']!r} type={n['type']}")

            # 第二步：查找视频卡片候选
            print("\n" + "=" * 60)
            print("【步骤 2】筛选视频卡片候选...")
            print("=" * 60)
            candidates = []
            for n in clickable_nodes:
                nid_lower = n["id"].lower()
                has_keyword = any(kw in nid_lower for kw in ["cover", "container", "card", "video", "thumb"])
                score = 1 if has_keyword else 0
                if 400 < n["y"] < 2500 and n["x"] > 100:
                    candidates.append({**n, "score": score})
            candidates.sort(key=lambda c: (-c["score"], c["y"]))

            print(f"      筛选出 {len(candidates)} 个视频卡片候选：")
            for idx, c in enumerate(candidates[:10], 1):
                print(f"      [{idx}] ({c['x']}, {c['y']}) score={c['score']} text={c['text']!r} id={c['id']!r}")

            if candidates:
                target = candidates[0]
                vx, vy = target["x"], target["y"]
                print(f"\n[点击] 取第一个候选: ({vx}, {vy})")
            else:
                vx, vy = 620, 800
                print(f"\n[点击] 无候选，兜底坐标: ({vx}, {vy})")

            # 第三步：点击
            print("\n" + "=" * 60)
            print("【步骤 3】点击视频卡片...")
            print("=" * 60)
            out = await run_on_phone(session, f"""
import time
from ascript.android import action
action.click({vx}, {vy})
time.sleep(0.5)
print("[OK] FIRST_VIDEO_CLICKED")
""", log_sec=3)
            print(f"      日志: {out['log'].strip()}")

            print("\n[完成] 请检查手机是否进入了视频播放页")


if __name__ == "__main__":
    asyncio.run(main())
