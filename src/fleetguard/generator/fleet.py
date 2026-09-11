from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime

from fleetguard.contracts import (
    AnomalyTruth,
    AssetMetadata,
    BogieMetadata,
    BogiePosition,
    TelemetryEvent,
    WheelMetadata,
    WheelsetMetadata,
    WheelsetPosition,
)
from fleetguard.generator.cycle import (
    DEFAULT_OPERATING_CYCLE,
    OperatingCycle,
)
from fleetguard.generator.healthy import generate_healthy_batch, generate_healthy_journey
from fleetguard.generator.route import JourneyPlan


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
        asset_id = f"FG-WGN-{asset_number:04d}"
        handbrake_position = BogiePosition(rng.choice(("a", "b")))
        bogies_list: list[BogieMetadata] = []
        for position in (BogiePosition.A, BogiePosition.B):
            wheelsets: list[WheelsetMetadata] = []
            for wheelset_number, wheelset_position in enumerate(
                (WheelsetPosition.LEADING, WheelsetPosition.TRAILING), start=1
            ):
                left_diameter = rng.uniform(900, 960)
                wheelsets.append(
                    WheelsetMetadata(
                        wheelset_id=(f"{asset_id}-BG{position.value.upper()}-WS{wheelset_number}"),
                        position=wheelset_position,
                        left_wheel=WheelMetadata(side="left", diameter_mm=round(left_diameter, 2)),
                        right_wheel=WheelMetadata(
                            side="right",
                            diameter_mm=round(left_diameter + rng.uniform(-0.8, 0.8), 2),
                        ),
                    )
                )
            bogies_list.append(
                BogieMetadata(
                    bogie_id=f"{asset_id}-BG{position.value.upper()}",
                    position=position,
                    handbrake_equipped=position == handbrake_position,
                    wheelsets=tuple(wheelsets),
                )
            )
        bogies = tuple(bogies_list)
        asset = AssetMetadata(
            asset_id=asset_id,
            fleet_id=fleet_id,
            commissioning_age_years=round(rng.uniform(1, 25), 2),
            nominal_load_tonnes=round(rng.uniform(45, 85), 2),
            bearing_baseline_temp_c=round(rng.uniform(38, 48), 3),
            vibration_baseline_g=round(rng.uniform(0.12, 0.25), 4),
            brake_pressure_baseline_bar=round(rng.uniform(4.8, 5.2), 3),
            bogies=bogies,
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


def generate_healthy_journey_fleet(
    assets: tuple[AssetMetadata, ...],
    start_time: datetime,
    journey: JourneyPlan,
) -> FleetBatch:
    if not assets:
        raise ValueError("at least one asset is required")
    if len({asset.asset_id for asset in assets}) != len(assets):
        raise ValueError("asset IDs must be unique")

    events: list[TelemetryEvent] = []
    truth: list[AnomalyTruth] = []
    for asset in assets:
        batch = generate_healthy_journey(asset, start_time, journey)
        events.extend(batch.events)
        truth.extend(batch.truth)
    return FleetBatch(assets=assets, events=tuple(events), truth=tuple(truth))
