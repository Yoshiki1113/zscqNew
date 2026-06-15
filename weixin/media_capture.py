"""Phone video capture and local media helpers for Weixin evidence collection."""
from __future__ import annotations

import base64
import os
import signal
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import main


MEDIA_DIR = Path(main.BASE_DIR) / "media"
MEDIA_DIR.mkdir(exist_ok=True)
DEFAULT_SCRCPY_DIR = Path(r"D:\software\scrcpy-win64-v3.3.3")


@dataclass
class RecordingSession:
    method: str
    local_path: Path
    process: subprocess.Popen
    started_at: str
    device_id: str | None = None
    remote_path: str = ""


def find_executable(name: str) -> str | None:
    path = shutil.which(name)
    if path:
        return path
    local = DEFAULT_SCRCPY_DIR / f"{name}.exe"
    if local.exists():
        return str(local)
    return None


def has_command(name: str) -> bool:
    return find_executable(name) is not None


def available_capture_methods() -> list[str]:
    methods = []
    if has_command("scrcpy"):
        methods.append("scrcpy")
    if has_command("adb"):
        methods.append("adb")
    methods.append("ascript")
    return methods


def run_checked(args: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    executable = find_executable(args[0])
    if executable:
        args = [executable] + args[1:]
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def probe_audio(video_path: str | Path) -> bool:
    """Return True if ffprobe sees at least one audio stream."""
    video_path = str(video_path)
    if not has_command("ffprobe"):
        raise RuntimeError("ffprobe is not available on PATH")
    p = run_checked(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            video_path,
        ],
        timeout=30,
    )
    return "audio" in (p.stdout or "").lower()


def extract_audio(video_path: str | Path, wav_path: str | Path | None = None) -> Path | None:
    """Extract mono 16 kHz wav for ASR. Return None if the video has no audio."""
    video_path = Path(video_path)
    wav_path = Path(wav_path) if wav_path else video_path.with_suffix(".wav")
    if not probe_audio(video_path):
        return None
    if not has_command("ffmpeg"):
        raise RuntimeError("ffmpeg is not available on PATH")

    p = run_checked(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ],
        timeout=120,
    )
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {p.stderr[-1000:]}")
    return wav_path


async def capture_with_phone_screenrecord(session, duration: int = 12, bit_rate: int = 1_200_000) -> Path:
    """
    Record a short MP4 on the phone with Android screenrecord and transfer it by base64 chunks.

    Important: Android's built-in screenrecord often has no internal audio. This path is mainly
    for validating video transfer and for devices/ROMs that support audio in screenrecord.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    remote = f"/sdcard/zscq_screen_{ts}.mp4"
    local = MEDIA_DIR / f"phone_screen_{ts}.mp4"

    code = f"""
import base64, os, subprocess, time
remote = r"{remote}"
try:
    subprocess.run([
        "screenrecord",
        "--time-limit", "{int(duration)}",
        "--bit-rate", "{int(bit_rate)}",
        remote,
    ], timeout={int(duration) + 8})
except Exception as e:
    print("SCREENRECORD_ERROR_START")
    print(str(e))
    print("SCREENRECORD_ERROR_END")

if os.path.exists(remote):
    print("VIDEO_B64_START")
    with open(remote, "rb") as f:
        while True:
            chunk = f.read(49152)
            if not chunk:
                break
            print(base64.b64encode(chunk).decode("ascii"))
    print("VIDEO_B64_END")
    try:
        os.remove(remote)
    except Exception:
        pass
"""
    out = await main.run_on_phone(session, code, log_sec=duration + 30)
    log = out.get("log", "")
    start = log.find("VIDEO_B64_START")
    end = log.find("VIDEO_B64_END")
    if start < 0 or end <= start:
        err = ""
        es = log.find("SCREENRECORD_ERROR_START")
        ee = log.find("SCREENRECORD_ERROR_END")
        if es >= 0 and ee > es:
            err = log[es + len("SCREENRECORD_ERROR_START") : ee].strip()
        raise RuntimeError(f"phone screenrecord transfer failed. {err}".strip())

    raw = log[start + len("VIDEO_B64_START") : end]
    chunks = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) >= 31 and line.startswith("["):
            line = line[31:].strip()
        line = re.sub(r"[^A-Za-z0-9+/=]", "", line)
        if not line:
            continue
        try:
            chunks.append(base64.b64decode(line))
        except Exception:
            # AScript logs can include status lines between payload chunks.
            continue
    if not chunks:
        raise RuntimeError("phone screenrecord transfer produced no decodable video chunks")
    data = b"".join(chunks)
    local.write_bytes(data)
    return local


def capture_with_scrcpy(duration: int = 12) -> Path:
    """
    Record directly to the computer with scrcpy when available.

    scrcpy is the preferred path for audio because modern versions can forward/record audio
    on supported Android devices.
    """
    if not has_command("scrcpy"):
        raise RuntimeError("scrcpy is not available on PATH")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    local = MEDIA_DIR / f"scrcpy_{ts}.mp4"

    args = [
        "scrcpy",
        "--no-playback",
        "--record",
        str(local),
        "--time-limit",
        str(int(duration)),
    ]
    p = run_checked(args, timeout=duration + 30)
    if p.returncode != 0:
        raise RuntimeError(f"scrcpy failed: {p.stderr[-1000:]}")
    return local


def _adb_devices() -> list[str]:
    if not has_command("adb"):
        return []
    p = run_checked(["adb", "devices"], timeout=15)
    devices = []
    for line in (p.stdout or "").splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


def _adb_prefix(device_id: str | None = None) -> list[str]:
    args = ["adb"]
    if device_id:
        args.extend(["-s", device_id])
    return args


def _resolve_single_adb_device(device_id: str | None = None) -> str | None:
    devices = _adb_devices()
    if device_id:
        return device_id
    if not devices:
        raise RuntimeError("adb is available but no authorized device is connected")
    if len(devices) > 1:
        raise RuntimeError(f"multiple adb devices found; pass device_id explicitly: {devices}")
    return devices[0]


def start_capture_session(
    method: str = "auto",
    prefer_scrcpy: bool = True,
    device_id: str | None = None,
    bit_rate: int = 1_200_000,
) -> RecordingSession:
    method = method.lower()
    if method not in {"auto", "scrcpy", "adb"}:
        raise ValueError("method must be one of: auto, scrcpy, adb")

    resolved_method = method
    if method == "auto":
        if prefer_scrcpy and has_command("scrcpy"):
            resolved_method = "scrcpy"
        elif has_command("adb"):
            resolved_method = "adb"
        else:
            raise RuntimeError("no supported long-running capture method is available")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")

    if resolved_method == "scrcpy":
        if not has_command("scrcpy"):
            raise RuntimeError("scrcpy is not available on PATH")
        local = MEDIA_DIR / f"scrcpy_{ts}.mp4"
        executable = find_executable("scrcpy") or "scrcpy"
        process = subprocess.Popen(
            [
                executable,
                "--no-playback",
                "--record",
                str(local),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        time.sleep(1.0)
        return RecordingSession(
            method="scrcpy",
            local_path=local,
            process=process,
            started_at=started_at,
        )

    if resolved_method == "adb":
        if not has_command("adb"):
            raise RuntimeError("adb is not available on PATH")
        device_id = _resolve_single_adb_device(device_id)
        local = MEDIA_DIR / f"adb_screen_{ts}.mp4"
        remote = f"/sdcard/zscq_screen_{ts}.mp4"
        executable = find_executable("adb") or "adb"
        process = subprocess.Popen(
            _adb_prefix(device_id)
            + [
                "shell",
                "screenrecord",
                "--bit-rate",
                str(int(bit_rate)),
                remote,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        time.sleep(1.0)
        return RecordingSession(
            method="adb",
            local_path=local,
            process=process,
            started_at=started_at,
            device_id=device_id,
            remote_path=remote,
        )

    raise RuntimeError(f"unsupported recording method: {resolved_method}")


def stop_capture_session(session: RecordingSession) -> Path:
    process = session.process
    if process.poll() is None:
        if session.method == "scrcpy":
            stop_scrcpy_process(process)
        else:
            process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)

    if session.method == "adb":
        prefix = _adb_prefix(session.device_id)
        pull = run_checked(prefix + ["pull", session.remote_path, str(session.local_path)], timeout=120)
        run_checked(prefix + ["shell", "rm", "-f", session.remote_path], timeout=15)
        if pull.returncode != 0:
            raise RuntimeError(f"adb pull failed: {pull.stderr[-1000:]}")

    if not session.local_path.exists() or session.local_path.stat().st_size == 0:
        raise RuntimeError(f"recording file missing or empty: {session.local_path}")
    return session.local_path


def stop_scrcpy_process(process: subprocess.Popen) -> None:
    if os.name == "nt":
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
            return
        except Exception:
            pass
    process.terminate()


def capture_with_adb(duration: int = 12, device_id: str | None = None, bit_rate: int = 1_200_000) -> Path:
    """
    Record on the phone with Android screenrecord, then pull the MP4 with adb.

    This is much more reliable than sending large MP4 data through AScript logs.
    Android's screenrecord commonly records video only; audio support depends on
    device/Android version and is checked later with ffprobe.
    """
    if not has_command("adb"):
        raise RuntimeError("adb is not available on PATH")

    devices = _adb_devices()
    if not device_id and len(devices) == 1:
        device_id = devices[0]
    if not device_id and not devices:
        raise RuntimeError("adb is available but no authorized device is connected")
    if not device_id and len(devices) > 1:
        raise RuntimeError(f"multiple adb devices found; pass device_id explicitly: {devices}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    remote = f"/sdcard/zscq_screen_{ts}.mp4"
    local = MEDIA_DIR / f"adb_screen_{ts}.mp4"
    prefix = _adb_prefix(device_id)

    record = run_checked(
        prefix
        + [
            "shell",
            "screenrecord",
            "--time-limit",
            str(int(duration)),
            "--bit-rate",
            str(int(bit_rate)),
            remote,
        ],
        timeout=duration + 20,
    )
    if record.returncode != 0:
        raise RuntimeError(f"adb screenrecord failed: {record.stderr[-1000:]}")

    pull = run_checked(prefix + ["pull", remote, str(local)], timeout=120)
    run_checked(prefix + ["shell", "rm", "-f", remote], timeout=15)
    if pull.returncode != 0:
        raise RuntimeError(f"adb pull failed: {pull.stderr[-1000:]}")
    if not local.exists() or local.stat().st_size == 0:
        raise RuntimeError("adb pull completed but local video is missing or empty")
    return local


async def capture_video(
    duration: int = 12,
    method: str = "auto",
    prefer_scrcpy: bool = True,
    device_id: str | None = None,
) -> Path:
    """Capture a short video by scrcpy, adb, or AScript fallback."""
    method = method.lower()
    if method not in {"auto", "scrcpy", "adb", "ascript"}:
        raise ValueError("method must be one of: auto, scrcpy, adb, ascript")

    if method == "scrcpy":
        return capture_with_scrcpy(duration=duration)
    if method == "adb":
        return capture_with_adb(duration=duration, device_id=device_id)
    if method == "auto" and prefer_scrcpy and has_command("scrcpy"):
        return capture_with_scrcpy(duration=duration)
    if method == "auto" and has_command("adb"):
        return capture_with_adb(duration=duration, device_id=device_id)

    sp = StdioServerParameters(command="python", args=["-m", "ascript_mcp.local"])
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            if not await main.connect_device_auto(session):
                raise RuntimeError("failed to connect phone")
            return await capture_with_phone_screenrecord(session, duration=duration)
