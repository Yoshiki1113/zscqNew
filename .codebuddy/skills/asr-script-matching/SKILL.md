---
name: asr-script-matching
description: >-
  Speech-to-text and reference script matching for evidence collection. Covers
  the full ASR pipeline (iFlytek cloud slicing, SenseVoice offline, Paraformer
  offline), the script_matcher.py engine (pinyin-based length-normalized
  windowing + char-level confirmation), context-expansion verification, and
  HTML comparison report generation. Use this skill whenever modifying ASR
  modules, the matching algorithm, or the comparison report generator in the
  weixin/ project.
---

# ASR & Script Matching Skill

## Overview

This skill covers two tightly-coupled modules in the weixin/ evidence system:

1. **ASR Pipeline** — Multi-backend speech-to-text with automatic fallback and long-audio slicing.
2. **Script Matcher** — Pinyin-based fuzzy matching of ASR text against a reference drama script, with length-normalized windowing, context-expansion verification, and HTML comparison reports.

Together they enable: 采集录像 → 提取音频 → 语音转文字 → 比对剧本 → 标注侵权位置。

## Architecture

```
weixin/
├── asr_xunfei.py           iFlytek cloud ASR (primary, WebSocket v2 + auto-slicing)
├── asr_sensevoice.py       SenseVoice offline ASR (sherpa-onnx) + ASR pipeline dispatcher
├── asr_paraformer.py       Paraformer offline ASR (sherpa-onnx, fastest)
├── script_matcher.py       Reference script matching engine
├── asr_comparison.html     Generated comparison report (latest run)
├── _script_raw.txt         Extracted reference script text (64k chars, "弃子归来震万城")
└── step_tests/
    ├── test_script_matcher.py    Script matching unit tests
    ├── test_xunfei_asr.py        iFlytek single-call test
    └── test_sensevoice_asr.py    SenseVoice single-call test
```

## ASR Pipeline (`asr_sensevoice.py` + `asr_xunfei.py`)

### Priority: iFlytek (cloud) → SenseVoice (offline) → Paraformer (offline)

```python
# asr_sensevoice.py — run_asr_pipeline(record, wav_path, video_identifier)
# 1) iFlytek cloud (best accuracy + punctuation)
# 2) SenseVoice offline (best offline quality)
# 3) Paraformer offline (fastest)
# After each success: auto-triggers _run_script_match(record)
```

### iFlytek Auto-Slicing (`asr_xunfei.py`)

The iFlytek API has a **60-second limit**. For audio >60s, the module
automatically slices into 50-second chunks with 2-second overlap:

```python
# transcribe_wav() internal logic:
if total_duration <= 60:
    _transcribe_pcm_chunk(pcm_data)    # single call
else:
    # Split into N chunks of 50s each (2s overlap)
    for chunk in slices:
        _transcribe_pcm_chunk(chunk)
    # Join results with "。" separator
```

**Key constants:**
| Constant | Value | Meaning |
|----------|-------|---------|
| `MAX_AUDIO_SECONDS` | 60 | API limit |
| `CHUNK_SECONDS` | 50 | Per-slice duration |
| Overlap | 2s | Prevent word-boundary cuts |

**Credentials:** Default appid/apikey/apisecret are embedded; also support
env vars `XUNFEI_APPID`, `XUNFEI_APIKEY`, `XUNFEI_APISECRET`.

### SenseVoice (`asr_sensevoice.py`)

- Backend: sherpa-onnx `OfflineRecognizer.from_sense_voice()`
- Model: `sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17`
- Features: built-in punctuation, ITN (inverse text normalization), int8 quantized
- Speed: ~3.6x real-time on CPU
- Also contains `run_asr_pipeline()` — the **main dispatcher** that tries all 3 backends

### Paraformer (`asr_paraformer.py`)

- Backend: sherpa-onnx `OfflineRecognizer.from_paraformer()`
- Model: `sherpa-onnx-paraformer-zh-small-2024-03-09`
- Speed: ~164x real-time (fastest offline option)
- No punctuation (ITN provides basic formatting)

### Functions reference

| Module | Function | Purpose |
|--------|----------|---------|
| `asr_xunfei.py` | `transcribe_wav(path)` | Cloud ASR with auto-slicing |
| `asr_xunfei.py` | `_transcribe_pcm_chunk(data)` | Core WebSocket v2 call |
| `asr_xunfei.py` | `core_transcribe_for_record(rec, path, vid)` | Attach result to EvidenceRecord |
| `asr_sensevoice.py` | `run_asr_pipeline(record, path, vid)` | **Main dispatcher** (3-backend fallback) |
| `asr_sensevoice.py` | `transcribe_wav(path)` | Standalone SenseVoice call |
| `asr_sensevoice.py` | `core_transcribe_for_record(rec, path, vid)` | Attach SenseVoice result |
| `asr_sensevoice.py` | `_run_script_match(record)` | Auto-trigger script matching after ASR |
| `asr_paraformer.py` | `transcribe_wav(path)` | Standalone Paraformer call |
| `asr_paraformer.py` | `core_transcribe_for_record(rec, path, vid)` | Attach Paraformer result |

## Script Matcher (`script_matcher.py`)

### Reference Script

- File: `weixin/_script_raw.txt` (64,001 chars)
- Source: 弃子归来震万城 (drama script)
- Content: 47 episodes, ~447 dialog lines after parsing
- Format: Episode headers (`第X集`), scene headers (`1-1 日 内 地点`), character lists, dialog (`人物：台词`)

### Three-Layer Matching Strategy

```
Input: ASR text
  │
  ▼
Layer 1 — Pinyin Conversion
  pypinyin.lazy_pinyin(query) → query_pinyin (no tones)
  All script dialog lines pre-indexed with pinyin
  │
  ▼
Layer 2 — Length-Normalized Windowing + rapidfuzz ratio
  target_len = ceil(query_char_len × 1.1)
  For each candidate line:
    if line_len ≤ target_len: use full line
    else: extract sliding windows of target_len chars
  fuzz.ratio(query_pinyin, window_pinyin) → pinyin_score
  │
  ▼
Layer 3 — Character-Level Confirmation
  difflib.SequenceMatcher(query_clean, window_clean) → char_score
  combined_score = pinyin × 0.6 + char × 0.4
  │
  ▼
Output: sorted [{
  script_text, display_text, character,
  similarity_score, pinyin_score, char_score,
  episode, scene, location, characters,
  line_index, matched_window, target_chars
}]
```

### Key design decisions

| Decision | Rationale |
|----------|-----------|
| Pinyin as matching layer | Eliminates ASR homophone errors (宗→松 both pinyin "zong") |
| `ratio` not `partial_ratio` | Length-equal windows → full comparison is more accurate |
| Window size = query × 1.1 | Guarantees length parity, slightly larger script window for tolerance |
| All `（...）` parens stripped | Stage directions & OS markers add noise; matching uses pure dialog only |
| `display_text` separate from `text` | Matching uses cleaned text; display shows original with parens |

### Script Text Cleaning

Before matching, all parenthetical content is stripped from dialog:
```python
# Original: （逼视顾母，压迫感十足）这一巴掌下去（怒吼），我跟你们顾家…
# Cleaned:  这一巴掌下去，我跟你们顾家…
dialog_text = _RE_PAREN_CONTENT.sub("", dialog_text)  # no count=1 limit
```

The `DialogLine` dataclass stores both:
- `text` → fully cleaned (used for matching)
- `display_text` → original with parens (used for HTML display)

### Context Expansion Verification

For high-scoring sentences (≥50%), expand context to confirm:
```python
# For each sentence matching ≥50%:
#   ±1 sentence → re-match → score_a
#   ±2 sentences → re-match → score_b
#   ±3 sentences → re-match → score_c
# Score trend indicates match quality:
#   ↑ stable → confirmed match
#   ↓ sharp drop → likely false positive / scene boundary
```

### Main API

```python
from script_matcher import match_query, get_index

# One-shot
result = match_query("我就知道流年你一定会回来", top_n=3)
# [{"script_text": "（哽咽）我就知道，流年……", "similarity_score": 0.98, ...}]

# Reuse index
idx = get_index()  # 447 lines, ~2s first load, cached afterwards
results = idx.match(asr_text, top_n=5, min_pinyin_score=0.40)
```

### Integration Point

In `run_asr_pipeline()` (asr_sensevoice.py), after each successful ASR backend:
```python
_fn(record, wav_path, video_identifier)  # ASR done
_run_script_match(record)                  # auto-match against script
```
Result written to `record.media_info["script_match"]`:
```json
{
  "status": "matched",
  "best_match": { "script_text": "...", "similarity_score": 0.98, ... },
  "top_candidates": [...]
}
```

### HTML Comparison Report

The comparison HTML (`weixin/asr_comparison.html`) shows:
- Left: ASR sentences (iFlytek output, sorted by match score descending)
- Right: Matching script original text with surrounding context
- Score bars: color-coded (green ≥85%, orange 65-85%, yellow 45-65%)
- Context expansion: ±1/±2/±3 sentence scores inline
- Summary: total sentences, ≥85% count, ≥65% count

Generated by `_gen_compare.py` (temporary, deleted after run).

## Common Tasks

### Add a new ASR backend
1. Create `weixin/asr_newbackend.py` with `core_transcribe_for_record(record, wav, vid)`.
2. Add it to `run_asr_pipeline()` in `asr_sensevoice.py` as a new fallback step.
3. Create `step_tests/test_newbackend_asr.py`.

### Tune matching thresholds
- `min_pinyin_score` in `ScriptIndex.match()` — raise to reduce false positives.
- `_LENGTH_RATIO` (1.1) — increase for more context, decrease for tighter match.
- `_WEIGHT_PINYIN` / `_WEIGHT_CHAR` — adjust balance between pinyin and char.

### Regenerate comparison HTML for a WAV file
```bash
cd weixin
python -c "from asr_xunfei import transcribe_wav; print(transcribe_wav('media/xxx.wav'))"
# Then use the output in _gen_compare.py to rebuild the HTML
```

### Update the reference script
1. Replace `weixin/_script_raw.txt` with the new script text.
2. Delete module cache or restart Python — `ScriptIndex` is auto-rebuilt on first access.
3. Verify: `python -c "from script_matcher import get_index; print(len(get_index().lines))"`

## Data Flow

```
WAV file
  │
  ▼
run_asr_pipeline(record, wav, vid)
  ├── iFlytek → asr_text (with punctuation)
  ├── SenseVoice → asr_text
  └── Paraformer → asr_text
  │
  ▼ (auto after each backend success)
_run_script_match(record)
  └── match_query(asr_text)
      └── ScriptIndex.match()
          └── 447 dialog lines → top-N matches
  │
  ▼
record.media_info["script_match"] = {
  status, best_match, top_candidates
}
  │
  ▼
save_record() → JSON/MySQL
```
