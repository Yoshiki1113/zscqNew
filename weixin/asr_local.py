"""Local CPU-friendly ASR helpers for recorded Weixin clips."""
from __future__ import annotations

import json
from pathlib import Path


def transcribe_with_faster_whisper(
    audio_path: str | Path,
    model_size: str = "small",
    compute_type: str = "int8",
    language: str = "zh",
) -> dict:
    """
    Transcribe with faster-whisper on CPU.

    Recommended CPU settings for an integrated-GPU/no-discrete-GPU machine:
    - model_size="small" for first validation
    - compute_type="int8" for speed and memory
    - model_size="medium" only if accuracy is not enough and runtime is acceptable
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Install with: pip install faster-whisper"
        ) from exc

    model = WhisperModel(model_size, device="cpu", compute_type=compute_type)
    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=True,
        beam_size=5,
    )
    segment_list = []
    text_parts = []
    for seg in segments:
        text = seg.text.strip()
        if text:
            text_parts.append(text)
        segment_list.append(
            {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": text,
            }
        )
    return {
        "backend": "faster-whisper",
        "model": model_size,
        "language": getattr(info, "language", language),
        "duration": float(getattr(info, "duration", 0) or 0),
        "text": "".join(text_parts),
        "segments": segment_list,
    }


def save_transcript(result: dict, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
