"""Local Paraformer speech-to-text via sherpa-onnx for Weixin video evidence.

Paraformer (达摩院) — 220M params, CER ~1.68% on AISHELL-1, Apache 2.0.
Model: sherpa-onnx-paraformer-zh-2024-03-09 (int8 quantized ~100MB).

Usage (from collector/main):
    from asr_paraformer import core_transcribe_for_record
    core_transcribe_for_record(record, wav_path, video_identifier)

Standalone test (step_tests):
    from asr_paraformer import transcribe_wav
    text = transcribe_wav(wav_path, model_dir="D:/path/to/model")
"""

from __future__ import annotations

import json
import os
import time
import wave
from pathlib import Path

import numpy as np
import sherpa_onnx

_DEFAULT_MODEL_SEARCH_PATHS = [
    r"D:\code\vscodeWorkDir\vosk\paraformer\sherpa-onnx-paraformer-zh-2024-03-09",
]
_PARAFORMER_MODEL_DIR = os.environ.get("PARAFORMER_MODEL_DIR", "")

MEDIA_DIR = Path(__file__).resolve().parent / "media"
MEDIA_DIR.mkdir(exist_ok=True)


def _resolve_model_dir(model_dir: str = "") -> str:
    if model_dir and Path(model_dir).is_dir():
        return str(Path(model_dir).resolve())
    env_dir = _PARAFORMER_MODEL_DIR or os.environ.get("PARAFORMER_MODEL_DIR", "")
    if env_dir and Path(env_dir).is_dir():
        return str(Path(env_dir).resolve())
    for candidate in _DEFAULT_MODEL_SEARCH_PATHS:
        if Path(candidate).is_dir():
            return candidate
    raise FileNotFoundError(
        f"Paraformer model not found. Set PARAFORMER_MODEL_DIR env var or place model at: "
        f"{_DEFAULT_MODEL_SEARCH_PATHS[0]}"
    )


def _create_recognizer(model_dir: str) -> sherpa_onnx.OfflineRecognizer:
    model_dir = Path(model_dir)
    onnx_file = model_dir / "model.int8.onnx"
    if not onnx_file.exists():
        onnx_file = model_dir / "model.onnx"
    tokens_file = model_dir / "tokens.txt"

    if not onnx_file.exists():
        raise FileNotFoundError(f"Model .onnx not found at {onnx_file}")
    if not tokens_file.exists():
        raise FileNotFoundError(f"tokens.txt not found at {tokens_file}")

    return sherpa_onnx.OfflineRecognizer.from_paraformer(
        paraformer=str(onnx_file),
        tokens=str(tokens_file),
        num_threads=4,
        sample_rate=16000,
        feature_dim=80,
        decoding_method="greedy_search",
        provider="cpu",
    )


def _read_wav_samples(wav_path: Path) -> np.ndarray:
    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        nch = wf.getnchannels()
        n_frames = wf.getnframes()
        audio_data = wf.readframes(n_frames)
    samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
    if nch > 1:
        samples = samples.reshape(-1, nch).mean(axis=1)
    return samples


def transcribe_wav(wav_path: str | Path, model_dir: str = "") -> str:
    """Transcribe a 16kHz mono PCM WAV file with Paraformer via sherpa-onnx."""
    wav_path = Path(wav_path)
    model_path = _resolve_model_dir(model_dir)
    model_name = Path(model_path).name

    print(f"[paraformer] loading model: {model_path}")
    t0 = time.time()
    recognizer = _create_recognizer(model_path)
    print(f"[paraformer] model loaded in {time.time() - t0:.1f}s ({model_name})")

    print(f"[paraformer] reading audio: {wav_path.name}")
    samples = _read_wav_samples(wav_path)
    duration = len(samples) / 16000.0
    print(f"[paraformer] audio duration: {duration:.1f}s")

    print(f"[paraformer] transcribing...")
    t1 = time.time()
    stream = recognizer.create_stream()
    stream.accept_waveform(16000, samples)
    recognizer.decode_stream(stream)
    result = stream.result
    full_text = (result.text or "").strip()
    elapsed = time.time() - t1

    print(
        f"[paraformer] transcription done in {elapsed:.1f}s "
        f"(audio {duration:.0f}s, speedup {duration / elapsed:.1f}x, {len(full_text)} chars)"
    )
    return full_text


def core_transcribe_for_record(record, wav_path: str, video_identifier: str = "") -> None:
    """Run Paraformer ASR and populate record.media_info fields in-place."""
    if not video_identifier:
        candidate = record.candidate if isinstance(record.candidate, dict) else {}
        video_identifier = candidate.get("video_identifier", "")
    if not video_identifier:
        from datetime import datetime
        video_identifier = datetime.now().strftime("%Y%m%d_%H%M%S")

    model_path = _resolve_model_dir("")
    model_name = Path(model_path).name

    asr_txt_path = MEDIA_DIR / f"{video_identifier}.asr.txt"
    asr_json_path = MEDIA_DIR / f"{video_identifier}.asr.json"

    full_text = transcribe_wav(wav_path, model_dir=model_path)

    asr_txt_path.write_text(full_text, encoding="utf-8")
    print(f"[paraformer] saved asr text: {asr_txt_path}")

    asr_json = {
        "backend": "paraformer",
        "model": model_name,
        "audio_path": str(wav_path),
        "video_identifier": video_identifier,
        "text": full_text,
        "text_length": len(full_text),
    }
    asr_json_path.write_text(json.dumps(asr_json, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[paraformer] saved asr json: {asr_json_path}")

    record.media_info["asr_text"] = full_text
    record.media_info["asr_text_path"] = str(asr_txt_path)
    record.media_info["asr_json_path"] = str(asr_json_path)
    record.media_info["asr_model"] = model_name
    record.media_info["asr_source_video_identifier"] = video_identifier

    print(f"[paraformer] ASR result attached to record (vid={video_identifier}, len={len(full_text)})")
