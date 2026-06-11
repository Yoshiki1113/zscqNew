"""Database schema and row mapping for Weixin video evidence."""
from __future__ import annotations

from models import EvidenceRecord


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS weixin_video_evidence (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    platform VARCHAR(32) NOT NULL DEFAULT 'weixin',
    search_keyword VARCHAR(255) NOT NULL,
    captured_at DATETIME NOT NULL,

    candidate_fingerprint VARCHAR(64) NOT NULL,
    candidate_title VARCHAR(500) NOT NULL DEFAULT '',
    candidate_author_name VARCHAR(255) NOT NULL DEFAULT '',
    candidate_publish_time VARCHAR(255) NOT NULL DEFAULT '',

    video_blogger_name VARCHAR(255) NOT NULL DEFAULT '',
    video_channel_id VARCHAR(128) NOT NULL DEFAULT '',
    video_channel_id_raw VARCHAR(255) NOT NULL DEFAULT '',
    video_channel_id_needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    video_link VARCHAR(1000) NOT NULL DEFAULT '',
    work_publish_time VARCHAR(255) NOT NULL DEFAULT '',
    like_count VARCHAR(64) NOT NULL DEFAULT '',
    comment_count VARCHAR(64) NOT NULL DEFAULT '',
    share_count VARCHAR(64) NOT NULL DEFAULT '',

    has_traffic_marker BOOLEAN NOT NULL DEFAULT FALSE,
    traffic_marker_text VARCHAR(255) NOT NULL DEFAULT '',
    target_blogger_name VARCHAR(255) NOT NULL DEFAULT '',
    target_video_channel_id VARCHAR(128) NOT NULL DEFAULT '',
    target_video_channel_id_raw VARCHAR(255) NOT NULL DEFAULT '',
    target_video_channel_id_needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    company_full_name VARCHAR(255) NOT NULL DEFAULT '',
    company_verified_at VARCHAR(255) NOT NULL DEFAULT '',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""".strip()


def evidence_record_to_db_row(record: EvidenceRecord) -> dict:
    """Flatten one EvidenceRecord into a single-row DB payload."""
    candidate = record.candidate or {}
    video_info = record.video_info or {}
    traffic_info = record.traffic_info or {}

    return {
        "platform": record.platform or "weixin",
        "search_keyword": record.search_keyword or "",
        "captured_at": record.capture_time or record.capture_timestamp or "",
        "candidate_fingerprint": candidate.get("fingerprint", "") or "",
        "candidate_title": candidate.get("title_text", "") or candidate.get("hit_text", "") or "",
        "candidate_author_name": candidate.get("author_name", "") or "",
        "candidate_publish_time": candidate.get("publish_time", "") or "",
        "video_blogger_name": video_info.get("blogger_name", "") or "",
        "video_channel_id": video_info.get("video_channel_id", "") or "",
        "video_channel_id_raw": video_info.get("video_channel_id_raw", "") or "",
        "video_channel_id_needs_review": bool(video_info.get("video_channel_id_needs_review", False)),
        "video_link": video_info.get("video_link", "") or "",
        "work_publish_time": video_info.get("publish_time", "") or "",
        "like_count": video_info.get("like_count", "") or "",
        "comment_count": video_info.get("comment_count", "") or "",
        "share_count": video_info.get("share_count", "") or "",
        "has_traffic_marker": bool(traffic_info.get("has_traffic_marker", False)),
        "traffic_marker_text": traffic_info.get("marker_text", "") or "",
        "target_blogger_name": traffic_info.get("target_blogger_name", "") or "",
        "target_video_channel_id": traffic_info.get("target_video_channel_id", "") or "",
        "target_video_channel_id_raw": traffic_info.get("target_video_channel_id_raw", "") or "",
        "target_video_channel_id_needs_review": bool(traffic_info.get("target_video_channel_id_needs_review", False)),
        "company_full_name": traffic_info.get("company_full_name", "") or "",
        "company_verified_at": traffic_info.get("company_verified_at", "") or "",
    }
