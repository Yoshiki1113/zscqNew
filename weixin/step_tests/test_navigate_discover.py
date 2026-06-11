"""
单步测试：从微信首页点击底部"发现"Tab，验证是否成功切换到发现页
用法: python test_navigate_discover.py
"""
import asyncio, json, re, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(encoding='utf-8')

PHONE_IP = "172.16.1.216"
PHONE_PORT = 9096
WECHAT_PACKAGE = "com.tencent.mm"
WECHAT_ACTIVITY = "com.tencent.mm/.ui.LauncherUI"


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

            # 第一步：启动微信到首页
            print("=" * 60)
            print("【步骤 1】启动微信...")
            print("=" * 60)
            out = await run_on_phone(session, f"""
import subprocess, time
subprocess.run(['am', 'start', '-n', '{WECHAT_ACTIVITY}'], timeout=5)
time.sleep(2.0)
print("[OK] WECHAT_LAUNCHED")
""", log_sec=5)
            print(f"      日志: {out['log'].strip()}")

            # 第二步：dump UI 树，查找"发现"Tab
            print("\n" + "=" * 60)
            print("【步骤 2】查找底部'发现'Tab...")
            print("=" * 60)
            ui = await get_ui_tree(session)
            views = ui.get("data", {}).get("views", [])

            # 遍历查找含"发现"文本且坐标在底部区域的节点
            discover_nodes = []
            def walk(nodes):
                for n in nodes:
                    t = n.get("text", "") or ""
                    i = n.get("id", "") or ""
                    cx = n.get("center_x")
                    cy = n.get("center_y")
                    c = n.get("clickable", False)
                    if "发现" in t and cy is not None and cy > 2000:
                        discover_nodes.append({"text": t, "id": i, "x": cx, "y": cy, "clickable": c})
                    walk(n.get("childs", []))
            walk(views)

            print(f"      找到 {len(discover_nodes)} 个含'发现'的底部节点：")
            for idx, node in enumerate(discover_nodes[:10], 1):
                print(f"      [{idx}] ({node['x']}, {node['y']}) text={node['text']!r} id={node['id']!r} clickable={node['clickable']}")

            if discover_nodes:
                target = discover_nodes[0]
                dx, dy = target["x"], target["y"]
                print(f"\n[点击] 取第一个: ({dx}, {dy})")
            else:
                dx, dy = 810, 2730
                print(f"\n[点击] 未找到，兜底坐标: ({dx}, {dy})")

            # 第三步：点击"发现"Tab
            print("\n" + "=" * 60)
            print("【步骤 3】点击'发现'Tab...")
            print("=" * 60)
            out = await run_on_phone(session, f"""
import time
from ascript.android import action
action.click({dx}, {dy})
time.sleep(1.5)
print("[OK] DISCOVER_CLICKED")
""", log_sec=3)
            print(f"      日志: {out['log'].strip()}")

            # 第四步：验证是否进入发现页
            print("\n" + "=" * 60)
            print("【步骤 4】验证页面（前30个可见节点）...")
            print("=" * 60)
            ui2 = await get_ui_tree(session)
            views2 = ui2.get("data", {}).get("views", [])

            discover_features = ["朋友圈", "视频号", "扫一扫", "搜一搜"]
            found_features = []
            def check(nodes):
                for n in nodes:
                    t = n.get("text", "") or ""
                    for feat in discover_features:
                        if feat in t:
                            found_features.append(feat)
                    check(n.get("childs", []))
            check(views2)

            if found_features:
                print(f"      [成功] 已进入发现页！识别到特征: {found_features}")
            else:
                print("      [判断] 未识别到发现页特征，请检查手机屏幕")

            print("\n[完成] 测试结束")


if __name__ == "__main__":
    asyncio.run(main())
