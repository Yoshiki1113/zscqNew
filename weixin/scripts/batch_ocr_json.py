"""Batch OCR backfill for existing Weixin evidence JSON files.

Usage:
    cd weixin
    conda run -n zscq python scripts/batch_ocr_json.py

This script reads saved screenshots for each JSON record, runs local OCR in batch,
fills structured fields, rewrites the JSON, regenerates the sibling HTML preview,
and rebuilds results.jsonl from the individual JSON files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_WEIXIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_WEIXIN_DIR))
sys.path.insert(0, str((_WEIXIN_DIR / "core").resolve()))
from core import main as core_main  # noqa: E402

sys.modules.setdefault("main", core_main)

from core.collector import (  # noqa: E402
    extract_author_name_from_card_image,
    extract_theater_account_name_from_image,
    fill_profile_fields_from_ocr,
    fill_traffic_fields_from_ocr,
    fill_video_channel_id_from_profile,
    fill_video_fields_from_ocr,
    find_traffic_marker_target_local,
    local_ocr_image,
)
from core.store import render_record_html  # noqa: E402


JSONS_DIR = _WEIXIN_DIR / "core" / "jsons"


def resolve_path(path_value: str) -> Path | None:
    if not path_value:
        return None
    candidate = Path(path_value)
    if candidate.exists():
        return candidate
    candidate = (_WEIXIN_DIR / path_value).resolve()
    if candidate.exists():
        return candidate
    return None


def first_screenshot_path(paths: list[str], prefix: str, exclude_prefixes: tuple[str, ...] = ()) -> Path | None:
    for raw_path in paths or []:
        path = resolve_path(raw_path)
        if not path:
            continue
        lower = path.name.lower()
        if any(lower.startswith(excluded) for excluded in exclude_prefixes):
            continue
        if lower.startswith(prefix):
            return path
    return None


def read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json_and_html(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)

    html_path = path.with_suffix(".html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(render_record_html(data, json_path=str(path)))


def backfill_video_info(data: dict, screenshots: list[str]) -> bool:
    changed = False
    video_info = data.setdefault("video_info", {})
    profile_info = data.setdefault("profile_info", {})

    play_path = first_screenshot_path(screenshots, "play_")
    if play_path:
        play_items = local_ocr_image(str(play_path))
        if play_items:
            if video_info.get("raw_ocr") != play_items:
                changed = True
            video_info["raw_ocr"] = play_items
            before = dict(video_info)
            fill_video_fields_from_ocr(video_info, play_items)
            changed = changed or video_info != before

    card_path = first_screenshot_path(
        screenshots,
        "profile_card_",
        exclude_prefixes=("profile_card_name_region_",),
    )
    region_path = first_screenshot_path(screenshots, "profile_card_name_region_")
    if card_path:
        blogger_name = extract_author_name_from_card_image(
            str(card_path),
            str(region_path) if region_path else "",
        )
        if blogger_name and video_info.get("blogger_name") != blogger_name:
            video_info["blogger_name"] = blogger_name
            changed = True
        if blogger_name and not profile_info.get("name"):
            profile_info["name"] = blogger_name
            changed = True

    profile_path = first_screenshot_path(screenshots, "profile_info_")
    if profile_path:
        profile_items = local_ocr_image(str(profile_path))
        if profile_items:
            if profile_info.get("raw_ocr") != profile_items:
                changed = True
            profile_info["raw_ocr"] = profile_items
            before_profile = dict(profile_info)
            fill_profile_fields_from_ocr(profile_info, profile_items)
            if not profile_info.get("name"):
                profile_info["name"] = video_info.get("blogger_name", "")
            changed = changed or profile_info != before_profile

            before_video = dict(video_info)
            fill_video_channel_id_from_profile(video_info, profile_info)
            changed = changed or video_info != before_video

    return changed


def backfill_traffic_info(data: dict, screenshots: list[str]) -> bool:
    changed = False
    traffic_info = data.setdefault("traffic_info", {})

    marker_region_path = first_screenshot_path(screenshots, "traffic_marker_region_")
    if marker_region_path:
        marker_text, _ = find_traffic_marker_target_local(str(marker_region_path))
        if marker_text:
            if not traffic_info.get("has_traffic_marker"):
                traffic_info["has_traffic_marker"] = True
                changed = True
            if traffic_info.get("marker_text") != marker_text:
                traffic_info["marker_text"] = marker_text
                changed = True

    traffic_page_path = first_screenshot_path(
        screenshots,
        "traffic_page_",
        exclude_prefixes=("traffic_page_name_region_",),
    )
    traffic_name_region_path = first_screenshot_path(screenshots, "traffic_page_name_region_")
    if traffic_page_path:
        target_name = extract_author_name_from_card_image(
            str(traffic_page_path),
            str(traffic_name_region_path) if traffic_name_region_path else "",
        )
        if not target_name:
            target_name = extract_theater_account_name_from_image(str(traffic_page_path))
        if target_name and traffic_info.get("target_blogger_name") != target_name:
            traffic_info["target_blogger_name"] = target_name
            changed = True

    traffic_info_path = first_screenshot_path(screenshots, "traffic_info_")
    if traffic_info_path:
        info_items = local_ocr_image(str(traffic_info_path))
        if info_items:
            if traffic_info.get("raw_ocr") != info_items:
                changed = True
            traffic_info["raw_ocr"] = info_items
            before = dict(traffic_info)
            fill_traffic_fields_from_ocr(traffic_info, info_items)
            changed = changed or traffic_info != before

    return changed


def rebuild_results_jsonl(json_files: list[Path]) -> None:
    lines = []
    for path in json_files:
        if path.name == "results.jsonl":
            continue
        data = read_json(path)
        lines.append(json.dumps(data, ensure_ascii=False))

    output_path = JSONS_DIR / "results.jsonl"
    with open(output_path, "w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line + "\n")


def main() -> None:
    json_files = sorted(
        path for path in JSONS_DIR.glob("*.json")
        if path.name != "results.jsonl"
    )
    print(f"[batch-ocr] Found {len(json_files)} JSON files in {JSONS_DIR}")

    processed = 0
    skipped = 0

    for index, json_path in enumerate(json_files, 1):
        print(f"\n[{index}/{len(json_files)}] {json_path.name}")
        data = read_json(json_path)
        screenshots = data.get("screenshots", []) or []
        if not screenshots:
            print("  [skip] no screenshots recorded")
            skipped += 1
            continue

        changed = False
        changed = backfill_video_info(data, screenshots) or changed
        changed = backfill_traffic_info(data, screenshots) or changed

        if not changed:
            print("  [skip] no OCR-derived changes")
            skipped += 1
            continue

        write_json_and_html(json_path, data)
        print("  [save] json/html refreshed")
        processed += 1

    rebuild_results_jsonl(json_files)
    print(f"\n[batch-ocr] Done: processed={processed}, skipped={skipped}")


if __name__ == "__main__":
    main()
