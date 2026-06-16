"""Single-step test: Paraformer ASR via sherpa-onnx.

Usage:
    python weixin/step_tests/test_paraformer_asr.py --audio media/xxx.wav

    # Compare both backends (SenseVoice + Paraformer)
    python weixin/step_tests/test_paraformer_asr.py --audio media/xxx.wav --compare-all --save-json compare.json
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
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def _audio_info(wav_path: Path) -> dict:
    import wave
    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        nch = wf.getnchannels()
        n_frames = wf.getnframes()
        duration = n_frames / sr if sr > 0 else 0
    return {
        "path": str(wav_path),
        "duration_sec": round(duration, 1),
        "sample_rate": sr,
    }


def _run_model(name: str, transcribe_fn, wav_path: str, model_dir: str = "") -> dict | None:
    """Run one ASR model and return result dict, or None on failure."""
    print(f"\n{'─' * 70}")
    print(f"  [{name}]")
    try:
        t0 = time.time()
        text = transcribe_fn(str(wav_path), model_dir=model_dir)
        elapsed = time.time() - t0
        return {"name": name, "text": text, "len": len(text), "elapsed": round(elapsed, 2)}
    except Exception as exc:
        print(f"  [FAIL] {exc}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Paraformer ASR single-step test")
    parser.add_argument("--audio", required=True, help="Path to 16kHz mono WAV file")
    parser.add_argument("--model", default="", help="Path to Paraformer model directory")
    parser.add_argument("--output", default="", help="Output text file path")
    parser.add_argument("--compare-all", action="store_true", help="Compare Paraformer vs SenseVoice")
    parser.add_argument("--save-json", default="", help="Save comparison JSON")
    args = parser.parse_args()

    audio_path = Path(args.audio).resolve()
    if not audio_path.exists():
        print(f"[ERROR] Audio not found: {audio_path}")
        sys.exit(1)

    info = _audio_info(audio_path)
    _print_separator("Audio Info")
    print(f"  File: {info['path']}")
    print(f"  Duration: {info['duration_sec']}s @ {info['sample_rate']}Hz")

    # --- Paraformer ---
    from asr_paraformer import transcribe_wav as pf_transcribe

    pf = _run_model("Paraformer", pf_transcribe, str(audio_path), model_dir=args.model)

    if pf:
        print(f"\n  Text ({pf['len']} chars):")
        print(f"  {pf['text'][:200]}")
    else:
        print("[ERROR] Paraformer failed")
        sys.exit(1)

    # --- Output ---
    output_path = Path(args.output) if args.output else audio_path.with_suffix(".paraformer.txt")
    if pf:
        output_path.write_text(pf["text"], encoding="utf-8")
        print(f"\n  Output: {output_path}")

    # --- Compare All ---
    if args.compare_all:
        _print_separator("Two-way Comparison (Paraformer + SenseVoice)")

        # SenseVoice
        from asr_sensevoice import transcribe_wav as sv_transcribe
        sv = _run_model("SenseVoice", sv_transcribe, str(audio_path))

        results = [r for r in [pf, sv] if r is not None]

        if len(results) >= 2:
            _print_separator("Summary")
            header = f"  {'Backend':<16s} {'Time':>8s} {'Chars':>7s}"
            print(header)
            print(f"  {'─' * 33}")
            for r in results:
                speedup = info["duration_sec"] / r["elapsed"] if r["elapsed"] > 0 else 0
                print(f"  {r['name']:<16s} {r['elapsed']:>7.2f}s {r['len']:>6d} ({speedup:.0f}x)")
            print()
            for r in results:
                print(f"  [{r['name']}] {r['text'][:100]}{'...' if len(r['text']) > 100 else ''}")
                print()

            if args.save_json:
                json_path = Path(args.save_json)
                data = {"audio": info, "results": [{"name": r["name"], "text": r["text"], "length": r["len"], "elapsed_sec": r["elapsed"]} for r in results]}
                json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  JSON: {json_path}")

    print()


if __name__ == "__main__":
    main()
