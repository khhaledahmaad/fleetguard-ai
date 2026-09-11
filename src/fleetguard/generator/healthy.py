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
    BogieTelemetry,
    ControllerHealthStatus,
    ControllerTelemetry,
    JourneyPhase,
    OperatingState,
    TelemetryEvent,
    WheelsetTelemetry,
)
from fleetguard.generator.cycle import DEFAULT_OPERATING_CYCLE, OperatingCycle
from fleetguard.generator.route import (
    LONDON_SWANSEA_FREIGHT_ROUTE,
    JourneyPlan,
    RailRoute,
    interpolate_route,
    journey_state_at,
)


@dataclass(frozen=True)
class HealthyBatch:
    events: tuple[TelemetryEvent, ...]
    truth: tuple[AnomalyTruth, ...]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def _ambient_temperature(event_time: datetime) -> float:
    minute = event_time.hour * 60 + event_time.minute
    return 14 + 6 * math.sin(2 * math.pi * (minute - 360) / 1440)


def _speed(state: OperatingState, progress: float, rng: random.Random, cruise: float) -> float:
    if state == OperatingState.STATIONARY:
        return 0.0
    if state == OperatingState.BRAKING:
        return _clamp(cruise * (1 - progress) + rng.normalvariate(0, 0.6), 0, 120)
    ramp = min(1.0, 0.35 + 2.5 * progress)
    return _clamp(
        cruise * ramp + 7 * math.sin(math.pi * progress) + rng.normalvariate(0, 1.2), 1, 120
    )


def _generate(
    asset: AssetMetadata,
    start_time: datetime,
    periods: int,
    seed: int,
    samples: list[tuple[JourneyPhase, OperatingState, float, float]],
    journey_id: str,
    route: RailRoute,
    reverse: bool,
    cruise_speed_kph: float,
) -> HealthyBatch:
    rng = random.Random(seed)
    events: list[TelemetryEvent] = []
    truth: list[AnomalyTruth] = []
    temperatures = {
        wheelset.wheelset_id: asset.bearing_baseline_temp_c - 8
        for bogie in asset.bogies
        for wheelset in bogie.wheelsets
    }
    previous_speed = 0.0

    for minute_index, (journey_phase, state, route_progress, phase_progress) in enumerate(samples):
        event_time = start_time + timedelta(minutes=minute_index)
        speed = _speed(state, phase_progress, rng, cruise_speed_kph)
        latitude, longitude = interpolate_route(route, route_progress, reverse)
        ambient = _ambient_temperature(event_time) + rng.normalvariate(0, 0.15)
        longitudinal = (speed - previous_speed) / 3.6 / 60
        lateral = (speed / 70) ** 2 * 0.22 * math.sin(route_progress * 16 * math.pi)
        vertical = rng.normalvariate(0, 0.025 + 0.0012 * speed)

        if state == OperatingState.BRAKING:
            bp = asset.brake_pressure_baseline_bar - 1.7 * phase_progress
            bcp = 0.1 + 3.0 * phase_progress
            ar = 5.0 - 0.65 * phase_progress
            sr = 5.0 - 0.12 * phase_progress
        else:
            bp = asset.brake_pressure_baseline_bar
            bcp = 0.05
            ar = min(5.0, 4.75 + 0.015 * minute_index)
            sr = min(5.0, 4.9 + 0.006 * minute_index)

        bogie_events: list[BogieTelemetry] = []
        axle_load = asset.nominal_load_tonnes / 4
        for bogie in asset.bogies:
            wheelset_events: list[WheelsetTelemetry] = []
            for wheelset in bogie.wheelsets:
                mean_diameter_m = (
                    wheelset.left_wheel.diameter_mm + wheelset.right_wheel.diameter_mm
                ) / 2000
                rpm = speed * 1000 / (60 * math.pi * mean_diameter_m)
                target_temp = max(
                    ambient + 5,
                    asset.bearing_baseline_temp_c + 0.12 * speed + 0.08 * (axle_load - 15),
                )
                current_temp = temperatures[wheelset.wheelset_id]
                current_temp += 0.12 * (target_temp - current_temp) + rng.normalvariate(0, 0.08)
                temperatures[wheelset.wheelset_id] = current_temp
                vibration = asset.vibration_baseline_g + 0.004 * speed + rng.normalvariate(0, 0.01)
                wheelset_events.append(
                    WheelsetTelemetry(
                        wheelset_id=wheelset.wheelset_id,
                        rotational_speed_rpm=round(_clamp(rpm, 0, 1000), 3),
                        wheel_speed_kph=round(speed, 3),
                        axle_load_tonnes=round(
                            _clamp(axle_load + rng.normalvariate(0, 0.15), 0, 30), 3
                        ),
                        left_bearing_temp_c=round(
                            _clamp(current_temp + rng.normalvariate(0, 0.1), -40, 150), 3
                        ),
                        right_bearing_temp_c=round(
                            _clamp(current_temp + rng.normalvariate(0, 0.1), -40, 150), 3
                        ),
                        vibration_rms_g=round(_clamp(vibration, 0, 10), 4),
                    )
                )
            bogie_events.append(
                BogieTelemetry(
                    bogie_id=bogie.bogie_id,
                    brake_cylinder_pressure_bar=round(
                        _clamp(bcp + rng.normalvariate(0, 0.025), 0, 5), 3
                    ),
                    wheelsets=tuple(wheelset_events),
                )
            )

        event_id = uuid5(
            NAMESPACE_URL, f"fleetguard:{asset.asset_id}:{event_time.isoformat()}:{seed}"
        )
        event = TelemetryEvent(
            event_id=event_id,
            asset_id=asset.asset_id,
            journey_id=journey_id,
            route_id=route.route_id,
            event_time=event_time,
            generated_at=event_time,
            operating_state=state,
            journey_phase=journey_phase,
            route_progress=round(route_progress, 6),
            latitude=round(latitude, 6),
            longitude=round(longitude, 6),
            speed_kph=round(speed, 3),
            ambient_temp_c=round(ambient, 3),
            longitudinal_acceleration_mps2=round(_clamp(longitudinal, -5, 5), 5),
            lateral_acceleration_mps2=round(_clamp(lateral, -5, 5), 5),
            vertical_acceleration_mps2=round(_clamp(vertical, -10, 10), 5),
            brake_pipe_pressure_bar=round(_clamp(bp + rng.normalvariate(0, 0.02), 0, 6), 3),
            auxiliary_reservoir_pressure_bar=round(
                _clamp(ar + rng.normalvariate(0, 0.015), 0, 6), 3
            ),
            secondary_reservoir_pressure_bar=round(
                _clamp(sr + rng.normalvariate(0, 0.01), 0, 6), 3
            ),
            bogies=tuple(bogie_events),
            controller=ControllerTelemetry(
                temperature_c=round(
                    _clamp(ambient + 8 + 0.025 * speed + rng.normalvariate(0, 0.1), -40, 100), 3
                ),
                supply_voltage_v=round(
                    _clamp(25.2 - 0.0005 * minute_index + rng.normalvariate(0, 0.015), 0, 32), 3
                ),
                health_status=ControllerHealthStatus.HEALTHY,
                uptime_s=minute_index * 60,
                reset_count=0,
                sensor_communication_error_count=0,
            ),
        )
        events.append(event)
        truth.append(
            AnomalyTruth(
                event_id=event_id,
                asset_id=asset.asset_id,
                is_anomaly=False,
                anomaly_type=AnomalyType.NONE,
                anomaly_severity=AnomalySeverity.NONE,
                affected_signal=None,
                anomaly_start_time=None,
                anomaly_progress=0,
            )
        )
        previous_speed = speed
    return HealthyBatch(events=tuple(events), truth=tuple(truth))


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
    samples = []
    for index in range(periods):
        state, phase_progress = cycle.state_at(index)
        samples.append((JourneyPhase.RUNNING, state, index / max(periods - 1, 1), phase_progress))
    return _generate(
        asset,
        start_time,
        periods,
        asset.generator_seed if seed is None else seed,
        samples,
        "FG-JNY-DEVELOPMENT",
        LONDON_SWANSEA_FREIGHT_ROUTE,
        False,
        70.0,
    )


def generate_healthy_journey(
    asset: AssetMetadata,
    start_time: datetime,
    journey: JourneyPlan,
    seed: int | None = None,
) -> HealthyBatch:
    if start_time.tzinfo is None or start_time.utcoffset() is None:
        raise ValueError("start_time must include timezone information")
    samples = [journey_state_at(journey, index) for index in range(journey.duration_minutes)]
    return _generate(
        asset,
        start_time,
        journey.duration_minutes,
        asset.generator_seed if seed is None else seed,
        samples,
        journey.journey_id,
        journey.route,
        journey.reverse,
        journey.nominal_speed_kph,
    )
