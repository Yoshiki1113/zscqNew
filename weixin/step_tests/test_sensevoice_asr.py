"""Single-step test: SenseVoice ASR via sherpa-onnx.

Usage:
    # Basic: transcribe a WAV file
    python weixin/step_tests/test_sensevoice_asr.py --audio media/xxx.wav

    # Specify model directory and output
    python weixin/step_tests/test_sensevoice_asr.py --audio media/xxx.wav --model D:/path/to/model --output result.txt
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Ensure weixin/ is on path
_WEIXIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_WEIXIN_DIR))


def _print_separator(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def _audio_info(wav_path: Path) -> dict:
    import wave
    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        nch = wf.getnchannels()
        n_frames = wf.getnframes()
        duration = n_frames / sr if sr > 0 else 0
    size_mb = wav_path.stat().st_size / (1024 * 1024)
    return {
        "path": str(wav_path),
        "sample_rate": sr,
        "channels": nch,
        "duration_sec": round(duration, 1),
        "size_mb": round(size_mb, 2),
    }


def main():
    parser = argparse.ArgumentParser(description="SenseVoice ASR single-step test")
    parser.add_argument("--audio", required=True, help="Path to input 16kHz mono WAV file")
    parser.add_argument("--model", default="", help="Path to SenseVoice ONNX model directory")
    parser.add_argument("--output", default="", help="Path to output text file (default: auto)")
    parser.add_argument("--save-json", default="", help="Save result JSON to this path")
    args = parser.parse_args()

    audio_path = Path(args.audio).resolve()
    if not audio_path.exists():
        print(f"[ERROR] Audio file not found: {audio_path}")
        sys.exit(1)

    # Show audio info
    info = _audio_info(audio_path)
    _print_separator("Audio Info")
    print(f"  File:       {info['path']}")
    print(f"  Duration:   {info['duration_sec']}s")
    print(f"  Size:       {info['size_mb']} MB")
    print(f"  Format:     {info['sample_rate']}Hz, {info['channels']}ch")

    # --- SenseVoice ---
    _print_separator("SenseVoice (sherpa-onnx)")
    try:
        from asr_sensevoice import transcribe_wav

        t0 = time.time()
        sv_text = transcribe_wav(str(audio_path), model_dir=args.model)
        sv_elapsed = time.time() - t0

        print(f"\n  Text ({len(sv_text)} chars):")
        print(f"  {sv_text[:200]}")
    except Exception as exc:
        print(f"  [ERROR] SenseVoice failed: {exc}")
        sv_text = ""
        sv_elapsed = 0

    # --- Output ---
    output_path = Path(args.output) if args.output else (audio_path.with_suffix(".sensevoice.txt"))
    if sv_text:
        output_path.write_text(sv_text, encoding="utf-8")
        print(f"\n  Output saved: {output_path}")

    # --- Save JSON ---
    if args.save_json:
        json_path = Path(args.save_json)
        json_path.write_text(
            json.dumps({
                "audio": info,
                "sensevoice": {
                    "text": sv_text,
                    "length": len(sv_text),
                    "elapsed_sec": round(sv_elapsed, 2),
                },
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n  JSON saved: {json_path}")

    print()


if __name__ == "__main__":
    main()
