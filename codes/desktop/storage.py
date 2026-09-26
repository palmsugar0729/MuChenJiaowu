"""JSON 文件读写，依赖 models。"""

import json
from pathlib import Path

from models import MonthData, Record

# 费率持久化路径，与 autosave 共用目录
_RATES_DIR = Path.home() / ".salary-counter"
_RATES_FILE = _RATES_DIR / "rates.json"


def _record_to_dict(r: Record) -> dict:
    return {
        "date": r.date.isoformat(),
        "start_time": r.start_time.isoformat(),
        "hours": r.hours,
        "class_type": r.class_type,
        "class_name": r.class_name,
        "note": r.note,
    }


def _record_from_dict(d: dict) -> Record:
    from datetime import date, time

    return Record(
        date=date.fromisoformat(d["date"]),
        start_time=time.fromisoformat(d["start_time"]),
        hours=d["hours"],
        class_type=d["class_type"],
        class_name=d.get("class_name", ""),
        note=d.get("note", ""),
    )


def save(filepath: str | Path, data: MonthData) -> None:
    payload = {
        "teacher_name": data.teacher_name,
        "records": [_record_to_dict(r) for r in data.records],
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load(filepath: str | Path) -> MonthData:
    with open(filepath, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return MonthData(
        teacher_name=payload.get("teacher_name", ""),
        records=[_record_from_dict(d) for d in payload.get("records", [])],
    )


# ── 费率持久化 ──────────────────────────────────────


def load_rates() -> dict | None:
    """读取持久化的费率配置，文件不存在或损坏返回 None。"""
    if not _RATES_FILE.exists():
        return None
    try:
        with open(_RATES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_rates(rates: dict[str, float]) -> None:
    """将费率配置写入 JSON 文件。"""
    _RATES_DIR.mkdir(parents=True, exist_ok=True)
    with open(_RATES_FILE, "w", encoding="utf-8") as f:
        json.dump(rates, f, ensure_ascii=False, indent=2)
