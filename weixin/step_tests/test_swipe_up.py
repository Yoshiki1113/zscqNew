"""
单步测试：在视频播放页向上滑动加载下一个视频，验证是否切换成功
用法: python test_swipe_up.py
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


def find_visible_by_id(nodes, target_id, min_y=500, max_y=2800):
    def walk(nlist):
        for n in nlist:
            nid = n.get("id", "") or ""
            cy = n.get("center_y")
            if target_id in nid and cy is not None and min_y <= cy <= max_y:
                return n
            childs = n.get("childs", [])
            if childs:
                r = walk(childs)
                if r:
                    return r
        return None
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

            # 第一步：上滑前 dump 并记录当前页面特征
            print("=" * 50)
            print("【步骤 1】上滑前获取当前页面文本节点...")
            print("=" * 50)
            ui1 = await get_ui_tree(session)
            views1 = ui1.get("data", {}).get("views", [])

            before_texts = []
            def collect_before(nodes):
                for n in nodes:
                    t = n.get("text", "") or ""
                    cy = n.get("center_y")
                    if t and len(t) > 1 and cy and 300 < cy < 2800:
                        before_texts.append({"text": t, "y": cy, "id": n.get("id", "")})
                    collect_before(n.get("childs", []))
            collect_before(views1)
            before_texts.sort(key=lambda n: n["y"])

            print(f"      上滑前可见文本节点（前15个）：")
            for bt in before_texts[:15]:
                print(f"        y={bt['y']:4d} text={bt['text']!r} id={bt['id']!r}")

            before_snapshot = [bt["text"] for bt in before_texts[:10]]

            # 第二步：执行上滑
            print("\n" + "=" * 50)
            print("【步骤 2】执行上滑操作...")
            print("=" * 50)
            out = await run_on_phone(session, """
import time
from ascript.android import action
action.slide(600, 2200, 600, 800, 300)
time.sleep(2.0)
print("[OK] SWIPE_UP_DONE")
""", log_sec=5)
            print(f"      日志: {out['log'].strip()}")
            print("      等待页面切换...")
            await asyncio.sleep(2.0)

            # 第三步：上滑后 dump 并对比
            print("\n" + "=" * 50)
            print("【步骤 3】上滑后获取当前页面文本节点...")
            print("=" * 50)
            ui2 = await get_ui_tree(session)
            views2 = ui2.get("data", {}).get("views", [])

            after_texts = []
            def collect_after(nodes):
                for n in nodes:
                    t = n.get("text", "") or ""
                    cy = n.get("center_y")
                    if t and len(t) > 1 and cy and 300 < cy < 2800:
                        after_texts.append({"text": t, "y": cy, "id": n.get("id", "")})
                    collect_after(n.get("childs", []))
            collect_after(views2)
            after_texts.sort(key=lambda n: n["y"])

            print(f"      上滑后可见文本节点（前15个）：")
            for at in after_texts[:15]:
                print(f"        y={at['y']:4d} text={at['text']!r} id={at['id']!r}")

            after_snapshot = [at["text"] for at in after_texts[:10]]

            # 对比判断
            print("\n" + "=" * 50)
            print("【判断】上滑结果")
            print("=" * 50)
            if before_snapshot == after_snapshot:
                print("[结果] 文本完全未变化，可能未切换成功")
            else:
                changed = [i for i, (a, b) in enumerate(zip(before_snapshot, after_snapshot)) if a != b]
                print(f"[结果] 页面已变化！{len(changed)} 个节点文本不同，索引: {changed}")

            print("\n[完成] 测试结束")


if __name__ == "__main__":
    asyncio.run(main())
