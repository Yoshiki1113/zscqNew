"""
临时调试脚本：在视频列表页点击第一个视频
用法: python test_click_first_video.py
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


def print_ui_tree(nodes, depth=0, max_depth=6, max_nodes=300):
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


def walk_all_clickable(nodes):
    """遍历所有 clickable=True 的节点，返回列表"""
    res = []
    def walk(nlist):
        for n in nlist:
            if n.get("clickable", False):
                res.append(n)
            walk(n.get("childs", []))
    walk(nodes)
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
            root_views = ui.get('data', {}).get('views', [])
            print(f"[调试] UI 树根节点数量: {len(root_views)}\n")

            # 1. 打印完整 UI 树
            print("=" * 70)
            print("完整 UI 树（前 6 层，最多 300 个节点）：")
            print("=" * 70)
            print_ui_tree(root_views, max_depth=6, max_nodes=300)
            print("=" * 70)

            # 2. 列出所有 clickable 节点（按 y 排序）
            print("\n[调试] 所有 clickable=True 的节点（按 y 排序）：")
            clickable_nodes = walk_all_clickable(root_views)
            clickable_nodes.sort(key=lambda n: n.get("center_y", 9999))
            for n in clickable_nodes:
                cx = n.get("center_x")
                cy = n.get("center_y")
                t = n.get("text", "") or ""
                i = n.get("id", "") or ""
                ty = n.get("type", "") or ""
                print(f"      ({cx}, {cy}) text={t!r} id={i!r} type={ty}")

            # 3. 精确找视频卡片：id 包含 container + type=RelativeLayout + x>100（排除左侧详情区）+ y在合理范围
            print("\n[调试] 视频卡片候选（id含container、type=RelativeLayout、x>100、500<y<2500）：")
            candidates = []
            for n in clickable_nodes:
                nid = n.get("id", "") or ""
                ntype = n.get("type", "") or ""
                cx = n.get("center_x")
                cy = n.get("center_y")
                if "container" in nid and ntype == "RelativeLayout" and cx and cx > 100 and cy and 500 < cy < 2500:
                    candidates.append(n)
            candidates.sort(key=lambda n: n.get("center_y", 9999))
            for idx, n in enumerate(candidates[:10], 1):
                cx = n.get("center_x")
                cy = n.get("center_y")
                t = n.get("text", "") or ""
                i = n.get("id", "") or ""
                print(f"      [{idx}] ({cx}, {cy}) text={t!r} id={i!r}")

            # 4. 取第一个视频卡片点击
            if candidates:
                target = candidates[0]
                tx, ty = target.get("center_x"), target.get("center_y")
                print(f"\n[点击] 取第 1 个视频卡片: ({tx}, {ty})")
            else:
                tx, ty = 319, 1086
                print(f"\n[点击] 无候选，兜底坐标: ({tx}, {ty})")

            out = await run_on_phone(session, f"""
import time
from ascript.android import action
action.click({tx}, {ty})
time.sleep(0.5)
print("[OK] FIRST_VIDEO_CLICKED")
""", log_sec=3)
            print(f"[点击] 日志: {out['log'].strip()}")

            print("\n[完成] 请检查手机是否进入了视频播放页")


if __name__ == "__main__":
    asyncio.run(main())
