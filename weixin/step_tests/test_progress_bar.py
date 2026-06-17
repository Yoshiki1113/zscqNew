"""Step test: on a playback page, reset the progress bar to start and read the time label."""
from __future__ import annotations

import asyncio
import cv2
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main  # noqa: E402
from core.collector import capture_single_via_adb_execout, crop_image_region, local_ocr_image  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

SHOW_CONTROLS_TAP_X = 540
SHOW_CONTROLS_TAP_Y = 1200
PROGRESS_BAR_Y = 2087
PROGRESS_BAR_START_X = 110
PROGRESS_BAR_END_X = 970
TIME_REGION_LEFT = 500
TIME_REGION_TOP = 1480
TIME_REGION_RIGHT = 980
TIME_REGION_BOTTOM = 1645
PROGRESS_REGION_LEFT = 60
PROGRESS_REGION_TOP = 2035
PROGRESS_REGION_RIGHT = 1020
PROGRESS_REGION_BOTTOM = 2145


def adb_input(*args: str) -> None:
    adb = main.find_adb()
    subprocess.run(
        [adb, "shell", "input", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def show_playback_controls() -> None:
    adb_input("tap", str(SHOW_CONTROLS_TAP_X), str(SHOW_CONTROLS_TAP_Y))
    time.sleep(0.6)


def reset_progress_to_start() -> None:
    adb_input(
        "swipe",
        str(PROGRESS_BAR_END_X),
        str(PROGRESS_BAR_Y),
        str(PROGRESS_BAR_START_X),
        str(PROGRESS_BAR_Y),
        "500",
    )
    time.sleep(1.0)


def normalize_time_text(text: str) -> str:
    compact = re.sub(r"\s+", "", text or "")
    compact = compact.replace("O", "0").replace("o", "0")
    compact = compact.replace("I", "1").replace("l", "1")
    return compact


def extract_time_text(ocr_items: list[dict]) -> str:
    candidates = []
    for item in ocr_items:
        raw_text = normalize_time_text(item.get("text", ""))
        x = item.get("x", 0)
        y = item.get("y", 0)
        match = re.search(r"\d{1,2}:\d{2}(?::\d{2})?", raw_text)
        if not match:
            continue
        text = match.group(0)
        candidates.append((abs(y - 1570) + abs(x - 700) / 10, text))
    candidates.sort(key=lambda pair: pair[0])
    return candidates[0][1] if candidates else ""


def parse_seconds(text: str) -> int | None:
    if not text:
        return None
    parts = [int(part) for part in text.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return minutes * 60 + seconds
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return hours * 3600 + minutes * 60 + seconds
    return None


def is_last_second(text: str) -> bool:
    seconds = parse_seconds(text)
    return seconds is not None and seconds <= 1


def capture_state(tag: str) -> dict:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shot_path = os.path.join(main.SCREENSHOT_DIR, f"progress_{tag}_{ts}.png")
    time_region_path = os.path.join(main.SCREENSHOT_DIR, f"progress_{tag}_time_region_{ts}.png")
    progress_region_path = os.path.join(main.SCREENSHOT_DIR, f"progress_{tag}_bar_region_{ts}.png")

    if not capture_single_via_adb_execout(shot_path):
        raise RuntimeError(f"failed to capture screenshot for {tag}")

    crop_image_region(shot_path, time_region_path, TIME_REGION_LEFT, TIME_REGION_TOP, TIME_REGION_RIGHT, TIME_REGION_BOTTOM)
    crop_image_region(
        shot_path,
        progress_region_path,
        PROGRESS_REGION_LEFT,
        PROGRESS_REGION_TOP,
        PROGRESS_REGION_RIGHT,
        PROGRESS_REGION_BOTTOM,
    )

    enlarged_time_region_path = os.path.join(main.SCREENSHOT_DIR, f"progress_{tag}_time_region_x3_{ts}.png")
    enlarge_region_image(time_region_path, enlarged_time_region_path, scale=3)

    time_items = local_ocr_image(enlarged_time_region_path if os.path.exists(enlarged_time_region_path) else time_region_path)
    time_text = extract_time_text(time_items)
    return {
        "screenshot": shot_path,
        "time_region": time_region_path,
        "time_region_x3": enlarged_time_region_path,
        "progress_region": progress_region_path,
        "time_region_ocr": time_items,
        "time_text": time_text,
        "remaining_seconds": parse_seconds(time_text),
        "is_last_second": is_last_second(time_text),
    }


def enlarge_region_image(src_path: str, dst_path: str, scale: int = 3) -> None:
    img = cv2.imread(src_path)
    if img is None:
        return
    enlarged = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    cv2.imwrite(dst_path, enlarged)


async def run() -> None:
    print("[flow] playback page -> show controls -> read time -> reset progress -> read time again")
    show_playback_controls()
    before = capture_state("before_reset")
    print(f"[time] before reset: {before['time_text']!r}, seconds={before['remaining_seconds']}")

    reset_progress_to_start()
    show_playback_controls()
    after = capture_state("after_reset")
    print(f"[time] after reset: {after['time_text']!r}, seconds={after['remaining_seconds']}")

    result = {
        "progress_bar_y": PROGRESS_BAR_Y,
        "reset_swipe": {
            "start_x": PROGRESS_BAR_END_X,
            "end_x": PROGRESS_BAR_START_X,
            "y": PROGRESS_BAR_Y,
        },
        "last_second_rule": "remaining_seconds <= 1 from bottom-right time OCR",
        "before_reset": before,
        "after_reset": after,
        "reset_looks_effective": (
            before["remaining_seconds"] is not None
            and after["remaining_seconds"] is not None
            and after["remaining_seconds"] > before["remaining_seconds"]
        ),
    }
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")


if __name__ == "__main__":
    asyncio.run(run())
