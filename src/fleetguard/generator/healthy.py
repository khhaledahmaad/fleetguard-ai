from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from fleetguard.contracts import (
    AnomalySeverity,
    AnomalyTruth,
    AnomalyType,
    AssetMetadata,
    OperatingState,
    TelemetryEvent,
)
from fleetguard.generator.cycle import (
    DEFAULT_OPERATING_CYCLE,
    OperatingCycle,
)


@dataclass(frozen=True)
class HealthyBatch:
    events: tuple[TelemetryEvent, ...]
    truth: tuple[AnomalyTruth, ...]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def _operating_state_and_speed(
    minute_index: int,
    rng: random.Random,
    cycle: OperatingCycle,
) -> tuple[OperatingState, float, float]:
    operating_state, phase_progress = cycle.state_at(minute_index)

    if operating_state == OperatingState.STATIONARY:
        return operating_state, 0.0, phase_progress

    if operating_state == OperatingState.MOVING:
        speed = 55 + 20 * math.sin(math.pi * phase_progress)
        speed += rng.normalvariate(0, 1.5)

        return (
            operating_state,
            _clamp(speed, 1, 120),
            phase_progress,
        )

    speed = 70 * (1 - phase_progress)
    speed += rng.normalvariate(0, 1)

    return (
        operating_state,
        _clamp(speed, 0, 120),
        phase_progress,
    )


def _ambient_temperature(event_time: datetime) -> float:
    minute_of_day = event_time.hour * 60 + event_time.minute
    daily_phase = 2 * math.pi * (minute_of_day - 360) / 1440

    return 14 + 6 * math.sin(daily_phase)


def generate_healthy_batch(
    asset: AssetMetadata,
    start_time: datetime,
    periods: int,
    seed: int | None = None,
    cycle: OperatingCycle = DEFAULT_OPERATING_CYCLE,
) -> HealthyBatch:
    if start_time.tzinfo is None or start_time.utcoffset() is None:
        raise ValueError("start_time must include timezone information")

    if periods < 1:
        raise ValueError("periods must be at least 1")

    effective_seed = asset.generator_seed if seed is None else seed
    rng = random.Random(effective_seed)

    events: list[TelemetryEvent] = []
    truth: list[AnomalyTruth] = []

    bearing_temperature = asset.bearing_baseline_temp_c - 8

    for minute_index in range(periods):
        event_time = start_time + timedelta(minutes=minute_index)
        operating_state, speed_kph, phase_progress = _operating_state_and_speed(
            minute_index,
            rng,
            cycle,
        )

        ambient_temp_c = _ambient_temperature(event_time)
        ambient_temp_c += rng.normalvariate(0, 0.15)

        axle_load_tonnes = asset.nominal_load_tonnes / 4
        axle_load_tonnes += rng.normalvariate(0, 0.2)
        axle_load_tonnes = _clamp(axle_load_tonnes, 10, 25)

        if operating_state == OperatingState.STATIONARY:
            target_bearing_temperature = max(
                ambient_temp_c + 5,
                asset.bearing_baseline_temp_c - 10,
            )
        else:
            target_bearing_temperature = (
                asset.bearing_baseline_temp_c + 0.12 * speed_kph + 0.08 * (axle_load_tonnes - 15)
            )

        bearing_temperature += 0.12 * (target_bearing_temperature - bearing_temperature)
        bearing_temperature += rng.normalvariate(0, 0.08)
        bearing_temperature = _clamp(bearing_temperature, -40, 150)

        vibration_rms_g = (
            asset.vibration_baseline_g
            + 0.004 * speed_kph
            + 0.01 * (axle_load_tonnes - 15)
            + rng.normalvariate(0, 0.01)
        )
        vibration_rms_g = _clamp(vibration_rms_g, 0, 10)

        if operating_state == OperatingState.BRAKING:
            braking_progress = braking_progress = phase_progress

            brake_pipe_pressure_bar = (
                asset.brake_pressure_baseline_bar
                - 1.7 * braking_progress
                + rng.normalvariate(0, 0.02)
            )
            brake_cylinder_pressure_bar = 0.1 + 3 * braking_progress + rng.normalvariate(0, 0.02)
        else:
            brake_pipe_pressure_bar = asset.brake_pressure_baseline_bar + rng.normalvariate(0, 0.02)
            brake_cylinder_pressure_bar = max(
                0,
                0.05 + rng.normalvariate(0, 0.01),
            )

        battery_voltage_v = 25.2 - 0.0005 * minute_index + rng.normalvariate(0, 0.015)

        event_id = uuid5(
            NAMESPACE_URL,
            (f"fleetguard:{asset.asset_id}:{event_time.isoformat()}:{effective_seed}"),
        )

        event = TelemetryEvent(
            event_id=event_id,
            asset_id=asset.asset_id,
            event_time=event_time,
            generated_at=event_time,
            operating_state=operating_state,
            speed_kph=round(speed_kph, 3),
            ambient_temp_c=round(ambient_temp_c, 3),
            axle_load_tonnes=round(axle_load_tonnes, 3),
            bearing_temp_c=round(bearing_temperature, 3),
            vibration_rms_g=round(vibration_rms_g, 4),
            brake_pipe_pressure_bar=round(
                _clamp(brake_pipe_pressure_bar, 0, 6),
                3,
            ),
            brake_cylinder_pressure_bar=round(
                _clamp(brake_cylinder_pressure_bar, 0, 5),
                3,
            ),
            battery_voltage_v=round(
                _clamp(battery_voltage_v, 0, 32),
                3,
            ),
        )

        healthy_truth = AnomalyTruth(
            event_id=event.event_id,
            asset_id=event.asset_id,
            is_anomaly=False,
            anomaly_type=AnomalyType.NONE,
            anomaly_severity=AnomalySeverity.NONE,
            affected_signal=None,
            anomaly_start_time=None,
            anomaly_progress=0.0,
        )

        events.append(event)
        truth.append(healthy_truth)

    return HealthyBatch(
        events=tuple(events),
        truth=tuple(truth),
    )
