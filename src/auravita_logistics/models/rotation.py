from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class RotationRecord:
    quarter_index: int
    quarter_label: str
    rotation_date: date
    client_id: str
    outgoing_lot_id: str | None
    outgoing_collection: str | None
    incoming_lot_id: str
    incoming_collection: str
    purchased_new: bool
    forced_repeat: bool
    reason: str
    same_quarter_stock_reuse: bool = False


@dataclass
class QuarterSummary:
    quarter_index: int
    quarter_label: str
    active_clients: int
    signups: int
    churn: int
    purchases: int
    retired_lots: int
    final_stock: int
    estimated_cost: float
    ready_pool_start: int = 0
    reconditioning_inflow: int = 0
    bridge_pool_required: int = 0
