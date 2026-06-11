"""
Kuaishou short drama auto scanner - optimized for speed
Usage: conda run -n zscq python main.py <task_id>
"""
import asyncio, json, re, sys, base64, os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(encoding='gbk')

# ========== Config ==========
PHONE_IP = os.environ.get("ASCRIPT_IP", "172.16.1.139")
PHONE_PORT = int(os.environ.get("ASCRIPT_PORT", "9096"))

DRAMA_LIST = [
    "闪婚后被大佬宠上天",
    "我的医妃不好惹",
    "我在80年代当后妈",
    "少爷当腻了只想好好打工",
]

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# ========== Faster helpers ==========

async def run_on_phone(session, code, log_sec=10):
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

async def get_ui_tree(session):
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

# ========== Fast batch ops (fewer deploy_and_run calls) ==========

async def go_home(session):
    """Go home via am start"""
    print("  [go home]")
    return await run_on_phone(session, """
import subprocess, time
subprocess.run(['am', 'start', '-n', 'com.kuaishou.nebula/com.yxcorp.gifshow.HomeActivity'], timeout=5)
time.sleep(2)
print("[OK] HOME")
""", log_sec=4)

async def search_drama_fast(session, drama_name):
    """Search a drama - batched into ONE deploy_and_run"""
    # First find search button via UI tree
    ui = await get_ui_tree(session)
    search_btns = (walk_ui(ui, id_sub="top_search", clickable=True) or
                   walk_ui(ui, id_sub="edit_btn", clickable=True) or
                   walk_ui(ui, id_sub="thanos_home", clickable=True))
    if search_btns:
        sx, sy = search_btns[0]['x'], search_btns[0]['y']
    else:
        sx, sy = 1158, 207

    # Get search field position from UI tree
    ui2 = await get_ui_tree(session)  # refresh after click
    # The search page might have loaded, find the actual EditText
    input_box = None
    views = ui2.get("data", {}).get("views", [])
    def find_input(nodes):
        for n in nodes:
            if n.get("type") == "EditText" and n.get("editable"):
                return n
            for c in n.get("childs", []):
                r = find_input([c])
                if r:
                    return r
        return None
    input_node = find_input(views)

    # Batch: click search, click input field, type, search, refresh
    code = f"""
import time
from ascript.android import action

# click search button
action.click({sx}, {sy})
time.sleep(0.8)

# click input field
{f"action.click({input_node['center_x']}, {input_node['center_y']}); time.sleep(0.3)" if input_node else "action.click(400, 400); time.sleep(0.3)"}
action.input('{drama_name}')
time.sleep(0.5)

# press search on keyboard (coord varies, try center-right area)
action.click(900, 600)
time.sleep(2)

# pull down refresh
action.swipe(632, 400, 632, 1000, 40)
time.sleep(2)
print("[OK] SEARCH_DONE")
"""
    await run_on_phone(session, code, log_sec=8)

async def find_videos_fast(session):
    """Get video candidates from UI tree"""
    ui = await get_ui_tree(session)
    candidates = (walk_ui(ui, id_sub="container", clickable=True) or
                  walk_ui(ui, id_sub="cover") or
                  walk_ui(ui, id_sub="thumb"))
    return [c for c in candidates if c['y'] > 400 and c['y'] < 2500]

async def capture_burst(session, count=10, interval=0.5, prefix="shot"):
    """Fast burst capture"""
    for i in range(count):
        await asyncio.sleep(interval)
        shot = await session.call_tool("screen_capture", {})
        for item in shot.content:
            if item.type == "image":
                data = base64.b64decode(item.data)
                path = os.path.join(SCREENSHOT_DIR, f"{prefix}_{i+1:02d}.png")
                with open(path, "wb") as f:
                    f.write(data)
                print(f"    [{i+1}/{count}] {os.path.basename(path)} ({len(data)} bytes)")

async def click_video_fast(session, x, y):
    """Click a video and wait briefly"""
    return await run_on_phone(session, f"""
import time
from ascript.android import action
action.click({x}, {y})
time.sleep(2)
print("[OK] VIDEO")
""", log_sec=4)

async def go_back(session):
    """Quick back"""
    return await run_on_phone(session, """
import time
from ascript.android import action
action.click(50, 200)
time.sleep(1.5)
print("[OK] BACK")
""", log_sec=3)

# ========== Tasks ==========

async def task_check_connection(session):
    print("\n" + "="*50)
    print("Task 0: Connection test")
    print("="*50)
    r = await session.call_tool("get_device_status", {})
    for item in r.content:
        if item.type == "text":
            txt = item.text.strip()
            brace = txt.find("{")
            if brace >= 0:
                txt = txt[brace:]
            info = json.loads(txt)
            dev = info["device"]
            sys_info = info["system"]
            screen = info["screen"]
            print(f"  Device: {dev['full_name']}")
            print(f"  OS: Android {sys_info['android_version']}")
            print(f"  Screen: {screen['width_px']}x{screen['height_px']}")
            print(f"  Battery: {info['battery']['level']}%")
            print(f"  Status: OK")

async def task_quick_scan(session):
    """Task 1: Fast scan - search, screenshot, extract author"""
    print("\n" + "="*50)
    print("Task 1: Quick scan all dramas")
    print("="*50)

    for name in DRAMA_LIST:
        print(f"\n--- {name} ---")
        await go_home(session)
        await search_drama_fast(session, name)
        videos = await find_videos_fast(session)

        if not videos:
            print("  no videos found")
            continue

        v = videos[0]
        print(f"  click video ({v['x']}, {v['y']})")
        await click_video_fast(session, v['x'], v['y'])

        print(f"  capture 3 shots...")
        safe = name.replace(" ", "").replace("/", "_")
        await capture_burst(3, 0.5, safe)

        # find author
        ui = await get_ui_tree(session)
        nodes = walk_ui(ui)
        author_pos = None
        for n in nodes:
            if '@' in n['text'] or 'user_name' in n['id']:
                author_pos = (n['x'], n['y'])
                break
        if not author_pos:
            for n in nodes:
                if n['y'] > 2000 and n['clickable']:
                    author_pos = (n['x'], n['y'])
                    break

        if author_pos:
            print(f"  click author at ({author_pos[0]}, {author_pos[1]})")
            await click_video_fast(session, author_pos[0], author_pos[1])
            # extract kuaishou ID
            ui2 = await get_ui_tree(session)
            kw_nodes = walk_ui(ui2, keyword="快手号")
            if not kw_nodes:
                kw_nodes = walk_ui(ui2, id_sub="profile")
            found = "N/A"
            for n in kw_nodes:
                m = re.search(r'[：:]\s*(\S+)', n['text'])
                if m:
                    found = m.group(1).strip()
                    break
                txt = n['text'].strip()
                if txt and len(txt) < 30 and txt != "快手号":
                    found = txt
            print(f"  >>> Author ID: {found}")
            await go_back(session)
        else:
            print("  >>> author not found")

async def task_burst_scan(session):
    """Task 2: Fast burst scan"""
    name = "少爷当腻了只想好好打工"
    video_count = 3
    shot_count = 5

    print("\n" + "="*50)
    print(f"Task 2: [{name}] x{video_count} videos, {shot_count} shots each")
    print("="*50)

    await go_home(session)
    await search_drama_fast(session, name)
    videos = await find_videos_fast(session)
    videos = videos[:video_count]
    print(f"  found {len(videos)} videos")

    for idx, v in enumerate(videos):
        print(f"\n  video {idx+1}/{len(videos)}")
        if idx > 0:
            await go_back(session)
        await click_video_fast(session, v['x'], v['y'])
        safe_name = name.replace(" ", "").replace("/", "_")
        await capture_burst(shot_count, 0.5, f"{safe_name}_v{idx+1}")

async def task_screenshot_test(session):
    """Task 3: 5 quick screenshots"""
    print("\n" + "="*50)
    print("Task 3: Screenshot test")
    print("="*50)
    await capture_burst(5, 0.5, "test_capture")

async def task_show_ui(session):
    """Task 4: Show UI tree"""
    print("\n" + "="*50)
    print("Task 4: UI tree snapshot")
    print("="*50)
    ui = await get_ui_tree(session)
    all_nodes = walk_ui(ui)
    for n in all_nodes[:30]:
        if n['text']:
            print(f"  [{n['type']}] '{n['text'][:50]}' ({n['x']},{n['y']}) clickable={n['clickable']}")

# ========== Main ==========

TASKS = {
    "0": ("Test connection", task_check_connection),
    "1": ("Quick scan (search->screenshot->author)", task_quick_scan),
    "2": ("Burst screenshots", task_burst_scan),
    "3": ("Screenshot test", task_screenshot_test),
    "4": ("Show UI tree", task_show_ui),
}

async def main():
    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])

    print("="*50)
    print("  Kuaishou Short Drama Scanner")
    print("="*50)
    print(f"  Phone: {PHONE_IP}:{PHONE_PORT}")
    print("="*50)
    print()

    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # connect with auto-scan fallback
            ok = False
            r = await session.call_tool("connect_device", {
                "ip": PHONE_IP, "port": PHONE_PORT, "connection_mode": "LocalIP"
            })
            for item in r.content:
                if item.type == "text":
                    if "失败" not in item.text and "fail" not in item.text.lower():
                        ok = True
            if not ok:
                print("  scanning for device...")
                r = await session.call_tool("scan_devices", {"port": PHONE_PORT})
                for item in r.content:
                    if item.type == "text":
                        for line in item.text.split("\n"):
                            if "IP:" in line:
                                m = re.search(r"IP:\s*([\d.]+):(\d+)", line)
                                if m:
                                    ip2, port2 = m.group(1), int(m.group(2))
                                    await session.call_tool("connect_device", {
                                        "ip": ip2, "port": port2, "connection_mode": "LocalIP"
                                    })
                                    globals()["PHONE_IP"] = ip2
                                    globals()["PHONE_PORT"] = port2
                                    break
                        break

            if len(sys.argv) < 2 or sys.argv[1] not in TASKS:
                print("Commands:")
                for k, (desc, _) in TASKS.items():
                    print(f"  python main.py {k}  - {desc}")
                return

            task_id = sys.argv[1]
            task_name, task_func = TASKS[task_id]
            print(f"Running: {task_name}")
            await task_func(session)
            print(f"\nDone! Screenshots: {SCREENSHOT_DIR}")

if __name__ == "__main__":
    asyncio.run(main())
