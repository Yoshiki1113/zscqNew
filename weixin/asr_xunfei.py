"""iFlytek (科大讯飞) cloud speech-to-text via WebSocket v2 API.

Uses the "语音听写（流式版）" (iat) service on ws-api.xfyun.cn/v2/iat.
Credentials from https://console.xfyun.cn/ → 语音听写（流式版）.

Usage:
    from asr_xunfei import transcribe_wav
    text = transcribe_wav(wav_path, appid="xxx", apikey="xxx", apisecret="xxx")

Environment variables: XUNFEI_APPID, XUNFEI_APIKEY, XUNFEI_APISECRET
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import ssl
import time
import wave
from datetime import datetime
from pathlib import Path
from threading import Event, Thread
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time

import websocket

_DEFAULT_APPID = os.environ.get("XUNFEI_APPID", "6df50e17")
_DEFAULT_APIKEY = os.environ.get("XUNFEI_APIKEY", "21dd94aa98239d94138b9cefd38e151d")
_DEFAULT_APISECRET = os.environ.get("XUNFEI_APISECRET", "OTRkMTZjZWY5ZDRkNmI3NThhMGQyNTZh")

MEDIA_DIR = Path(__file__).resolve().parent / "media"
MEDIA_DIR.mkdir(exist_ok=True)

HOST = "ws-api.xfyun.cn"
URL = "wss://ws-api.xfyun.cn/v2/iat"
MAX_AUDIO_SECONDS = 60
CHUNK_SECONDS = 50       # per-chunk duration when slicing long audio
FRAME_SIZE = 8000
FRAME_INTERVAL = 0.04


def _create_url(appid: str, apikey: str, apisecret: str) -> str:
    """Build signed WebSocket v2 URL."""
    from time import mktime
    now = datetime.now()
    date = format_date_time(mktime(now.timetuple()))

    signature_origin = f"host: {HOST}\ndate: {date}\nGET /v2/iat HTTP/1.1"
    signature_sha = hmac.new(
        apisecret.encode("utf-8"), signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()
    signature = base64.b64encode(signature_sha).decode("utf-8")

    authorization_origin = (
        f'api_key="{apikey}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")

    params = urlencode({"authorization": authorization, "date": date, "host": HOST})
    return f"{URL}?{params}"


def _read_wav_pcm(wav_path: Path) -> bytes:
    with wave.open(str(wav_path), "rb") as wf:
        return wf.readframes(wf.getnframes())


def _transcribe_pcm_chunk(
    pcm_data: bytes,
    appid: str,
    apikey: str,
    apisecret: str,
    chunk_index: int = 0,
) -> str:
    """Core: send one chunk of PCM bytes to iFlytek and return the transcribed text."""
    duration = len(pcm_data) / 32000.0
    result_texts: list[str] = []
    finished = Event()
    error_msg: list[str] = []

    common_args = {"app_id": appid}
    business_args = {"domain": "iat", "language": "zh_cn", "accent": "mandarin", "vinfo": 1, "vad_eos": 10000}

    def on_open(ws):
        def send_audio():
            status = 0
            pos = 0
            while True:
                buf = pcm_data[pos:pos + FRAME_SIZE]
                pos += FRAME_SIZE

                if not buf:
                    d = {"data": {"status": 2, "format": "audio/L16;rate=16000",
                                  "audio": str(base64.b64encode(b""), "utf-8"), "encoding": "raw"}}
                    ws.send(json.dumps(d))
                    time.sleep(1)
                    break

                if status == 0:
                    d = {"common": common_args, "business": business_args,
                         "data": {"status": 0, "format": "audio/L16;rate=16000",
                                  "audio": str(base64.b64encode(buf), "utf-8"), "encoding": "raw"}}
                    ws.send(json.dumps(d))
                    status = 1
                else:
                    d = {"data": {"status": 1, "format": "audio/L16;rate=16000",
                                  "audio": str(base64.b64encode(buf), "utf-8"), "encoding": "raw"}}
                    ws.send(json.dumps(d))
                time.sleep(FRAME_INTERVAL)
            ws.close()

        Thread(target=send_audio, daemon=True).start()

    def on_message(ws, message):
        msg = json.loads(message)
        code = msg.get("code", -1)
        if code != 0:
            error_msg.append(f"code={code}: {msg.get('message', '')}")
            finished.set()
            ws.close()
            return

        data = msg.get("data", {})
        result = data.get("result", {})
        ws_data = result.get("ws", [])
        if ws_data:
            segment = "".join(j.get("w", "") for i in ws_data for j in i.get("cw", []))
            if segment:
                result_texts.append(segment)

        if data.get("status") == 2:
            finished.set()

    def on_error(ws, error):
        error_msg.append(str(error))
        finished.set()

    def on_close(ws, *args):
        finished.set()

    ws_url = _create_url(appid, apikey, apisecret)
    ws = websocket.WebSocketApp(
        ws_url, on_open=on_open, on_message=on_message,
        on_error=on_error, on_close=on_close,
    )
    ws_thread = Thread(target=lambda: ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}), daemon=True)
    ws_thread.start()

    timeout = max(30.0, duration * 2 + 10)
    if not finished.wait(timeout=timeout):
        error_msg.append(f"Timeout after {timeout:.0f}s")
        ws.close()

    ws_thread.join(timeout=5)

    if error_msg:
        raise RuntimeError(f"iFlytek ASR failed (chunk {chunk_index}): {'; '.join(error_msg)}")

    return "".join(result_texts)


def transcribe_wav(
    wav_path: str | Path,
    appid: str = "",
    apikey: str = "",
    apisecret: str = "",
) -> str:
    """Transcribe a 16kHz mono PCM WAV file with iFlytek cloud ASR (v2).

    For audio longer than CHUNK_SECONDS (50s), the file is automatically
    sliced into overlapping chunks, each sent to the API separately,
    and the results are concatenated.
    """
    wav_path = Path(wav_path)
    appid = appid or _DEFAULT_APPID
    apikey = apikey or _DEFAULT_APIKEY
    apisecret = apisecret or _DEFAULT_APISECRET

    print(f"[xunfei] reading audio: {wav_path.name}")
    pcm_data = _read_wav_pcm(wav_path)
    total_duration = len(pcm_data) / 32000.0
    print(f"[xunfei] audio duration: {total_duration:.1f}s")

    # ---- short audio: single call ----
    if total_duration <= MAX_AUDIO_SECONDS:
        print(f"[xunfei] connecting to {HOST}/v2/iat ...")
        t0 = time.time()
        full_text = _transcribe_pcm_chunk(pcm_data, appid, apikey, apisecret)
        elapsed = time.time() - t0
        print(f"[xunfei] done in {elapsed:.1f}s ({len(full_text)} chars)")
        return full_text

    # ---- long audio: slice & stitch ----
    bytes_per_sec = 32000  # 16kHz mono 16-bit PCM
    chunk_bytes = CHUNK_SECONDS * bytes_per_sec
    overlap_bytes = 2 * bytes_per_sec  # 2s overlap to avoid word-boundary cuts

    num_chunks = (len(pcm_data) + chunk_bytes - overlap_bytes - 1) // (chunk_bytes - overlap_bytes)
    print(f"[xunfei] audio {total_duration:.0f}s > {MAX_AUDIO_SECONDS}s limit, "
          f"splitting into {num_chunks} chunks of {CHUNK_SECONDS}s each...")

    all_texts: list[str] = []
    t_start = time.time()

    for i in range(num_chunks):
        start_byte = max(0, i * (chunk_bytes - overlap_bytes))
        end_byte = min(len(pcm_data), start_byte + chunk_bytes)
        chunk = pcm_data[start_byte:end_byte]
        chunk_dur = len(chunk) / bytes_per_sec

        print(f"[xunfei]   chunk {i + 1}/{num_chunks} "
              f"({start_byte / bytes_per_sec:.0f}s - {end_byte / bytes_per_sec:.0f}s, {chunk_dur:.1f}s) ...")
        t0 = time.time()

        try:
            chunk_text = _transcribe_pcm_chunk(chunk, appid, apikey, apisecret, chunk_index=i)
            elapsed_c = time.time() - t0
            print(f"[xunfei]   chunk {i + 1} done in {elapsed_c:.1f}s ({len(chunk_text)} chars): {chunk_text[:60]}...")
            all_texts.append(chunk_text)
        except Exception as e:
            print(f"[xunfei]   chunk {i + 1} FAILED: {e}")
            all_texts.append(f"[chunk_{i}_error]")

        # Small delay between chunks to avoid rate limiting
        if i < num_chunks - 1:
            time.sleep(0.5)

    total_elapsed = time.time() - t_start
    full_text = "。".join(t for t in all_texts if not t.startswith("[chunk_"))
    print(f"[xunfei] all chunks done in {total_elapsed:.1f}s, "
          f"joined text: {len(full_text)} chars")
    return full_text


def core_transcribe_for_record(record, wav_path: str, video_identifier: str = "") -> None:
    """Run iFlytek v2 ASR and populate record.media_info fields."""
    if not video_identifier:
        candidate = record.candidate if isinstance(record.candidate, dict) else {}
        video_identifier = candidate.get("video_identifier", "")
    if not video_identifier:
        video_identifier = datetime.now().strftime("%Y%m%d_%H%M%S")

    asr_txt_path = MEDIA_DIR / f"{video_identifier}.asr.txt"
    asr_json_path = MEDIA_DIR / f"{video_identifier}.asr.json"

    full_text = transcribe_wav(wav_path)

    asr_txt_path.write_text(full_text, encoding="utf-8")
    asr_json = {"backend": "xunfei", "model": "iat-v2", "video_identifier": video_identifier,
                "text": full_text, "text_length": len(full_text)}
    asr_json_path.write_text(json.dumps(asr_json, ensure_ascii=False, indent=2), encoding="utf-8")

    record.media_info["asr_text"] = full_text
    record.media_info["asr_text_path"] = str(asr_txt_path)
    record.media_info["asr_json_path"] = str(asr_json_path)
    record.media_info["asr_model"] = "xunfei-iat-v2"
    record.media_info["asr_source_video_identifier"] = video_identifier
    print(f"[xunfei] attached to record (vid={video_identifier}, len={len(full_text)})")
