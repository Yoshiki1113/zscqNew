"""
单步测试：dump 当前页面完整 UI 树（增强版）
功能：
  1. 检测当前顶层 Activity
  2. 自动启动微信并导航到视频号（如需）
  3. 增大 dump 深度/节点数，尝试不同 mode
用法: python test_dump_ui_tree.py
"""
import asyncio, json, os, re, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(encoding='utf-8')

PHONE_IP = "172.16.1.216"
PHONE_PORT = 9096
WECHAT_PACKAGE = "com.tencent.mm"


async def get_ui_tree(session, mode=0):
    r = await session.call_tool("dump_ui_tree", {"mode": mode})
    for item in r.content:
        if item.type == "text":
            return json.loads(item.text)
    return {}


def print_ui_tree(nodes, depth=0, max_depth=12, max_nodes=2000):
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


async def run_on_phone(session, code, log_sec=10):
    """通过 deploy_and_run 在手机端执行代码"""
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


async def get_current_activity(session):
    """通过 dumpsys activity 获取当前顶层 Activity"""
    code = """
import subprocess, json
result = subprocess.run(
    ['dumpsys', 'activity', 'activities'],
    capture_output=True, text=True
)
lines = result.stdout.splitlines()
output = []
for line in lines[:50]:
    if 'com.tencent.mm' in line or 'mResumedActivity' in line or 'mFocusedWindow' in line:
        output.append(line.strip())
print(json.dumps(output, ensure_ascii=False))
"""
    out = await run_on_phone(session, code, log_sec=5)
    r_text = out['log']
    try:
        return json.loads(r_text)
    except Exception:
        return [r_text]
    for item in r.content:
        if item.type == "text":
            try:
                return json.loads(item.text)
            except Exception:
                return [item.text]
    return []


async def start_wechat(session):
    """启动微信到前台"""
    print("[启动] 正在启动微信...")
    code = f"""
import subprocess
subprocess.run(['am', 'start', '-n', '{WECHAT_PACKAGE}/.ui.LauncherUI'])
print('微信已启动')
"""
    await run_on_phone(session, code, log_sec=5)
    await asyncio.sleep(3)


async def click_discover_tab(session):
    """点击底部'发现'Tab（兜底坐标 x≈800, y≈2450）"""
    print("[导航] 点击发现 Tab...")
    code = """
from ascript.android import action
action.click(800, 2450)
print('点击发现 Tab')
"""
    await run_on_phone(session, code, log_sec=3)
    await asyncio.sleep(2)


async def click_video_channel(session):
    """点击发现页中的'视频号'入口（兜底坐标 x≈600, y≈500）"""
    print("[导航] 点击视频号入口...")
    code = """
from ascript.android import action
action.click(600, 500)
print('点击视频号入口')
"""
    await run_on_phone(session, code, log_sec=3)
    await asyncio.sleep(3)


async def main():
    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[MCP] 服务端已启动\n")

            if not await connect_device_auto(session):
                print("[✗] 未找到设备")
                return

            # 1. 检测当前 Activity
            print("[调试] 检测当前 Activity...")
            activity_info = await get_current_activity(session)
            for line in activity_info:
                print(f"  > {line}")
            print()

            # 2. 尝试启动微信
            await start_wechat(session)

            # 3. 导航到发现 -> 视频号
            await click_discover_tab(session)
            await click_video_channel(session)

            # 4. 再次检测 Activity
            print("\n[调试] 再次检测 Activity...")
            activity_info = await get_current_activity(session)
            for line in activity_info:
                print(f"  > {line}")
            print()

            # 5. dump UI 树（尝试 mode 0 和 mode 1）
            for mode in [0, 1]:
                print(f"\n[调试] 正在 dump UI 树（mode={mode}）...")
                ui = await get_ui_tree(session, mode=mode)
                root_views = ui.get('data', {}).get('views', [])
                print(f"[调试] UI 树根节点数量: {len(root_views)}")

                if len(root_views) > 0:
                    print("\n" + "=" * 70)
                    print(f"完整 UI 树（mode={mode}，前 12 层，最多 2000 个节点）：")
                    print("=" * 70)
                    print_ui_tree(root_views, max_depth=12, max_nodes=2000)
                    print("=" * 70)

            print("\n[完成] UI 树输出完毕")


if __name__ == "__main__":
    asyncio.run(main())
