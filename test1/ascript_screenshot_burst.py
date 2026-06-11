"""
短剧视频批量截图 - 每个视频截10张，每秒1张，回传PC
用法：先手动打开快手到主页，再运行本脚本
"""
import asyncio, json, re, sys, base64, os, time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(encoding='utf-8')

DRAMA = "少爷当腻了只想好好打工"
VIDEO_COUNT = 5       # 连续看前几个视频
SHOT_COUNT = 10       # 每个视频截多少张
SHOT_INTERVAL = 1.0   # 间隔秒数

SCREENSHOT_DIR = "D:/code/vscodeWorkDir/zscqNew/test1/screenshots"

async def run(session, code, log_sec=12):
    r = await session.call_tool("deploy_and_run", {
        "project_name": "zscqAndroid",
        "code": code,
        "log_seconds": log_sec
    })
    out = {"log": "", "images": []}
    for item in r.content:
        if item.type == "text":
            out["log"] += item.text + "\n"
        elif item.type == "image":
            out["images"].append(item.data)
    return out

async def ui_tree(session):
    r = await session.call_tool("dump_ui_tree", {"mode": 0})
    for item in r.content:
        if item.type == "text":
            return json.loads(item.text)
    return {}

def walk_ui(data, keyword=None, id_sub=None, clickable=None):
    views = data.get("data", {}).get("views", [])
    res = []
    def walk(nodes, depth=0):
        for n in nodes:
            t = n.get("text", "") or ""
            i = n.get("id", "") or ""
            c = n.get("clickable", False)
            if depth > 0 or (t or i):
                ok = True
                if keyword and keyword not in t: ok = False
                if id_sub and id_sub not in i: ok = False
                if clickable is not None and c != clickable: ok = False
                if ok and (t or i):
                    res.append({
                        "text": t, "id": i, "clickable": c,
                        "x": n.get("center_x"), "y": n.get("center_y"),
                        "type": n.get("type", "")
                    })
            walk(n.get("childs", []), depth + 1)
    walk([{"childs": views}])
    return res

def tap(x, y, s=1):
    return f"""
import time
from ascript.android import action
action.click({x}, {y})
time.sleep({s})
"""

async def capture_burst(session, video_index, drama_name):
    """连续截图SHOT_COUNT张，保存到PC"""
    safe = drama_name.replace(" ", "").replace("/", "_").replace("?", "")
    for i in range(SHOT_COUNT):
        await asyncio.sleep(SHOT_INTERVAL)
        shot = await session.call_tool("screen_capture", {})
        for item in shot.content:
            if item.type == "image":
                data = base64.b64decode(item.data)
                fname = f"{safe}_v{video_index}_{i+1:02d}.png"
                path = os.path.join(SCREENSHOT_DIR, fname)
                with open(path, "wb") as f:
                    f.write(data)
                print(f"  [{video_index}.{i+1}] {fname} ({len(data)} bytes)")
            elif item.type == "text":
                print(f"  [{video_index}.{i+1}] {item.text[:80]}")

async def main():
    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool("connect_device", {"ip": "172.16.1.139", "port": 9096, "connection_mode": "LocalIP"})

            os.makedirs(SCREENSHOT_DIR, exist_ok=True)
            print(f"=== {DRAMA} - 每个视频截{SHOT_COUNT}张 ===")

            # 1. 回到快手主页
            print("[1] 回到主页")
            await run(session, """
import subprocess, time
subprocess.run(['am', 'start', '-n', 'com.kuaishou.nebula/com.yxcorp.gifshow.HomeActivity'], timeout=10)
time.sleep(4)
print("[OK] HOME")
""", 6)

            # 2. 点击搜索
            print("[2] 点击搜索")
            ui = await ui_tree(session)
            search_btns = walk_ui(ui, id_sub="top_search", clickable=True) or \
                         walk_ui(ui, id_sub="edit_btn", clickable=True) or \
                         walk_ui(ui, id_sub="thanos_home", clickable=True)
            if search_btns:
                btn = search_btns[0]
                print(f"  搜索按钮: ({btn['x']}, {btn['y']})")
                await run(session, tap(btn['x'], btn['y'], 3), 5)
            else:
                await run(session, tap(1158, 207, 3), 5)

            # 3. 输入搜索词
            print(f"[3] 输入: {DRAMA}")
            await run(session, f"""
import time
from ascript.android import action
action.click(400, 400)
time.sleep(0.5)
action.input('{DRAMA}')
time.sleep(1)
print("[OK] INPUT")
""", 8)

            # 4. 执行搜索
            print("[4] 搜索")
            await run(session, tap(900, 500, 5), 8)

            # 5. 下拉刷新
            print("[5] 下拉刷新")
            await run(session, """
import time
from ascript.android import action
action.swipe(632, 400, 632, 1000, 60)
time.sleep(3)
print("[OK] REFRESH")
""")

            # 6. 找搜索结果中的视频列表
            print(f"[6] 查找搜索结果中的视频...")
            ui = await ui_tree(session)
            candidates = (walk_ui(ui, id_sub="container", clickable=True) or
                         walk_ui(ui, id_sub="cover") or
                         walk_ui(ui, id_sub="thumb"))
            valid = [c for c in candidates if c['y'] > 400 and c['y'] < 2500]

            if not valid:
                print("  未找到视频，用默认坐标")
                valid = [{"x": 319, "y": 1079}]

            # 只取前VIDEO_COUNT个
            targets = valid[:VIDEO_COUNT]
            print(f"  找到 {len(targets)} 个视频，处理前 {len(targets)} 个")

            for idx, v in enumerate(targets):
                print(f"\n{'='*50}")
                print(f"=== 视频 {idx+1}/{len(targets)} ===")

                # 回到搜索结果页面
                if idx > 0:
                    print("  返回搜索结果...")
                    await run(session, tap(50, 200, 3), 5)

                # 点击视频
                print(f"  点击视频 ({v['x']}, {v['y']})")
                await run(session, tap(v['x'], v['y'], 3), 6)

                # 连截 SHOT_COUNT 张
                print(f"  开始连截 {SHOT_COUNT} 张...")
                await capture_burst(session, idx + 1, DRAMA)

            print(f"\n=== 完成! 共 {len(targets)} 个视频，每个 {SHOT_COUNT} 张截图 ===")
            print(f"   保存到: {SCREENSHOT_DIR}")

if __name__ == "__main__":
    asyncio.run(main())
