from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime

from fleetguard.contracts import (
    STANDARD_SAMPLING_INTERVAL_SECONDS,
    AnomalyTruth,
    AssetMetadata,
    AxleMetadata,
    AxlePosition,
    BogieMetadata,
    TelemetryEvent,
    WheelMetadata,
    WheelSide,
)
from fleetguard.generator.anomalies import (
    AnomalyScenario,
    inject_anomaly_scenarios,
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
        handbrake_bogie_id = rng.choice((1, 2))
        bogies_list: list[BogieMetadata] = []
        for bogie_id in (1, 2):
            axles: list[AxleMetadata] = []
            for axle_position in (AxlePosition.OUTER, AxlePosition.INNER):
                left_diameter = rng.uniform(900, 960)
                axles.append(
                    AxleMetadata(
                        axle_position=axle_position,
                        wheels=(
                            WheelMetadata(
                                wheel_side=WheelSide.LEFT,
                                diameter_mm=round(left_diameter, 2),
                            ),
                            WheelMetadata(
                                wheel_side=WheelSide.RIGHT,
                                diameter_mm=round(left_diameter + rng.uniform(-0.8, 0.8), 2),
                            ),
                        ),
                    )
                )
            bogies_list.append(
                BogieMetadata(
                    bogie_id=bogie_id,
                    handbrake_equipped=bogie_id == handbrake_bogie_id,
                    axles=tuple(axles),
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
    sampling_interval_seconds: int = 60,
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
            sampling_interval_seconds=sampling_interval_seconds,
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
    sampling_interval_seconds: int = STANDARD_SAMPLING_INTERVAL_SECONDS,
) -> FleetBatch:
    if not assets:
        raise ValueError("at least one asset is required")
    if len({asset.asset_id for asset in assets}) != len(assets):
        raise ValueError("asset IDs must be unique")

    events: list[TelemetryEvent] = []
    truth: list[AnomalyTruth] = []
    for asset in assets:
        batch = generate_healthy_journey(
            asset,
            start_time,
            journey,
            sampling_interval_seconds=sampling_interval_seconds,
        )
        events.extend(batch.events)
        truth.extend(batch.truth)
    return FleetBatch(assets=assets, events=tuple(events), truth=tuple(truth))


def inject_fleet_anomaly_scenarios(
    fleet_batch: FleetBatch,
    scenarios: tuple[AnomalyScenario, ...],
) -> FleetBatch:
    injected_batch = inject_anomaly_scenarios(
        events=fleet_batch.events,
        truth=fleet_batch.truth,
        scenarios=scenarios,
    )

    return FleetBatch(
        assets=fleet_batch.assets,
        events=injected_batch.events,
        truth=injected_batch.truth,
    )
