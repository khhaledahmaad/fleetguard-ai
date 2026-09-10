from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime

from fleetguard.contracts import AnomalyTruth, AssetMetadata, TelemetryEvent
from fleetguard.generator.cycle import (
    DEFAULT_OPERATING_CYCLE,
    OperatingCycle,
)
from fleetguard.generator.healthy import generate_healthy_batch


@dataclass(frozen=True)
class FleetBatch:
    assets: tuple[AssetMetadata, ...]
    events: tuple[TelemetryEvent, ...]
    truth: tuple[AnomalyTruth, ...]


def generate_fleet_assets(
    asset_count: int,
    seed: int,
    fleet_id: str = "FG-DEMO-01",
) -> tuple[AssetMetadata, ...]:
    if not 1 <= asset_count <= 9999:
        raise ValueError("asset_count must be between 1 and 9999")

    rng = random.Random(seed)
    assets: list[AssetMetadata] = []

    for asset_number in range(1, asset_count + 1):
        asset = AssetMetadata(
            asset_id=f"FG-WGN-{asset_number:04d}",
            fleet_id=fleet_id,
            commissioning_age_years=round(rng.uniform(1, 25), 2),
            nominal_load_tonnes=round(rng.uniform(45, 85), 2),
            bearing_baseline_temp_c=round(rng.uniform(38, 48), 3),
            vibration_baseline_g=round(rng.uniform(0.12, 0.25), 4),
            brake_pressure_baseline_bar=round(rng.uniform(4.8, 5.2), 3),
            generator_seed=rng.randrange(0, 2**31),
        )
        assets.append(asset)

    return tuple(assets)


def generate_healthy_fleet(
    assets: tuple[AssetMetadata, ...],
    start_time: datetime,
    periods: int,
    cycle: OperatingCycle = DEFAULT_OPERATING_CYCLE,
) -> FleetBatch:
    if not assets:
        raise ValueError("at least one asset is required")

    asset_ids = [asset.asset_id for asset in assets]

    if len(asset_ids) != len(set(asset_ids)):
        raise ValueError("asset IDs must be unique")

    events: list[TelemetryEvent] = []
    truth: list[AnomalyTruth] = []

    for asset in assets:
        asset_batch = generate_healthy_batch(
            asset=asset,
            start_time=start_time,
            periods=periods,
            cycle=cycle,
        )

        events.extend(asset_batch.events)
        truth.extend(asset_batch.truth)

    return FleetBatch(
        assets=assets,
        events=tuple(events),
        truth=tuple(truth),
    )
