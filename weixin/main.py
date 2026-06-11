"""
Weixin video monitor.

Flow:
1. Assume the user is already on the Weixin video page.
2. Search the target keyword.
3. Switch to the "视频" tab in the search results.
4. Open the first video in the top-left.
5. Collect evidence from the current video page.
6. Open author info by avatar -> three dots -> more info.
7. Return to the video page and swipe to the next video.
"""
import asyncio
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.stdout.reconfigure(encoding="utf-8")
sys.modules.setdefault("main", sys.modules[__name__])

PHONE_IP = "172.16.1.216"
PHONE_PORT = 9096
WECHAT_ACTIVITY = "com.tencent.mm/.ui.LauncherUI"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENSHOT_DIR = os.path.join(BASE_DIR, "screenshots")
JSONS_DIR = os.path.join(BASE_DIR, "jsons")
DEFAULT_KEYWORD = "我修仙归来把众神训成了小学生"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(JSONS_DIR, exist_ok=True)


DEFAULT_SCRCPY_DIR = r"D:\software\scrcpy-win64-v3.3.3"


def find_adb():
    path = shutil.which("adb")
    if path:
        return path
    local = os.path.join(DEFAULT_SCRCPY_DIR, "adb.exe")
    return local if os.path.exists(local) else "adb"


def get_phone_wlan_ip_via_adb():
    adb = find_adb()
    proc = subprocess.run(
        [adb, "shell", "ip", "addr", "show", "wlan0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        return ""
    match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/", proc.stdout)
    return match.group(1) if match else ""


def env_int(name, default):
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        print(f"[config] ignore invalid {name}={raw!r}, use {default}")
        return default
    return value if value > 0 else default


def env_bool(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


async def run_on_phone(session, code, log_sec=10):
    """Run a short script on the phone and return combined logs/images."""
    r = await session.call_tool(
        "deploy_and_run",
        {"project_name": "zscqAndroid", "code": code, "log_seconds": log_sec},
    )
    out = {"log": "", "images": []}
    for item in r.content:
        if item.type == "text":
            out["log"] += item.text.encode("utf-8", "replace").decode("utf-8") + "\n"
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
    results = []
    views = data.get("data", {}).get("views", []) if isinstance(data, dict) else data

    def walk(nodes):
        for n in nodes:
            match = True
            text = n.get("text", "") or ""
            desc = n.get("desc", "") or ""
            if keyword and keyword not in text and keyword not in desc:
                match = False
            if id_sub and id_sub not in (n.get("id", "") or ""):
                match = False
            if clickable is not None and n.get("clickable") != clickable:
                match = False
            if match:
                results.append(
                    {
                        "x": n.get("center_x", 0),
                        "y": n.get("center_y", 0),
                        "id": n.get("id", ""),
                        "text": text,
                    }
                )
            walk(n.get("childs", []))

    walk(views)
    return results


async def connect_device_auto(session):
    print(f"[连接] 尝试直连 {PHONE_IP}:{PHONE_PORT} ...")
    r = await session.call_tool(
        "connect_device",
        {"ip": PHONE_IP, "port": PHONE_PORT, "connection_mode": "LocalIP"},
    )
    ok = any(
        "失败" not in c.text and "fail" not in c.text.lower()
        for c in r.content
        if c.type == "text"
    )
    if ok:
        print("[连接] 直连成功")
        return True

    adb_ip = get_phone_wlan_ip_via_adb()
    if adb_ip and adb_ip != PHONE_IP:
        print(f"[连接] 尝试 ADB 发现的当前 IP {adb_ip}:{PHONE_PORT} ...")
        r = await session.call_tool(
            "connect_device",
            {"ip": adb_ip, "port": PHONE_PORT, "connection_mode": "LocalIP"},
        )
        ok = any(
            "失败" not in c.text and "fail" not in c.text.lower()
            for c in r.content
            if c.type == "text"
        )
        if ok:
            print(f"[连接] ADB 当前 IP 直连成功: {adb_ip}:{PHONE_PORT}")
            return True

    print("[连接] 直连失败，扫描设备中...")
    r = await session.call_tool("scan_devices", {"port": PHONE_PORT})
    for item in r.content:
        if item.type != "text":
            continue
        for line in item.text.split("\n"):
            m = re.search(r"IP:\s*([\d.]+):(\d+)", line)
            if not m:
                continue
            ip2, port2 = m.group(1), int(m.group(2))
            await session.call_tool(
                "connect_device",
                {"ip": ip2, "port": port2, "connection_mode": "LocalIP"},
            )
            print(f"[连接] 扫描发现设备 {ip2}:{port2}")
            return True
    return False


async def ensure_wechat_home(session):
    await run_on_phone(
        session,
        f"""
import subprocess, time
subprocess.run(['am', 'start', '-n', '{WECHAT_ACTIVITY}'], timeout=5)
time.sleep(2.0)
print("[OK] WECHAT_LAUNCHED")
""",
        log_sec=5,
    )


async def navigate_to_discover(session):
    await run_on_phone(
        session,
        """
import time
from ascript.android import action, node
discover = node.Selector().text("发现").find()
if discover:
    discover.click()
else:
    action.click(810, 2730)
time.sleep(1.0)
print("[OK] DISCOVER")
""",
        log_sec=4,
    )


async def navigate_to_video_channel(session):
    await run_on_phone(
        session,
        """
import time
from ascript.android import action, node
vc = node.Selector().text("视频号").find()
if vc:
    vc.click()
else:
    action.click(620, 980)
time.sleep(1.5)
print("[OK] VIDEO_CHANNEL")
""",
        log_sec=4,
    )


async def search_keyword(session, keyword):
    """Search a keyword from the current video page."""
    print(f"[搜索] {keyword}")
    escaped = keyword.replace("'", "\\'")

    for retry in range(2):
        print(f"  [输入] 第{retry + 1}轮...")
        await run_on_phone(
            session,
            f"""
import time
from ascript.android import action
action.click(540, 100)
time.sleep(0.5)
action.click(875, 184)
time.sleep(1.5)
action.click(300, 210)
time.sleep(0.3)
for _ in range(20):
    action.click(957, 1703)
    time.sleep(0.02)
time.sleep(0.3)
action.input('{escaped}')
time.sleep(0.5)
print("[OK] INPUT_DONE")
""",
            log_sec=8,
        )

        await run_on_phone(
            session,
            """
import time
from ascript.android import action, node
submitted = False
try:
    btn = node.Selector().text("搜索").find()
    if btn:
        btn.click()
        submitted = True
        print("[OK] SUBMIT_SELECTOR")
except Exception as e:
    print(f"[~] SUBMIT_SELECTOR_ERR: {e}")
time.sleep(0.5)
if not submitted:
    action.click(950, 210)
    time.sleep(0.5)
    action.click(960, 2550)
    time.sleep(0.5)
    print("[OK] SUBMIT_COORD")
""",
            log_sec=5,
        )

        ok = await wait_for_search_results(session, keyword)
        if ok:
            print(f"  [搜索] 第{retry + 1}轮成功进入结果页")
            return True
        print(f"  [搜索] 第{retry + 1}轮未进入结果页，重试...")

    print("[搜索] 失败：无法进入搜索结果页")
    return False


async def go_back(session):
    subprocess.run(
        [find_adb(), "shell", "input", "keyevent", "4"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    await asyncio.sleep(0.8)
    print("[OK] ADB_BACK")


async def swipe_up(session):
    await run_on_phone(
        session,
        """
import time
from ascript.android import action
action.swipe(540, 2000, 540, 400, 300)
time.sleep(0.8)
print("[OK] SWIPED")
""",
        log_sec=5,
    )


async def ocr_recognize(session, engine="paddle"):
    """OCR the current phone screen."""
    code = f'''
from ascript.android.screen import Ocr
import json
Ocr.set_engine("{engine}")
results = Ocr.ocr()
output = []
for item in results:
    if isinstance(item, dict):
        text = item.get("text", "")
        if "box" in item:
            box = item["box"]
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            x, y = int(sum(xs)/len(xs)), int(sum(ys)/len(ys))
            w, h = max(xs) - min(xs), max(ys) - min(ys)
        else:
            x = item.get("x", item.get("center_x", 0))
            y = item.get("y", item.get("center_y", 0))
            w = item.get("w", 0)
            h = item.get("h", 0)
    elif isinstance(item, (list, tuple)) and len(item) >= 2:
        box = item[0]
        text_info = item[1]
        text = str(text_info[0] if isinstance(text_info, (list, tuple)) else text_info)
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        x, y = int(sum(xs)/len(xs)), int(sum(ys)/len(ys))
        w, h = max(xs) - min(xs), max(ys) - min(ys)
    else:
        text = str(item)
        x = y = w = h = 0
    output.append({{"text": text, "x": x, "y": y, "w": w, "h": h}})
print("OCR_START")
print(json.dumps(output, ensure_ascii=False))
print("OCR_END")
'''
    out = await run_on_phone(session, code, log_sec=15)
    log = out["log"]
    s = log.find("OCR_START")
    e = log.find("OCR_END")
    if s >= 0 and e > s:
        return json.loads(log[s + 9 : e].strip())
    return []


async def capture_to_local(session, count=5, interval=0.8, prefix="cap"):
    paths = []
    for i in range(count):
        ts = datetime.now().strftime("%H%M%S")
        path = os.path.join(SCREENSHOT_DIR, f"{prefix}_{ts}_{i}.png")
        ok = await capture_single(session, path)
        if ok:
            paths.append(path)
        await asyncio.sleep(interval)
    return paths


async def capture_series(session, keyword, blogger_name, screenshot_dir, count=10, interval=1.0):
    safekey = re.sub(r'[\\/:*?"<>|]', "_", keyword)[:20]
    safename = re.sub(r'[\\/:*?"<>|]', "_", blogger_name)[:20]
    ts = datetime.now().strftime("%m%d_%H%M")
    subdir = os.path.join(screenshot_dir, f"{ts}_{safekey}_{safename}")
    os.makedirs(subdir, exist_ok=True)
    paths = []
    for i in range(count):
        path = os.path.join(subdir, f"{i:02d}.png")
        ok = await capture_single(session, path)
        if ok:
            paths.append(path)
        await asyncio.sleep(interval)
    return subdir, paths


def parse_ocr_video_info(ocr_results):
    info = {"blogger_name": "", "title": "", "like_count": "", "comment_count": "", "share_count": ""}
    if not ocr_results:
        return info
    for r in ocr_results:
        text = r.get("text", "")
        if "关注" in text or "+关注" in text:
            info["blogger_name"] = text.replace("+关注", "").replace("关注", "").strip()
        if not info["title"] and len(text) > 10 and 500 < r.get("y", 0) < 2200:
            info["title"] = text
    numbers = []
    for r in ocr_results:
        m = re.search(r"([\d.]+[万wW]?)", r.get("text", ""))
        if m:
            numbers.append(m.group(1))
    if len(numbers) >= 1:
        info["like_count"] = numbers[0]
    if len(numbers) >= 2:
        info["comment_count"] = numbers[1]
    if len(numbers) >= 3:
        info["share_count"] = numbers[2]
    return info


def save_video_info(keyword, record):
    os.makedirs(JSONS_DIR, exist_ok=True)
    path = os.path.join(JSONS_DIR, f"info_{datetime.now().strftime('%m%d_%H%M%S')}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    print(f"[保存] 视频信息已保存: {path}")


async def read_video_info(session):
    ocr_results = await ocr_recognize(session)
    return parse_ocr_video_info(ocr_results), ""


async def enter_profile(session):
    """From the video page: avatar -> three dots -> more info."""
    await run_on_phone(
        session,
        """
import time
from ascript.android import action, node
action.click(140, 2140)
time.sleep(1.2)
action.click(970, 835)
time.sleep(0.8)
more_info = None
try:
    more_info = node.Selector().text("更多信息").find()
except Exception:
    more_info = None
if more_info:
    more_info.click()
else:
    action.click(540, 2050)
time.sleep(1.5)
print("[OK] PROFILE_INFO_ENTERED")
""",
        log_sec=6,
    )
    await asyncio.sleep(1.5)


async def read_profile_info(session):
    ocr_results = await ocr_recognize(session)
    return parse_ocr_video_info(ocr_results), ocr_results


async def enter_profile(session):
    """From the video page: avatar -> three dots -> more info, with safe waits."""
    await run_on_phone(
        session,
        """
import time
from ascript.android import action
action.click(140, 2140)
time.sleep(1.5)
action.click(970, 835)
time.sleep(1.8)
action.click(540, 2050)
time.sleep(2.0)
print("[OK] PROFILE_INFO_ENTERED")
""",
        log_sec=8,
    )
    await asyncio.sleep(1.0)


def find_visible_by_id(nodes, target_id, min_y=500, max_y=2800):
    results = []

    def walk(nodes_):
        for n in nodes_:
            nid = n.get("id", "") or ""
            cy = n.get("center_y", 0)
            if target_id in nid and min_y < cy < max_y:
                results.append(n)
            walk(n.get("childs", []))

    walk(nodes)
    return results


async def wait_for_search_results(session, keyword, timeout=8):
    for i in range(timeout):
        await asyncio.sleep(1)
        ocr = await ocr_recognize(session)
        texts = "".join(x.get("text", "") for x in ocr)
        if keyword in texts and ("视频号" in texts or "搜索" not in texts):
            print(f"  [校验] 第{i + 1}s 检测到结果页")
            return True
        if any("拼音" in x.get("text", "") or "空格" in x.get("text", "") for x in ocr):
            print(f"  [校验] 第{i + 1}s 仍在输入态")
            continue
        print(f"  [校验] 第{i + 1}s 等待中...")
    print(f"  [校验] × 超时 {timeout}s 未进入结果页")
    return False


async def click_first_video_result(session):
    print("[结果页] 点击左上角第一个视频...")
    await run_on_phone(
        session,
        """
import time
from ascript.android import action
# Search results page: click inside the first video card body.
action.click(266, 964)
time.sleep(1.8)
print("[OK] FIRST_VIDEO_OPENED")
""",
        log_sec=5,
    )
    await asyncio.sleep(2.0)


async def search_keyword(session, keyword):
    """Fast search path: submit search and skip slow OCR result-page checks."""
    print(f"[search] {keyword}")
    escaped = keyword.replace("'", "\\'")

    await run_on_phone(
        session,
        f"""
import time
from ascript.android import action
action.click(540, 100)
time.sleep(0.5)
action.click(875, 184)
time.sleep(1.5)
action.click(300, 210)
time.sleep(0.3)
for _ in range(20):
    action.click(957, 1703)
    time.sleep(0.02)
time.sleep(0.3)
action.input('{escaped}')
time.sleep(0.5)
print("[OK] INPUT_DONE")
""",
        log_sec=8,
    )

    await run_on_phone(
        session,
        """
import time
from ascript.android import action, node
submitted = False
try:
    btn = node.Selector().text("搜索").find()
    if btn:
        btn.click()
        submitted = True
        print("[OK] SUBMIT_SELECTOR")
except Exception as e:
    print(f"[~] SUBMIT_SELECTOR_ERR: {e}")
time.sleep(0.5)
if not submitted:
    action.click(950, 210)
    time.sleep(0.5)
    action.click(960, 2550)
    time.sleep(0.5)
    print("[OK] SUBMIT_COORD")
""",
        log_sec=5,
    )

    await asyncio.sleep(1.8)
    print("[search] submitted; skipping slow OCR result-page check")
    return True


async def search_keyword(session, keyword):
    """Fixed-coordinate search path with slightly slower pacing for stability."""
    print(f"[search] {keyword}")
    escaped = keyword.replace("'", "\\'")

    await run_on_phone(
        session,
        f"""
import time
from ascript.android import action
action.click(540, 100)
time.sleep(0.5)
action.click(885, 180)
time.sleep(1.0)
action.click(300, 210)
time.sleep(0.35)
for _ in range(20):
    action.click(957, 1703)
    time.sleep(0.02)
time.sleep(0.35)
action.input('{escaped}')
time.sleep(0.8)
action.click(950, 215)
time.sleep(2.0)
action.click(302, 350)
time.sleep(1.8)
print("[OK] SEARCH_SUBMITTED")
""",
        log_sec=5,
    )

    await asyncio.sleep(1.5)
    print("[search] submitted; skipping slow OCR result-page check")
    return True


async def build_current_video_candidate(session, keyword, index):
    ocr = await ocr_recognize(session)
    items = ocr if isinstance(ocr, list) else ocr.get("items", [])

    title_text = ""
    author_name = ""
    publish_time = ""

    for it in items:
        txt = (it.get("text", "") or "").strip()
        y = it.get("y", 0)
        if not txt:
            continue
        if not title_text and len(txt) >= 6 and 500 <= y <= 2200:
            title_text = txt
        if ("关注" in txt or "+关注" in txt) and not author_name:
            author_name = txt.replace("+关注", "").replace("关注", "").strip()
        if not publish_time and re.search(r"(刚刚|\d+分钟前|\d+小时前|\d+天前|\d{4}[-/.]\d{1,2}[-/.]\d{1,2})", txt):
            publish_time = txt

    if not title_text:
        title_text = f"video_{index}"

    raw = f"weixin|{keyword}|{author_name}|{publish_time}|{title_text[:30]}"
    fp = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return {
        "keyword": keyword,
        "hit_text": title_text,
        "title_text": title_text,
        "author_name": author_name,
        "publish_time": publish_time,
        "fingerprint": fp,
        "score": 1,
        "click_x": 0,
        "click_y": 0,
    }


async def capture_single(session, path):
    code = """
import base64, cv2, time
from ascript.android import screen
for _ in range(3):
    img = screen.capture_cv()
    if img is not None:
        break
    time.sleep(1)
if img is not None:
    _, buf = cv2.imencode('.png', img)
    print(base64.b64encode(buf.tobytes()).decode('utf-8'))
"""
    out = await run_on_phone(session, code, log_sec=8)
    log = out.get("log", "")
    lines = log.splitlines()
    chunks = []
    for ln in lines:
        if len(ln) >= 31 and ln.startswith("["):
            ln = ln[31:]
        chunks.append(ln)
    raw = "".join(chunks)
    hpos = raw.find("iVBORw0KGgo")
    if hpos < 0:
        return False
    raw = raw[hpos:]
    raw = re.sub(r"[^A-Za-z0-9+/]", "", raw)
    while len(raw) % 4 != 0:
        raw += "="
    data = base64.b64decode(raw)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return True


async def run():
    print("=" * 60)
    print("微信视频号监测 v2 — 视频结果直达取证")
    print("=" * 60)

    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[MCP] 服务端已启动")

            if not await connect_device_auto(session):
                print("[x] 设备未连接")
                return
            print("[✓] 设备已连接")
            print("[起点] 当前从微信视频号页面开始")

            keyword = DEFAULT_KEYWORD
            ok = await search_keyword(session, keyword)
            if not ok:
                print("[错误] 搜索失败，无法继续")
                return

            from db import insert_evidence_record
            from navigator import swipe, wait_for_video_page
            from collector import collect_current_video
            from store import save_record, load_seen

            await click_first_video_result(session)
            if env_bool("WEIXIN_VERIFY_VIDEO_PAGE", False) and not await wait_for_video_page(session, timeout=5):
                print("[错误] 未能从搜索结果进入第一个视频")
                return

            print("[视频] 已进入第一个视频，开始视频流取证")
            seen = load_seen()
            duplicate_rounds = 0
            max_duplicate_rounds = 3
            max_videos = env_int("WEIXIN_MAX_VIDEOS", 10)
            record_seconds = env_int("WEIXIN_RECORD_SECONDS", 90)
            print(f"[config] max_videos={max_videos}, record_seconds={record_seconds}")

            for index in range(1, max_videos + 1):
                print(f"\n{'=' * 50}\n[视频] 第 {index} 条")
                candidate = await build_current_video_candidate(session, keyword, index)

                if candidate["fingerprint"] in seen:
                    duplicate_rounds += 1
                    print(f"[视频] 命中已采集内容，连续重复 {duplicate_rounds}/{max_duplicate_rounds}")
                    if duplicate_rounds >= max_duplicate_rounds:
                        print("[结束] 连续重复达到上限")
                        break
                else:
                    duplicate_rounds = 0

                record = await collect_current_video(
                    session,
                    keyword,
                    candidate,
                    seen,
                    record_seconds=record_seconds,
                )
                save_record(record)
                if env_bool("WEIXIN_WRITE_DB", False):
                    row_id = insert_evidence_record(record)
                    print(f"[db] inserted row id={row_id}")

                await swipe(session)
                await asyncio.sleep(2)

    print("\n[完成]")


if __name__ == "__main__":
    asyncio.run(run())
