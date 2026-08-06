from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, timedelta
from enum import Enum
from pathlib import Path
from typing import Any
import json


QUARTER_START_MONTHS = {1: 1, 2: 4, 3: 7, 4: 10}


def quarter_parts(start_year: int, quarter_index: int) -> tuple[int, int]:
    if quarter_index < 1:
        raise ValueError("quarter_index must be >= 1")
    year_offset = (quarter_index - 1) // 4
    quarter = ((quarter_index - 1) % 4) + 1
    return start_year + year_offset, quarter


def quarter_label(start_year: int, quarter_index: int) -> str:
    year, quarter = quarter_parts(start_year, quarter_index)
    return f"{year}-T{quarter}"


def quarter_start_date(start_year: int, quarter_index: int) -> date:
    year, quarter = quarter_parts(start_year, quarter_index)
    return date(year, QUARTER_START_MONTHS[quarter], 1)


def rotation_date_for_slot(start_year: int, quarter_index: int, slot: int, gap_weeks: int) -> date:
    return quarter_start_date(start_year, quarter_index) + timedelta(weeks=slot * gap_weeks)


def parse_numeric_suffix(identifier: str) -> int:
    digits = "".join(character for character in identifier if character.isdigit())
    return int(digits) if digits else 0


def ensure_parent_directory(file_path: str | Path) -> None:
    Path(file_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return {key: serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize(item) for item in value]
    return value


def dump_json(payload: Any, output_path: str | Path) -> None:
    ensure_parent_directory(output_path)
    with Path(output_path).expanduser().resolve().open("w", encoding="utf-8") as handle:
        json.dump(serialize(payload), handle, indent=2, ensure_ascii=False)
