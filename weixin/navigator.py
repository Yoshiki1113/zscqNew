"""Weixin video navigator helpers."""
import asyncio

from main import (
    run_on_phone,
    get_ui_tree,
    ocr_recognize,
    ensure_wechat_home as _ensure_wechat_home,
    navigate_to_discover as _navigate_to_discover,
    navigate_to_video_channel as _navigate_to_video_channel,
    search_keyword as _search_keyword,
    go_back as _go_back,
    swipe_up as _swipe_up,
)


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
    """OCR-based check that we reached the video detail page."""
    for _ in range(timeout):
        await asyncio.sleep(1)
        ocr = await ocr_recognize(session)
        items = ocr.get("items", ocr) if isinstance(ocr, dict) else ocr
        texts = "".join((it.get("text", "") or "") for it in (items or []))
        markers = (
            "关注",
            "+关注",
            "免费剧集",
            "全56集",
            "可能含有AI",
            "点赞",
            "评论",
            "转发",
        )
        if any(token in texts for token in markers):
            return True
    return False


async def click_candidate(session, candidate):
    """Click a candidate video with multiple attempts."""
    cx, cy = candidate.get("click_x", 540), candidate.get("click_y", 800)

    ui = await get_ui_tree(session)
    views = ui.get("data", {}).get("views", [])
    target = None

    def walk(nodes):
        nonlocal target
        for n in nodes:
            if target:
                return
            t = n.get("text", "") or ""
            cy2 = n.get("center_y", 0)
            if t and abs(cy2 - cy) < 60 and n.get("clickable"):
                target = n
                return
            walk(n.get("childs", []))

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
