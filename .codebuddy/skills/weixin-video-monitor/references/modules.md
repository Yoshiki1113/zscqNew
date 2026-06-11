# Module Reference

## main.py (785 lines)

**Role**: Entry point and MCP lifecycle manager.

### Key Functions

| Function | Lines | Purpose |
|----------|-------|---------|
| `find_adb()` | 44–49 | Locate adb executable (PATH → scrcpy dir → "adb") |
| `get_phone_wlan_ip_via_adb()` | 52–66 | Get phone WiFi IP via `adb shell ip addr show wlan0` |
| `env_int()` / `env_bool()` | 69–85 | Environment variable readers with defaults |
| `run_on_phone(session, code, log_sec)` | 88–100 | Execute Python snippet on phone via MCP `deploy_and_run`, return `{log, images}` |
| `get_ui_tree(session)` | 103–108 | Dump Android accessibility UI tree (limited use for Weixin) |
| `walk_ui(data, keyword, id_sub, clickable)` | 111–138 | Recursive UI tree search |
| `connect_device_auto(session)` | 141–188 | Auto-connect: direct IP → ADB IP → LAN scan |
| `ensure_wechat_home(session)` | 191–201 | Launch Weixin via `am start` |
| `navigate_to_discover(session)` | 204–218 | Navigate to "发现" tab (selector → coord fallback) |
| `navigate_to_video_channel(session)` | 222–237 | Navigate to "视频号" entry |
| `search_keyword(session, keyword)` ×3 | 240–635 | Three definitions with progressive simplification (see below) |
| `go_back(session)` | 304–315 | Press back via `adb shell input keyevent 4` |
| `swipe_up(session)` | 318–329 | Swipe up to next video (540,2000→540,400) |
| `ocr_recognize(session, engine)` | 332–376 | Run phone-side PaddleOCR, return `[{text, x, y, w, h}]` |
| `capture_single(session, path)` | 676–709 | Capture screenshot via Ascript `screen.capture_cv()` → base64 → local file |
| `wait_for_search_results(session, keyword, timeout)` | 512–525 | OCR-poll loop to confirm we reached search results page |
| `build_current_video_candidate(session, keyword, index)` | 638–673 | OCR current screen and build a candidate dict with fingerprint |
| `run()` | 712–781 | Main async entry: startup → search → collect loop |

### search_keyword() Evolution

There are three definitions; each later one shadows the previous:

1. **V1 (lines 240–301)**: Full flow including OCR-based result-page verification
   (`wait_for_search_results`), slow but reliable.
2. **V2 (lines 545–599)**: Streamlined — skips OCR verification, fast path for
   stable coordinate environments.
3. **V3 (lines 602–635, active)**: Fixed-coordinate path with slightly different
   timing. Also skips OCR verification. Currently used by `run()`.

---

## collector.py (1013 lines)

**Role**: Core evidence collection engine. Everything that happens on a single
video page flows through this module.

### Constants (lines 20–54)

```python
SHARE_BUTTON_X = 746         # Share button on playback page
SHARE_BUTTON_Y = 2153
SHARE_TRAY_SWIPE_START_X = 880  # Swipe share tray right→left
SHARE_TRAY_SWIPE_END_X = 140
SHARE_TRAY_Y = 1910
COPY_LINK_X = 950            # "复制链接" button default
COPY_LINK_Y = 1900

TRAFFIC_MARKER_X = 192       # Free-series marker (e.g. "全28集")
TRAFFIC_MARKER_Y = 1693
TRAFFIC_MARKER_LEFT = 66     # Marker OCR region crop
TRAFFIC_MARKER_TOP = 1635
TRAFFIC_MARKER_RIGHT = 666
TRAFFIC_MARKER_BOTTOM = 1721

AUTHOR_AVATAR_X = 140        # Author avatar on playback page
AUTHOR_AVATAR_Y = 2140
AUTHOR_MORE_BUTTON_X = 970   # Three-dots on author card
AUTHOR_MORE_BUTTON_Y = 835
AUTHOR_MORE_INFO_X = 540     # "更多信息" on dropdown
AUTHOR_MORE_INFO_Y = 2050
AUTHOR_CARD_NAME_LEFT = 310  # Name region on card
AUTHOR_CARD_NAME_TOP = 735
AUTHOR_CARD_NAME_RIGHT = 790
AUTHOR_CARD_NAME_BOTTOM = 885
```

### Key Functions

| Function | Lines | Purpose |
|----------|-------|---------|
| `collect_current_video()` | 81–149 | **Main entry**: orchestrates all evidence steps for one video |
| `capture_single_with_adb_fallback()` | 152–160 | Screenshot: adb exec-out first, then adb remote fallback |
| `write_and_validate_screenshot()` | 163–176 | Write screenshot bytes, validate via cv2 (not black, not flat) |
| `validate_screenshot_file()` | 179–195 | Check mean/std of image to reject black/flat captures |
| `capture_single_via_adb_execout()` | 198–210 | `adb exec-out screencap -p` — primary method |
| `capture_single_via_adb()` | 213–251 | `adb shell screencap` + `adb pull` — fallback |
| `copy_video_link()` | 264–294 | Full flow: set sentinel clipboard → share sheet → OCR copy-link → read clipboard |
| `extract_link_from_clipboard_text()` | 381–383 | Regex `https?://\S+` from raw clipboard text |
| `find_copy_link_button_from_image()` | 386–409 | OCR a crop region to locate "复制链接" button coordinates |
| `collect_traffic_info()` | 412–462 | Full traffic marker flow: detect → open subject → avatar card → more-info → OCR |
| `fill_video_fields_from_ocr()` | 768–815 | Parse playback page OCR into `video_info` dict |
| `fill_traffic_fields_from_ocr()` | 939–996 | Parse traffic page OCR into `traffic_info` dict |
| `fill_profile_fields_from_ocr()` | 891–910 | Parse profile page OCR into `profile_info` dict |
| `local_ocr_image()` | 629–663 | Run local PaddleOCR on an image file, return `[{text, x, y, w, h}]` |
| `get_local_paddle_ocr()` | 619–626 | Lazy-init singleton PaddleOCR instance |
| `crop_image_region()` | 603–616 | cv2-based region cropping |
| `extract_author_name_from_card_image()` | 519–529 | Try region OCR first, then full-card OCR |
| `is_probable_author_name()` | 550–576 | Heuristic filter: skip known non-name tokens |
| `find_traffic_marker_text_local()` | 818–820 | OCR a crop to find "免费剧集" or "全N集" |

---

## media_capture.py (312 lines)

**Role**: Screen recording via three methods (scrcpy preferred, adb fallback,
Ascript last resort). Also provides ffprobe/ffmpeg audio extraction.

### Functions

| Function | Lines | Purpose |
|----------|-------|---------|
| `capture_video(duration, method)` | 285–311 | **Main entry**: smart dispatch to best available method |
| `capture_with_scrcpy(duration)` | 191–214 | **Preferred**: `scrcpy --no-playback --record` for audio-capable recording |
| `capture_with_adb(duration, device_id)` | 236–282 | adb screenrecord on phone → adb pull to PC |
| `capture_with_phone_screenrecord(session, duration)` | 116–188 | Ascript-based: screenrecord on phone → base64 transfer |
| `probe_audio(video_path)` | 62–82 | ffprobe check for audio stream |
| `extract_audio(video_path)` | 85–113 | ffmpeg extract mono 16kHz wav for ASR |
| `available_capture_methods()` | 36–42 | List all available methods based on installed tools |

---

## navigator.py (117 lines)

**Role**: Thin wrapper around main.py navigation functions, providing a
consistent API for the collection loop.

| Function | Purpose |
|----------|---------|
| `ensure_home(session)` | Launch Weixin to home |
| `to_discover(session)` | Navigate to discover tab |
| `to_video_channel(session)` | Navigate to video channel |
| `search(session, keyword)` | Submit search |
| `back(session)` | ADB back key |
| `swipe(session, times)` | Swipe up N times |
| `wait_for_video_page(session, timeout)` | OCR-check for video detail page markers |
| `click_candidate(session, candidate)` | Click a candidate with multi-strategy fallback |

---

## scanner.py (164 lines)

**Role**: OCR-based candidate scanning for search result pages.

| Function | Purpose |
|----------|---------|
| `scan_current_screen(session, keyword)` | Full-screen OCR → extract video candidate cards |
| `_keyword_fragments(keyword)` | Break keyword into 4-char sliding window fragments for fuzzy match |
| `_text_matches_keyword(text, keyword)` | Match text against keyword or fragments |
| `is_hit(text, keywords)` | Simple multi-keyword containment check |
| `fingerprint(candidate)` | MD5 dedup fingerprint from keyword+author+title |

---

## models.py (105 lines)

**Role**: Data models as Python dataclasses.

| Class | Purpose |
|-------|---------|
| `OCRItem` | Single OCR result: text, x, y, w, h |
| `Candidate` | A search-result candidate video: keyword, title_text, author_name, publish_time, like/comment/share counts, click coords, score, fingerprint |
| `EvidenceRecord` | Complete evidence record with nested dicts for video_info, profile_info, traffic_info, media_info |

---

## store.py (50 lines)

**Role**: JSON persistence layer.

| Function | Purpose |
|----------|---------|
| `save_record(record)` | Save EvidenceRecord as `result_{ts}_{fp}.json` + append to `results.jsonl` |
| `load_seen(path)` | Load all fingerprints from `results.jsonl` for dedup |

---

## db.py + db_mapping.py (100 + 76 lines)

**Role**: MySQL persistence (optional, gated by `WEIXIN_WRITE_DB`).

### db.py Functions

| Function | Purpose |
|----------|---------|
| `get_connection(database)` | Create pymysql connection from env vars |
| `ensure_database_and_table()` | CREATE DATABASE + CREATE TABLE if not exists |
| `insert_evidence_row(row)` | INSERT a flat dict row |
| `insert_evidence_record(record)` | Flatten EvidenceRecord → insert |
| `insert_record_dict(record_dict)` | Dict → EvidenceRecord → insert |
| `insert_json_file(json_path)` | Read JSON file → insert |

### db_mapping.py

- `CREATE_TABLE_SQL`: Full DDL for `weixin_video_evidence` table
- `evidence_record_to_db_row(record)`: Flatten nested EvidenceRecord into a single flat row

---

## text_quality.py (38 lines)

**Role**: Clean and analyze OCR-extracted video channel IDs for ambiguous
characters (I/l/1, O/0).

| Function | Purpose |
|----------|---------|
| `compact_ocr_id(text)` | Strip non-ID characters |
| `analyze_video_channel_id(raw_text)` | Return normalized ID + list of ambiguous positions for review |
