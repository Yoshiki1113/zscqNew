"""Batch ASR for existing JSON evidence records using iFlytek cloud ASR.

Usage:
    cd weixin
    conda run -n zscq python scripts/batch_asr_json.py

This script:
1. Scans jsons/*.json for records with video_identifier
2. Finds corresponding WAV files in media/ (by vid or by recording_audio_path)
3. Runs iFlytek ASR on each WAV
4. Updates the JSON with asr_text, asr_json_path, and script_match
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Ensure weixin/ is on path
_WEIXIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_WEIXIN_DIR))

JSONS_DIR = Path("core/jsons")
MEDIA_DIR = Path("core/media")
ASR_OUTPUT_DIR = MEDIA_DIR / "asr_results"
ASR_OUTPUT_DIR.mkdir(exist_ok=True)


def find_audio_for_json(json_path: Path) -> Path | None:
    """Find the corresponding WAV file for a JSON record."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Check if recording_audio_path is already recorded
    audio_path_str = data.get("media_info", {}).get("recording_audio_path", "")
    if audio_path_str:
        p = Path(audio_path_str)
        if p.exists():
            return p
        # Try relative to weixin dir
        p = _WEIXIN_DIR / audio_path_str
        if p.exists():
            return p

    # 2. Search by video_identifier
    vid = data.get("candidate", {}).get("video_identifier", "")
    if vid:
        # Look for any WAV containing the vid
        wavs = list(MEDIA_DIR.rglob(f"*{vid}*.wav"))
        if wavs:
            return wavs[0]
        # Also check media/ root
        wavs = list(MEDIA_DIR.glob(f"*{vid}*.wav"))
        if wavs:
            return wavs[0]

    return None


def run_xunfei_asr(wav_path: Path) -> tuple[str, dict]:
    """Run iFlytek ASR and return (text, metadata_dict)."""
    from asr.xunfei import transcribe_wav

    print(f"  [xunfei] transcribing: {wav_path.name}")
    t0 = time.time()
    text = transcribe_wav(str(wav_path))
    elapsed = time.time() - t0

    print(f"  [xunfei] done: {len(text)} chars in {elapsed:.1f}s")
    return text, {
        "backend": "xunfei",
        "audio_path": str(wav_path),
        "elapsed_sec": round(elapsed, 2),
        "text_length": len(text),
    }


def run_script_match(asr_text: str) -> dict:
    """Run script matching against the reference script."""
    try:
        from asr.script_matcher import match_query
        results = match_query(asr_text, top_n=3)
        if results:
            return {
                "status": "matched",
                "best_match": results[0],
                "top_candidates": results,
            }
        return {"status": "not_found"}
    except Exception as e:
        print(f"  [script_match] failed: {e}")
        return {"status": "error", "error": str(e)}


def update_json_with_asr(json_path: Path, asr_text: str, asr_meta: dict, script_match: dict) -> None:
    """Update the JSON file with ASR results."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Update media_info
    if "media_info" not in data:
        data["media_info"] = {}
    data["media_info"]["asr_text"] = asr_text
    data["media_info"]["asr_model"] = "xunfei"
    data["media_info"]["asr_source_video_identifier"] = data.get("candidate", {}).get("video_identifier", "")

    # Save ASR result JSON
    vid = data.get("candidate", {}).get("video_identifier", "")
    asr_json_path = ASR_OUTPUT_DIR / f"{vid}.asr.json"
    asr_json_path.write_text(
        json.dumps({
            **asr_meta,
            "text": asr_text,
            "script_match": script_match,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    data["media_info"]["asr_json_path"] = str(asr_json_path)

    # Save script match
    data["media_info"]["script_match"] = script_match

    # Write back
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  [save] updated: {json_path.name}")


def main():
    json_files = sorted(JSONS_DIR.glob("*.json"))
    print(f"[batch-asr] Found {len(json_files)} JSON files in {JSONS_DIR}")

    processed = 0
    skipped = 0
    failed = 0

    for idx, json_path in enumerate(json_files, 1):
        print(f"\n[{idx}/{len(json_files)}] {json_path.name}")

        # Find audio
        wav_path = find_audio_for_json(json_path)
        if not wav_path:
            print(f"  [skip] no audio found")
            skipped += 1
            continue

        print(f"  [audio] {wav_path.name}")

        # Check if already has ASR
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("media_info", {}).get("asr_text"):
            print(f"  [skip] already has ASR text")
            skipped += 1
            continue

        # Run ASR
        try:
            asr_text, asr_meta = run_xunfei_asr(wav_path)
            if not asr_text:
                print(f"  [skip] empty ASR result")
                skipped += 1
                continue

            # Run script match
            script_match = run_script_match(asr_text)
            if script_match.get("status") == "matched":
                best = script_match.get("best_match", {})
                print(f"  [script] matched: {best.get('similarity_score', 0):.1%} | "
                      f"{best.get('episode', '?')} {best.get('scene', '?')}")

            # Update JSON
            update_json_with_asr(json_path, asr_text, asr_meta, script_match)
            processed += 1

        except Exception as e:
            print(f"  [fail] ASR error: {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"[batch-asr] Done: processed={processed}, skipped={skipped}, failed={failed}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
