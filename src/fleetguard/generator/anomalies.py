from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from fleetguard.contracts import (
    AnomalySeverity,
    AnomalyTruth,
    AnomalyType,
    TelemetryEvent,
)

_BEARING_EFFECTS = {
    AnomalySeverity.LOW: (8.0, 0.15),
    AnomalySeverity.MEDIUM: (18.0, 0.35),
    AnomalySeverity.HIGH: (35.0, 0.70),
}

_BRAKE_LEAK_EFFECTS = {
    AnomalySeverity.LOW: (0.20, 0.08),
    AnomalySeverity.MEDIUM: (0.45, 0.18),
    AnomalySeverity.HIGH: (0.80, 0.35),
}

_SENSOR_DRIFT_EFFECTS = {
    AnomalySeverity.LOW: 4.0,
    AnomalySeverity.MEDIUM: 10.0,
    AnomalySeverity.HIGH: 20.0,
}


@dataclass(frozen=True)
class InjectedBatch:
    events: tuple[TelemetryEvent, ...]
    truth: tuple[AnomalyTruth, ...]


@dataclass(frozen=True)
class ComponentTarget:
    asset_id: str
    bogie_id: Literal[1, 2] | None = None
    axle_position: Literal["inner", "outer"] | None = None
    wheel_side: Literal["left", "right"] | None = None
    signal_name: str | None = None


@dataclass(frozen=True)
class AnomalyScenario:
    scenario_id: str
    anomaly_type: AnomalyType
    target: ComponentTarget
    start_time: datetime
    end_time: datetime
    peak_severity: AnomalySeverity

    def __post_init__(self) -> None:
        if self.start_time.tzinfo is None or self.end_time.tzinfo is None:
            raise ValueError("Scenario timestamps must be timezone-aware")

        if self.end_time <= self.start_time:
            raise ValueError("Scenario end_time must be after start_time")

        if self.anomaly_type is AnomalyType.BEARING_DEGRADATION and (
            self.target.bogie_id is None
            or self.target.axle_position is None
            or self.target.wheel_side is None
        ):
            raise ValueError(
                "Bearing degradation requires bogie, axle and wheel targeting"
            )

        if (
            self.anomaly_type is AnomalyType.BRAKE_PRESSURE_LEAK
            and self.target.signal_name != "brake_pipe_pressure_bar"
        ):
            raise ValueError(
                "Brake-pressure leakage requires "
                "signal_name='brake_pipe_pressure_bar'"
            )

        if self.anomaly_type is AnomalyType.SENSOR_FAULT and (
            self.target.signal_name != "bearing_temp_c"
            or self.target.bogie_id is None
            or self.target.axle_position is None
            or self.target.wheel_side is None
        ):
            raise ValueError(
                "Bearing-temperature sensor drift requires "
                "bogie, axle, wheel and signal targeting"
            )

    def is_active(self, event_time: datetime) -> bool:
        return self.start_time <= event_time <= self.end_time

    def progress_at(self, event_time: datetime) -> float:
        if event_time <= self.start_time:
            return 0.0

        if event_time >= self.end_time:
            return 1.0

        elapsed = (event_time - self.start_time).total_seconds()
        duration = (self.end_time - self.start_time).total_seconds()
        return elapsed / duration


def inject_bearing_degradation(
    event: TelemetryEvent,
    truth: AnomalyTruth,
    scenario: AnomalyScenario,
) -> tuple[TelemetryEvent, AnomalyTruth]:
    """Return copied event and truth records with one bearing anomaly applied."""
    if scenario.anomaly_type is not AnomalyType.BEARING_DEGRADATION:
        raise ValueError("scenario must describe bearing degradation")

    if event.event_id != truth.event_id or event.asset_id != truth.asset_id:
        raise ValueError("event and truth identities must match")

    if (
        event.asset_id != scenario.target.asset_id
        or event.event_time < scenario.start_time
    ):
        return event, truth

    progress = scenario.progress_at(event.event_time)
    if progress == 0:
        return event, truth

    maximum_temperature_rise, maximum_vibration_rise = _BEARING_EFFECTS[
        scenario.peak_severity
    ]
    updated_bogies = []
    target_found = False

    for bogie in event.bogies:
        updated_axles = []
        for axle in bogie.axles:
            is_target_axle = (
                bogie.bogie_id == scenario.target.bogie_id
                and axle.axle_position == scenario.target.axle_position
            )
            updated_wheels = []

            for wheel in axle.wheels:
                is_target_wheel = (
                    is_target_axle and wheel.wheel_side == scenario.target.wheel_side
                )
                if is_target_wheel:
                    target_found = True
                    updated_wheels.append(
                        wheel.model_copy(
                            update={
                                "bearing_temp_c": round(
                                    min(
                                        150.0,
                                        wheel.bearing_temp_c
                                        + maximum_temperature_rise * progress,
                                    ),
                                    3,
                                )
                            }
                        )
                    )
                else:
                    updated_wheels.append(wheel)

            if is_target_axle:
                updated_axles.append(
                    axle.model_copy(
                        update={
                            "vibration_rms_g": round(
                                min(
                                    10.0,
                                    axle.vibration_rms_g
                                    + maximum_vibration_rise * progress,
                                ),
                                4,
                            ),
                            "wheels": tuple(updated_wheels),
                        }
                    )
                )
            else:
                updated_axles.append(axle)

        updated_bogies.append(bogie.model_copy(update={"axles": tuple(updated_axles)}))

    if not target_found:
        raise ValueError("bearing degradation target was not found in telemetry event")

    component = (
        f"bogie:{scenario.target.bogie_id}/"
        f"axle:{scenario.target.axle_position}/"
        f"wheel:{scenario.target.wheel_side}"
    )
    updated_event = event.model_copy(update={"bogies": tuple(updated_bogies)})
    updated_truth = truth.model_copy(
        update={
            "is_anomaly": True,
            "anomaly_type": AnomalyType.BEARING_DEGRADATION,
            "anomaly_severity": scenario.peak_severity,
            "affected_component": component,
            "affected_signal": "bearing_temp_c",
            "anomaly_start_time": scenario.start_time,
            "anomaly_progress": round(progress, 6),
        }
    )
    return updated_event, updated_truth


def inject_brake_pressure_leak(
    event: TelemetryEvent,
    truth: AnomalyTruth,
    scenario: AnomalyScenario,
) -> tuple[TelemetryEvent, AnomalyTruth]:
    """Apply a progressive wagon-level pneumatic pressure leak."""
    if scenario.anomaly_type is not AnomalyType.BRAKE_PRESSURE_LEAK:
        raise ValueError("scenario must describe brake-pressure leakage")

    if event.event_id != truth.event_id or event.asset_id != truth.asset_id:
        raise ValueError("event and truth identities must match")

    if (
        event.asset_id != scenario.target.asset_id
        or event.event_time < scenario.start_time
    ):
        return event, truth

    progress = scenario.progress_at(event.event_time)

    if progress == 0:
        return event, truth

    maximum_pipe_loss, maximum_auxiliary_loss = _BRAKE_LEAK_EFFECTS[
        scenario.peak_severity
    ]

    updated_event = event.model_copy(
        update={
            "brake_pipe_pressure_bar": round(
                max(
                    0.0,
                    event.brake_pipe_pressure_bar - maximum_pipe_loss * progress,
                ),
                3,
            ),
            "auxiliary_reservoir_pressure_bar": round(
                max(
                    0.0,
                    event.auxiliary_reservoir_pressure_bar
                    - maximum_auxiliary_loss * progress,
                ),
                3,
            ),
        }
    )

    updated_truth = truth.model_copy(
        update={
            "is_anomaly": True,
            "anomaly_type": AnomalyType.BRAKE_PRESSURE_LEAK,
            "anomaly_severity": scenario.peak_severity,
            "affected_component": "wagon:pneumatic_system",
            "affected_signal": "brake_pipe_pressure_bar",
            "anomaly_start_time": scenario.start_time,
            "anomaly_progress": round(progress, 6),
        }
    )

    return updated_event, updated_truth


def inject_bearing_temperature_sensor_drift(
    event: TelemetryEvent,
    truth: AnomalyTruth,
    scenario: AnomalyScenario,
) -> tuple[TelemetryEvent, AnomalyTruth]:
    """Apply progressive bias to one bearing-temperature sensor."""
    if scenario.anomaly_type is not AnomalyType.SENSOR_FAULT:
        raise ValueError("scenario must describe a sensor fault")

    if event.event_id != truth.event_id or event.asset_id != truth.asset_id:
        raise ValueError("event and truth identities must match")

    if (
        event.asset_id != scenario.target.asset_id
        or event.event_time < scenario.start_time
    ):
        return event, truth

    progress = scenario.progress_at(event.event_time)

    if progress == 0:
        return event, truth

    maximum_temperature_bias = _SENSOR_DRIFT_EFFECTS[scenario.peak_severity]

    updated_bogies = []
    target_found = False

    for bogie in event.bogies:
        updated_axles = []

        for axle in bogie.axles:
            is_target_axle = (
                bogie.bogie_id == scenario.target.bogie_id
                and axle.axle_position == scenario.target.axle_position
            )

            updated_wheels = []

            for wheel in axle.wheels:
                is_target_wheel = (
                    is_target_axle and wheel.wheel_side == scenario.target.wheel_side
                )

                if is_target_wheel:
                    target_found = True

                    updated_wheels.append(
                        wheel.model_copy(
                            update={
                                "bearing_temp_c": round(
                                    min(
                                        150.0,
                                        wheel.bearing_temp_c
                                        + maximum_temperature_bias * progress,
                                    ),
                                    3,
                                )
                            }
                        )
                    )
                else:
                    updated_wheels.append(wheel)

            updated_axles.append(
                axle.model_copy(update={"wheels": tuple(updated_wheels)})
                if is_target_axle
                else axle
            )

        updated_bogies.append(bogie.model_copy(update={"axles": tuple(updated_axles)}))

    if not target_found:
        raise ValueError("sensor-fault target was not found in telemetry event")

    component = (
        f"bogie:{scenario.target.bogie_id}/"
        f"axle:{scenario.target.axle_position}/"
        f"wheel:{scenario.target.wheel_side}/"
        "sensor:bearing_temp_c"
    )

    updated_event = event.model_copy(update={"bogies": tuple(updated_bogies)})

    updated_truth = truth.model_copy(
        update={
            "is_anomaly": True,
            "anomaly_type": AnomalyType.SENSOR_FAULT,
            "anomaly_severity": scenario.peak_severity,
            "affected_component": component,
            "affected_signal": "bearing_temp_c",
            "anomaly_start_time": scenario.start_time,
            "anomaly_progress": round(progress, 6),
        }
    )

    return updated_event, updated_truth


def inject_anomaly_scenarios(
    events: tuple[TelemetryEvent, ...],
    truth: tuple[AnomalyTruth, ...],
    scenarios: tuple[AnomalyScenario, ...],
) -> InjectedBatch:
    """Apply ordered anomaly scenarios across a generated telemetry batch."""
    if len(events) != len(truth):
        raise ValueError("events and truth must contain the same number of records")

    updated_events: list[TelemetryEvent] = []
    updated_truth: list[AnomalyTruth] = []

    for event, truth_record in zip(events, truth, strict=True):
        current_event = event
        current_truth = truth_record

        for scenario in scenarios:
            if scenario.anomaly_type is AnomalyType.BEARING_DEGRADATION:
                current_event, current_truth = inject_bearing_degradation(
                    current_event,
                    current_truth,
                    scenario,
                )

            elif scenario.anomaly_type is AnomalyType.BRAKE_PRESSURE_LEAK:
                current_event, current_truth = inject_brake_pressure_leak(
                    current_event,
                    current_truth,
                    scenario,
                )

            elif scenario.anomaly_type is AnomalyType.SENSOR_FAULT:
                current_event, current_truth = inject_bearing_temperature_sensor_drift(
                    current_event,
                    current_truth,
                    scenario,
                )

            else:
                raise ValueError(
                    f"unsupported anomaly type: " f"{scenario.anomaly_type}"
                )

        updated_events.append(current_event)
        updated_truth.append(current_truth)

    return InjectedBatch(
        events=tuple(updated_events),
        truth=tuple(updated_truth),
    )
