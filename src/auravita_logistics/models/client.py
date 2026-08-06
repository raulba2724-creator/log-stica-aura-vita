from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class ClientState(str, Enum):
    ACTIVE = "ACTIVO"
    INACTIVE = "BAJA"


@dataclass
class ClientEvent:
    quarter_index: int
    quarter_label: str
    event_date: date
    event_type: str
    detail: str


@dataclass
class Client:
    id: str
    signup_date: date
    signup_quarter_index: int
    signup_quarter_label: str
    cohort_slot: int
    state: ClientState = ClientState.ACTIVE
    end_date: date | None = None
    end_quarter_index: int | None = None
    received_collections: list[str] = field(default_factory=list)
    received_lots: list[str] = field(default_factory=list)
    current_lot_id: str | None = None
    history: list[ClientEvent] = field(default_factory=list)

    def recent_collections(self, lookback_rotations: int) -> list[str]:
        return self.received_collections[-lookback_rotations:]
