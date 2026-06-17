"""Isolated PaddleOCR worker used by the Weixin collector.

The main collector keeps automation state alive for a long run, but PaddleOCR
can retain native memory across calls. This worker keeps that memory in a child
process so the parent can restart it periodically.
"""
from __future__ import annotations

import gc
import json
import os
import re
import sys
from typing import Any


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PADDLEX_CACHE_DIR = os.path.join(BASE_DIR, ".paddlex-cache")
MAX_JOBS = int(os.environ.get("WEIXIN_OCR_WORKER_MAX_JOBS", "8") or "8")
MAX_MEMORY_MB = int(
    os.environ.get(
        "WEIXIN_OCR_WORKER_MAX_MEMORY_MB",
        os.environ.get("WEIXIN_OCR_WORKER_MAX_RSS_MB", "2000"),
    )
    or "2000"
)

_OCR = None
_JOBS = 0


def configure_paddle_runtime_env() -> None:
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    os.environ["PADDLE_PDX_CACHE_HOME"] = PADDLEX_CACHE_DIR
    os.environ["FLAGS_enable_pir_api"] = "0"
    os.environ["FLAGS_json_format_model"] = "0"
    os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"
    os.environ["PADDLE_PDX_DISABLE_MKLDNN_MODEL_BL"] = "True"
    os.environ["FLAGS_use_mkldnn"] = "0"
    os.environ["FLAGS_use_onednn"] = "0"
    os.environ.setdefault("FLAGS_allocator_strategy", "naive_best_fit")


def get_memory_mb() -> int:
    try:
        import psutil  # type: ignore

        proc = psutil.Process(os.getpid())
        mem = proc.memory_info()
        values = [getattr(mem, "rss", 0)]
        try:
            full = proc.memory_full_info()
            values.extend(
                [
                    getattr(full, "private", 0),
                    getattr(full, "uss", 0),
                ]
            )
        except Exception:
            pass
        return int(max(values) / 1024 / 1024)
    except Exception:
        return 0


def get_ocr():
    global _OCR
    if _OCR is None:
        os.makedirs(PADDLEX_CACHE_DIR, exist_ok=True)
        from paddleocr import PaddleOCR

        _OCR = create_paddle_ocr(PaddleOCR)
    return _OCR


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def create_paddle_ocr(PaddleOCR):
    kwargs = {
        "use_angle_cls": env_bool("WEIXIN_OCR_USE_ANGLE_CLS", False),
        "lang": os.environ.get("WEIXIN_OCR_LANG", "ch"),
        "enable_mkldnn": False,
        "cpu_threads": env_int("WEIXIN_OCR_CPU_THREADS", 2),
        "rec_batch_num": env_int("WEIXIN_OCR_REC_BATCH_NUM", 1),
        "cls_batch_num": env_int("WEIXIN_OCR_CLS_BATCH_NUM", 1),
        "det_limit_side_len": env_int("WEIXIN_OCR_DET_LIMIT_SIDE_LEN", 960),
        "ocr_version": os.environ.get("WEIXIN_OCR_VERSION", "PP-OCRv4"),
    }

    while True:
        try:
            return PaddleOCR(**kwargs)
        except (TypeError, ValueError) as exc:
            bad_arg = parse_unsupported_kwarg(exc)
            if not bad_arg or bad_arg not in kwargs:
                raise
            print(f"[ocr-worker] drop unsupported PaddleOCR kwarg: {bad_arg}", file=sys.stderr)
            kwargs.pop(bad_arg)


def parse_unsupported_kwarg(exc: Exception) -> str:
    message = str(exc)
    patterns = (
        r"Unknown argument:\s*([A-Za-z_][A-Za-z0-9_]*)",
        r"unexpected keyword argument '([^']+)'",
        r"got an unexpected keyword argument '([^']+)'",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return match.group(1)
    return ""


def run_local_ocr(ocr, image_path: str):
    if hasattr(ocr, "ocr"):
        try:
            return ocr.ocr(image_path, cls=True)
        except TypeError as exc:
            if "unexpected keyword argument 'cls'" not in str(exc):
                raise
            return ocr.ocr(image_path)
    if hasattr(ocr, "predict"):
        return ocr.predict(image_path)
    raise RuntimeError("PaddleOCR object has neither ocr() nor predict()")


def extract_ocr_lines(result) -> list:
    if not result:
        return []
    if isinstance(result, dict):
        return extract_ocr_lines_from_dict(result)
    if isinstance(result, list):
        if result and isinstance(result[0], list):
            return result[0]
        if result and isinstance(result[0], dict):
            lines = []
            for page in result:
                lines.extend(extract_ocr_lines_from_dict(page))
            return lines
        return result
    return []


def extract_ocr_lines_from_dict(page: dict) -> list:
    texts = page.get("rec_texts") or page.get("texts") or page.get("text")
    if isinstance(texts, str):
        texts = [texts]
    if not isinstance(texts, list) or not texts:
        return []

    boxes = (
        page.get("rec_polys")
        or page.get("dt_polys")
        or page.get("boxes")
        or page.get("polys")
        or page.get("points")
    )
    if boxes is None:
        boxes = [None] * len(texts)

    scores = page.get("rec_scores") or page.get("scores") or [1.0] * len(texts)
    lines = []
    for index, text in enumerate(texts):
        box = boxes[index] if index < len(boxes) else None
        score = scores[index] if index < len(scores) else 1.0
        lines.append([box, (text, score)])
    return lines


def normalize_ocr_line(line):
    if isinstance(line, (list, tuple)) and len(line) >= 2:
        return line[0], line[1]
    if isinstance(line, dict):
        box = (
            line.get("box")
            or line.get("bbox")
            or line.get("points")
            or line.get("poly")
            or line.get("polygon")
        )
        rec = (
            line.get("rec")
            or line.get("text")
            or line.get("label")
            or line.get("transcription")
        )
        if isinstance(rec, str):
            rec = (rec, 1.0)
        return box, rec
    return None, None


def coerce_ocr_box_points(box) -> list:
    if box is None:
        return []
    if hasattr(box, "tolist"):
        box = box.tolist()
    if isinstance(box, tuple):
        box = list(box)
    if not isinstance(box, list):
        return []
    if len(box) == 4 and all(isinstance(value, (int, float)) for value in box):
        left, top, right, bottom = box
        return [[left, top], [right, top], [right, bottom], [left, bottom]]
    points = []
    for point in box:
        if hasattr(point, "tolist"):
            point = point.tolist()
        if isinstance(point, tuple):
            point = list(point)
        if isinstance(point, list) and len(point) >= 2:
            points.append(point)
    return points


def local_ocr_image(image_path: str) -> list[dict[str, Any]]:
    ocr = get_ocr()
    result = run_local_ocr(ocr, image_path)
    lines = extract_ocr_lines(result)
    del result
    if not lines:
        return []

    items = []
    for line in lines:
        box, rec = normalize_ocr_line(line)
        if box is None or rec is None:
            continue
        text = str(rec[0]).strip() if isinstance(rec, (list, tuple)) else str(rec).strip()
        if not text:
            continue
        points = coerce_ocr_box_points(box)
        xs = [int(point[0]) for point in points]
        ys = [int(point[1]) for point in points]
        if not xs or not ys:
            continue
        confidence = 0.0
        if isinstance(rec, (list, tuple)) and len(rec) >= 2:
            try:
                confidence = float(rec[1])
            except Exception:
                confidence = 0.0
        items.append(
            {
                "text": text,
                "x": int(sum(xs) / len(xs)),
                "y": int(sum(ys) / len(ys)),
                "w": max(xs) - min(xs),
                "h": max(ys) - min(ys),
                "confidence": confidence,
            }
        )
    gc.collect()
    return items


def handle_request(payload: dict) -> dict:
    global _JOBS
    image_path = payload.get("image_path", "")
    if not image_path:
        raise ValueError("image_path is required")
    items = local_ocr_image(image_path)
    _JOBS += 1
    memory_mb = get_memory_mb()
    should_restart = _JOBS >= MAX_JOBS or (MAX_MEMORY_MB > 0 and memory_mb > MAX_MEMORY_MB)
    return {
        "ok": True,
        "items": items,
        "jobs": _JOBS,
        "memory_mb": memory_mb,
        "restart": should_restart,
    }


def main() -> int:
    configure_paddle_runtime_env()
    protocol_out = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
            response = handle_request(payload)
        except Exception as exc:
            response = {"ok": False, "error": repr(exc), "jobs": _JOBS, "memory_mb": get_memory_mb()}
        protocol_out.write(json.dumps(response, ensure_ascii=False) + "\n")
        if response.get("restart"):
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
