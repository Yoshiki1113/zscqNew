"""Text quality helpers for OCR-derived Weixin evidence fields."""
from __future__ import annotations

import re


AMBIGUOUS_ID_CHARS = set("Il1O0")


def compact_ocr_id(text: str) -> str:
    """Keep only characters that can appear in a Weixin video channel id."""
    return re.sub(r"[^A-Za-z0-9_-]", "", text or "").strip()


def analyze_video_channel_id(raw_text: str) -> dict:
    """
    Return OCR quality metadata for a video channel id.

    We do not blindly convert I/l/1 or O/0 because Weixin ids may be mixed
    alphanumeric strings. The normalized value is only whitespace/punctuation
    cleanup; ambiguous characters are flagged for review.
    """
    normalized = compact_ocr_id(raw_text)
    ambiguous_positions = [
        {"index": index, "char": char}
        for index, char in enumerate(normalized)
        if char in AMBIGUOUS_ID_CHARS
    ]
    return {
        "raw": raw_text or "",
        "normalized": normalized,
        "needs_review": bool(ambiguous_positions),
        "ambiguous_positions": ambiguous_positions,
        "review_note": "OCR may confuse I/l/1 or O/0 in video channel ids."
        if ambiguous_positions
        else "",
    }
