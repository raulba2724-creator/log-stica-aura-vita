from __future__ import annotations

from dataclasses import dataclass
from random import Random

from auravita_logistics.assignment_engine import AssignmentEngine
from auravita_logistics.catalog import CollectionCatalog
from auravita_logistics.config import SimulationConfig
from auravita_logistics.inventory import InventoryManager
from auravita_logistics.models import Client, QuarterSummary, RotationRecord
from auravita_logistics.rotation_engine import RotationEngine


@dataclass
class SimulationResult:
    config: SimulationConfig
    clients: dict[str, Client]
    inventory: InventoryManager
    catalog: CollectionCatalog
    quarter_summaries: list[QuarterSummary]
    rotation_records: list[RotationRecord]
    total_estimated_cost: float


class LogisticsSimulation:
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.catalog = CollectionCatalog(config)
        self.inventory = InventoryManager(config)
        self.clients: dict[str, Client] = {}
        self.assignment_engine = AssignmentEngine(config, self.catalog, self.inventory)
        self.rotation_engine = RotationEngine(
            config=config,
            catalog=self.catalog,
            inventory=self.inventory,
            assignment_engine=self.assignment_engine,
            clients=self.clients,
            rng=Random(config.churn.random_seed),
        )

    def run(self) -> SimulationResult:
        self.rotation_engine.preload_inventory()
        quarter_summaries: list[QuarterSummary] = []
        for quarter_index, signups in enumerate(self.config.quarterly_signups, start=1):
            quarter_summaries.append(self.rotation_engine.process_quarter(quarter_index, signups))

        return SimulationResult(
            config=self.config,
            clients=self.clients,
            inventory=self.inventory,
            catalog=self.catalog,
            quarter_summaries=quarter_summaries,
            rotation_records=list(self.rotation_engine.rotation_records),
            total_estimated_cost=self.rotation_engine.purchase_cost_accumulator,
        )
