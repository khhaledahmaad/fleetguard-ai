from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from fleetguard.contracts import (
    STANDARD_SAMPLING_INTERVAL_SECONDS,
    SUPPORTED_SAMPLING_INTERVALS,
    AnomalySeverity,
    AnomalyTruth,
    AnomalyType,
    AssetMetadata,
    AxleTelemetry,
    BogieTelemetry,
    ControllerHealthStatus,
    ControllerTelemetry,
    JourneyPhase,
    OperatingState,
    RailCondition,
    TelemetryEvent,
    TravelDirection,
    WheelTelemetry,
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


Sample = tuple[int, JourneyPhase, OperatingState, float, float]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def _validate_sampling_interval(value: int) -> None:
    if value not in SUPPORTED_SAMPLING_INTERVALS:
        raise ValueError("sampling_interval_seconds must be one of 1, 10 or 60")


def _ambient_temperature(event_time: datetime) -> float:
    second = event_time.hour * 3600 + event_time.minute * 60 + event_time.second
    return 14 + 6 * math.sin(2 * math.pi * (second - 21600) / 86400)


def _rail_condition(route_progress: float, ambient_temp_c: float) -> RailCondition:
    if ambient_temp_c <= 1:
        return RailCondition.ICY
    if 0.62 <= route_progress <= 0.72:
        return RailCondition.LEAF_CONTAMINATED
    if 0.18 <= route_progress <= 0.45:
        return RailCondition.WET
    return RailCondition.DRY


def _true_adhesion(condition: RailCondition, route_progress: float) -> float:
    baseline = {
        RailCondition.DRY: 0.30,
        RailCondition.WET: 0.17,
        RailCondition.LEAF_CONTAMINATED: 0.09,
        RailCondition.ICY: 0.05,
    }[condition]
    return _clamp(baseline + 0.008 * math.sin(route_progress * 12 * math.pi), 0, 0.6)


def _speed(state: OperatingState, progress: float, rng: random.Random, cruise: float) -> float:
    if state == OperatingState.STATIONARY:
        return 0.0
    if state == OperatingState.BRAKING:
        return _clamp(cruise * (1 - progress) + rng.normalvariate(0, 0.25), 0, 120)
    ramp = min(1.0, 20 * progress)
    value = cruise * ramp + 7 * math.sin(math.pi * progress)
    return _clamp(value + rng.normalvariate(0, 0.4), 1, 120)


def _generate(
    asset: AssetMetadata,
    start_time: datetime,
    seed: int,
    samples: list[Sample],
    journey_id: str,
    route: RailRoute,
    direction: TravelDirection,
    cruise_speed_kph: float,
    sampling_interval_seconds: int,
) -> HealthyBatch:
    rng = random.Random(seed)
    events: list[TelemetryEvent] = []
    truth: list[AnomalyTruth] = []
    temperatures = {
        (bogie.bogie_id, axle.axle_position): asset.bearing_baseline_temp_c - 8
        for bogie in asset.bogies
        for axle in bogie.axles
    }
    previous_speed = 0.0
    thermal_alpha = 1 - math.exp(-sampling_interval_seconds / 480)
    noise_scale = math.sqrt(sampling_interval_seconds / 60)

    for elapsed_seconds, journey_phase, state, route_progress, phase_progress in samples:
        event_time = start_time + timedelta(seconds=elapsed_seconds)
        speed = _speed(state, phase_progress, rng, cruise_speed_kph)
        latitude, longitude = interpolate_route(
            route, route_progress, direction == TravelDirection.REVERSE
        )
        ambient = _ambient_temperature(event_time) + rng.normalvariate(0, 0.15)
        longitudinal = (speed - previous_speed) / 3.6 / sampling_interval_seconds
        lateral = (speed / 70) ** 2 * 0.22 * math.sin(route_progress * 16 * math.pi)
        vertical = rng.normalvariate(0, 0.025 + 0.0012 * speed)
        condition = _rail_condition(route_progress, ambient)
        true_adhesion = _true_adhesion(condition, route_progress)
        estimated_adhesion = true_adhesion + rng.normalvariate(0, 0.008)

        if state == OperatingState.BRAKING:
            bp = asset.brake_pressure_baseline_bar - 1.7 * phase_progress
            bcp = 0.1 + 3.0 * phase_progress
            ar = 5.0 - 0.65 * phase_progress
            sr = 5.0 - 0.12 * phase_progress
        else:
            bp = asset.brake_pressure_baseline_bar
            bcp = 0.05
            ar = min(5.0, 4.75 + 0.00025 * elapsed_seconds)
            sr = min(5.0, 4.9 + 0.0001 * elapsed_seconds)

        bogie_events: list[BogieTelemetry] = []
        axle_load = asset.nominal_load_tonnes / 4
        for bogie in asset.bogies:
            axle_events: list[AxleTelemetry] = []
            for axle in bogie.axles:
                mean_diameter_m = sum(wheel.diameter_mm for wheel in axle.wheels) / 2000
                rpm = speed * 1000 / (60 * math.pi * mean_diameter_m)
                target_temp = max(
                    ambient + 5,
                    asset.bearing_baseline_temp_c + 0.12 * speed + 0.08 * (axle_load - 15),
                )
                key = (bogie.bogie_id, axle.axle_position)
                current_temp = temperatures[key]
                current_temp += thermal_alpha * (target_temp - current_temp)
                current_temp += rng.normalvariate(0, 0.08 * noise_scale)
                temperatures[key] = current_temp
                vibration = asset.vibration_baseline_g + 0.004 * speed + rng.normalvariate(0, 0.01)
                axle_events.append(
                    AxleTelemetry(
                        axle_position=axle.axle_position,
                        rotational_speed_rpm=round(_clamp(rpm, 0, 1000), 3),
                        wheel_speed_kph=round(speed, 3),
                        axle_load_tonnes=round(
                            _clamp(axle_load + rng.normalvariate(0, 0.15), 0, 30), 3
                        ),
                        vibration_rms_g=round(_clamp(vibration, 0, 10), 4),
                        wheels=tuple(
                            WheelTelemetry(
                                wheel_side=wheel.wheel_side,
                                bearing_temp_c=round(
                                    _clamp(
                                        current_temp + rng.normalvariate(0, 0.1),
                                        -40,
                                        150,
                                    ),
                                    3,
                                ),
                            )
                            for wheel in axle.wheels
                        ),
                    )
                )
            bogie_events.append(
                BogieTelemetry(
                    bogie_id=bogie.bogie_id,
                    handbrake_equipped=bogie.handbrake_equipped,
                    brake_cylinder_pressure_bar=round(
                        _clamp(bcp + rng.normalvariate(0, 0.025), 0, 5), 3
                    ),
                    axles=tuple(axle_events),
                )
            )

        event_id = uuid5(
            NAMESPACE_URL,
            f"fleetguard:{asset.asset_id}:{event_time.isoformat()}:{seed}",
        )
        event = TelemetryEvent(
            event_id=event_id,
            asset_id=asset.asset_id,
            journey_id=journey_id,
            route_id=route.route_id,
            event_time=event_time,
            generated_at=event_time,
            sampling_interval_seconds=sampling_interval_seconds,
            travel_direction=direction,
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
            rail_condition=condition,
            estimated_adhesion_coefficient=round(_clamp(estimated_adhesion, 0, 0.6), 4),
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
                    _clamp(
                        ambient + 8 + 0.025 * speed + rng.normalvariate(0, 0.1),
                        -40,
                        100,
                    ),
                    3,
                ),
                supply_voltage_v=round(
                    _clamp(
                        25.2 - 0.0000083 * elapsed_seconds + rng.normalvariate(0, 0.015),
                        0,
                        32,
                    ),
                    3,
                ),
                health_status=ControllerHealthStatus.HEALTHY,
                uptime_seconds=elapsed_seconds,
                reset_count=0,
                sensor_communication_error_count=0,
            ),
        )
        events.append(event)
        truth.append(
            AnomalyTruth(
                event_id=event_id,
                asset_id=asset.asset_id,
                true_adhesion_coefficient=round(true_adhesion, 4),
                is_anomaly=False,
                anomaly_type=AnomalyType.NONE,
                anomaly_severity=AnomalySeverity.NONE,
                affected_component=None,
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
    sampling_interval_seconds: int = 60,
) -> HealthyBatch:
    if start_time.tzinfo is None or start_time.utcoffset() is None:
        raise ValueError("start_time must include timezone information")
    if periods < 1:
        raise ValueError("periods must be at least 1")
    _validate_sampling_interval(sampling_interval_seconds)
    samples: list[Sample] = []
    for index in range(periods):
        elapsed = index * sampling_interval_seconds
        state, phase_progress = cycle.state_at(elapsed // 60)
        samples.append(
            (
                elapsed,
                JourneyPhase.RUNNING,
                state,
                index / max(periods - 1, 1),
                phase_progress,
            )
        )
    return _generate(
        asset,
        start_time,
        asset.generator_seed if seed is None else seed,
        samples,
        f"FG-JNY-{start_time:%Y%m%d}-0000",
        LONDON_SWANSEA_FREIGHT_ROUTE,
        TravelDirection.FORWARD,
        70.0,
        sampling_interval_seconds,
    )


def generate_healthy_journey(
    asset: AssetMetadata,
    start_time: datetime,
    journey: JourneyPlan,
    seed: int | None = None,
    sampling_interval_seconds: int = STANDARD_SAMPLING_INTERVAL_SECONDS,
) -> HealthyBatch:
    if start_time.tzinfo is None or start_time.utcoffset() is None:
        raise ValueError("start_time must include timezone information")
    _validate_sampling_interval(sampling_interval_seconds)
    samples = [
        (elapsed, *journey_state_at(journey, elapsed))
        for elapsed in range(0, journey.duration_seconds, sampling_interval_seconds)
    ]
    return _generate(
        asset,
        start_time,
        asset.generator_seed if seed is None else seed,
        samples,
        journey.journey_id,
        journey.route,
        journey.travel_direction,
        journey.nominal_speed_kph,
        sampling_interval_seconds,
    )
