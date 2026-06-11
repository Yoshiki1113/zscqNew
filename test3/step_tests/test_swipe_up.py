"""
单步测试：在视频播放页向上滑动加载下一个视频
用法: python test_swipe_up.py
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

            # 上滑前获取当前博主名
            print("\n" + "=" * 50)
            print("【步骤 1】上滑前获取当前视频博主")
            print("=" * 50)
            ui1 = await get_ui_tree(session)
            views1 = ui1.get('data', {}).get('views', [])
            before_node = find_visible_by_id(views1, "user_name_text_view")
            before_name = before_node.get('text', '') if before_node else '[未找到]'
            print(f"[上滑前] 博主: {before_name!r}")

            # 执行上滑操作
            print("\n" + "=" * 50)
            print("【步骤 2】执行上滑操作")
            print("=" * 50)
            # 从屏幕底部向上滑动 (x=600, y=2200 -> y=800)，持续 300ms
            out = await run_on_phone(session, """
import time
from ascript.android import action
action.slide(600, 2200, 600, 800, 300)
time.sleep(2.0)
print("[OK] SWIPE_UP_DONE")
""", log_sec=5)
            print(f"[上滑] 日志: {out['log'].strip()}")
            print("[上滑] 等待页面切换...")
            await asyncio.sleep(2.0)

            # 上滑后获取当前博主名
            print("\n" + "=" * 50)
            print("【步骤 3】上滑后获取当前视频博主")
            print("=" * 50)
            ui2 = await get_ui_tree(session)
            views2 = ui2.get('data', {}).get('views', [])
            after_node = find_visible_by_id(views2, "user_name_text_view")
            after_name = after_node.get('text', '') if after_node else '[未找到]'
            print(f"[上滑后] 博主: {after_name!r}")

            # 判断是否切换成功
            print("\n" + "=" * 50)
            print("【判断】上滑结果")
            print("=" * 50)
            if before_name == after_name:
                print(f"[结果] 博主未变化，可能仍在同一视频或未加载成功")
            else:
                print(f"[结果] 视频已切换！")
                print(f"       之前: {before_name!r}")
                print(f"       现在: {after_name!r}")

            print("\n[完成] 测试结束")


if __name__ == "__main__":
    asyncio.run(main())
