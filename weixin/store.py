"""微信视频号监测 — 存储层：保存结果到 JSON"""
import json, os
from datetime import datetime

from main import JSONS_DIR
from models import EvidenceRecord


def save_record(record: EvidenceRecord):
    """保存一条完整取证记录到 JSON 文件"""
    os.makedirs(JSONS_DIR, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fp = (record.candidate or {}).get("fingerprint", "unknown")[:12]
    path = os.path.join(JSONS_DIR, f"result_{ts}_{fp}.json")

    data = record.to_dict()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 追加到 results.jsonl
    lpath = os.path.join(JSONS_DIR, "results.jsonl")
    with open(lpath, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")

    print(f"[存储] 已保存: {path}")
    return path


def load_seen(path=None):
    """加载已有指纹集合，用于去重"""
    if path is None:
        path = os.path.join(JSONS_DIR, "results.jsonl")
    seen = set()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    fp = d.get("candidate", {}).get("fingerprint", "")
                    if fp:
                        seen.add(fp)
                except json.JSONDecodeError:
                    continue
    print(f"[存储] 已加载 {len(seen)} 条去重指纹")
    return seen
