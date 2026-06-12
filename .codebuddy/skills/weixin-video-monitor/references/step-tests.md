# Step Tests Reference

The `weixin/step_tests/` directory contains 18 single-step test scripts. Each
script starts its own MCP session and tests one specific operation in isolation.
This allows rapid debugging of individual pipeline steps without running the
full collection flow.

## Test Scripts

| Script | Size | Test Target | What It Validates |
|--------|------|------------|-------------------|
| `test_navigate_discover.py` | 6.1 KB | Navigation to "发现" tab | `navigate_to_discover()` — selector + coord fallback |
| `test_navigate_video_channel.py` | 6.0 KB | Navigation to "视频号" | `navigate_to_video_channel()` — enters video channel from discover page |
| `test_search.py` | 1.7 KB | Search keyword submission | `search_keyword()` — full input + submit flow |
| `test_click_first_video.py` | 5.6 KB | Click first search result | `click_first_video_result()` — enters video detail from result page |
| `test_read_video_info.py` | 9.1 KB | Read video page info | OCR recognition of blogger name, likes, comments on playback page |
| `test_ocr.py` | 5.9 KB | OCR full-screen recognition | Tests phone-side `Ocr.ocr()` and parse logic |
| `test_dump_ui_tree.py` | 7.2 KB | UI tree dump | Dumps Android accessibility tree (limited for Weixin) |
| `test_swipe_up.py` | 6.3 KB | Swipe to next video | `swipe_up()` gesture verification |
| `test_back_button.py` | 6.2 KB | ADB back key | `adb shell input keyevent 4` behavior |
| `test_progress_bar.py` | 5.7 KB | Video progress bar | Detects progress bar state on playback page |
| `test_capture_traffic_region.py` | 1.9 KB | Traffic marker screenshot | Tests capturing the traffic marker region crop |
| `test_collect_traffic_info.py` | 1.3 KB | Traffic info collection | Full `collect_traffic_info()` flow |
| `test_traffic_path_debug.py` | 3.6 KB | Traffic navigation path | Debugs the click path for entering traffic subject |
| `test_copy_video_link.py` | 1.1 KB | Copy video link | Tests share-sheet → copy-link → clipboard read |
| `test_clipboard_read.py` | 1.7 KB | Clipboard read | Tests `read_phone_clipboard()` and `set_phone_clipboard()` |
| `test_fast_profile_flow.py` | 2.4 KB | Fast profile entry | Tests rapid avatar → three-dot → more-info flow |
| `test_insert_json_to_db.py` | 548 B | DB insert | Tests `insert_json_file()` from an existing JSON result |
| `大模型中文语音识别.py` | 8.1 KB | ASR (Chinese STT) | Tests large-model Chinese speech recognition |

## Usage

Run any test from the `weixin/` directory:

```powershell
python .\step_tests\test_ocr.py
```

Each test:
1. Starts its own MCP session
2. Connects to the phone automatically
3. Performs the target operation
4. Prints detailed output including OCR results, coordinates, screenshots
5. Exits cleanly

## Test Dependencies

Tests typically depend on:
- Phone connected via USB/WiFi with Ascript service running (port 9096)
- Weixin app installed and in a known state (sometimes manually pre-positioned)
- `zscqAndroid` project deployed on phone (for `deploy_and_run` to work)
