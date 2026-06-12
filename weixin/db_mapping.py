"""Database schema and row mapping for Weixin video evidence."""
from __future__ import annotations

import json
from datetime import datetime

from models import EvidenceRecord


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS weixin_video_evidence (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    platform VARCHAR(32) NOT NULL DEFAULT 'weixin',
    search_keyword VARCHAR(255) NOT NULL,
    captured_at DATETIME NOT NULL,
    captured_at_raw VARCHAR(64) NOT NULL DEFAULT '',

    candidate_fingerprint VARCHAR(64) NOT NULL,
    candidate_title VARCHAR(500) NOT NULL DEFAULT '',
    candidate_author_name VARCHAR(255) NOT NULL DEFAULT '',
    candidate_publish_time VARCHAR(255) NOT NULL DEFAULT '',
    candidate_click_x INT NOT NULL DEFAULT 0,
    candidate_click_y INT NOT NULL DEFAULT 0,

    video_blogger_name VARCHAR(255) NOT NULL DEFAULT '',
    video_channel_id VARCHAR(128) NOT NULL DEFAULT '',
    video_channel_id_raw VARCHAR(255) NOT NULL DEFAULT '',
    video_channel_id_needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    video_channel_id_ambiguous_positions_json LONGTEXT NOT NULL,
    video_link VARCHAR(1000) NOT NULL DEFAULT '',
    work_publish_time VARCHAR(255) NOT NULL DEFAULT '',
    like_count VARCHAR(64) NOT NULL DEFAULT '',
    comment_count VARCHAR(64) NOT NULL DEFAULT '',
    share_count VARCHAR(64) NOT NULL DEFAULT '',

    profile_name VARCHAR(255) NOT NULL DEFAULT '',
    profile_account VARCHAR(255) NOT NULL DEFAULT '',

    has_traffic_marker BOOLEAN NOT NULL DEFAULT FALSE,
    traffic_marker_text VARCHAR(255) NOT NULL DEFAULT '',
    target_blogger_name VARCHAR(255) NOT NULL DEFAULT '',
    target_video_channel_id VARCHAR(128) NOT NULL DEFAULT '',
    target_video_channel_id_raw VARCHAR(255) NOT NULL DEFAULT '',
    target_video_channel_id_needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    target_video_channel_id_ambiguous_positions_json LONGTEXT NOT NULL,
    company_full_name VARCHAR(255) NOT NULL DEFAULT '',
    company_verified_at VARCHAR(255) NOT NULL DEFAULT '',

    recording_video_path VARCHAR(1000) NOT NULL DEFAULT '',
    recording_audio_path VARCHAR(1000) NOT NULL DEFAULT '',
    recording_started_at VARCHAR(64) NOT NULL DEFAULT '',
    recording_ended_at VARCHAR(64) NOT NULL DEFAULT '',
    recording_duration_seconds INT NOT NULL DEFAULT 0,
    has_audio BOOLEAN NULL DEFAULT NULL,
    asr_text LONGTEXT NOT NULL,
    asr_json_path VARCHAR(1000) NOT NULL DEFAULT '',

    screenshots_json LONGTEXT NOT NULL,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
""".strip()


def _to_mysql_datetime(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return raw
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _json_dumps(value) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def evidence_record_to_db_row(record: EvidenceRecord) -> dict:
    """Flatten one EvidenceRecord into a single-row DB payload."""
    candidate = record.candidate or {}
    video_info = record.video_info or {}
    profile_info = record.profile_info or {}
    traffic_info = record.traffic_info or {}
    media_info = record.media_info or {}

    captured_at_raw = record.capture_time or record.capture_timestamp or ""

    return {
        "platform": record.platform or "weixin",
        "search_keyword": record.search_keyword or "",
        "captured_at": _to_mysql_datetime(captured_at_raw),
        "captured_at_raw": captured_at_raw,
        "candidate_fingerprint": candidate.get("fingerprint", "") or "",
        "candidate_title": candidate.get("title_text", "") or candidate.get("hit_text", "") or "",
        "candidate_author_name": candidate.get("author_name", "") or "",
        "candidate_publish_time": candidate.get("publish_time", "") or "",
        "candidate_click_x": int(candidate.get("click_x", 0) or 0),
        "candidate_click_y": int(candidate.get("click_y", 0) or 0),
        "video_blogger_name": video_info.get("blogger_name", "") or "",
        "video_channel_id": video_info.get("video_channel_id", "") or "",
        "video_channel_id_raw": video_info.get("video_channel_id_raw", "") or "",
        "video_channel_id_needs_review": bool(video_info.get("video_channel_id_needs_review", False)),
        "video_channel_id_ambiguous_positions_json": _json_dumps(
            video_info.get("video_channel_id_ambiguous_positions", [])
        ),
        "video_link": video_info.get("video_link", "") or "",
        "work_publish_time": video_info.get("publish_time", "") or "",
        "like_count": video_info.get("like_count", "") or "",
        "comment_count": video_info.get("comment_count", "") or "",
        "share_count": video_info.get("share_count", "") or "",
        "profile_name": profile_info.get("name", "") or "",
        "profile_account": profile_info.get("account", "") or "",
        "has_traffic_marker": bool(traffic_info.get("has_traffic_marker", False)),
        "traffic_marker_text": traffic_info.get("marker_text", "") or "",
        "target_blogger_name": traffic_info.get("target_blogger_name", "") or "",
        "target_video_channel_id": traffic_info.get("target_video_channel_id", "") or "",
        "target_video_channel_id_raw": traffic_info.get("target_video_channel_id_raw", "") or "",
        "target_video_channel_id_needs_review": bool(
            traffic_info.get("target_video_channel_id_needs_review", False)
        ),
        "target_video_channel_id_ambiguous_positions_json": _json_dumps(
            traffic_info.get("target_video_channel_id_ambiguous_positions", [])
        ),
        "company_full_name": traffic_info.get("company_full_name", "") or "",
        "company_verified_at": traffic_info.get("company_verified_at", "") or "",
        "recording_video_path": media_info.get("recording_video_path", "") or "",
        "recording_audio_path": media_info.get("recording_audio_path", "") or "",
        "recording_started_at": media_info.get("recording_started_at", "") or "",
        "recording_ended_at": media_info.get("recording_ended_at", "") or "",
        "recording_duration_seconds": int(media_info.get("recording_duration_seconds", 0) or 0),
        "has_audio": media_info.get("has_audio", None),
        "asr_text": media_info.get("asr_text", "") or "",
        "asr_json_path": media_info.get("asr_json_path", "") or "",
        "screenshots_json": _json_dumps(record.screenshots or []),
    }
