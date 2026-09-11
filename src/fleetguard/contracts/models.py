from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "2.0"

SignalName = Literal[
    "speed_kph",
    "latitude",
    "longitude",
    "longitudinal_acceleration_mps2",
    "lateral_acceleration_mps2",
    "vertical_acceleration_mps2",
    "axle_load_tonnes",
    "wheelset_rotational_speed_rpm",
    "bearing_temp_c",
    "vibration_rms_g",
    "brake_pipe_pressure_bar",
    "auxiliary_reservoir_pressure_bar",
    "secondary_reservoir_pressure_bar",
    "brake_cylinder_pressure_bar",
    "controller_temp_c",
    "controller_supply_voltage_v",
    "controller_health_status",
]


class OperatingState(StrEnum):
    STATIONARY = "stationary"
    MOVING = "moving"
    BRAKING = "braking"


class JourneyPhase(StrEnum):
    ORIGIN_DWELL = "origin_dwell"
    RUNNING = "running"
    INTERMEDIATE_DWELL = "intermediate_dwell"
    DESTINATION_DWELL = "destination_dwell"


class ControllerHealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAULT = "fault"
    OFFLINE = "offline"


class BogiePosition(StrEnum):
    A = "a"
    B = "b"


class WheelsetPosition(StrEnum):
    LEADING = "leading"
    TRAILING = "trailing"


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
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class WheelMetadata(ContractModel):
    side: Literal["left", "right"]
    diameter_mm: float = Field(ge=800, le=1100)


class WheelsetMetadata(ContractModel):
    wheelset_id: str = Field(pattern=r"^FG-WGN-\d{4}-BG[AB]-WS[12]$")
    position: WheelsetPosition
    left_wheel: WheelMetadata
    right_wheel: WheelMetadata

    @model_validator(mode="after")
    def validate_wheels(self) -> Self:
        if self.left_wheel.side != "left" or self.right_wheel.side != "right":
            raise ValueError("wheel sides must match their wheelset positions")
        if abs(self.left_wheel.diameter_mm - self.right_wheel.diameter_mm) > 2:
            raise ValueError("healthy wheel diameter difference cannot exceed 2 mm")
        return self


class BogieMetadata(ContractModel):
    bogie_id: str = Field(pattern=r"^FG-WGN-\d{4}-BG[AB]$")
    position: BogiePosition
    handbrake_equipped: bool
    wheelsets: tuple[WheelsetMetadata, WheelsetMetadata]

    @model_validator(mode="after")
    def validate_wheelset_positions(self) -> Self:
        if {item.position for item in self.wheelsets} != {
            WheelsetPosition.LEADING,
            WheelsetPosition.TRAILING,
        }:
            raise ValueError("each bogie requires one leading and one trailing wheelset")
        return self


class AssetMetadata(ContractModel):
    schema_version: Literal["2.0"] = SCHEMA_VERSION
    asset_id: str = Field(pattern=r"^FG-WGN-\d{4}$")
    asset_type: Literal["freight_wagon"] = "freight_wagon"
    fleet_id: str = Field(pattern=r"^FG-[A-Z0-9]+-\d{2}$")
    commissioning_age_years: float = Field(ge=0, le=50)
    nominal_load_tonnes: float = Field(ge=10, le=100)
    bearing_baseline_temp_c: float = Field(ge=-10, le=85)
    vibration_baseline_g: float = Field(ge=0, le=1)
    brake_pressure_baseline_bar: float = Field(ge=3, le=6)
    bogies: tuple[BogieMetadata, BogieMetadata]
    generator_seed: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_bogie_configuration(self) -> Self:
        if {item.position for item in self.bogies} != {BogiePosition.A, BogiePosition.B}:
            raise ValueError("each wagon requires bogies A and B")
        if sum(item.handbrake_equipped for item in self.bogies) != 1:
            raise ValueError("exactly one bogie must be handbrake-equipped")
        return self


class WheelsetTelemetry(ContractModel):
    wheelset_id: str = Field(pattern=r"^FG-WGN-\d{4}-BG[AB]-WS[12]$")
    rotational_speed_rpm: float = Field(ge=0, le=1000)
    wheel_speed_kph: float = Field(ge=0, le=140)
    axle_load_tonnes: float = Field(ge=0, le=30)
    left_bearing_temp_c: float = Field(ge=-40, le=150)
    right_bearing_temp_c: float = Field(ge=-40, le=150)
    vibration_rms_g: float = Field(ge=0, le=10)


class BogieTelemetry(ContractModel):
    bogie_id: str = Field(pattern=r"^FG-WGN-\d{4}-BG[AB]$")
    brake_cylinder_pressure_bar: float = Field(ge=0, le=5)
    wheelsets: tuple[WheelsetTelemetry, WheelsetTelemetry]


class ControllerTelemetry(ContractModel):
    temperature_c: float = Field(ge=-40, le=100)
    supply_voltage_v: float = Field(ge=0, le=32)
    health_status: ControllerHealthStatus
    uptime_s: int = Field(ge=0)
    reset_count: int = Field(ge=0)
    sensor_communication_error_count: int = Field(ge=0)


class TelemetryEvent(ContractModel):
    schema_version: Literal["2.0"] = SCHEMA_VERSION
    event_id: UUID
    asset_id: str = Field(pattern=r"^FG-WGN-\d{4}$")
    journey_id: str = Field(pattern=r"^FG-JNY-[A-Z0-9-]+$")
    route_id: str = Field(pattern=r"^FG-RTE-[A-Z0-9-]+$")
    event_time: datetime
    generated_at: datetime
    operating_state: OperatingState
    journey_phase: JourneyPhase
    route_progress: float = Field(ge=0, le=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    speed_kph: float = Field(ge=0, le=120)
    ambient_temp_c: float = Field(ge=-40, le=50)
    longitudinal_acceleration_mps2: float = Field(ge=-5, le=5)
    lateral_acceleration_mps2: float = Field(ge=-5, le=5)
    vertical_acceleration_mps2: float = Field(ge=-10, le=10)
    brake_pipe_pressure_bar: float = Field(ge=0, le=6)
    auxiliary_reservoir_pressure_bar: float = Field(ge=0, le=6)
    secondary_reservoir_pressure_bar: float = Field(ge=0, le=6)
    bogies: tuple[BogieTelemetry, BogieTelemetry]
    controller: ControllerTelemetry

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
        if len({item.bogie_id for item in self.bogies}) != 2:
            raise ValueError("telemetry requires two distinct bogies")
        return self


class AnomalyTruth(ContractModel):
    schema_version: Literal["2.0"] = SCHEMA_VERSION
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
    def require_timezone_when_present(cls, value: datetime | None) -> datetime | None:
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
