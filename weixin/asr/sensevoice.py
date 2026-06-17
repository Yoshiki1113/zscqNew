"""Local SenseVoice-Small speech-to-text via sherpa-onnx for Weixin video evidence.

Usage (from collector/main):
    from sensevoice import core_transcribe_for_record
    core_transcribe_for_record(record, wav_path, video_identifier)

Standalone test (step_tests):
    from sensevoice import transcribe_wav
    text = transcribe_wav(wav_path, model_dir="D:/path/to/model")
"""

from __future__ import annotations

import json
import os
import time
import wave
from pathlib import Path

# Default model paths
_DEFAULT_MODEL_SEARCH_PATHS = [
    r"D:\code\vscodeWorkDir\vosk\sensevoice\sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17",
]
_SENSEVOICE_MODEL_DIR = os.environ.get("SENSEVOICE_MODEL_DIR", "")

MEDIA_DIR = Path(__file__).resolve().parent / "media"
MEDIA_DIR.mkdir(exist_ok=True)


def run_asr_pipeline(record, wav_path: str, video_identifier: str) -> None:
    """Run ASR with priority: iFlytek (cloud) → SenseVoice (offline) → Paraformer (fastest).

    iFlytek: best accuracy + punctuation, cloud API (10000 free calls).
    SenseVoice: excellent offline quality + built-in punctuation + ITN.
    Paraformer: fastest offline inference (98x real-time), good accuracy.

    After each successful backend, script matching is automatically triggered.
    """
    # 1) Try iFlytek cloud ASR (best accuracy)
    try:
        from .xunfei import core_transcribe_for_record as _fn
        _fn(record, wav_path, video_identifier)
        _run_script_match(record)
        return
    except (FileNotFoundError, ImportError) as e:
        print(f"[asr] iFlytek unavailable ({e}), trying SenseVoice...")
    except Exception as e:
        print(f"[asr] iFlytek error: {e}, trying SenseVoice...")

    # 2) Try SenseVoice offline (best quality + punctuation)
    try:
        _fn = core_transcribe_for_record  # use the local function directly
        _fn(record, wav_path, video_identifier)
        _run_script_match(record)
        return
    except (FileNotFoundError, ImportError) as e:
        print(f"[asr] SenseVoice unavailable ({e}), trying Paraformer...")
    except Exception as e:
        print(f"[asr] SenseVoice error: {e}, trying Paraformer...")

    # 3) Try Paraformer offline (fastest)
    try:
        from .paraformer import core_transcribe_for_record as _fn
        _fn(record, wav_path, video_identifier)
        _run_script_match(record)
        return
    except (FileNotFoundError, ImportError) as e:
        print(f"[asr] Paraformer also unavailable ({e})")
        raise
    except Exception as e:
        print(f"[asr] Paraformer error: {e}")
        raise


def _run_script_match(record) -> None:
    """Match ASR text against the reference script and populate record.media_info['script_match'].

    This is called automatically after each successful ASR backend transcription.
    Falls back gracefully if the script file or matching library is unavailable.
    """
    try:
        from .script_matcher import match_query
        asr_text = record.media_info.get("asr_text", "")
        if not asr_text:
            record.media_info["script_match"] = {"status": "not_found", "error": "no asr_text"}
            return

        results = match_query(asr_text, top_n=3)
        if results:
            record.media_info["script_match"] = {
                "status": "matched",
                "best_match": results[0],
                "top_candidates": results,
            }
            print(f"[script_matcher] matched: score={results[0]['similarity_score']:.2%} "
                  f"episode={results[0].get('episode', '?')}")
        else:
            record.media_info["script_match"] = {"status": "not_found"}
            print(f"[script_matcher] no match found in script")
    except FileNotFoundError:
        record.media_info["script_match"] = {"status": "script_unavailable"}
        print(f"[script_matcher] script file not available, skipping")
    except ImportError as e:
        record.media_info["script_match"] = {"status": "script_unavailable", "error": str(e)}
        print(f"[script_matcher] dependency unavailable ({e}), skipping")
    except Exception as e:
        record.media_info["script_match"] = {"status": "error", "error": str(e)}
        print(f"[script_matcher] match failed: {e}")


def _resolve_model_dir(model_dir: str = "") -> str:
    """Resolve SenseVoice model directory from env, explicit arg, or default paths."""
    if model_dir and Path(model_dir).is_dir():
        return str(Path(model_dir).resolve())
    env_dir = _SENSEVOICE_MODEL_DIR or os.environ.get("SENSEVOICE_MODEL_DIR", "")
    if env_dir and Path(env_dir).is_dir():
        return str(Path(env_dir).resolve())
    for candidate in _DEFAULT_MODEL_SEARCH_PATHS:
        if Path(candidate).is_dir():
            return candidate
    raise FileNotFoundError(
        f"SenseVoice model not found. Set SENSEVOICE_MODEL_DIR env var or place model at: "
        f"{_DEFAULT_MODEL_SEARCH_PATHS[0]}"
    )


def _create_recognizer(model_dir: str) -> sherpa_onnx.OfflineRecognizer:
    """Create a sherpa-onnx OfflineRecognizer for SenseVoice."""
    import sherpa_onnx

    model_dir = Path(model_dir)
    # Prefer int8 quantized model for better CPU performance
    onnx_file = model_dir / "model.int8.onnx"
    if not onnx_file.exists():
        onnx_file = model_dir / "model.onnx"
    tokens_file = model_dir / "tokens.txt"

    if not onnx_file.exists():
        raise FileNotFoundError(f"Model .onnx not found at {onnx_file}")
    if not tokens_file.exists():
        raise FileNotFoundError(f"tokens.txt not found at {tokens_file}")

    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=str(onnx_file),
        tokens=str(tokens_file),
        num_threads=4,
        sample_rate=16000,
        decoding_method="greedy_search",
        provider="cpu",
        language="zh",
        use_itn=True,
    )


def _read_wav_samples(wav_path: Path) -> np.ndarray:
    """Read a 16kHz mono PCM WAV file and return float32 samples normalized to [-1, 1]."""
    import numpy as np

    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        nch = wf.getnchannels()
        n_frames = wf.getnframes()
        audio_data = wf.readframes(n_frames)

    samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

    # Convert to mono if multi-channel
    if nch > 1:
        samples = samples.reshape(-1, nch).mean(axis=1)
    return samples


def _wav_duration_seconds(wav_path: Path) -> float:
    """Estimate WAV duration from file size (16kHz, mono, 16-bit PCM)."""
    try:
        size = wav_path.stat().st_size
        return max(0.0, (size - 44) / 32000.0)
    except OSError:
        return 0.0


def transcribe_wav(wav_path: str | Path, model_dir: str = "") -> str:
    """Transcribe a 16kHz mono PCM WAV file with SenseVoice via sherpa-onnx.

    Returns the full transcribed text string with punctuation.
    """
    wav_path = Path(wav_path)
    model_path = _resolve_model_dir(model_dir)
    model_name = Path(model_path).name

    print(f"[sensevoice] loading model: {model_path}")
    t0 = time.time()
    recognizer = _create_recognizer(model_path)
    print(f"[sensevoice] model loaded in {time.time() - t0:.1f}s ({model_name})")

    print(f"[sensevoice] reading audio: {wav_path.name}")
    samples = _read_wav_samples(wav_path)
    duration = len(samples) / 16000.0
    print(f"[sensevoice] audio duration: {duration:.1f}s")

    print(f"[sensevoice] transcribing...")
    t1 = time.time()
    stream = recognizer.create_stream()
    stream.accept_waveform(16000, samples)
    recognizer.decode_stream(stream)
    result = stream.result
    full_text = (result.text or "").strip()
    elapsed = time.time() - t1

    print(
        f"[sensevoice] transcription done in {elapsed:.1f}s "
        f"(audio {duration:.0f}s, speedup {duration / elapsed:.1f}x, {len(full_text)} chars)"
    )
    return full_text


def core_transcribe_for_record(record, wav_path: str, video_identifier: str = "") -> None:
    """Run SenseVoice ASR and populate record.media_info fields in-place.

    Args:
        record: EvidenceRecord instance.
        wav_path: Path to the 16kHz mono WAV file.
        video_identifier: Unique ID for this video (from candidate["video_identifier"]).
    """
    if not video_identifier:
        candidate = record.candidate if isinstance(record.candidate, dict) else {}
        video_identifier = candidate.get("video_identifier", "")
    if not video_identifier:
        from datetime import datetime
        video_identifier = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Resolve model and name
    model_path = _resolve_model_dir("")
    model_name = Path(model_path).name

    # Construct output paths
    asr_txt_path = MEDIA_DIR / f"{video_identifier}.asr.txt"
    asr_json_path = MEDIA_DIR / f"{video_identifier}.asr.json"

    # Run transcription
    full_text = transcribe_wav(wav_path, model_dir=model_path)

    # Write text output
    asr_txt_path.write_text(full_text, encoding="utf-8")
    print(f"[sensevoice] saved asr text: {asr_txt_path}")

    # Write JSON output
    asr_json = {
        "backend": "sensevoice",
        "model": model_name,
        "audio_path": str(wav_path),
        "video_identifier": video_identifier,
        "text": full_text,
        "text_length": len(full_text),
    }
    asr_json_path.write_text(json.dumps(asr_json, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[sensevoice] saved asr json: {asr_json_path}")

    # Populate record.media_info
    record.media_info["asr_text"] = full_text
    record.media_info["asr_text_path"] = str(asr_txt_path)
    record.media_info["asr_json_path"] = str(asr_json_path)
    record.media_info["asr_model"] = model_name
    record.media_info["asr_source_video_identifier"] = video_identifier

    print(f"[sensevoice] ASR result attached to record (vid={video_identifier}, len={len(full_text)})")
