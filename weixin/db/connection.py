"""Manual MySQL helpers for Weixin video evidence.

This module is intentionally not wired into the main collection flow yet.
Use it only when you want to test DB writes separately from the live workflow.
"""
from __future__ import annotations

import json
import os

import pymysql

from db.mapping import CREATE_TABLE_SQL, evidence_record_to_db_row
from db.models import EvidenceRecord


DB_HOST = os.environ.get("WEIXIN_DB_HOST", "localhost")
DB_PORT = int(os.environ.get("WEIXIN_DB_PORT", "3306"))
DB_USER = os.environ.get("WEIXIN_DB_USER", "root")
DB_PASSWORD = os.environ.get("WEIXIN_DB_PASSWORD", "1234")
DB_NAME = os.environ.get("WEIXIN_DB_NAME", "zscq")


def get_connection(database: str | None = None):
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=database,
        charset="utf8mb4",
        autocommit=True,
    )


def ensure_database_and_table() -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        conn.close()

    conn = get_connection(DB_NAME)
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
    finally:
        conn.close()


def insert_evidence_row(row: dict) -> int:
    ensure_database_and_table()
    columns = list(row.keys())
    sql = f"""
    INSERT INTO weixin_video_evidence (
        {", ".join(f"`{col}`" for col in columns)}
    ) VALUES (
        {", ".join(["%s"] * len(columns))}
    )
    """.strip()
    values = [row[col] for col in columns]

    conn = get_connection(DB_NAME)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, values)
            return int(cur.lastrowid)
    finally:
        conn.close()


def insert_evidence_record(record: EvidenceRecord) -> int:
    row = evidence_record_to_db_row(record)
    return insert_evidence_row(row)


def insert_record_dict(record_dict: dict) -> int:
    record = EvidenceRecord(
        platform=record_dict.get("platform", "weixin"),
        search_keyword=record_dict.get("search_keyword", ""),
        capture_time=record_dict.get("capture_time", ""),
        capture_timestamp=record_dict.get("capture_timestamp", ""),
        candidate=record_dict.get("candidate", {}) or {},
    )
    record.video_info.update(record_dict.get("video_info", {}) or {})
    record.profile_info.update(record_dict.get("profile_info", {}) or {})
    record.traffic_info.update(record_dict.get("traffic_info", {}) or {})
    record.media_info.update(record_dict.get("media_info", {}) or {})
    record.screenshots = list(record_dict.get("screenshots", []) or [])
    return insert_evidence_record(record)


def insert_json_file(json_path: str) -> int:
    with open(json_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return insert_record_dict(data)
