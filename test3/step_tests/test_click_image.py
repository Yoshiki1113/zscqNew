"""
临时调试脚本：在当前搜索结果页点击"图片"Tab
用法: python test_click_image.py
"""
import asyncio, json, os, re, sys
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


def find_tabs_container(data):
    """递归查找 id 包含 tabs 的 HorizontalScrollView/ViewGroup"""
    views = data.get("data", {}).get("views", [])
    def walk(nodes):
        for n in nodes:
            i = n.get("id", "") or ""
            t = n.get("type", "") or ""
            if "tabs" in i.lower() and ("ScrollView" in t or "ViewGroup" in t or "View" in t):
                return n
            childs = n.get("childs", [])
            if childs:
                r = walk(childs)
                if r:
                    return r
        return None
    return walk(views)


def get_clickable_children(node):
    """获取某个节点下所有 clickable=True 的直接子节点（按 x 排序）"""
    res = []
    for c in node.get("childs", []):
        if c.get("clickable", False):
            res.append(c)
    res.sort(key=lambda n: n.get("center_x", 0))
    return res


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

            # 找 tabs 容器
            tabs_node = find_tabs_container(ui)
            if not tabs_node:
                print("[✗] 未找到 tabs 容器")
                return

            # 获取 clickable 子节点
            children = get_clickable_children(tabs_node)
            print(f"[调试] tabs 容器下 clickable 子节点共 {len(children)} 个（按 x 排序）：")
            for idx, c in enumerate(children, 1):
                cx = c.get("center_x")
                cy = c.get("center_y")
                print(f"      [{idx}] ({cx}, {cy}) type={c.get('type', '')}")

            # 点击第 3 个（图片）
            target_idx = 3
            if len(children) >= target_idx:
                target = children[target_idx - 1]
                tx, ty = target.get("center_x"), target.get("center_y")
                print(f"\n[点击] 目标 tabs[{target_idx}] = ({tx}, {ty})  ← 应该是'图片'")
            else:
                tx, ty = 592, 366
                print(f"\n[点击] 节点不足，使用兜底坐标: ({tx}, {ty})")

            out = await run_on_phone(session, f"""
import time
from ascript.android import action
action.click({tx}, {ty})
time.sleep(0.8)
print("[OK] IMAGE_TAB_CLICKED")
""", log_sec=3)
            print(f"[点击] 日志: {out['log'].strip()}")

            print("\n[完成] 请检查手机屏幕是否切换到了'图片'Tab")


if __name__ == "__main__":
    asyncio.run(main())
