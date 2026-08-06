from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class CollectionEvent:
    quarter_index: int
    quarter_label: str
    event_date: date
    event_type: str
    detail: str


@dataclass
class Collection:
    name: str
    launch_quarter_index: int
    launch_quarter_label: str
    lifespan_quarters: int
    lot_ids: list[str] = field(default_factory=list)
    assignment_count: int = 0
    retired_lot_ids: list[str] = field(default_factory=list)
    history: list[CollectionEvent] = field(default_factory=list)

    @property
    def retirement_quarter_index(self) -> int:
        return self.launch_quarter_index + self.lifespan_quarters

    def is_active_in(self, quarter_index: int) -> bool:
        return self.launch_quarter_index <= quarter_index < self.retirement_quarter_index
