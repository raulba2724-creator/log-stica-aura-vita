from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class LotState(str, Enum):
    STOCK = "STOCK"
    CLIENT = "CLIENTE"
    RETIRED = "RETIRADO"
    REPAIR = "REPARACION"


@dataclass
class LotMovement:
    quarter_index: int
    quarter_label: str
    event_date: date
    event_type: str
    location: str
    client_id: str | None = None
    note: str = ""


@dataclass
class Lot:
    id: str
    collection_name: str
    purchase_date: date
    purchase_quarter_index: int
    purchase_quarter_label: str
    state: LotState
    location: str
    current_client_id: str | None = None
    usage_count: int = 0
    client_history: list[str] = field(default_factory=list)
    movement_history: list[LotMovement] = field(default_factory=list)
    last_return_date: date | None = None
    last_return_quarter_index: int | None = None
    retired_date: date | None = None
    retired_quarter_index: int | None = None
    retirement_reason: str | None = None
    stock_since_quarter_index: int = 1
