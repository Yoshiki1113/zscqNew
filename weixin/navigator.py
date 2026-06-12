"""Weixin video navigator helpers."""
import asyncio
import os

from main import (
    SCREENSHOT_DIR,
    ensure_wechat_home as _ensure_wechat_home,
    get_ui_tree,
    go_back as _go_back,
    navigate_to_discover as _navigate_to_discover,
    navigate_to_video_channel as _navigate_to_video_channel,
    ocr_recognize,
    run_on_phone,
    search_keyword as _search_keyword,
    scale_rect,
    swipe_up as _swipe_up,
)
from collector import capture_single_via_adb_execout, crop_image_region, local_ocr_image


async def ensure_home(session):
    await _ensure_wechat_home(session)


async def to_discover(session):
    await _navigate_to_discover(session)


async def to_video_channel(session):
    await _navigate_to_video_channel(session)


async def search(session, keyword):
    await _search_keyword(session, keyword)


async def back(session):
    await _go_back(session)


async def swipe(session, times=1):
    for _ in range(times):
        await _swipe_up(session)
        await asyncio.sleep(0.5)


async def wait_for_video_page(session, timeout=5):
    """Confirm we are on a playback page via UI tree first, then bottom-region screenshot OCR."""
    for _ in range(timeout):
        await asyncio.sleep(1)
        if await is_video_page_via_ui_tree(session):
            return True
        if is_video_page_via_bottom_screenshot():
            return True
    return False


async def is_video_page_via_ui_tree(session) -> bool:
    ui = await get_ui_tree(session)
    views = ui.get("data", {}).get("views", []) if isinstance(ui, dict) else []
    if not views:
        return False

    hits = []

    def walk(nodes):
        for node in nodes:
            text = (node.get("text", "") or "").strip()
            desc = (node.get("desc", "") or "").strip()
            node_id = node.get("id", "") or ""
            cy = node.get("center_y", 0)
            merged = f"{text} {desc}"
            if 1500 <= cy <= 2400 and any(token in merged for token in ("关注", "热评", "评论", "转发", "点赞", "免费剧集")):
                hits.append((text, desc, node_id, cy))
            walk(node.get("childs", []))

    walk(views)
    return len(hits) >= 2


def is_video_page_via_bottom_screenshot() -> bool:
    screen_path = os.path.join(SCREENSHOT_DIR, "_video_page_probe.png")
    region_path = os.path.join(SCREENSHOT_DIR, "_video_page_probe_bottom.png")
    if not capture_single_via_adb_execout(screen_path):
        return False
    left, top, right, bottom = scale_rect(0, 2060, 1080, 2400)
    if not crop_image_region(screen_path, region_path, left, top, right, bottom):
        return False

    items = local_ocr_image(region_path)
    texts = [(item.get("text", "") or "").strip() for item in items]
    merged = " ".join(texts)
    markers = ("关注", "+关注", "免费剧集", "评论", "转发", "点赞", "AI生成")
    score = sum(1 for token in markers if token in merged)
    digit_count = sum(1 for text in texts if text.isdigit())
    return score >= 2 or (score >= 1 and digit_count >= 2)


async def click_candidate(session, candidate):
    """Click a candidate video with multiple attempts."""
    cx, cy = candidate.get("click_x", 540), candidate.get("click_y", 800)

    ui = await get_ui_tree(session)
    views = ui.get("data", {}).get("views", [])
    target = None

    def walk(nodes):
        nonlocal target
        for node in nodes:
            if target:
                return
            text = node.get("text", "") or ""
            cy2 = node.get("center_y", 0)
            if text and abs(cy2 - cy) < 60 and node.get("clickable"):
                target = node
                return
            walk(node.get("childs", []))

    walk(views)

    if target:
        cx, cy = target["center_x"], target["center_y"]
        print(f"[click] UI target: ({cx}, {cy})")

    attempts = [
        (cx, cy, "candidate"),
        (540, cy, "card-center"),
        (620, 800, "first-result-fallback"),
    ]
    for ax, ay, label in attempts:
        await run_on_phone(
            session,
            f"""
import time
from ascript.android import action
action.click({ax}, {ay})
time.sleep(1.5)
print("[OK] CANDIDATE_CLICKED")
""",
            log_sec=4,
        )
        print(f"[click] {label}: ({ax}, {ay})")
        ok = await wait_for_video_page(session)
        if ok:
            print("[click] entered video detail")
            return True
        await asyncio.sleep(0.8)

    print("[click] failed to enter video detail")
    return False
