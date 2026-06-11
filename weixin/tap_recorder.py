"""Record touch coordinates from an Android phone through adb getevent.

Usage:
    python -u weixin\tap_recorder.py

Then operate the phone manually. Press Ctrl+C to stop.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_SCRCPY_DIR = Path(r"D:\software\scrcpy-win64-v3.3.3")
EVENT_RE = re.compile(
    r"(?:(/dev/input/event\d+):\s+)?(?:\[[^\]]+\]\s+)?"
    r"([0-9a-fA-F]{4})\s+([0-9a-fA-F]{4})\s+([0-9a-fA-F]+)"
)

EV_ABS = 0x0003
EV_KEY = 0x0001
ABS_MT_POSITION_X = 0x0035
ABS_MT_POSITION_Y = 0x0036
ABS_MT_TRACKING_ID = 0x0039
BTN_TOUCH = 0x014A


def find_adb() -> str:
    path = shutil.which("adb")
    if path:
        return path
    local = DEFAULT_SCRCPY_DIR / "adb.exe"
    if local.exists():
        return str(local)
    raise FileNotFoundError("adb not found on PATH or in D:\\software\\scrcpy-win64-v3.3.3")


def adb(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(
        [find_adb(), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def read_size() -> tuple[int, int]:
    p = adb(["shell", "wm", "size"])
    match = re.search(r"Physical size:\s*(\d+)x(\d+)", p.stdout)
    if not match:
        raise RuntimeError(f"cannot read screen size: {p.stdout or p.stderr}")
    return int(match.group(1)), int(match.group(2))


def read_abs_ranges() -> tuple[int, int]:
    p = adb(["shell", "getevent", "-lp"], timeout=20)
    max_x = max_y = 0
    event_path = ""
    for line in p.stdout.splitlines():
        device_match = re.search(r"add device \d+:\s+(\S+)", line)
        if device_match:
            event_path = device_match.group(1)
            continue
        max_match = re.search(r"(ABS_MT_POSITION_X|ABS_X|ABS_MT_POSITION_Y|ABS_Y).*max\s+(\d+)", line)
        if not max_match:
            continue
        code_name = max_match.group(1)
        raw_max = int(max_match.group(2))
        if code_name in ("ABS_MT_POSITION_X", "ABS_X"):
            max_x = max(max_x, raw_max)
        elif code_name in ("ABS_MT_POSITION_Y", "ABS_Y"):
            max_y = max(max_y, raw_max)
    return max_x, max_y


def find_touch_event() -> str | None:
    p = adb(["shell", "getevent", "-lp"], timeout=20)
    current_event = None
    current_text = []
    candidates = []
    for line in p.stdout.splitlines():
        device_match = re.search(r"add device \d+:\s+(\S+)", line)
        if device_match:
            if current_event and any("ABS_MT_POSITION_X" in item for item in current_text):
                candidates.append((current_event, "\n".join(current_text)))
            current_event = device_match.group(1)
            current_text = []
        elif current_event:
            current_text.append(line)
    if current_event and any("ABS_MT_POSITION_X" in item for item in current_text):
        candidates.append((current_event, "\n".join(current_text)))
    for event_path, text in candidates:
        if "BTN_TOUCH" in text:
            return event_path
    return candidates[0][0] if candidates else None


def hex_value(raw: str) -> int:
    value = int(raw, 16)
    if value & 0x80000000:
        value -= 0x100000000
    return value


def scale(value: int, raw_max: int, screen_max: int) -> int:
    if raw_max <= 0:
        return value
    return round(value * screen_max / raw_max)


def emit_tap(tap_index: int, raw_x: int, raw_y: int, max_x: int, max_y: int, width: int, height: int, down_at: float | None) -> None:
    x = scale(raw_x, max_x, width)
    y = scale(raw_y, max_y, height)
    duration_ms = 0
    if down_at is not None:
        duration_ms = round((time.monotonic() - down_at) * 1000)
    print(f"[tap {tap_index:02d}] x={x}, y={y}, duration={duration_ms}ms")
    sys.stdout.flush()


def main() -> int:
    adb_path = find_adb()
    width, height = read_size()
    max_x, max_y = read_abs_ranges()
    touch_event = find_touch_event()
    print(f"[adb] {adb_path}")
    print(f"[screen] {width}x{height}, touch_raw_max={max_x}x{max_y}, event={touch_event or 'auto'}")
    print("[record] operate the phone manually; Ctrl+C to stop")

    getevent_args = [adb_path, "shell", "getevent", "-lt"]
    if touch_event:
        getevent_args.append(touch_event)
    proc = subprocess.Popen(
        getevent_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    raw_x = raw_y = None
    down_at = None
    tap_index = 0
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            match = EVENT_RE.search(line)
            if not match:
                continue
            event_path = match.group(1)
            if touch_event and event_path != touch_event:
                continue
            etype = int(match.group(2), 16)
            code = int(match.group(3), 16)
            value = hex_value(match.group(4))

            if etype == EV_ABS and code in (ABS_MT_POSITION_X, 0x0000):
                raw_x = value
            elif etype == EV_ABS and code in (ABS_MT_POSITION_Y, 0x0001):
                raw_y = value
            elif etype == EV_ABS and code == ABS_MT_TRACKING_ID:
                if value >= 0:
                    down_at = time.monotonic()
                elif raw_x is not None and raw_y is not None:
                    tap_index += 1
                    emit_tap(tap_index, raw_x, raw_y, max_x, max_y, width, height, down_at)
                    down_at = None
            elif etype == EV_KEY and code == BTN_TOUCH:
                if value == 1:
                    down_at = time.monotonic()
                elif value == 0 and raw_x is not None and raw_y is not None:
                    tap_index += 1
                    emit_tap(tap_index, raw_x, raw_y, max_x, max_y, width, height, down_at)
                    down_at = None
    except KeyboardInterrupt:
        print("\n[record] stopped")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
