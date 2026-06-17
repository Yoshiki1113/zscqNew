"""Fix DB schema and batch import JSON evidence records."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db.connection import get_connection, DB_NAME, ensure_database_and_table
from db import insert_json_file
from db.mapping import CREATE_TABLE_SQL


def _parse_columns(sql: str) -> list[tuple[str, str]]:
    """Parse (column_name, column_def) from CREATE_TABLE_SQL."""
    cols = []
    for line in sql.strip().splitlines():
        line = line.strip().rstrip(",")
        if not line or line.startswith("(") or line.startswith(")") or line.startswith("CREATE") or line.startswith("id") or line.startswith("created_at") or line.startswith("updated_at"):
            continue
        m = re.match(r"`?(\w+)`?\s+(.+)", line)
        if m:
            cols.append((m.group(1), m.group(2)))
    return cols


def fix_schema():
    """Add missing columns to existing table."""
    ensure_database_and_table()
    conn = get_connection(DB_NAME)
    try:
        with conn.cursor() as cur:
            cur.execute("DESCRIBE weixin_video_evidence")
            existing = {row[0] for row in cur.fetchall()}
            print(f"[db] existing columns: {len(existing)}")

            columns = _parse_columns(CREATE_TABLE_SQL)
            added = 0
            for col, dtype in columns:
                if col not in existing:
                    try:
                        cur.execute(f"ALTER TABLE weixin_video_evidence ADD COLUMN `{col}` {dtype}")
                        print(f"  [db] added: {col}")
                        added += 1
                    except Exception as e:
                        print(f"  [db] skip {col}: {e}")
                else:
                    print(f"  [db] exists: {col}")
            print(f"[db] total added: {added}")
    finally:
        conn.close()


def batch_import():
    jsons_dir = ROOT / "core" / "jsons"
    json_files = sorted(jsons_dir.glob("*.json"))
    print(f"\n[db] found {len(json_files)} JSON files in {jsons_dir}")

    processed = 0
    failed = 0
    for j in json_files:
        try:
            row_id = insert_json_file(str(j))
            print(f"  [ok] {j.name} => row_id={row_id}")
            processed += 1
            time.sleep(0.05)
        except Exception as e:
            print(f"  [fail] {j.name}: {e}")
            failed += 1

    print(f"\n[db] Done: processed={processed}, failed={failed}")


if __name__ == "__main__":
    fix_schema()
    batch_import()

