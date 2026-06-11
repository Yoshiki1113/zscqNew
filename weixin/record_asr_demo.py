"""One-shot test: record current phone video, pull to PC, extract audio, run local ASR."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from asr_local import save_transcript, transcribe_with_faster_whisper
from media_capture import available_capture_methods, capture_video, extract_audio, probe_audio


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=12)
    parser.add_argument("--model", default="small")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--method", choices=["auto", "scrcpy", "adb", "ascript"], default="auto")
    parser.add_argument("--device-id", default=None)
    parser.add_argument("--no-scrcpy", action="store_true", help="Deprecated alias for --method adb/ascript fallback.")
    parser.add_argument("--skip-asr", action="store_true")
    args = parser.parse_args()

    method = "auto"
    if args.no_scrcpy:
        method = "adb"
    if args.method != "auto":
        method = args.method

    print(f"[media] available_methods={available_capture_methods()}")
    video_path = await capture_video(
        duration=args.duration,
        method=method,
        prefer_scrcpy=not args.no_scrcpy,
        device_id=args.device_id,
    )
    print(f"[media] video={video_path}")

    has_audio = probe_audio(video_path)
    print(f"[media] has_audio={has_audio}")
    if not has_audio:
        print("[media] no audio stream found; ASR skipped")
        return

    wav_path = extract_audio(video_path)
    print(f"[media] audio={wav_path}")
    if args.skip_asr:
        return

    result = transcribe_with_faster_whisper(
        wav_path,
        model_size=args.model,
        compute_type=args.compute_type,
        language="zh",
    )
    out_path = Path(video_path).with_suffix(".asr.json")
    save_transcript(result, out_path)
    print(f"[asr] text={result['text']}")
    print(f"[asr] json={out_path}")


if __name__ == "__main__":
    asyncio.run(main())
