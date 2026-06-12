"""Evidence collection from an opened Weixin video page."""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
from datetime import datetime

import cv2

from main import SCREENSHOT_DIR, find_adb, run_on_phone, scale_point, scale_rect
from media_capture import extract_audio, probe_audio
from models import EvidenceRecord
from text_quality import analyze_video_channel_id


DEFAULT_RECORD_SECONDS = 90

SHARE_BUTTON_X = 746
SHARE_BUTTON_Y = 2153
SHARE_TRAY_SWIPE_START_X = 880
SHARE_TRAY_SWIPE_END_X = 140
SHARE_TRAY_Y = 1910
COPY_LINK_X = 950
COPY_LINK_Y = 1900
CLIPBOARD_POPUP_CLOSE_X = 281
CLIPBOARD_POPUP_CLOSE_Y = 2062

TRAFFIC_MARKER_X = 192
TRAFFIC_MARKER_Y = 1693
TRAFFIC_MARKER_LEFT = 66
TRAFFIC_MARKER_TOP = 1635
TRAFFIC_MARKER_RIGHT = 666
TRAFFIC_MARKER_BOTTOM = 1721
TRAFFIC_FIRST_EPISODE_X = 130
TRAFFIC_FIRST_EPISODE_Y = 1342
TRAFFIC_AVATAR_X = 140
TRAFFIC_AVATAR_Y = 2140
TRAFFIC_MORE_BUTTON_X = 975
TRAFFIC_MORE_BUTTON_Y = 834
TRAFFIC_MORE_INFO_X = 517
TRAFFIC_MORE_INFO_Y = 2063

AUTHOR_AVATAR_X = 140
AUTHOR_AVATAR_Y = 2140
AUTHOR_MORE_BUTTON_X = 970
AUTHOR_MORE_BUTTON_Y = 835
AUTHOR_MORE_INFO_X = 540
AUTHOR_MORE_INFO_Y = 2050
AUTHOR_CARD_NAME_LEFT = 310
AUTHOR_CARD_NAME_TOP = 735
AUTHOR_CARD_NAME_RIGHT = 790
AUTHOR_CARD_NAME_BOTTOM = 885

_LOCAL_PADDLE_OCR = None

MIN_FULL_SCREENSHOT_BYTES = 4096
PADDLEX_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".paddlex-cache")


def configure_paddle_runtime_env() -> None:
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    os.environ["PADDLE_PDX_CACHE_HOME"] = PADDLEX_CACHE_DIR
    os.environ["FLAGS_enable_pir_api"] = "0"
    os.environ["FLAGS_json_format_model"] = "0"
    os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"
    os.environ["PADDLE_PDX_DISABLE_MKLDNN_MODEL_BL"] = "True"
    os.environ["FLAGS_use_mkldnn"] = "0"
    os.environ["FLAGS_use_onednn"] = "0"
    os.environ.setdefault("FLAGS_allocator_strategy", "auto_growth")


configure_paddle_runtime_env()


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


async def collect_current_video(session, keyword, candidate_dict, seen, recording_video_path: str = ""):
    """Collect one complete evidence record from the current playback page."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = candidate_dict.get("fingerprint", ts)[:12]
    capture_time = _now_iso()

    record = EvidenceRecord(
        search_keyword=keyword,
        capture_time=capture_time,
        capture_timestamp=capture_time,
        candidate=candidate_dict,
    )

    if recording_video_path:
        video_path = recording_video_path
        record.media_info["recording_video_path"] = str(video_path)
        has_audio = probe_audio(video_path)
        record.media_info["has_audio"] = has_audio
        if has_audio:
            wav_path = extract_audio(video_path)
            if wav_path:
                record.media_info["recording_audio_path"] = str(wav_path)
        print(f"[evidence] use pre-recorded segment: {video_path} audio={has_audio}")

    print("[evidence] capture playback screenshot...")
    play_path = os.path.join(SCREENSHOT_DIR, f"play_{slug}_0.png")
    play_ocr = []
    if await capture_single_with_adb_fallback(session, play_path, f"play_{slug}"):
        record.screenshots.append(play_path)
        play_ocr = local_ocr_image(play_path)
        print(f"[ocr] playback items={len(play_ocr)}")
        record.video_info["raw_ocr"] = play_ocr
        fill_video_fields_from_ocr(record.video_info, play_ocr)

    print("[evidence] collect traffic info if a free-series marker is present...")
    await collect_traffic_info(session, record, slug, play_ocr)

    print("[evidence] open author profile card...")
    await open_author_profile_card(session)
    await capture_author_profile_card(session, record, slug)

    print("[evidence] open author more-info page...")
    await open_author_more_info_from_card(session)
    await asyncio.sleep(1.5)

    profile_path = os.path.join(SCREENSHOT_DIR, f"profile_info_{slug}_0.png")
    if await capture_single_with_adb_fallback(session, profile_path, f"profile_info_{slug}"):
        record.screenshots.append(profile_path)
        profile_ocr = local_ocr_image(profile_path)
        print(f"[ocr] profile info items={len(profile_ocr)}")
        record.profile_info["raw_ocr"] = profile_ocr
        fill_profile_fields_from_ocr(record.profile_info, profile_ocr)
        if not record.profile_info.get("name"):
            record.profile_info["name"] = record.video_info.get("blogger_name", "")
        fill_video_channel_id_from_profile(record.video_info, record.profile_info)

    fp = candidate_dict.get("fingerprint", "")
    if fp:
        seen.add(fp)

    await back_from_profile(session)

    print("[evidence] copy video link from share sheet...")
    record.video_info["video_link"] = await copy_video_link(session, slug)
    return record


async def capture_single_with_adb_fallback(session, path: str, tag: str) -> bool:
    if capture_single_via_adb_execout(path):
        print(f"[capture] adb exec-out screencap ok: {path}")
        return True
    print(f"[capture] adb exec-out screencap failed, fallback to adb remote screencap: {path}")
    if capture_single_via_adb(path, tag):
        print(f"[capture] adb remote screencap ok: {path}")
        return True
    return False


def write_and_validate_screenshot(path: str, data: bytes, source: str) -> bool:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    ok, reason = validate_screenshot_file(path)
    if not ok:
        print(f"[capture] {source} produced unusable image: {reason}")
        try:
            os.remove(path)
        except OSError:
            pass
        return False
    print(f"  [screenshot] {path} ({len(data)} bytes)")
    return True


def validate_screenshot_file(path: str, min_size: int = MIN_FULL_SCREENSHOT_BYTES) -> tuple[bool, str]:
    if not os.path.exists(path):
        return False, "file missing"
    size = os.path.getsize(path)
    if size < min_size:
        return False, f"file too small ({size} bytes)"
    img = cv2.imread(path)
    if img is None or img.size == 0:
        return False, "cv2 cannot read image"
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mean = float(gray.mean())
    std = float(gray.std())
    if mean < 3.0 and std < 2.0:
        return False, f"near-black image (mean={mean:.2f}, std={std:.2f})"
    if std < 0.5:
        return False, f"nearly flat image (mean={mean:.2f}, std={std:.2f})"
    return True, "ok"


def capture_single_via_adb_execout(path: str) -> bool:
    adb = find_adb()
    shot = subprocess.run(
        [adb, "exec-out", "screencap", "-p"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if shot.returncode != 0 or not shot.stdout:
        err = shot.stderr.decode("utf-8", "replace").strip()
        print(f"[capture] adb exec-out screencap failed: {err}")
        return False
    return write_and_validate_screenshot(path, shot.stdout, "adb exec-out screencap")


def capture_single_via_adb(path: str, tag: str) -> bool:
    adb = find_adb()
    remote_path = f"/sdcard/{tag}.png"
    os.makedirs(os.path.dirname(path), exist_ok=True)

    shot = subprocess.run(
        [adb, "shell", "screencap", "-p", remote_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if shot.returncode != 0:
        print(f"[capture] adb screencap failed: {shot.stderr.strip()}")
        return False

    pull = subprocess.run(
        [adb, "pull", remote_path, path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if pull.returncode != 0:
        print(f"[capture] adb pull failed: {pull.stderr.strip()}")
        return False
    ok, reason = validate_screenshot_file(path)
    if not ok:
        print(f"[capture] adb remote screencap produced unusable image: {reason}")
        try:
            os.remove(path)
        except OSError:
            pass
        return False
    return True


async def back_from_profile(session):
    """Return from author info back to the playback page."""
    from navigator import back

    await back(session)
    await asyncio.sleep(1)
    await back(session)
    await asyncio.sleep(1)


async def copy_video_link(session, slug: str = "") -> str:
    """Copy the current video link via a debuggable share-sheet path."""
    tag = slug or datetime.now().strftime("%Y%m%d_%H%M%S")
    sentinel = f"__WEIXIN_COPY_PENDING_{tag}__"
    await set_phone_clipboard(session, sentinel)

    await open_share_sheet_to_copy_area(session)

    share_path = os.path.join(SCREENSHOT_DIR, f"share_sheet_{tag}_0.png")
    copy_x, copy_y = COPY_LINK_X, COPY_LINK_Y
    if await capture_single_with_adb_fallback(session, share_path, f"share_sheet_{tag}"):
        found = find_copy_link_button_from_image(share_path, tag)
        if found:
            copy_x, copy_y = found
            print(f"[evidence] copy-link OCR target: ({copy_x}, {copy_y})")
        else:
            print(f"[evidence] copy-link OCR target not found; using fixed ({copy_x}, {copy_y})")

    await tap_copy_link_button(session, copy_x, copy_y)

    for attempt in range(1, 6):
        await asyncio.sleep(0.6)
        raw_link = await read_phone_clipboard(session)
        link = extract_link_from_clipboard_text(raw_link)
        print(f"[evidence] clipboard read {attempt}/5: {raw_link!r}")
        if link and sentinel not in raw_link:
            print(f"[evidence] copied video link: {link}")
            return link

    print("[evidence] video link copy did not return clipboard text")
    return ""


async def open_share_sheet_to_copy_area(session) -> None:
    share_x, share_y = scale_point(SHARE_BUTTON_X, SHARE_BUTTON_Y)
    tray_start_x, tray_y = scale_point(SHARE_TRAY_SWIPE_START_X, SHARE_TRAY_Y)
    tray_end_x, _ = scale_point(SHARE_TRAY_SWIPE_END_X, SHARE_TRAY_Y)
    code = f"""
import time
from ascript.android import action

action.click({share_x}, {share_y})
time.sleep(1.2)
action.swipe({tray_start_x}, {tray_y}, {tray_end_x}, {tray_y}, 350)
time.sleep(0.5)
action.swipe({tray_start_x}, {tray_y}, {tray_end_x}, {tray_y}, 350)
time.sleep(0.8)
print("[OK] SHARE_SHEET_READY")
"""
    await run_on_phone(session, code, log_sec=6)


async def tap_copy_link_button(session, x: int, y: int) -> None:
    tap_x, tap_y = scale_point(x, y)
    code = f"""
import time
from ascript.android import action

action.click({tap_x}, {tap_y})
time.sleep(1.0)
print("[OK] COPY_LINK_TAPPED")
"""
    await run_on_phone(session, code, log_sec=5)


async def set_phone_clipboard(session, text: str) -> None:
    escaped = text.replace("\\", "\\\\").replace("'", "\\'")
    code = f"""
try:
    from ascript.android.system import Clipboard
    Clipboard.set('{escaped}')
    print("[OK] CLIPBOARD_SET_ASCRIPT")
except Exception as e:
    print("[~] CLIPBOARD_SET_ASCRIPT_ERR:" + repr(e))
    try:
        from android.content import ClipData, Context
        from com.aojoy.airscript import Globals
        ctx = Globals.getContext()
        cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE)
        cm.setPrimaryClip(ClipData.newPlainText("weixin", "{escaped}"))
        print("[OK] CLIPBOARD_SET_ANDROID")
    except Exception as e2:
        print("[~] CLIPBOARD_SET_ANDROID_ERR:" + repr(e2))
"""
    await run_on_phone(session, code, log_sec=4)


async def read_phone_clipboard(session) -> str:
    code = """
clip_text = ""
try:
    from ascript.android.system import Clipboard
    clip_text = str(Clipboard.get() or "")
except Exception as e:
    print("[~] CLIPBOARD_GET_ASCRIPT_ERR:" + repr(e))

if not clip_text:
    try:
        from android.content import Context
        from com.aojoy.airscript import Globals
        ctx = Globals.getContext()
        cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE)
        clip = cm.getPrimaryClip()
        if clip and clip.getItemCount() > 0:
            clip_text = str(clip.getItemAt(0).coerceToText(ctx) or "")
    except Exception as e:
        print("[~] CLIPBOARD_GET_ANDROID_ERR:" + repr(e))

print("CLIPBOARD_START")
print(clip_text)
print("CLIPBOARD_END")
"""
    out = await run_on_phone(session, code, log_sec=4)
    log = out.get("log", "")
    start = log.find("CLIPBOARD_START")
    end = log.find("CLIPBOARD_END")
    if start < 0 or end <= start:
        return ""
    return log[start + len("CLIPBOARD_START"):end].strip()


def extract_link_from_clipboard_text(raw_text: str) -> str:
    match = re.search(r"https?://\S+", raw_text or "")
    return match.group(0).rstrip(")]}>,.;'\"") if match else ""


def find_copy_link_button_from_image(image_path: str, tag: str) -> tuple[int, int] | None:
    region_path = os.path.join(SCREENSHOT_DIR, f"share_copy_region_{tag}.png")
    left, top, right, bottom = scale_rect(520, 1760, 1080, 2025)
    if not crop_image_region(image_path, region_path, left, top, right, bottom):
        return None

    items = local_ocr_image(region_path)
    candidates = []
    for item in items:
        text = (item.get("text", "") or "").strip()
        if not text:
            continue
        if "复制" not in text:
            continue
        if "链接" not in text and "口令" in text:
            continue
        x = item.get("x", 0) + left
        y = item.get("y", 0) + top
        candidates.append((abs(x - COPY_LINK_X) + abs(y - COPY_LINK_Y), x, y, text))

    if not candidates:
        return None
    _, x, y, text = sorted(candidates, key=lambda item: item[0])[0]
    print(f"[evidence] copy-link OCR text: {text}")
    return int(x), int(y)


async def collect_traffic_info(session, record: EvidenceRecord, slug: str, play_ocr=None) -> None:
    """Open the free-series traffic entry and collect target subject info."""
    marker_text, region_path = await detect_traffic_marker(session, slug)
    if region_path:
        record.screenshots.append(region_path)
    if not marker_text:
        marker_text = find_traffic_marker_text_from_items(play_ocr or [])
        if marker_text:
            print(f"[traffic] playback OCR marker fallback: {marker_text}")
    if not marker_text:
        print("[traffic] no free-series marker found on playback page")
        return

    record.traffic_info["has_traffic_marker"] = True
    record.traffic_info["marker_text"] = marker_text
    print(f"[traffic] found marker: {marker_text}")

    await open_traffic_subject(session)
    await open_traffic_avatar_card(session)

    traffic_page_path = os.path.join(SCREENSHOT_DIR, f"traffic_page_{slug}_0.png")
    if await capture_single_with_adb_fallback(session, traffic_page_path, f"traffic_page_{slug}"):
        record.screenshots.append(traffic_page_path)
        traffic_name_region_path = os.path.join(SCREENSHOT_DIR, f"traffic_page_name_region_{slug}.png")
        left, top, right, bottom = scale_rect(
            AUTHOR_CARD_NAME_LEFT,
            AUTHOR_CARD_NAME_TOP,
            AUTHOR_CARD_NAME_RIGHT,
            AUTHOR_CARD_NAME_BOTTOM,
        )
        if crop_image_region(
            traffic_page_path,
            traffic_name_region_path,
            left,
            top,
            right,
            bottom,
        ):
            record.screenshots.append(traffic_name_region_path)
        target_name = extract_author_name_from_card_image(traffic_page_path, traffic_name_region_path)
        if not target_name:
            target_name = extract_theater_account_name_from_image(traffic_page_path)
        record.traffic_info["target_blogger_name"] = target_name
        if target_name:
            print(f"[traffic] target account card name: {target_name}")

    await open_traffic_more_info_from_avatar_card(session)

    traffic_info_path = os.path.join(SCREENSHOT_DIR, f"traffic_info_{slug}_0.png")
    if await capture_single_with_adb_fallback(session, traffic_info_path, f"traffic_info_{slug}"):
        record.screenshots.append(traffic_info_path)
        info_ocr = local_ocr_image(traffic_info_path)
        print(f"[ocr] traffic info items={len(info_ocr)}")
        record.traffic_info["raw_ocr"] = info_ocr
        fill_traffic_fields_from_ocr(record.traffic_info, info_ocr)

    await back_from_traffic_info(session)


async def open_author_profile_card(session) -> None:
    avatar_x, avatar_y = scale_point(AUTHOR_AVATAR_X, AUTHOR_AVATAR_Y)
    code = f"""
import time
from ascript.android import action

action.click({avatar_x}, {avatar_y})
time.sleep(1.6)
print("[OK] AUTHOR_PROFILE_CARD_OPENED")
"""
    await run_on_phone(session, code, log_sec=5)
    await asyncio.sleep(0.6)


async def open_author_more_info_from_card(session) -> None:
    more_button_x, more_button_y = scale_point(AUTHOR_MORE_BUTTON_X, AUTHOR_MORE_BUTTON_Y)
    more_info_x, more_info_y = scale_point(AUTHOR_MORE_INFO_X, AUTHOR_MORE_INFO_Y)
    code = f"""
import time
from ascript.android import action

action.click({more_button_x}, {more_button_y})
time.sleep(1.2)
action.click({more_info_x}, {more_info_y})
time.sleep(2.0)
print("[OK] AUTHOR_MORE_INFO_OPENED")
"""
    await run_on_phone(session, code, log_sec=8)
    await asyncio.sleep(0.8)


async def capture_author_profile_card(session, record: EvidenceRecord, slug: str) -> None:
    card_path = os.path.join(SCREENSHOT_DIR, f"profile_card_{slug}_0.png")
    if not await capture_single_with_adb_fallback(session, card_path, f"profile_card_{slug}"):
        return

    record.screenshots.append(card_path)
    region_path = os.path.join(SCREENSHOT_DIR, f"profile_card_name_region_{slug}.png")
    left, top, right, bottom = scale_rect(
        AUTHOR_CARD_NAME_LEFT,
        AUTHOR_CARD_NAME_TOP,
        AUTHOR_CARD_NAME_RIGHT,
        AUTHOR_CARD_NAME_BOTTOM,
    )
    if crop_image_region(
        card_path,
        region_path,
        left,
        top,
        right,
        bottom,
    ):
        record.screenshots.append(region_path)

    blogger_name = extract_author_name_from_card_image(card_path, region_path)
    if blogger_name:
        record.video_info["blogger_name"] = blogger_name
        record.profile_info["name"] = blogger_name
        print(f"[profile] author card blogger name: {blogger_name}")
    else:
        print("[profile] author card blogger name not found")


def extract_author_name_from_card_image(card_path: str, region_path: str = "") -> str:
    if region_path and os.path.exists(region_path):
        region_items = local_ocr_image(region_path)
        print(f"[ocr] profile card name region items={len(region_items)}")
        name = extract_author_name_from_card_items(region_items, cropped=True)
        if name:
            return name

    card_items = local_ocr_image(card_path)
    print(f"[ocr] profile card items={len(card_items)}")
    return extract_author_name_from_card_items(card_items, cropped=False)


def extract_author_name_from_card_items(ocr_items, cropped: bool = False) -> str:
    items = ocr_items if isinstance(ocr_items, list) else []
    candidates = []
    for item in items:
        text = (item.get("text", "") or "").strip()
        x = item.get("x", 0)
        y = item.get("y", 0)
        if not is_probable_author_name(text):
            continue
        if cropped:
            candidates.append((abs(y - 70) + abs(x - 240) / 10, text))
            continue
        if AUTHOR_CARD_NAME_LEFT <= x <= AUTHOR_CARD_NAME_RIGHT and AUTHOR_CARD_NAME_TOP <= y <= AUTHOR_CARD_NAME_BOTTOM:
            candidates.append((abs(y - 808) + abs(x - 550) / 10, text))
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1] if candidates else ""


def is_probable_author_name(text: str) -> bool:
    if not text or len(text) < 2 or len(text) > 32:
        return False
    ignored_tokens = (
        "关注",
        "私信",
        "视频号",
        "账号",
        "企业",
        "公司",
        "有限",
        "原创",
        "主页",
        "剧集",
        "作品",
        "粉丝",
        "获赞",
        "评论",
        "IP",
        "归属地",
        "资料",
        "搜索",
        "更多",
    )
    if any(token in text for token in ignored_tokens):
        return False
    return bool(re.search(r"[\u4e00-\u9fa5A-Za-z0-9]", text))


async def detect_traffic_marker(session, slug: str) -> tuple[str, str]:
    """Detect the free-series marker from a cropped playback-page region."""
    screen_path = os.path.join(SCREENSHOT_DIR, f"traffic_marker_full_{slug}.png")
    if not await capture_single_with_adb_fallback(session, screen_path, f"traffic_marker_{slug}"):
        return "", ""

    region_path = os.path.join(SCREENSHOT_DIR, f"traffic_marker_region_{slug}.png")
    left, top, right, bottom = scale_rect(
        TRAFFIC_MARKER_LEFT,
        TRAFFIC_MARKER_TOP,
        TRAFFIC_MARKER_RIGHT,
        TRAFFIC_MARKER_BOTTOM,
    )
    if not crop_image_region(
        screen_path,
        region_path,
        left,
        top,
        right,
        bottom,
    ):
        return "", ""

    marker_text = find_traffic_marker_text_local(region_path)
    print(f"[ocr] traffic marker region text={marker_text!r}")
    if marker_text:
        print(f"[traffic] region OCR marker: {marker_text}")
    return marker_text, region_path


def crop_image_region(src_path: str, dst_path: str, left: int, top: int, right: int, bottom: int) -> bool:
    img = cv2.imread(src_path)
    if img is None:
        return False
    height, width = img.shape[:2]
    left = max(0, min(left, width - 1))
    top = max(0, min(top, height - 1))
    right = max(left + 1, min(right, width))
    bottom = max(top + 1, min(bottom, height))
    region = img[top:bottom, left:right]
    if region.size == 0:
        return False
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    return bool(cv2.imwrite(dst_path, region))


def get_local_paddle_ocr():
    global _LOCAL_PADDLE_OCR
    if _LOCAL_PADDLE_OCR is None:
        os.makedirs(PADDLEX_CACHE_DIR, exist_ok=True)
        from paddleocr import PaddleOCR

        _LOCAL_PADDLE_OCR = PaddleOCR(use_angle_cls=True, lang="ch")
    return _LOCAL_PADDLE_OCR


def local_ocr_image(image_path: str) -> list[dict]:
    try:
        ocr = get_local_paddle_ocr()
        result = run_local_ocr(ocr, image_path)
    except Exception as exc:
        print(f"[ocr] local OCR failed for {image_path}: {exc}")
        return []

    lines = extract_ocr_lines(result)
    if not lines:
        return []

    items = []
    for line in lines:
        box, rec = normalize_ocr_line(line)
        if box is None or rec is None:
            continue
        text = str(rec[0]).strip() if isinstance(rec, (list, tuple)) else str(rec).strip()
        if not text:
            continue
        points = coerce_ocr_box_points(box)
        xs = [int(point[0]) for point in points]
        ys = [int(point[1]) for point in points]
        if not xs or not ys:
            continue
        items.append(
            {
                "text": text,
                "x": int(sum(xs) / len(xs)),
                "y": int(sum(ys) / len(ys)),
                "w": max(xs) - min(xs),
                "h": max(ys) - min(ys),
            }
        )
    return items


def run_local_ocr(ocr, image_path: str):
    if hasattr(ocr, "ocr"):
        try:
            return ocr.ocr(image_path, cls=True)
        except TypeError as exc:
            if "unexpected keyword argument 'cls'" not in str(exc):
                raise
            return ocr.ocr(image_path)
    if hasattr(ocr, "predict"):
        return ocr.predict(image_path)
    raise RuntimeError("PaddleOCR object has neither ocr() nor predict()")


def extract_ocr_lines(result) -> list:
    if not result:
        return []
    if isinstance(result, dict):
        return extract_ocr_lines_from_dict(result)
    if isinstance(result, list):
        if result and isinstance(result[0], list):
            return result[0]
        if result and isinstance(result[0], dict):
            lines = []
            for page in result:
                lines.extend(extract_ocr_lines_from_dict(page))
            return lines
        return result
    return []


def extract_ocr_lines_from_dict(page: dict) -> list:
    texts = page.get("rec_texts") or page.get("texts") or page.get("text")
    if isinstance(texts, str):
        texts = [texts]
    if not isinstance(texts, list) or not texts:
        return []

    boxes = (
        page.get("rec_polys")
        or page.get("dt_polys")
        or page.get("boxes")
        or page.get("polys")
        or page.get("points")
    )
    if boxes is None:
        boxes = [None] * len(texts)

    scores = page.get("rec_scores") or page.get("scores") or [1.0] * len(texts)
    lines = []
    for index, text in enumerate(texts):
        box = boxes[index] if index < len(boxes) else None
        score = scores[index] if index < len(scores) else 1.0
        lines.append([box, (text, score)])
    return lines


def normalize_ocr_line(line):
    if isinstance(line, (list, tuple)) and len(line) >= 2:
        return line[0], line[1]
    if isinstance(line, dict):
        box = (
            line.get("box")
            or line.get("bbox")
            or line.get("points")
            or line.get("poly")
            or line.get("polygon")
        )
        rec = (
            line.get("rec")
            or line.get("text")
            or line.get("label")
            or line.get("transcription")
        )
        if isinstance(rec, str):
            rec = (rec, 1.0)
        return box, rec
    return None, None


def coerce_ocr_box_points(box) -> list:
    if box is None:
        return []
    if hasattr(box, "tolist"):
        box = box.tolist()
    if isinstance(box, tuple):
        box = list(box)
    if not isinstance(box, list):
        return []
    if len(box) == 4 and all(isinstance(value, (int, float)) for value in box):
        left, top, right, bottom = box
        return [[left, top], [right, top], [right, bottom], [left, bottom]]
    points = []
    for point in box:
        if hasattr(point, "tolist"):
            point = point.tolist()
        if isinstance(point, tuple):
            point = list(point)
        if isinstance(point, list) and len(point) >= 2:
            points.append(point)
    return points


def fill_video_fields_from_ocr(video_info: dict, ocr_items) -> None:
    items = ocr_items if isinstance(ocr_items, list) else []

    blogger_name = ""
    publish_time = ""
    like_count = ""
    comment_count = ""
    share_count = ""

    for item in items:
        text = (item.get("text", "") or "").strip()
        x = item.get("x", 0)
        y = item.get("y", 0)
        if not text:
            continue
        if not blogger_name and ("关注" in text or "+关注" in text):
            blogger_name = text.replace("+关注", "").replace("关注", "").strip()
            continue
        if not blogger_name and 2120 <= y <= 2265 and 80 <= x <= 460:
            if re.fullmatch(r"[\u4e00-\u9fa5A-Za-z0-9_]{2,20}", text):
                blogger_name = text
        if "VideoMate" in text:
            continue
        if not publish_time and re.search(r"(\d+(秒|分钟|小时|天|周|月|年)前|\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2})", text):
            publish_time = text

    stats = []
    for item in items:
        text = (item.get("text", "") or "").strip()
        x = item.get("x", 0)
        y = item.get("y", 0)
        if 2140 <= y <= 2300 and x >= 540:
            match = re.fullmatch(r"[\d.]+[wW万]?", text)
            if match:
                stats.append((x, match.group(0)))
    stats.sort(key=lambda pair: pair[0])
    if len(stats) >= 1:
        like_count = stats[0][1]
    if len(stats) >= 2:
        comment_count = stats[1][1]
    if len(stats) >= 3:
        share_count = stats[2][1]

    video_info["blogger_name"] = blogger_name
    video_info["publish_time"] = publish_time
    video_info["like_count"] = like_count
    video_info["comment_count"] = comment_count
    video_info["share_count"] = share_count


def find_traffic_marker_text_local(image_path: str) -> str:
    texts = [item["text"] for item in local_ocr_image(image_path)]
    return find_traffic_marker_text_from_texts(texts)


def find_traffic_marker_text_from_items(ocr_items) -> str:
    texts = [(item.get("text", "") or "").strip() for item in ocr_items or []]
    return find_traffic_marker_text_from_texts(texts)


def find_traffic_marker_text_from_texts(texts: list[str]) -> str:
    for text in texts:
        if not text:
            continue
        if "免费剧集" in text or re.search(r"全\s*\d+\s*集", text):
            return text
    merged = "".join(text for text in texts if text)
    if "免费剧集" in merged or re.search(r"全\s*\d+\s*集", merged):
        return merged
    return ""


async def open_traffic_subject(session) -> None:
    marker_x, marker_y = scale_point(TRAFFIC_MARKER_X, TRAFFIC_MARKER_Y)
    episode_x, episode_y = scale_point(TRAFFIC_FIRST_EPISODE_X, TRAFFIC_FIRST_EPISODE_Y)
    code = f"""
import time
from ascript.android import action

action.click({marker_x}, {marker_y})
time.sleep(1.5)
action.click({episode_x}, {episode_y})
time.sleep(2.8)
print("[OK] TRAFFIC_SUBJECT_OPENED")
"""
    await run_on_phone(session, code, log_sec=6)
    await asyncio.sleep(1.0)


async def open_traffic_avatar_card(session) -> None:
    avatar_x, avatar_y = scale_point(TRAFFIC_AVATAR_X, TRAFFIC_AVATAR_Y)
    code = f"""
import time
from ascript.android import action

action.click({avatar_x}, {avatar_y})
time.sleep(1.8)
print("[OK] TRAFFIC_AVATAR_CARD_OPENED")
"""
    await run_on_phone(session, code, log_sec=5)
    await asyncio.sleep(0.8)


def extract_theater_account_name_from_image(image_path: str) -> str:
    items = local_ocr_image(image_path)
    candidates = []
    for item in items:
        text = (item.get("text", "") or "").strip()
        x = item.get("x", 0)
        y = item.get("y", 0)
        if not text or len(text) < 2:
            continue
        if "免费剧集" in text or ("第" in text and "集" in text):
            continue
        if "关注" in text or "+关注" in text:
            clean = text.replace("+关注", "").replace("关注", "").strip()
            if clean:
                return clean
        if any(token in text for token in ("有限公司", "有限责任公司", "原创内容", "关注", "私信", "主页", "视频", "剧集", "评论", "获赞", "粉丝")):
            continue
        if 720 <= y <= 980 and 120 <= x <= 760 and 2 <= len(text) <= 20:
            candidates.append((abs(y - 845) + abs(x - 420) / 10, text))
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1] if candidates else ""


def fill_profile_fields_from_ocr(profile_info: dict, ocr_items) -> None:
    items = ocr_items if isinstance(ocr_items, list) else []
    texts = [(item.get("text", "") or "").strip() for item in items]

    account = ""
    for index, text in enumerate(texts):
        if not text:
            continue
        if "视频号ID" in text or "视频号" in text or "账号" in text:
            account = pick_neighbor_value(texts, index)
            break

    if not account:
        for text in texts:
            compact = re.sub(r"\s+", "", text)
            if re.fullmatch(r"sph[A-Za-z0-9_-]{6,64}", compact):
                account = compact
                break

    profile_info["account"] = account


def fill_video_channel_id_from_profile(video_info: dict, profile_info: dict) -> None:
    account = profile_info.get("account", "") or ""
    if not account:
        return
    id_quality = analyze_video_channel_id(account)
    video_info["video_channel_id_raw"] = id_quality["raw"]
    video_info["video_channel_id"] = id_quality["normalized"]
    video_info["video_channel_id_needs_review"] = id_quality["needs_review"]
    video_info["video_channel_id_ambiguous_positions"] = id_quality["ambiguous_positions"]


async def open_traffic_more_info_from_avatar_card(session) -> None:
    more_button_x, more_button_y = scale_point(TRAFFIC_MORE_BUTTON_X, TRAFFIC_MORE_BUTTON_Y)
    more_info_x, more_info_y = scale_point(TRAFFIC_MORE_INFO_X, TRAFFIC_MORE_INFO_Y)
    code = f"""
import time
from ascript.android import action

action.click({more_button_x}, {more_button_y})
time.sleep(1.6)
action.click({more_info_x}, {more_info_y})
time.sleep(2.0)
print("[OK] TRAFFIC_MORE_INFO_OPENED")
"""
    await run_on_phone(session, code, log_sec=8)
    await asyncio.sleep(1.0)


def fill_traffic_fields_from_ocr(traffic_info: dict, ocr_items) -> None:
    items = ocr_items if isinstance(ocr_items, list) else []
    texts = [(item.get("text", "") or "").strip() for item in items]

    raw_id = ""
    company_name = ""
    verified_at = ""

    for index, text in enumerate(texts):
        if not text:
            continue
        if not raw_id and ("视频号ID" in text or "视频号" in text or "账号" in text):
            raw_id = pick_neighbor_value(texts, index)
        if not company_name and ("企业全称" in text or "企业" in text or "公司" in text or "主体" in text):
            company_name = pick_neighbor_value(texts, index)
        if not verified_at and ("认证时间" in text or "完成微信认证" in text):
            verified_at = pick_neighbor_value(texts, index) if "认证时间" in text else text

    if not raw_id:
        for text in texts:
            compact = re.sub(r"\s+", "", text)
            if re.fullmatch(r"[A-Za-z0-9_-]{6,64}", compact) and not compact.isdigit():
                raw_id = compact
                break

    if not company_name:
        for text in texts:
            if any(token in text for token in ("有限公司", "有限责任公司", "公司")):
                company_name = text
                break

    if not verified_at:
        for text in texts:
            if re.search(r"\d{4}年\d{1,2}月\d{1,2}日", text):
                verified_at = text
                break

    id_quality = analyze_video_channel_id(raw_id)
    traffic_info["target_video_channel_id_raw"] = id_quality["raw"]
    traffic_info["target_video_channel_id"] = id_quality["normalized"]
    traffic_info["target_video_channel_id_needs_review"] = id_quality["needs_review"]
    traffic_info["target_video_channel_id_ambiguous_positions"] = id_quality["ambiguous_positions"]
    traffic_info["company_full_name"] = company_name
    traffic_info["company_verified_at"] = verified_at


def pick_neighbor_value(texts: list[str], index: int) -> str:
    for candidate_index in (index, index + 1, index - 1):
        if candidate_index < 0 or candidate_index >= len(texts):
            continue
        value = texts[candidate_index]
        if "：" in value:
            return value.split("：", 1)[1].strip()
        if ":" in value:
            return value.split(":", 1)[1].strip()
        if candidate_index != index and value:
            return value.strip()
    return ""


async def back_from_traffic_info(session) -> None:
    adb = find_adb()
    for index in range(4):
        subprocess.run(
            [adb, "shell", "input", "keyevent", "4"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        print(f"[traffic] ADB back {index + 1}/4")
        await asyncio.sleep(1.0 if index < 3 else 1.2)
