# Current Weixin Flow

## Start State

- User is already on the Weixin Channels page.
- Device control uses AScript MCP plus ADB.
- Primary swipe between videos uses `adb shell input swipe`.

## Main Flow

1. Search the keyword.
2. Switch to the video results tab.
3. Open the first video.
4. Confirm the playback page:
   - try UI tree first
   - if UI tree is not useful, capture an ADB screenshot and verify the bottom playback layout
5. Collect evidence for the current video:
   - screen recording
   - playback screenshot + OCR
   - traffic marker detection
   - traffic subject info when present
   - author card and author more-info page
   - share sheet and copied video link
   - save one JSON result
6. If more videos are requested:
   - ADB swipe up to the next video
   - confirm the next playback page
   - continue collection
7. Stop when `WEIXIN_MAX_VIDEOS` is reached.

## Current Reliable Points

- ADB-based swipe to the next video is working in the main flow.
- Playback-page confirmation now uses screenshot fallback and is no longer pure OCR.
- Key taps and crop regions are being migrated to screen-size-scaled coordinates based on `1080x2400`.

## Current Known Weak Point

- Share-sheet "copy link" OCR is still not fully stable.
- The fallback fixed tap is currently succeeding, so the end-to-end flow is not blocked.

## Database Import

- JSON-to-MySQL mapping lives in `weixin/db_mapping.py`.
- The schema now includes:
  - candidate basics
  - video/profile/traffic core fields
  - ambiguous-position JSON fields
  - media recording fields
  - screenshots JSON
- `captured_at` is normalized to MySQL `DATETIME`, and the original ISO string is also preserved as `captured_at_raw`.
