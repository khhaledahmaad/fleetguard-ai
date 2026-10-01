"""Build balanced coverage cohorts without assigning labels by wagon number."""

from __future__ import annotations

import hashlib
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import to_jsonable_python

from fleetguard.contracts import AnomalySeverity, AnomalyType, AssetMetadata, TelemetryEvent
from fleetguard.generator.anomalies import AnomalyScenario, ComponentTarget
from fleetguard.generator.extended_anomalies import AXLE_TYPES
from fleetguard.generator.fleet import generate_fleet_assets
from fleetguard.generator.route import DEFAULT_ROUTES, JourneyPlan, create_journey_plan

SPLITS = ("train", "validation", "test")
VARIANTS = tuple(
    t.value
    for t in AnomalyType
    if t not in (AnomalyType.NONE, AnomalyType.CONTROLLER_SUPPLY_FAILURE)
) + ("controller_supply_failure:persistent", "controller_supply_failure:bounded")
PLAN_VERSION = "1.0"


class PortfolioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    start_time: datetime
    sampling_interval_seconds: Literal[1, 10, 60] = 10
    replicates: int = Field(default=1, ge=1, le=20)
    healthy_per_split: int = Field(default=3, ge=1, le=100)

    @field_validator("start_time")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("start_time must include a UTC offset")
        return value


def derived_seed(seed: int, namespace: str) -> int:
    """Stable independent streams; never use Python's process-randomised hash()."""
    return int.from_bytes(hashlib.sha256(f"{seed}:{namespace}".encode()).digest()[:4], "big")


@dataclass(frozen=True)
class Assignment:
    split: str
    asset: AssetMetadata
    variant: str
    journey_seed: int
    scenario_seed: int
    journey_number: int

    @property
    def relative_directory(self) -> str:
        return f"runs/{self.split}/{self.asset.asset_id}"


def plan_assignments(config: PortfolioConfig) -> tuple[Assignment, ...]:
    per_split = len(VARIANTS) * config.replicates + config.healthy_per_split
    assets = list(generate_fleet_assets(3 * per_split, config.seed))
    random.Random(derived_seed(config.seed, "splits")).shuffle(assets)
    assignments = []
    for index, split in enumerate(SPLITS):
        variants = list(VARIANTS) * config.replicates + ["healthy"] * config.healthy_per_split
        random.Random(derived_seed(config.seed, f"assignment:{split}")).shuffle(variants)
        for asset, variant in zip(
            assets[index * per_split : (index + 1) * per_split], variants, strict=True
        ):
            assignments.append(
                Assignment(
                    split,
                    asset,
                    variant,
                    derived_seed(config.seed, f"journey:{asset.asset_id}"),
                    derived_seed(config.seed, f"scenario:{asset.asset_id}"),
                    int(asset.asset_id[-4:]),
                )
            )
    return tuple(assignments)


def plan_journey(assignment: Assignment, config: PortfolioConfig) -> JourneyPlan:
    route = random.Random(assignment.journey_seed).choice(DEFAULT_ROUTES)
    return create_journey_plan(
        assignment.journey_seed,
        route=route,
        service_date=config.start_time.date(),
        journey_number=assignment.journey_number,
    )


def serialise_scenario(scenario: AnomalyScenario | None) -> dict | None:
    return None if scenario is None else to_jsonable_python(asdict(scenario))


def choose_scenario(
    assignment: Assignment, events: tuple[TelemetryEvent, ...]
) -> AnomalyScenario | None:
    """Randomise only over eligible components and sampled operating contexts."""
    if assignment.variant == "healthy":
        return None
    rng = random.Random(assignment.scenario_seed)
    kind = AnomalyType(assignment.variant.split(":")[0])
    step = events[0].sampling_interval_seconds
    horizon = events[-1].event_time + timedelta(seconds=step)
    # Leave room for progressive development and for bounded recovery.
    candidates = [e for e in events if e.event_time < horizon - timedelta(minutes=15)]
    kwargs = {}
    target = ComponentTarget(assignment.asset.asset_id)
    if kind in AXLE_TYPES or kind in (AnomalyType.BEARING_DEGRADATION, AnomalyType.SENSOR_FAULT):
        bogie = rng.choice(assignment.asset.bogies)
        axle = rng.choice(bogie.axles)
        wheel = rng.choice(axle.wheels) if kind not in AXLE_TYPES else None
        target = ComponentTarget(
            assignment.asset.asset_id,
            bogie.bogie_id,
            axle.axle_position,
            wheel.wheel_side if wheel else None,
            "bearing_temp_c" if kind == AnomalyType.SENSOR_FAULT else None,
        )
    elif kind == AnomalyType.PRESSURE_TRANSDUCER_FAILURE:
        signal, bogie_id = rng.choice(
            [
                ("brake_pipe_pressure_bar", None),
                ("auxiliary_reservoir_pressure_bar", None),
                ("secondary_reservoir_pressure_bar", None),
                ("brake_cylinder_pressure_bar", 1),
                ("brake_cylinder_pressure_bar", 2),
            ]
        )
        target = ComponentTarget(assignment.asset.asset_id, bogie_id=bogie_id, signal_name=signal)
    elif kind == AnomalyType.BRAKE_PRESSURE_LEAK:
        target = ComponentTarget(assignment.asset.asset_id, signal_name="brake_pipe_pressure_bar")
    elif kind == AnomalyType.BRAKE_RELEASE_FAILURE:
        target = ComponentTarget(assignment.asset.asset_id, bogie_id=rng.choice((1, 2)))

    if kind == AnomalyType.WHEEL_SLIDE:
        candidates = [e for e in candidates if e.brake_demand == "apply" and e.speed_kph > 5]
    elif kind == AnomalyType.BRAKE_RELEASE_FAILURE:
        transitions = {
            b.event_time
            for a, b in zip(events, events[1:], strict=False)
            if a.brake_demand == "apply" and b.brake_demand == "release"
        }
        candidates = [e for e in candidates if e.event_time in transitions]
    elif kind == AnomalyType.PREMATURE_BATTERY_DEPLETION:
        # Require enough stationary time to show warning and cutoff in this short journey.
        candidates = [
            e
            for e in candidates
            if e.journey_phase == "origin_dwell"
            and e.event_time < events[0].event_time + timedelta(minutes=5)
        ]
        kwargs["battery_extra_drain_v_per_hour"] = rng.uniform(6, 12)
    elif kind in (
        AnomalyType.LOCKED_AXLE,
        AnomalyType.SUSPECTED_WHEEL_FLAT,
        AnomalyType.UNDEMANDED_BRAKE_APPLICATION,
    ):
        candidates = [e for e in candidates if e.speed_kph > 10 and e.brake_demand == "release"]
    else:
        # Preserve at least a short healthy baseline before any other fault.
        candidates = [
            e for e in candidates if e.event_time >= events[0].event_time + timedelta(minutes=5)
        ]
    if not candidates:
        raise ValueError(f"no eligible onset for {assignment.asset.asset_id}: {assignment.variant}")
    onset = rng.choice(candidates).event_time
    duration = timedelta(minutes=rng.randint(3, 10))
    if kind == AnomalyType.WHEEL_SLIDE:
        duration = timedelta(seconds=rng.choice((60, 90, 120)))
    if kind in (AnomalyType.AXLE_SPEED_GENERATOR_FAILURE, AnomalyType.PRESSURE_TRANSDUCER_FAILURE):
        kwargs["failure_encoding"] = rng.choice(("missing", "invalid"))
    if kind == AnomalyType.CONTROLLER_SUPPLY_FAILURE:
        mode = assignment.variant.split(":")[1]
        kwargs["outage_mode"] = mode
        if mode == "bounded":
            kwargs["recovery_time"] = onset + duration + timedelta(minutes=rng.randint(2, 4))
    return AnomalyScenario(
        scenario_id=f"FG-PORT-{assignment.asset.asset_id}",
        anomaly_type=kind,
        target=target,
        start_time=onset,
        end_time=onset + duration,
        peak_severity=rng.choice(
            (AnomalySeverity.LOW, AnomalySeverity.MEDIUM, AnomalySeverity.HIGH)
        ),
        **kwargs,
    )
