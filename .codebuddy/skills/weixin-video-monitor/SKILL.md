---
name: weixin-video-monitor
description: >-
  This skill should be used when working with the Weixin Video Channel (微信视频号)
  evidence collection system located in the weixin/ directory. It covers the
  full automated monitoring pipeline: Android device connection via MCP/Ascript,
  in-app search, video playback evidence collection (screen recording,
  screenshots, OCR), iFlytek (primary cloud) / SenseVoice / Paraformer offline speech-to-text, author profile extraction,
  traffic marker detection for copyright infringement, and result persistence
  (JSON + MySQL). Also includes the FastAPI web platform (weixin/web/) for
  one-click evidence collection with real-time SSE monitoring. Use this skill
  whenever modifying, debugging, extending, or understanding any part of the
  weixin/ project.
---

# Weixin Video Monitor Skill

## Overview

This project implements an automated evidence-collection pipeline for Weixin
Video Channel (微信视频号). It automates searching for suspected infringing
content, collecting video proof (screen recording + screenshots), extracting
textual information via local PaddleOCR, transcribing audio via iFlytek (primary cloud) / SenseVoice / Paraformer offline
ASR, and persisting structured evidence records as both JSON files and MySQL rows.

The system communicates with an Android phone through the **Ascript MCP server**
(`ascript_mcp.local`), which exposes tools for UI automation. On the PC side,
**scrcpy** records screen video, **adb** captures screenshots, **PaddleOCR
(PP-OCRv5)** processes captured images locally, and **iFlytek (cloud, primary)** / **SenseVoice (sherpa-onnx)** / **Paraformer (sherpa-onnx)** performs offline
speech-to-text on extracted audio.

## Architecture

```
weixin/
├── main.py                Entry point — MCP lifecycle, search, orchestration
├── collector.py           Core evidence engine — single-video collection (14 steps)
├── media_capture.py       Screen recording via scrcpy/adb/Ascript
├── asr_xunfei.py           iFlytek cloud speech-to-text (primary, WebSocket v2)
├── asr_sensevoice.py       SenseVoice offline speech-to-text (sherpa-onnx)
├── asr_paraformer.py       Paraformer offline speech-to-text (sherpa-onnx)
├── asr_local.py           Legacy: faster-whisper ASR (not used in pipeline)
├── navigator.py           Page navigation helpers (back, swipe, discover)
├── scanner.py             OCR-based candidate scanning on search result pages
├── models.py              Data models: OCRItem, Candidate, EvidenceRecord, Task, ReviewResult
├── store.py               JSON persistence + dedup fingerprint cache + HTML preview
├── db.py + db_mapping.py  MySQL persistence (pymysql)
├── text_quality.py        OCR text cleaning and quality analysis
├── tap_recorder.py        Coordinate recording utility via adb getevent
├── step_tests/            20+ single-step test scripts (test_xunfei_asr.py, test_sensevoice_asr.py, test_paraformer_asr.py, test_all_asr.py)
├── web/                   [NEW] FastAPI web platform for one-click evidence collection
│   ├── app.py             FastAPI entry point (port 8900)
│   ├── config.py          DB + directory configuration
│   ├── routes/            home, task (SSE), results, evidence
│   ├── services/          checks, task_runner, db_service
│   ├── templates/         Jinja2 templates (home, task, results, evidence)
│   └── static/            CSS + JS (SSE client, status polling, stop button)
├── jsons/                 Output: per-record JSON files + results.jsonl
├── media/                 Output: mp4 recordings + wav audio + asr.txt/asr.json
├── screenshots/           Output: PNG screenshots from each collection step
└── .paddlex-cache/        Cached PaddleOCR models (PP-OCRv5)
```

## Full Pipeline (main.py run())

### Phase 1 — Startup & Connection

1. Print banner.
2. Start Ascript MCP server: `python -m ascript_mcp.local`.
3. Connect to phone via direct IP, ADB WiFi IP, or LAN scan.

### Phase 2 — Search

1. Use `search_keyword()` to input and submit a keyword via fixed coordinates.
2. Steps: tap header (540,100) → magnifier (885,180) → input (300,210) → clear ×20 (957,1703) → type keyword → submit (950,215) → video tab (302,350).

### Phase 3 — Video Stream Loop

1. Click first video result at (266, 964).
2. Load dedup fingerprints from `jsons/results.jsonl`.
3. For each video (up to `WEIXIN_MAX_VIDEOS`, default 10):
   - Build candidate fingerprint from current screen OCR.
   - Check dedup; stop after `max_duplicate_rounds` (3) consecutive duplicates.
   - Call `collector.collect_current_video()` to gather all evidence.
   - Stop recording → `attach_recording_media()` (probe/extract audio + **iFlytek/SenseVoice/Paraformer ASR**)
   - Save to JSON via `store.save_record()`.
   - Optionally write to MySQL via `db.insert_evidence_record()`.
   - Swipe up to next video via `navigator.swipe()`.
   - Start new recording segment for next video.

### Single-Video Evidence Collection (collector.py)

`collect_current_video()` performs these steps **in order**:

| # | Step | Method | Output |
|---|------|--------|--------|
| 1 | **Record screen video** | `scrcpy --no-playback --record` (default 90s) | `media/scrcpy_*.mp4` |
| 2 | **Probe audio** | `ffprobe` on recorded mp4 | `has_audio` boolean |
| 3 | **Extract audio (if present)** | `ffmpeg` mono 16kHz pcm_s16le wav | `media/scrcpy_*.wav` |
| 3a | **ASR (iFlytek→SenseVoice→Paraformer)** | `asr_sensevoice.run_asr_pipeline()` | `media/{vid}.asr.txt`, `.asr.json` |
| 4 | **Screenshot playback page** | `adb exec-out screencap -p` | `screenshots/play_*.png` |
| 5 | **OCR playback page** | Local PaddleOCR (PP-OCRv5) | `video_info` fields |
| 6 | **Detect traffic marker** | OCR region crop, search "免费剧集"/"全N集" | `traffic_info.marker_text` |
| 7 | **Enter traffic subject** | Tap marker → episode → avatar → more-info | Traffic screenshots |
| 8 | **OCR traffic info** | Local PaddleOCR | Target account name, channel ID, company |
| 9 | **Open author profile card** | Tap avatar (140, 2140) | `screenshots/profile_card_*.png` |
| 10 | **OCR profile card** | Region crop (310, 735, 790, 885) | Blogger name |
| 11 | **Open author more-info page** | Three dots (970, 835) → "更多信息" (540, 2050) | `screenshots/profile_info_*.png` |
| 12 | **OCR profile info** | Local PaddleOCR | Video channel ID, account name |
| 13 | **Return to playback** | `adb shell input keyevent 4` × 2 | — |
| 14 | **Copy video link** | Open share sheet → OCR "复制链接" → clipboard | `video_info.video_link` |

## ASR Pipeline (`run_asr_pipeline()`)

Dispatch priority: **iFlytek (cloud, primary, auto-slicing)** → **SenseVoice (offline)** → **Paraformer (offline)**.
After each backend succeeds, script matching is auto-triggered via `_run_script_match()`.

> **Detailed docs**: See the `asr-script-matching` skill for full ASR architecture,
> iFlytek auto-slicing logic, script matching algorithm, and HTML comparison reports.

### SenseVoice via sherpa-onnx

Model at `D:\code\vscodeWorkDir\vosk\sensevoice\sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17\`:
- **model.int8.onnx** (preferred, int8 quantized): faster CPU inference
- **model.onnx** (full precision fallback)
- **tokens.txt**: vocabulary
- Supports: zh, en, ja, ko, yue + auto language detection + ITN + punctuation
- Model load: ~1.1s, Inference: ~0.2s for 12s audio (72x real-time on CPU)
- License: Apache 2.0

### run_asr_pipeline()

```python
from asr_sensevoice import run_asr_pipeline
run_asr_pipeline(record, wav_path, video_identifier)
```

Tries SenseVoice first; if model not found or import fails, falls back to Vosk.
Populates `media_info` fields: asr_text, asr_text_path, asr_json_path, asr_model, asr_source_video_identifier.
ASR backend recorded in `asr_json["backend"]` ("sensevoice" or "vosk").

### Integration Points (identical for both backends)

1. **`main.py` `attach_recording_media()`**: After extract_audio → computing vid → run_asr_pipeline()
2. **`collector.py` pre-recorded branch**: Same flow as main.py
3. **`web/services/task_runner.py`**: After collect + hold → if audio exists → run_asr_pipeline() + file tracking

### iFlytek Cloud (`asr_xunfei.py`) — Primary

- Endpoint: `wss://ws-api.xfyun.cn/v2/iat` (WebSocket v2)
- Credentials from https://console.xfyun.cn/ → 语音听写（流式版）
- Env vars: `XUNFEI_APPID`, `XUNFEI_APIKEY`, `XUNFEI_APISECRET`
- 10000 free calls, ~3.3s for 12s audio, excellent accuracy + punctuation

### Paraformer via sherpa-onnx (`asr_paraformer.py`)

- Model: `D:\code\vscodeWorkDir\vosk\paraformer\sherpa-onnx-paraformer-zh-2024-03-09\`
- model.int8.onnx (~100MB), tokens.txt, am.mvn
- Fastest: 0.1s inference for 12s audio (98x real-time), no punctuation
- License: Apache 2.0

### Anti-Mixing Rule

All ASR output files named by `video_identifier`:
- `media/{video_identifier}.asr.txt` / `.asr.json`
- `asr_source_video_identifier` for binding verification

### Integration Points

1. **`main.py`** / **`collector.py`**: After extract_audio → `run_asr_pipeline()`
2. **`web/services/task_runner.py`**: After collect + hold → if audio → `run_asr_pipeline()`

### Step Tests

```bash
# All backends comparison
python weixin/step_tests/test_all_asr.py --audio media/xxx.wav
# Individual tests
python weixin/step_tests/test_xunfei_asr.py --audio media/xxx.wav
python weixin/step_tests/test_sensevoice_asr.py --audio media/xxx.wav
python weixin/step_tests/test_paraformer_asr.py --audio media/xxx.wav
```

## Web Platform (`weixin/web/`)

FastAPI-based web UI on port 8900 for one-click evidence collection with real-time monitoring.

### Pages & Routes

| Page | Route | Features |
|------|-------|----------|
| Home | `GET /` | Platform selector, keyword input, 5 pre-flight checks (USB/ADB/AScript/Recording/Storage), "一键取证" button with confirmation modal |
| Task Monitor | `GET /task/{id}` | Real-time SSE log stream, current step display, stop button with file cleanup |
| Results List | `GET /results` | Card grid with filtering by blogger name, review status, date range |
| Evidence Detail | `GET /evidence/{id}` | Dual-column: left structured fields + review buttons, right video player + screenshot gallery + raw JSON |

### Key Features

- **Confirmation Modal**: Before starting, shows "请手动登入微信并打开至视频号播放页主页" with "我已完成" button
- **Stop Button**: Interrupts running pipeline via `asyncio.Event`, cleans up created files (screenshots, JSONs, HTMLs, media) by `_session_stamp` glob matching
- **SSE Logging**: `GET /api/tasks/{task_id}/stream` returns `StreamingResponse` pushing log lines via `asyncio.Queue`
- **Review Workflow**: Three status buttons (侵权/白名单/不确定) + notes → writes to `review_results` table

### Web Task Runner Flow

1. MCP connect → device connect
2. Search keyword
3. Click first video → load dedup fingerprints
4. **Loop**: build candidate → dedup check → `collect_current_video()` → hold → ASR (if audio) → `save_record()` → DB insert → swipe up → repeat
5. File tracking for cleanup: `_track_file()` + `_session_stamp`-based glob cleanup

## Data Flow

```
EvidenceRecord (models.py)
  ├── platform: "weixin"
  ├── search_keyword
  ├── capture_time / capture_timestamp
  ├── candidate: { fingerprint, video_identifier, title_text, author_name, ... }
  ├── video_info: { blogger_name, video_channel_id, video_link, like_count, ... }
  ├── profile_info: { name, account, subject_type, company_full_name, ... }
  ├── traffic_info: { has_traffic_marker, marker_text, target_blogger_name, company_full_name, ... }
  ├── media_info: {
  │     recording_video_path, recording_audio_path, has_audio,
  │     asr_text, asr_text_path, asr_json_path, asr_model, asr_source_video_identifier
  │   }
  └── screenshots: [ path1, path2, ... ]
```

Output paths:
- Per-record JSON: `jsons/result_{timestamp}_{keyword}_{blogger}_{video_identifier}.json`
- Per-record HTML: `jsons/result_{timestamp}_{keyword}_{blogger}_{video_identifier}.html`
- Aggregate JSONL: `jsons/results.jsonl`
- MySQL tables: `zscq.weixin_video_evidence`, `zscq.tasks`, `zscq.review_results`

## Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `WEIXIN_MAX_VIDEOS` | 10 | Max videos to collect per run |
| `WEIXIN_RECORD_SECONDS` | 300 | Recording duration per video (CLI only) |
| `WEIXIN_POST_EVIDENCE_HOLD_SECONDS` | 240 | Hold time after collection before stopping recording |
| `WEIXIN_VERIFY_VIDEO_PAGE` | false | Whether to OCR-verify video detail page entry |
| `WEIXIN_WRITE_DB` | false | Whether to insert records into MySQL |
| `WEIXIN_DB_HOST/PORT/USER/PASSWORD/NAME` | localhost:3306 | MySQL connection |
| `VOSK_MODEL_DIR` | auto-detect | Path to Vosk model directory |
| `SENSEVOICE_MODEL_DIR` | auto-detect | Path to SenseVoice ONNX model directory |

## Database Schema

### `weixin_video_evidence` — Evidence records (40+ columns)
Key columns: search_keyword, candidate_fingerprint, video_blogger_name, video_channel_id, video_link, like/comment/share_count, profile_name/account/subject_type, company_full_name, has_traffic_marker, recording_video/audio_path, asr_text/asr_text_path/asr_json_path/asr_model/asr_source_video_identifier, review_status, screenshots_json.
Backends: "vosk-model-cn-0.22" (Vosk) or "sherpa-onnx-sense-voice-..." (SenseVoice).

### `tasks` — Task lifecycle
id, keyword, status (pending/running/completed/failed/cancelled), log_json, video_count, started_at/ended_at, created_at.

### `review_results` — Human review verdicts
evidence_row_id (unique), review_status (侵权/白名单/不确定), reviewer, notes, reviewed_at.

## Step Tests (19 scripts)

| Script | Tests |
|--------|-------|
| `test_sensevoice_asr.py` | **[NEW]** SenseVoice offline speech-to-text via sherpa-onnx, optional Vosk comparison |
| `test_vosk_asr.py` | Vosk offline speech-to-text on WAV files |
| `test_search.py` | Search keyword input and submission |
| `test_click_first_video.py` | Click first video result |
| `test_collect_traffic_info.py` | Traffic marker detection + subject collection |
| `test_copy_video_link.py` | Share sheet → clipboard video link copy |
| `test_fast_profile_flow.py` | Author profile card + more-info page |
| `test_read_video_info.py` | OCR playback page for video metadata |
| `test_capture_traffic_region.py` | Region crop for traffic marker OCR |
| `test_swipe_up.py` | Swipe to next video |
| `test_back_button.py` | Back navigation |
| `test_clipboard_read.py` | Clipboard read via Ascript/Android |
| `test_dump_ui_tree.py` | UI tree dump (limited on Weixin) |
| `test_navigate_discover.py` | Navigate to discover page |
| `test_navigate_video_channel.py` | Navigate to video channel |
| `test_ocr.py` | Local PaddleOCR test |
| `test_progress_bar.py` | Progress bar detection |
| `test_traffic_path_debug.py` | Traffic path debug |
| `test_insert_json_to_db.py` | DB insert from JSON |
| `大模型中文语音识别.py` | Xunfei iFlytek cloud ASR demo (not used) |

## Common Patterns When Modifying This Project

### Adding a new collection step
1. Define coordinate constants in `collector.py`.
2. Write an async function using `run_on_phone()` + `capture_single_with_adb_fallback()`.
3. Use `local_ocr_image()` for text extraction.
4. Add the step call inside `collect_current_video()`.

### Adding a new ASR backend
1. Create `weixin/asr_xxx.py` with `core_transcribe_for_record()`-compatible entry point.
2. Update `attach_recording_media()` in `main.py` and pre-recorded branch in `collector.py`.
3. Also update `web/services/task_runner.py` loop.
4. Add step test in `step_tests/`.

### Changing coordinates
All interaction coordinates are in `collector.py` (lines 20–54) and `main.py` search/navigation functions. Display assumed: 1080×2400.

### Debugging a single step
Use the corresponding script in `step_tests/`. Each script starts its own MCP session and tests one operation in isolation.

### Web platform changes
- Routes in `web/routes/`, services in `web/services/`, templates in `web/templates/`.
- Jinja2 filters registered in `web/app.py` **before** route imports.
- SSE uses `asyncio.Queue` + `StreamingResponse`.
- Stop functionality uses `asyncio.Event` + `_TaskCancelled` exception.
