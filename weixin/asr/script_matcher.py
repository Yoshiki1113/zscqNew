"""Script-vs-ASR text matching engine for Weixin video evidence system.

Three-layer matching strategy:
  1. Pinyin conversion – convert both query and script lines to pinyin,
     naturally filtering ASR homophone errors (e.g. 宗→松 both map to zong/song).
  2. rapidfuzz partial_ratio on pinyin – fast approximate match to collect
     top-K candidates from ~2000 dialog lines.
  3. difflib.SequenceMatcher on character level – fine-grained confirmation,
     combined with pinyin score for the final ranking.

Usage:
    from script_matcher import match_query
    result = match_query("宗也配说普渡众生", top_n=3)
    # Returns list of dicts with script_text, similarity_score, episode, scene, etc.

    # Or use the class directly for repeated queries:
    from script_matcher import get_index
    idx = get_index()
    result = idx.match("some asr text")
"""

from __future__ import annotations

import re
import os
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

# --- Module-level singleton index ---
_index: Optional["ScriptIndex"] = None

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "data" / "_script_raw.txt"


def get_index(script_path: str | Path | None = None) -> "ScriptIndex":
    """Return the module-level singleton ScriptIndex, creating it on first call."""
    global _index
    if _index is None:
        path = script_path or _SCRIPT_PATH
        _index = ScriptIndex(path)
    return _index


def match_query(query_text: str, top_n: int = 3, min_pinyin_score: float = 0.40,
                script_path: str | Path | None = None) -> list[dict]:
    """Convenience wrapper: match an ASR text against the script.

    Returns up to *top_n* results, each a dict with:
        script_text, similarity_score, episode, scene, location,
        characters, char_start, char_end, pinyin_score, char_score
    """
    idx = get_index(script_path)
    return idx.match(query_text, top_n=top_n, min_pinyin_score=min_pinyin_score)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DialogLine:
    """One parsed dialog line with its context."""
    text: str                          # fully cleaned text (no parens, for matching)
    display_text: str = ""             # original text with parens kept (for display)
    character: str = ""                # speaker name
    pinyin: str = ""                   # space-joined pinyin syllables (no tones)
    clean_text: str = ""               # punctuation-stripped text for char-level matching
    pinyin_syllables: list = field(default_factory=list)  # per-character pinyin list
    episode: str = ""                  # e.g. "第1集"
    scene: str = ""                    # e.g. "1-1"
    location: str = ""                 # e.g. "顾家别墅客厅"
    characters: list[str] = field(default_factory=list)  # scene-level character list
    char_start: int = 0                # byte offset in cleaned script text
    char_end: int = 0                  # byte offset end
    line_index: int = 0                # 0-based line index


# ---------------------------------------------------------------------------
# Script parser & indexer
# ---------------------------------------------------------------------------

class ScriptIndex:
    """Load and index the script text for fast pinyin-based matching."""

    # Regex patterns for script parsing
    _RE_EPISODE = re.compile(r"^第(\d+)集[:：]\s*(.+)$")
    _RE_SCENE = re.compile(r"^(\d+-\d+)\s+([日夜])\s+([内外])\s*(.+)$")
    _RE_CHARACTERS = re.compile(r"^出场人物[:：]\s*(.+)$")
    _RE_STAGE_DIRECTION = re.compile(r"^▲")
    _RE_DIALOG = re.compile(
        r"^([^\uff08：:\n▲]+)"             # character name (stop at full-width paren or colon)
        r"(?:\s*[\uff08(][^\uff09)]*[\uff09)])?"  # optional parenthetical (action/OS)
        r"[:：]\s*(.+)$"                      # colon + dialog text
    )
    _RE_PAREN_CONTENT = re.compile(r"[\uff08(][^\uff09)]*[\uff09)]")  # strip parenthetical notes
    # Reject lines that look like character bios / descriptions
    _RE_NON_DIALOG = re.compile(
        r"^(身份标签|外形数据|身高|体重|形象|穿着风格|人设性格|参考形象)"
    )

    def __init__(self, script_path: str | Path):
        self.script_path = Path(script_path)
        self.lines: list[DialogLine] = []
        self._pinyin_to_idx: dict[str, list[int]] = {}  # pinyin prefix → line indices
        self._load_and_parse()
        self._build_index()

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _load_and_parse(self) -> None:
        """Load raw script, extract dialog lines with context."""
        raw_text = self.script_path.read_text(encoding="utf-8")

        # Accumulate context as we scan
        current_episode = ""
        current_scene = ""
        current_location = ""
        current_characters: list[str] = []
        in_script_body = False  # True after first episode header

        # Split into logical lines (Windows/Linux newlines)
        raw_lines = raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        char_offset = 0
        line_index = 0

        for raw_line in raw_lines:
            stripped = raw_line.strip()
            char_offset += len(raw_line.encode("utf-8"))  # approximate tracking

            # Skip empty lines
            if not stripped:
                continue

            # Episode header: 第1集：...
            m = self._RE_EPISODE.match(stripped)
            if m:
                current_episode = f"第{m.group(1)}集"
                in_script_body = True  # Enter script body
                continue

            # Skip all content before the first episode header (front matter: bios, intros)
            if not in_script_body:
                continue

            # Scene header: 1-1 日 内 顾家别墅客厅
            m = self._RE_SCENE.match(stripped)
            if m:
                current_scene = m.group(1)
                current_location = m.group(4).strip()
                continue

            # Character list: 出场人物：...
            m = self._RE_CHARACTERS.match(stripped)
            if m:
                chars_str = m.group(1)
                current_characters = [
                    c.strip() for c in chars_str.replace("、", ",").split(",") if c.strip()
                ]
                continue

            # Skip stage directions and non-dialog metadata
            if self._RE_STAGE_DIRECTION.match(stripped):
                continue
            if self._RE_NON_DIALOG.match(stripped):
                continue

            # Try to match a dialog line
            m = self._RE_DIALOG.match(stripped)
            if not m:
                continue

            char_name = m.group(1).strip()
            dialog_text = m.group(2).strip()

            # Preserve original (with parens) for display
            display_text = dialog_text

            # Fully clean: strip ALL parenthetical stage directions
            # e.g. "（声音嘶哑）流年，二十年了（抽泣），可你呢？" → "流年，二十年了，可你呢？"
            dialog_text = self._RE_PAREN_CONTENT.sub("", dialog_text).strip()

            # Skip lines that look like descriptions rather than speech
            if self._is_description_line(stripped, char_name, dialog_text):
                continue

            # Convert to pinyin from fully cleaned text
            from pypinyin import lazy_pinyin
            pinyin_syllables = lazy_pinyin(dialog_text, errors="ignore")
            pinyin_syl_list = [p for p in pinyin_syllables if p and p != " "]
            pinyin_str = " ".join(pinyin_syl_list)
            # Clean text: strip punctuation for char-level matching
            clean = re.sub(r"[，。！？、；：\u201c\u201d\u2018\u2019（）\s]", "", dialog_text)

            # Skip lines with essentially no pinyin content
            if len(pinyin_str.replace(" ", "")) < 2:
                continue

            dl = DialogLine(
                text=dialog_text,
                display_text=display_text,
                character=char_name,
                pinyin=pinyin_str,
                clean_text=clean,
                pinyin_syllables=pinyin_syl_list,
                episode=current_episode,
                scene=current_scene,
                location=current_location,
                characters=list(current_characters),
                char_start=char_offset - len(stripped.encode("utf-8")),
                char_end=char_offset,
                line_index=line_index,
            )
            self.lines.append(dl)
            line_index += 1

    @staticmethod
    def _is_description_line(raw_line: str, char_name: str, dialog_text: str) -> bool:
        """Heuristic: reject lines that are character descriptions, not speech."""
        desc_markers = (
            "身份标签", "外形数据", "身高：", "体重：", "形象：",
            "穿着风格", "人设性格", "参考形象", "性格：", "简介",
        )
        if any(m in raw_line for m in desc_markers):
            return True
        # Very long "dialog" (>200 chars) is likely description
        if len(dialog_text) > 200:
            return True
        return False

    # ------------------------------------------------------------------
    # Index building
    # ------------------------------------------------------------------

    def _build_index(self) -> None:
        """Build a prefix index on pinyin for fast candidate filtering."""
        for i, dl in enumerate(self.lines):
            pinyin_no_space = dl.pinyin.replace(" ", "")
            # Index by first 2 pinyin chars as quick filter
            prefix = pinyin_no_space[:4] if len(pinyin_no_space) >= 4 else pinyin_no_space
            self._pinyin_to_idx.setdefault(prefix, []).append(i)

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    # Window extraction constants
    _LENGTH_RATIO = 1.1    # script window = ceil(query_len * 1.1)
    _STRIDE_DIVISOR = 3    # stride = window_len // divisor
    _WEIGHT_PINYIN = 0.6   # pinyin weight in combined score
    _WEIGHT_CHAR = 0.4     # char-level weight

    def match(
        self,
        query_text: str,
        top_n: int = 3,
        min_pinyin_score: float = 0.40,
    ) -> list[dict]:
        """Match *query_text* against the script using length-normalized windowing.

        For each candidate dialog line, we extract sliding windows of size
        ≈ ceil(query_char_len * 1.1) so that query and target are similar
        length.  This eliminates the noise from matching a 15-char ASR
        fragment against a 150-char monologue.

        Parameters:
            query_text: ASR-transcribed Chinese text.
            top_n:      Max number of results to return.
            min_pinyin_score: Minimum pinyin ratio to consider a candidate.

        Returns:
            List of result dicts sorted by similarity_score descending.
        """
        if not query_text or not self.lines:
            return []

        # ---- Layer 1: query pinyin + clean text ----
        from pypinyin import lazy_pinyin
        query_pinyin_raw = lazy_pinyin(query_text, errors="ignore")
        query_py_list = [p for p in query_pinyin_raw if p and p != " "]
        if not query_py_list:
            return []
        query_py_nospace = "".join(query_py_list)
        query_clean = re.sub(r"[，。！？、；：\u201c\u201d\u2018\u2019（）\s]", "", query_text)
        query_char_len = len(query_clean)

        # Target window character count: ceil(query_chars * 1.1)
        target_chars = max(int(query_char_len * self._LENGTH_RATIO) + 1, query_char_len + 2)

        # ---- Layer 2: length-normalized pinyin window matching ----
        from rapidfuzz import fuzz

        # Quick prefix filter
        prefix = query_py_nospace[:4] if len(query_py_nospace) >= 4 else query_py_nospace
        candidate_indices = self._pinyin_to_idx.get(prefix, list(range(len(self.lines))))

        # Each candidate: (line_idx, best_pinyin_score, best_window_clean_text, window_char_start)
        candidates: list[tuple[int, float, str, int]] = []

        for i in candidate_indices:
            dl = self.lines[i]
            clean = dl.clean_text
            py_list = dl.pinyin_syllables
            line_char_len = len(clean)

            # Line too short: use full line as-is
            if line_char_len <= target_chars:
                py_win = "".join(py_list)
                score = fuzz.ratio(query_py_nospace, py_win) / 100.0
                if score >= min_pinyin_score:
                    candidates.append((i, score, clean, 0))
                continue

            # Line longer: extract sliding windows of target_chars characters
            stride = max(1, target_chars // self._STRIDE_DIVISOR)
            best_score = 0.0
            best_clean_win = ""
            best_win_start = 0

            for start in range(0, line_char_len - target_chars + 1, stride):
                end = start + target_chars
                clean_win = clean[start:end]
                # Corresponding pinyin: need character-aligned slicing
                # Since clean_text strips punctuation, we can't directly slice py_list.
                # We approximate by slicing py_list proportionally and then trimming.
                # Simpler: regenerate pinyin for the window
                py_win = "".join(lazy_pinyin(clean_win, errors="ignore"))
                score = fuzz.ratio(query_py_nospace, py_win) / 100.0
                if score > best_score:
                    best_score = score
                    best_clean_win = clean_win
                    best_win_start = start

            if best_score >= min_pinyin_score:
                candidates.append((i, best_score, best_clean_win, best_win_start))

        if not candidates:
            # Fallback: scan all lines
            for i, dl in enumerate(self.lines):
                if i in {c[0] for c in candidates}:
                    continue
                clean = dl.clean_text
                py_list = dl.pinyin_syllables
                line_char_len = len(clean)
                if line_char_len <= target_chars:
                    py_win = "".join(py_list)
                    score = fuzz.ratio(query_py_nospace, py_win) / 100.0
                    if score >= min_pinyin_score:
                        candidates.append((i, score, clean, 0))
                    continue
                stride = max(1, target_chars // self._STRIDE_DIVISOR)
                best_score = 0.0
                best_clean_win = ""
                best_win_start = 0
                for start in range(0, line_char_len - target_chars + 1, stride):
                    clean_win = clean[start:start + target_chars]
                    py_win = "".join(lazy_pinyin(clean_win, errors="ignore"))
                    score = fuzz.ratio(query_py_nospace, py_win) / 100.0
                    if score > best_score:
                        best_score = score
                        best_clean_win = clean_win
                        best_win_start = start
                if best_score >= min_pinyin_score:
                    candidates.append((i, best_score, best_clean_win, best_win_start))

        if not candidates:
            return []

        # ---- Layer 3: char-level confirmation on length-matched windows ----
        candidates.sort(key=lambda x: x[1], reverse=True)
        top_k = candidates[:max(top_n * 3, 10)]

        results = []
        for line_idx, pinyin_score, clean_win, win_start in top_k:
            dl = self.lines[line_idx]

            char_score = 0.0
            if query_clean and clean_win:
                sm = SequenceMatcher(None, query_clean, clean_win)
                char_score = sm.ratio()
                # If win matches poorly, also try the query as the shorter side
                if len(query_clean) > len(clean_win):
                    sm2 = SequenceMatcher(None, clean_win, query_clean)
                    char_score = max(char_score, sm2.ratio())

            combined_score = pinyin_score * self._WEIGHT_PINYIN + char_score * self._WEIGHT_CHAR

            results.append({
                "script_text": dl.display_text,  # original text with parens for display
                "script_text_clean": dl.text,    # cleaned text used for matching
                "character": dl.character,
                "similarity_score": round(combined_score, 4),
                "pinyin_score": round(pinyin_score, 4),
                "char_score": round(char_score, 4),
                "episode": dl.episode,
                "scene": dl.scene,
                "location": dl.location,
                "characters": dl.characters,
                "char_start": dl.char_start,
                "char_end": dl.char_end,
                "line_index": dl.line_index,
                "matched_window": clean_win,
                "target_chars": target_chars,
            })

        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return results[:top_n]


# ---------------------------------------------------------------------------
# Standalone CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    idx = get_index()
    print(f"[script_matcher] Loaded {len(idx.lines)} dialog lines from script.\n")

    # Test with sample ASR texts from three_way_comparison.json
    test_queries = [
        "松也配说普度众生这倒是尤浅胆怯真想看看他如何收场用是我的小伙钱都让他们打造精神神像了那都是血汗钱啊是",
        "松也配以说普度众生，这道士有情弹气，真想看看他如何收场。又是我的小伙钳都让他们打造金神神像了，那都是虚汗钱。",
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"{'='*70}")
        print(f"Query {i} ({len(query)} chars): {query[:60]}...")
        print(f"{'='*70}")
        results = match_query(query, top_n=3)
        for j, r in enumerate(results, 1):
            print(f"\n  #{j}  similarity={r['similarity_score']:.2%}  "
                  f"(pinyin={r['pinyin_score']:.2%}  char={r['char_score']:.2%})")
            print(f"        episode={r['episode']}  scene={r['scene']}  location={r['location']}")
            print(f"        speaker={r['character']}  characters={r['characters']}")
            print(f"        text: {r['script_text'][:80]}...")
        if not results:
            print("  (no matches found)")
        print()
