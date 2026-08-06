from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Campaign:
    id: str
    name: str
    start_quarter_index: int
    end_quarter_index: int | None = None
    promoted_collections: list[str] = field(default_factory=list)
