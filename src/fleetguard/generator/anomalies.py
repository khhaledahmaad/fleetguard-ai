from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal


class AnomalyType(StrEnum):
    BEARING_DEGRADATION = "bearing_degradation"
    BRAKE_PRESSURE_LEAK = "brake_pressure_leak"
    SENSOR_DRIFT = "sensor_drift"


class AnomalySeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


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
