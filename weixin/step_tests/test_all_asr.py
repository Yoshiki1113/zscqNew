"""Single-step test: All ASR backends comparison.

Usage:
    python weixin/step_tests/test_all_asr.py --audio media/xxx.wav
    python weixin/step_tests/test_all_asr.py --audio media/xxx.wav --save-json compare.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_WEIXIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_WEIXIN_DIR))


def _print_separator(title: str) -> None:
    print(f"\n{'=' * 75}")
    print(f"  {title}")
    print(f"{'=' * 75}")


def _audio_info(wav_path: Path) -> dict:
    import wave
    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        n_frames = wf.getnframes()
        duration = n_frames / sr if sr > 0 else 0
    return {"path": str(wav_path), "duration_sec": round(duration, 1), "sample_rate": sr}


def _run_model(label: str, fn, *fn_args) -> dict | None:
    print(f"\n{'─' * 75}")
    print(f"  [{label}]")
    try:
        t0 = time.time()
        text = fn(*fn_args)
        elapsed = time.time() - t0
        return {"name": label, "text": str(text or ""), "len": len(text or ""), "elapsed": round(elapsed, 2)}
    except Exception as exc:
        print(f"  [FAIL] {exc}")
        return None


def main():
    parser = argparse.ArgumentParser(description="All ASR backends comparison")
    parser.add_argument("--audio", required=True, help="Path to 16kHz mono WAV file")
    parser.add_argument("--save-json", default="", help="Save comparison to JSON")
    parser.add_argument("--skip-xunfei", action="store_true", help="Skip iFlytek cloud ASR")
    parser.add_argument("--skip-sensevoice", action="store_true", help="Skip SenseVoice")
    parser.add_argument("--skip-paraformer", action="store_true", help="Skip Paraformer")
    args = parser.parse_args()

    audio_path = Path(args.audio).resolve()
    if not audio_path.exists():
        print(f"[ERROR] Audio not found: {audio_path}")
        sys.exit(1)

    info = _audio_info(audio_path)
    _print_separator(f"Audio: {info['duration_sec']}s @ {info['sample_rate']}Hz")
    print(f"  {info['path']}")

    results = []

    if not args.skip_xunfei:
        from asr.xunfei import transcribe_wav as xf_fn
        r = _run_model("iFlytek (cloud)", xf_fn, str(audio_path))
        if r: results.append(r)

    if not args.skip_sensevoice:
        from asr.sensevoice import transcribe_wav as sv_fn
        r = _run_model("SenseVoice", sv_fn, str(audio_path))
        if r: results.append(r)

    if not args.skip_paraformer:
        from asr.paraformer import transcribe_wav as pf_fn
        r = _run_model("Paraformer", pf_fn, str(audio_path))
        if r: results.append(r)

    if not results:
        print("[ERROR] All models failed or were skipped")
        sys.exit(1)

    _print_separator("Summary")
    print(f"  {'Backend':<20s} {'Total':>8s} {'Chars':>7s}")
    print(f"  {'─' * 38}")
    for r in results:
        print(f"  {r['name']:<20s} {r['elapsed']:>7.2f}s {r['len']:>6d}")

    print(f"\n  {'─' * 75}")
    for r in results:
        preview = r["text"][:150]
        print(f"  [{r['name']}] {preview}{'...' if len(r['text']) > 150 else ''}")
        print()

    if args.save_json:
        json_path = Path(args.save_json)
        json_path.write_text(json.dumps({"audio": info, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  JSON saved: {json_path}")

    print()


if __name__ == "__main__":
    main()
