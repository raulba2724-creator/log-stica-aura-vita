from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


@dataclass(frozen=True)
class NamingConfig:
    client_prefix: str = "C"
    lot_prefix: str = "L"
    client_pad: int = 5
    lot_pad: int = 5


@dataclass(frozen=True)
class AssignmentConfig:
    lookback_rotations: int = 4
    allow_repeat_when_no_alternative: bool = True
    new_lot_collection_strategy: str = "oldest_active_then_name"


@dataclass(frozen=True)
class ChurnConfig:
    starts_from_quarter: int = 3
    min_per_quarter: int = 1
    max_per_quarter: int = 3
    random_seed: int = 42

    def draw_count(self, active_clients: int, quarter_index: int, rng: Any) -> int:
        if quarter_index < self.starts_from_quarter or active_clients <= 0:
            return 0
        floor = min(self.min_per_quarter, active_clients)
        ceiling = min(self.max_per_quarter, active_clients)
        return rng.randint(floor, ceiling)


@dataclass(frozen=True)
class LogisticsConfig:
    warehouse_location: str = "ALMACEN"
    retired_location: str = "RETIRADO"
    repair_location: str = "REPARACION"
    cohort_gap_weeks: int = 2


@dataclass(frozen=True)
class SimulationConfig:
    simulation_name: str
    start_year: int
    simulation_quarters: int
    quarterly_signups: list[int]
    initial_collections: list[str]
    future_collections: list[str]
    collections_per_year: int
    collection_lifespan_quarters: int
    default_purchase_cost: float
    purchase_cost_by_collection: dict[str, float] = field(default_factory=dict)
    preloaded_stock_by_collection: dict[str, int] = field(default_factory=dict)
    churn: ChurnConfig = field(default_factory=ChurnConfig)
    naming: NamingConfig = field(default_factory=NamingConfig)
    assignment: AssignmentConfig = field(default_factory=AssignmentConfig)
    logistics: LogisticsConfig = field(default_factory=LogisticsConfig)

    @classmethod
    def from_dict(cls, raw_data: dict[str, Any]) -> "SimulationConfig":
        config = cls(
            simulation_name=raw_data["simulation_name"],
            start_year=raw_data["start_year"],
            simulation_quarters=raw_data["simulation_quarters"],
            quarterly_signups=list(raw_data["quarterly_signups"]),
            initial_collections=list(raw_data["initial_collections"]),
            future_collections=list(raw_data.get("future_collections", [])),
            collections_per_year=raw_data.get("collections_per_year", 2),
            collection_lifespan_quarters=raw_data.get("collection_lifespan_quarters", 12),
            default_purchase_cost=float(raw_data.get("default_purchase_cost", 0.0)),
            purchase_cost_by_collection={
                name: float(cost) for name, cost in raw_data.get("purchase_cost_by_collection", {}).items()
            },
            preloaded_stock_by_collection={
                name: int(quantity) for name, quantity in raw_data.get("preloaded_stock_by_collection", {}).items()
            },
            churn=ChurnConfig(**raw_data.get("churn", {})),
            naming=NamingConfig(**raw_data.get("naming", {})),
            assignment=AssignmentConfig(**raw_data.get("assignment", {})),
            logistics=LogisticsConfig(**raw_data.get("logistics", {})),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.simulation_quarters < 1:
            raise ValueError("simulation_quarters must be >= 1")
        if len(self.quarterly_signups) != self.simulation_quarters:
            raise ValueError("quarterly_signups length must match simulation_quarters")
        if len(self.initial_collections) != 4:
            raise ValueError("initial_collections must start with exactly 4 collections")
        if self.collections_per_year < 1:
            raise ValueError("collections_per_year must be >= 1")
        if self.collection_lifespan_quarters < 1:
            raise ValueError("collection_lifespan_quarters must be >= 1")
        if self.assignment.lookback_rotations < 1:
            raise ValueError("lookback_rotations must be >= 1")
        if self.churn.min_per_quarter > self.churn.max_per_quarter:
            raise ValueError("churn min_per_quarter cannot be greater than max_per_quarter")

    def active_purchase_cost(self, collection_name: str) -> float:
        return self.purchase_cost_by_collection.get(collection_name, self.default_purchase_cost)


def load_config(config_path: str | Path) -> SimulationConfig:
    with Path(config_path).expanduser().resolve().open("r", encoding="utf-8") as handle:
        return SimulationConfig.from_dict(json.load(handle))
