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

    if event.asset_id != scenario.target.asset_id or not scenario.is_active(event.event_time):
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
