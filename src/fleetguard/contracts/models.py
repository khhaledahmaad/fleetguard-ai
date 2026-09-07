from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0"

SignalName = Literal[
    "speed_kph",
    "ambient_temp_c",
    "axle_load_tonnes",
    "bearing_temp_c",
    "vibration_rms_g",
    "brake_pipe_pressure_bar",
    "brake_cylinder_pressure_bar",
    "battery_voltage_v",
]


class OperatingState(StrEnum):
    STATIONARY = "stationary"
    MOVING = "moving"
    BRAKING = "braking"


class AnomalyType(StrEnum):
    NONE = "none"
    BEARING_DEGRADATION = "bearing_degradation"
    BRAKE_PRESSURE_LEAK = "brake_pressure_leak"
    SENSOR_FAULT = "sensor_fault"


class AnomalySeverity(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )


class AssetMetadata(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    asset_id: str = Field(pattern=r"^FG-WGN-\d{4}$")
    asset_type: Literal["freight_wagon"] = "freight_wagon"
    fleet_id: str = Field(pattern=r"^FG-[A-Z0-9]+-\d{2}$")

    commissioning_age_years: float = Field(ge=0, le=50)
    nominal_load_tonnes: float = Field(ge=10, le=100)

    bearing_baseline_temp_c: float = Field(ge=-10, le=85)
    vibration_baseline_g: float = Field(ge=0, le=1)
    brake_pressure_baseline_bar: float = Field(ge=3, le=6)

    generator_seed: int = Field(ge=0)


class TelemetryEvent(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    event_id: UUID
    asset_id: str = Field(pattern=r"^FG-WGN-\d{4}$")

    event_time: datetime
    generated_at: datetime
    operating_state: OperatingState

    speed_kph: float = Field(ge=0, le=120)
    ambient_temp_c: float = Field(ge=-40, le=50)
    axle_load_tonnes: float = Field(ge=0, le=30)
    bearing_temp_c: float = Field(ge=-40, le=150)
    vibration_rms_g: float = Field(ge=0, le=10)
    brake_pipe_pressure_bar: float = Field(ge=0, le=6)
    brake_cylinder_pressure_bar: float = Field(ge=0, le=5)
    battery_voltage_v: float = Field(ge=0, le=32)

    @field_validator("event_time", "generated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include timezone information")
        return value

    @model_validator(mode="after")
    def validate_event_relationships(self) -> Self:
        if self.generated_at < self.event_time:
            raise ValueError("generated_at cannot precede event_time")

        if self.operating_state == OperatingState.STATIONARY and self.speed_kph > 1:
            raise ValueError("stationary events cannot have speed above 1 km/h")

        return self


class AnomalyTruth(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    event_id: UUID
    asset_id: str = Field(pattern=r"^FG-WGN-\d{4}$")

    is_anomaly: bool
    anomaly_type: AnomalyType
    anomaly_severity: AnomalySeverity
    affected_signal: SignalName | None
    anomaly_start_time: datetime | None
    anomaly_progress: float = Field(ge=0, le=1)

    @field_validator("anomaly_start_time")
    @classmethod
    def require_timezone_when_present(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("anomaly_start_time must include timezone information")
        return value

    @model_validator(mode="after")
    def validate_anomaly_consistency(self) -> Self:
        if self.is_anomaly:
            if self.anomaly_type == AnomalyType.NONE:
                raise ValueError("anomalous records require an anomaly type")
            if self.anomaly_severity == AnomalySeverity.NONE:
                raise ValueError("anomalous records require a severity")
            if self.affected_signal is None:
                raise ValueError("anomalous records require an affected signal")
            if self.anomaly_start_time is None:
                raise ValueError("anomalous records require an anomaly start time")
        else:
            if self.anomaly_type != AnomalyType.NONE:
                raise ValueError("healthy records must use anomaly_type='none'")
            if self.anomaly_severity != AnomalySeverity.NONE:
                raise ValueError("healthy records must use anomaly_severity='none'")
            if self.affected_signal is not None:
                raise ValueError("healthy records cannot have an affected signal")
            if self.anomaly_start_time is not None:
                raise ValueError("healthy records cannot have an anomaly start time")
            if self.anomaly_progress != 0:
                raise ValueError("healthy records must have zero anomaly progress")

        return self
