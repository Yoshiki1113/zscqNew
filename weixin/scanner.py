"""Weixin video scanner: OCR quick scan + candidate extraction."""
import hashlib
import re

from main import ocr_recognize
from models import Candidate


def _keyword_fragments(keyword: str) -> list[str]:
    keyword = (keyword or "").strip()
    if len(keyword) <= 4:
        return [keyword] if keyword else []
    frags = []
    for i in range(0, len(keyword) - 3, 2):
        frags.append(keyword[i:i + 4])
    return list(dict.fromkeys([f for f in frags if f]))


def _text_matches_keyword(text: str, keyword: str) -> bool:
    text = (text or "").strip()
    keyword = (keyword or "").strip()
    if not text or not keyword:
        return False
    if keyword in text:
        return True
    if text in keyword and len(text) >= 4:
        return True
    return any(frag in text for frag in _keyword_fragments(keyword))


async def scan_current_screen(session, keyword):
    """
    OCR the current screen and extract candidate videos related to keyword.
    Returns a score-sorted list of Candidate objects.
    """
    raw = await ocr_recognize(session)
    items = raw.get("items", raw) if isinstance(raw, dict) else raw
    if not items:
        return []

    hits = []
    for it in items:
        txt = (it.get("text", "") or "").strip()
        x = it.get("x", 0)
        y = it.get("y", 0)
        if not _text_matches_keyword(txt, keyword):
            continue
        if y < 350 or y > 2400:
            continue
        if len(txt) < 3:
            continue
        if txt == keyword:
            continue
        hits.append(it)
        print(f"  [命中] '{txt[:30]}' @ ({x}, {y})")

    if not hits:
        return []

    candidates = []
    seen_ys = set()

    for hit in hits:
        hy = hit["y"]
        if any(abs(hy - sy) < 30 for sy in seen_ys):
            continue
        seen_ys.add(hy)

        nearby = [it for it in items if abs(it.get("y", 0) - hy) < 250]
        nearby.sort(key=lambda x: x.get("y", 0))

        title_text = (hit.get("text", "") or "").strip()
        author_name = ""
        publish_time = ""
        like_count = ""
        comment_count = ""
        share_count = ""
        number_parts = []

        for it in nearby:
            txt = (it.get("text", "") or "").strip()
            x = it.get("x", 0)
            y = it.get("y", 0)
            if not txt:
                continue

            if (
                len(txt) > len(title_text)
                and hy - 80 <= y <= hy + 120
                and 5 <= len(txt) <= 60
            ):
                title_text = txt

            if "+关注" in txt:
                author_name = txt.replace("+关注", "").strip()
            elif (
                not author_name
                and hy + 20 <= y <= hy + 220
                and 2 <= len(txt) <= 15
                and not re.search(r"[\d:]", txt)
                and x < 760
            ):
                author_name = txt

            if not publish_time and re.search(
                r"(刚刚|\d+分钟前|\d+小时前|\d+天前|\d{4}[-/.]\d{1,2}[-/.]\d{1,2})",
                txt,
            ):
                publish_time = txt

            if re.search(r"^[\d.]+[万wW]?$", txt):
                number_parts.append(txt)

        for i, np in enumerate(number_parts):
            if i == 0:
                like_count = np
            elif i == 1:
                comment_count = np
            elif i == 2:
                share_count = np

        click_x = min(max(hit.get("x", 540), 200), 880)
        click_y = min(hy + 120, 2500)

        score = 1
        if len(title_text) >= max(len(keyword) + 2, 6):
            score += 1
        if author_name:
            score += 1
        if like_count and re.search(r"\d", like_count):
            score += 1
        if 500 <= hy <= 1800:
            score += 1

        candidates.append(
            Candidate(
                keyword=keyword,
                hit_text=hit.get("text", ""),
                title_text=title_text,
                author_name=author_name,
                publish_time=publish_time,
                like_count=like_count,
                comment_count=comment_count,
                share_count=share_count,
                click_x=click_x,
                click_y=click_y,
                score=score,
            )
        )

    candidates.sort(key=lambda c: -c.score)
    return candidates


def is_hit(text: str, keywords: list) -> bool:
    """Return whether text contains any keyword."""
    return any(kw in text for kw in keywords)


def fingerprint(candidate: Candidate) -> str:
    """Generate a dedup fingerprint for content."""
    raw = f"weixin|{candidate.keyword}|{candidate.author_name}|{candidate.title_text[:30]}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()
