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
from pathlib import Path

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
BASE_SCREEN_WIDTH = 1080
BASE_SCREEN_HEIGHT = 2400
DEFAULT_KEYWORD = "弃子归来震万城"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(JSONS_DIR, exist_ok=True)


DEFAULT_SCRCPY_DIR = r"D:\software\scrcpy-win64-v3.3.3"
_SCREEN_SIZE_CACHE = None


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


def get_phone_screen_size_via_adb(force_refresh: bool = False) -> tuple[int, int]:
    global _SCREEN_SIZE_CACHE
    if _SCREEN_SIZE_CACHE and not force_refresh:
        return _SCREEN_SIZE_CACHE

    adb = find_adb()
    proc = subprocess.run(
        [adb, "shell", "wm", "size"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode == 0:
        match = re.search(r"Physical size:\s*(\d+)x(\d+)", proc.stdout)
        if not match:
            match = re.search(r"Override size:\s*(\d+)x(\d+)", proc.stdout)
        if match:
            _SCREEN_SIZE_CACHE = (int(match.group(1)), int(match.group(2)))
            return _SCREEN_SIZE_CACHE

    _SCREEN_SIZE_CACHE = (BASE_SCREEN_WIDTH, BASE_SCREEN_HEIGHT)
    return _SCREEN_SIZE_CACHE


def scale_x(x: int, width: int | None = None) -> int:
    width = width or get_phone_screen_size_via_adb()[0]
    return int(round(x * width / BASE_SCREEN_WIDTH))


def scale_y(y: int, height: int | None = None) -> int:
    height = height or get_phone_screen_size_via_adb()[1]
    return int(round(y * height / BASE_SCREEN_HEIGHT))


def scale_point(x: int, y: int) -> tuple[int, int]:
    width, height = get_phone_screen_size_via_adb()
    return scale_x(x, width), scale_y(y, height)


def scale_rect(left: int, top: int, right: int, bottom: int) -> tuple[int, int, int, int]:
    width, height = get_phone_screen_size_via_adb()
    return (
        scale_x(left, width),
        scale_y(top, height),
        scale_x(right, width),
        scale_y(bottom, height),
    )


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def iso_duration_seconds(started_at: str, ended_at: str) -> int:
    return max(
        1,
        int(
            (
                datetime.fromisoformat(ended_at)
                - datetime.fromisoformat(started_at)
            ).total_seconds()
        ),
    )


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


def _tool_call_succeeded(result) -> bool:
    texts = [c.text for c in result.content if getattr(c, "type", "") == "text"]
    merged = "\n".join(texts).lower()
    if not merged.strip():
        return False
    failure_tokens = ("fail", "error", "失败", "错误", "未连接")
    success_tokens = ("connected", "已连接", "success", "成功", "本地端口")
    if any(token in merged for token in failure_tokens):
        return False
    return any(token in merged for token in success_tokens)


async def connect_device_auto_v2(session):
    print(f"[connect] try direct LocalIP {PHONE_IP}:{PHONE_PORT} ...")
    result = await session.call_tool(
        "connect_device",
        {"ip": PHONE_IP, "port": PHONE_PORT, "connection_mode": "LocalIP"},
    )
    if _tool_call_succeeded(result):
        print("[connect] direct LocalIP connected")
        return True

    adb_ip = get_phone_wlan_ip_via_adb()
    if adb_ip and adb_ip != PHONE_IP:
        print(f"[connect] try current WLAN IP from adb {adb_ip}:{PHONE_PORT} ...")
        result = await session.call_tool(
            "connect_device",
            {"ip": adb_ip, "port": PHONE_PORT, "connection_mode": "LocalIP"},
        )
        if _tool_call_succeeded(result):
            print(f"[connect] current WLAN IP connected: {adb_ip}:{PHONE_PORT}")
            return True

    print("[connect] LocalIP failed, scanning devices ...")
    result = await session.call_tool("scan_devices", {"port": PHONE_PORT})
    for item in result.content:
        if getattr(item, "type", "") != "text":
            continue
        for line in item.text.splitlines():
            if "USB(ADB)" in line:
                prefix = line.split("USB(ADB)", 1)[0]
                serial_match = re.search(r":\s*([A-Za-z0-9._:-]+)\s*$", prefix)
                if serial_match:
                    serial = serial_match.group(1)
                    print(f"[connect] found USB ADB device, try serial {serial} ...")
                    adb_result = await session.call_tool(
                        "connect_device",
                        {"ip": serial, "connection_mode": "ADB"},
                    )
                    if _tool_call_succeeded(adb_result):
                        print(f"[connect] USB ADB connected: {serial}")
                        return True

            lan_match = re.search(r"IP:\s*([\d.]+):(\d+)", line)
            if not lan_match:
                continue
            ip2, port2 = lan_match.group(1), int(lan_match.group(2))
            print(f"[connect] try scanned LocalIP {ip2}:{port2} ...")
            lan_result = await session.call_tool(
                "connect_device",
                {"ip": ip2, "port": port2, "connection_mode": "LocalIP"},
            )
            if _tool_call_succeeded(lan_result):
                print(f"[connect] scanned LocalIP connected: {ip2}:{port2}")
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
        f"""
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
    adb = find_adb()
    x1, y1 = scale_point(540, 2000)
    x2, y2 = scale_point(540, 400)
    proc = subprocess.run(
        [adb, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), "300"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        print(f"[swipe] adb swipe failed: {proc.stderr.strip()}")
    else:
        print("[swipe] adb swipe sent")
    await asyncio.sleep(1.2)


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
        f"""
import time
from ascript.android import action
# Search results page: click inside the first video card body.
action.click({scale_point(266, 964)[0]}, {scale_point(266, 964)[1]})
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
    header_safe_x, header_safe_y = scale_point(540, 100)
    open_search_x, open_search_y = scale_point(885, 180)
    focus_input_x, focus_input_y = scale_point(300, 210)
    clear_input_x, clear_input_y = scale_point(957, 1703)
    submit_x, submit_y = scale_point(950, 215)
    video_tab_x, video_tab_y = scale_point(302, 350)

    await run_on_phone(
        session,
        f"""
import time
from ascript.android import action
action.click({header_safe_x}, {header_safe_y})
time.sleep(0.5)
action.click({open_search_x}, {open_search_y})
time.sleep(1.0)
action.click({focus_input_x}, {focus_input_y})
time.sleep(0.35)
for _ in range(20):
    action.click({clear_input_x}, {clear_input_y})
    time.sleep(0.02)
time.sleep(0.35)
action.input('{escaped}')
time.sleep(0.8)
action.click({submit_x}, {submit_y})
time.sleep(2.0)
action.click({video_tab_x}, {video_tab_y})
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


def attach_recording_media(record, video_path: str, started_at: str, ended_at: str):
    from media_capture import extract_audio, probe_audio

    record.media_info["recording_video_path"] = str(video_path)
    record.media_info["recording_started_at"] = started_at
    record.media_info["recording_ended_at"] = ended_at
    record.media_info["recording_duration_seconds"] = iso_duration_seconds(started_at, ended_at)

    has_audio = False
    try:
        has_audio = probe_audio(video_path)
    except Exception as exc:
        print(f"[record] probe audio failed: {exc}")
    record.media_info["has_audio"] = has_audio

    if has_audio:
        try:
            wav_path = extract_audio(video_path)
        except Exception as exc:
            print(f"[record] extract audio failed: {exc}")
        else:
            if wav_path:
                record.media_info["recording_audio_path"] = str(wav_path)


async def run():
    print("=" * 60)
    print("weixin video monitor main flow")
    print("=" * 60)

    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[mcp] initialized")

            if not await connect_device_auto_v2(session):
                print("[x] device not connected")
                return
            print("[ok] device connected")

            keyword = DEFAULT_KEYWORD
            if not await search_keyword(session, keyword):
                print("[x] search failed")
                return

            from collector import collect_current_video
            from db import insert_evidence_record
            from media_capture import start_capture_session, stop_capture_session
            from store import load_seen, save_record
            from navigator import wait_for_video_page

            capture_method = os.environ.get("WEIXIN_CAPTURE_METHOD", "auto").strip().lower() or "auto"
            capture_prefer_scrcpy = env_bool("WEIXIN_PREFER_SCRCPY", True)
            hold_seconds = env_int("WEIXIN_POST_EVIDENCE_HOLD_SECONDS", 240)
            max_videos = env_int("WEIXIN_MAX_VIDEOS", 10)
            verify_video_page = env_bool("WEIXIN_VERIFY_VIDEO_PAGE", False)
            write_db = env_bool("WEIXIN_WRITE_DB", False)
            print(
                f"[config] max_videos={max_videos}, hold_seconds={hold_seconds}, "
                f"capture_method={capture_method}, prefer_scrcpy={capture_prefer_scrcpy}"
            )

            segment = None
            try:
                segment = start_capture_session(
                    method=capture_method,
                    prefer_scrcpy=capture_prefer_scrcpy,
                )
                print(f"[record] first segment started: {segment.local_path}")

                await click_first_video_result(session)
                if verify_video_page and not await wait_for_video_page(session, timeout=5):
                    print("[x] first video page not confirmed")
                    return

                seen = load_seen()
                duplicate_rounds = 0
                max_duplicate_rounds = 3

                for index in range(1, max_videos + 1):
                    print(f"\n{'=' * 50}\n[video] index={index}")
                    candidate = await build_current_video_candidate(session, keyword, index)

                    if candidate["fingerprint"] in seen:
                        duplicate_rounds += 1
                        print(
                            f"[video] duplicate fingerprint {duplicate_rounds}/{max_duplicate_rounds}: "
                            f"{candidate['fingerprint']}"
                        )
                        if duplicate_rounds >= max_duplicate_rounds:
                            print("[flow] stop after repeated duplicates")
                            break
                    else:
                        duplicate_rounds = 0

                    record = await collect_current_video(session, keyword, candidate, seen)

                    print(f"[record] hold current video for {hold_seconds}s before stop")
                    await asyncio.sleep(hold_seconds)

                    ended_at = now_iso()
                    video_path = stop_capture_session(segment)
                    attach_recording_media(record, str(video_path), segment.started_at, ended_at)
                    print(f"[record] segment saved: {video_path}")
                    segment = None

                    save_record(record)
                    if write_db:
                        row_id = insert_evidence_record(record)
                        print(f"[db] inserted row id={row_id}")

                    if index >= max_videos:
                        print("[flow] reached max_videos; stop after current segment")
                        continue

                    next_segment = start_capture_session(
                        method=capture_method,
                        prefer_scrcpy=capture_prefer_scrcpy,
                    )
                    print(f"[record] next segment started before swipe: {next_segment.local_path}")

                    try:
                        await swipe_up(session)
                        await asyncio.sleep(2.0)
                        if verify_video_page:
                            ok = await wait_for_video_page(session, timeout=5)
                            if ok:
                                print("[flow] swipe completed; next video page detected")
                            else:
                                print("[flow] swipe sent but next video page was not confirmed")
                                stop_capture_session(next_segment)
                                break
                    except Exception:
                        stop_capture_session(next_segment)
                        raise

                    segment = next_segment
            finally:
                if segment is not None:
                    try:
                        stop_capture_session(segment)
                    except Exception as exc:
                        print(f"[record] final segment cleanup failed: {exc}")

    print("\n[done]")


if __name__ == "__main__":
    asyncio.run(run())
