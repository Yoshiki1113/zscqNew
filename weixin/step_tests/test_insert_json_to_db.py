"""Manual DB insert test for one saved Weixin evidence JSON file."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db import insert_json_file  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python test_insert_json_to_db.py <json_path>")
        return
    json_path = sys.argv[1]
    print(f"[db] importing json: {json_path}")
    row_id = insert_json_file(json_path)
    print(f"[db] inserted row id: {row_id}")


if __name__ == "__main__":
    main()
