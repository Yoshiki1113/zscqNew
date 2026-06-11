---
name: weixin-video-monitor
description: >-
  This skill should be used when working with the Weixin Video Channel (微信视频号)
  evidence collection system located in the weixin/ directory. It covers the
  full automated monitoring pipeline: Android device connection via MCP/Ascript,
  in-app search, video playback evidence collection (screen recording,
  screenshots, OCR), author profile extraction, traffic marker detection for
  copyright infringement, and result persistence (JSON + MySQL). Use this skill
  whenever modifying, debugging, extending, or understanding any part of the
  weixin/ project, including main.py, collector.py, navigator.py, scanner.py,
  media_capture.py, models.py, store.py, db.py, or any step_tests/ scripts.
---

# Weixin Video Monitor Skill

## Overview

This project implements an automated evidence-collection pipeline for Weixin
Video Channel (微信视频号). It automates searching for suspected infringing
content, collecting video proof (screen recording + screenshots), extracting
textual information via local PaddleOCR, and persisting structured evidence
records as both JSON files and MySQL rows.

The system communicates with an Android phone through the **Ascript MCP server**
(`ascript_mcp.local`), which exposes tools for UI automation (`deploy_and_run`,
`dump_ui_tree`, `connect_device`, `scan_devices`). On the PC side, **scrcpy**
records screen video, **adb** captures screenshots, and **PaddleOCR (PP-OCRv5)**
processes captured images locally.

## Architecture

```
weixin/
├── main.py              Entry point (785 lines) — MCP lifecycle, search, orchestration
├── collector.py         Core evidence engine (1013 lines) — single-video collection
├── media_capture.py     Screen recording via scrcpy/adb/Ascript
├── navigator.py         Page navigation helpers (to discover, video channel, back, swipe)
├── scanner.py           OCR-based candidate scanning on search result pages
├── models.py            Data models: OCRItem, Candidate, EvidenceRecord
├── store.py             JSON persistence + dedup fingerprint cache
├── db.py + db_mapping.py  MySQL persistence (pymysql)
├── text_quality.py      OCR text cleaning and quality analysis
├── asr_local.py         Optional: faster-whisper speech-to-text on audio
├── tap_recorder.py      Coordinate recording utility via adb getevent
├── step_tests/          18 single-step test scripts for debugging each phase
├── jsons/               Output: per-record JSON files + results.jsonl
├── media/               Output: mp4 recordings + wav audio
├── screenshots/         Output: PNG screenshots from each collection step
└── .paddlex-cache/      Cached PaddleOCR models (PP-OCRv5)
```

## Full Pipeline (main.py run())

### Phase 1 — Startup & Connection (lines 712–726)

1. Print banner.
2. Start Ascript MCP server: `python -m ascript_mcp.local`.
3. Connect to phone:
   - First try direct IP (`172.16.1.216:9096`).
   - Then try ADB-discovered WiFi IP via `ip addr show wlan0`.
   - Finally scan LAN for devices on port 9096.

### Phase 2 — Search (lines 728–733)

1. Use `search_keyword()` (third definition, lines 602–635) to input and submit a
   keyword.
2. Navigate steps (fixed coordinates):
   - Tap top-center (540, 100) to expose search bar.
   - Tap magnifier icon (885, 180).
   - Tap search input field (300, 210).
   - Clear existing text by tapping delete key 20 times (957, 1703).
   - Type keyword via `action.input()`.
   - Tap search submit (950, 215).
   - Tap first result tab if needed (302, 350).
3. Skip OCR-based result-page verification for speed.

### Phase 3 — Video Stream Loop (lines 744–779)

1. Click first video result at (266, 964).
2. Load dedup fingerprints from `jsons/results.jsonl`.
3. For each video (up to `WEIXIN_MAX_VIDEOS`, default 10):
   - Build candidate fingerprint from current screen OCR.
   - Check dedup; stop after `max_duplicate_rounds` (3) consecutive duplicates.
   - Call `collector.collect_current_video()` to gather all evidence.
   - Save to JSON via `store.save_record()`.
   - Optionally write to MySQL via `db.insert_evidence_record()`.
   - Swipe up to next video via `navigator.swipe()`.

### Single-Video Evidence Collection (collector.py)

The function `collect_current_video()` (line 81) performs these steps in order:

| # | Step | Method | Output |
|---|------|--------|--------|
| 1 | **Record screen video** | `scrcpy --no-playback --record` for `record_seconds` (default 90s) | `media/scrcpy_*.mp4` |
| 2 | **Probe audio** | `ffprobe` on recorded mp4 | `has_audio` boolean |
| 3 | **Extract audio (if present)** | `ffmpeg` mono 16kHz wav | `media/scrcpy_*.wav` |
| 4 | **Screenshot playback page** | `adb exec-out screencap -p` | `screenshots/play_*.png` |
| 5 | **OCR playback page** | Local PaddleOCR (PP-OCRv5) | `video_info` fields |
| 6 | **Detect traffic marker** | OCR region crop (left=66, top=1635, right=666, bottom=1721), search for "免费剧集" or "全N集" | `traffic_info.marker_text` |
| 7 | **Enter traffic subject (if marker found)** | Tap marker → tap first episode → tap avatar → more-info | Traffic subject screenshots |
| 8 | **OCR traffic info** | Local PaddleOCR | Target account name, video channel ID, company name, verified date |
| 9 | **Open author profile card** | Tap avatar (140, 2140) | `screenshots/profile_card_*.png` |
| 10 | **OCR profile card** | Region crop (310, 735, 790, 885) | Blogger name |
| 11 | **Open author more-info page** | Three dots (970, 835) → "更多信息" (540, 2050) | `screenshots/profile_info_*.png` |
| 12 | **OCR profile info** | Local PaddleOCR | Video channel ID, account name |
| 13 | **Return to playback** | `adb shell input keyevent 4` × 2 | — |
| 14 | **Copy video link** | Open share sheet → OCR find "复制链接" → clipboard read | `video_info.video_link` |

## Key Design Decisions

### Why adb exec-out screencap instead of MCP screen_capture?

Weixin Video Channel uses hardware-accelerated SurfaceView/TextureView for
content rendering. The MCP `screen_capture` tool and Android Accessibility
`dump_ui_tree` both return empty/black results for Weixin video pages.
`adb exec-out screencap -p` at the ADB level captures the composited screen
buffer, bypassing this limitation.

### Why local PaddleOCR instead of phone-side OCR?

Phone-side Ascript OCR (`Ocr.ocr()`) was unreliable and slow for this use case.
Screenshots are captured via adb to the PC, and PP-OCRv5 (PaddleOCR) processes
them locally. Models are cached in `.paddlex-cache/`.

### Fixed Coordinates Strategy

Since UI tree access is unavailable for Weixin pages, all interactions use
hardcoded pixel coordinates calibrated for a 1080×2400 display. Critical
coordinates are defined as constants in `collector.py` (lines 20–54).

## Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `WEIXIN_MAX_VIDEOS` | 10 | Max videos to collect per run |
| `WEIXIN_RECORD_SECONDS` | 90 | Duration of screen recording per video |
| `WEIXIN_VERIFY_VIDEO_PAGE` | false | Whether to OCR-verify entry to video detail page |
| `WEIXIN_WRITE_DB` | false | Whether to insert records into MySQL |
| `WEIXIN_DB_HOST` | localhost | MySQL host |
| `WEIXIN_DB_PORT` | 3306 | MySQL port |
| `WEIXIN_DB_USER` | root | MySQL user |
| `WEIXIN_DB_PASSWORD` | 1234 | MySQL password |
| `WEIXIN_DB_NAME` | zscq | MySQL database name |

## Data Flow

```
EvidenceRecord (models.py)
  ├── platform: "weixin"
  ├── search_keyword
  ├── capture_time / capture_timestamp
  ├── candidate: { fingerprint, title_text, author_name, ... }
  ├── video_info: { blogger_name, video_channel_id, video_link, like_count, ... }
  ├── profile_info: { name, account, raw_ocr }
  ├── traffic_info: { has_traffic_marker, marker_text, target_blogger_name, company_full_name, ... }
  ├── media_info: { recording_video_path, recording_audio_path, has_audio, ... }
  └── screenshots: [ path1, path2, ... ]
```

Output paths:
- Per-record JSON: `jsons/result_{timestamp}_{fingerprint[:12]}.json`
- Aggregate JSONL: `jsons/results.jsonl`
- MySQL table: `zscq.weixin_video_evidence`

## Step Tests

18 single-step test scripts in `weixin/step_tests/` allow isolated debugging
of each phase. See `references/step-tests.md` for the full list and usage.

## Common Patterns When Modifying This Project

### Adding a new collection step

1. Define coordinate constants in `collector.py`.
2. Write an async function that uses `run_on_phone()` for UI interaction and
   `capture_single_with_adb_fallback()` for screenshots.
3. Use `local_ocr_image()` for text extraction from screenshots.
4. Add the step call inside `collect_current_video()`.

### Changing coordinates

All interaction coordinates are in `collector.py` (lines 20–54) and `main.py`
search/navigation functions. The display is assumed to be 1080×2400.

### Debugging a single step

Use the corresponding script in `step_tests/`. Each script starts its own MCP
session and tests one specific operation in isolation.

## Module Reference

For detailed module-level documentation, see:
- `references/modules.md` — Per-module API docs and implementation notes
- `references/step-tests.md` — Complete list of step test scripts and their purposes
