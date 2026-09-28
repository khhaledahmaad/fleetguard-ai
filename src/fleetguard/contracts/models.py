from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "3.2"
SUPPORTED_SAMPLING_INTERVALS = (1, 10, 60)
STANDARD_SAMPLING_INTERVAL_SECONDS = 10
FEATURE_WINDOW_SECONDS = 60

SignalName = Literal[
    "speed_kph",
    "wheel_speed_kph",
    "latitude",
    "longitude",
    "longitudinal_acceleration_mps2",
    "lateral_acceleration_mps2",
    "vertical_acceleration_mps2",
    "axle_load_tonnes",
    "rotational_speed_rpm",
    "bearing_temp_c",
    "vibration_rms_g",
    "brake_pipe_pressure_bar",
    "auxiliary_reservoir_pressure_bar",
    "secondary_reservoir_pressure_bar",
    "brake_cylinder_pressure_bar",
    "estimated_adhesion_coefficient",
    "controller_temperature_c",
    "controller_supply_voltage_v",
    "controller_health_status",
    "battery_voltage_v",
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


class TravelDirection(StrEnum):
    FORWARD = "forward"
    REVERSE = "reverse"


class RailCondition(StrEnum):
    DRY = "dry"
    WET = "wet"
    LEAF_CONTAMINATED = "leaf_contaminated"
    ICY = "icy"


class ControllerHealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAULT = "fault"
    OFFLINE = "offline"


class PowerSource(StrEnum):
    AXLE_GENERATORS = "axle_generators"
    BATTERY = "battery"


class AxlePosition(StrEnum):
    INNER = "inner"
    OUTER = "outer"


class WheelSide(StrEnum):
    LEFT = "left"
    RIGHT = "right"


class LoadState(StrEnum):
    LOADED = "loaded"
    EMPTY = "empty"


class AnomalyType(StrEnum):
    NONE = "none"
    BEARING_DEGRADATION = "bearing_degradation"
    BRAKE_PRESSURE_LEAK = "brake_pressure_leak"
    SENSOR_FAULT = "sensor_fault"
    AXLE_SPEED_GENERATOR_FAILURE = "axle_speed_generator_failure"
    WHEEL_SLIDE = "wheel_slide"
    LOCKED_AXLE = "locked_axle"
    SUSPECTED_WHEEL_FLAT = "suspected_wheel_flat"
    PRESSURE_TRANSDUCER_FAILURE = "pressure_transducer_failure"
    BRAKE_RELEASE_FAILURE = "brake_release_failure"
    UNDEMANDED_BRAKE_APPLICATION = "undemanded_brake_application"
    PREMATURE_BATTERY_DEPLETION = "premature_battery_depletion"
    CONTROLLER_SUPPLY_FAILURE = "controller_supply_failure"


class AnomalySeverity(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class SignalQuality(ContractModel):
    status: Literal["valid", "missing", "invalid"] = "valid"
    raw_value: float | None = None

    @model_validator(mode="after")
    def validate_raw(self) -> Self:
        if self.status != "invalid" and self.raw_value is not None:
            raise ValueError("raw_value is reserved for invalid device codes")
        return self


class QualityTelemetry(ContractModel):
    # Only exceptions are stored. An omitted entry means a valid measurement.
    signal_quality: dict[str, SignalQuality] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_quality(self) -> Self:
        for name, quality in self.signal_quality.items():
            if name not in type(self).model_fields or name == "signal_quality":
                raise ValueError(f"unknown quality signal: {name}")
            if quality.status != "valid" and getattr(self, name) is not None:
                raise ValueError("unavailable measurements must be null")
        for name in type(self).model_fields:
            if getattr(self, name) is None:
                quality = self.signal_quality.get(name)
                if quality is None or quality.status == "valid":
                    raise ValueError(f"null measurement requires quality: {name}")
        return self


class WheelMetadata(ContractModel):
    wheel_side: WheelSide
    diameter_mm: float = Field(ge=800, le=1100)


class AxleMetadata(ContractModel):
    axle_position: AxlePosition
    wheels: tuple[WheelMetadata, WheelMetadata]

    @model_validator(mode="after")
    def validate_wheels(self) -> Self:
        if {wheel.wheel_side for wheel in self.wheels} != {WheelSide.LEFT, WheelSide.RIGHT}:
            raise ValueError("each axle requires left and right wheels")
        if abs(self.wheels[0].diameter_mm - self.wheels[1].diameter_mm) > 2:
            raise ValueError("healthy wheel diameter difference cannot exceed 2 mm")
        return self


class BogieMetadata(ContractModel):
    bogie_id: Literal[1, 2]
    handbrake_equipped: bool
    axles: tuple[AxleMetadata, AxleMetadata]

    @model_validator(mode="after")
    def validate_axles(self) -> Self:
        if {axle.axle_position for axle in self.axles} != {AxlePosition.INNER, AxlePosition.OUTER}:
            raise ValueError("each bogie requires inner and outer axles")
        return self


class AssetMetadata(ContractModel):
    schema_version: Literal["3.2"] = SCHEMA_VERSION
    asset_id: str = Field(pattern=r"^FG-WGN-\d{4}$")
    asset_type: Literal["freight_wagon"] = "freight_wagon"
    fleet_id: str = Field(pattern=r"^FG-[A-Z0-9]+-\d{2}$")
    commissioning_age_years: float = Field(ge=0, le=50)
    nominal_load_tonnes: float = Field(ge=10, le=100)
    bearing_baseline_temp_c: float = Field(ge=-10, le=85)
    vibration_baseline_g: float = Field(ge=0, le=1)
    brake_pressure_baseline_bar: float = Field(ge=3, le=6)
    battery_standby_days: float = Field(ge=5, le=7)
    bogies: tuple[BogieMetadata, BogieMetadata]
    generator_seed: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_bogies(self) -> Self:
        if {bogie.bogie_id for bogie in self.bogies} != {1, 2}:
            raise ValueError("each wagon requires bogies 1 and 2")
        if sum(bogie.handbrake_equipped for bogie in self.bogies) != 1:
            raise ValueError("exactly one bogie must be handbrake-equipped")
        return self


class WheelTelemetry(ContractModel):
    wheel_side: WheelSide
    bearing_temp_c: float = Field(ge=-40, le=150)


class AxleTelemetry(QualityTelemetry):
    axle_position: AxlePosition
    rotational_speed_rpm: float | None = Field(ge=0, le=1000)
    wheel_speed_kph: float | None = Field(ge=0, le=140)
    axle_load_tonnes: float = Field(ge=0, le=30)
    vibration_rms_g: float = Field(ge=0, le=10)
    wheels: tuple[WheelTelemetry, WheelTelemetry]


class BogieTelemetry(QualityTelemetry):
    bogie_id: Literal[1, 2]
    handbrake_equipped: bool
    brake_cylinder_pressure_bar: float | None = Field(ge=0, le=5)
    axles: tuple[AxleTelemetry, AxleTelemetry]


class ControllerTelemetry(ContractModel):
    temperature_c: float = Field(ge=-40, le=100)
    supply_voltage_v: float = Field(ge=0, le=32)
    health_status: ControllerHealthStatus
    uptime_seconds: int = Field(ge=0)
    reset_count: int = Field(ge=0)
    sensor_communication_error_count: int = Field(ge=0)


class JourneyMetadata(ContractModel):
    schema_version: Literal["3.2"] = SCHEMA_VERSION
    journey_id: str = Field(pattern=r"^FG-JNY-\d{8}-\d{4}$")
    route_id: str = Field(pattern=r"^FG-RTE-[A-Z0-9-]+$")
    origin_terminal: str
    destination_terminal: str
    travel_direction: TravelDirection
    scheduled_start_time: datetime
    estimated_duration_seconds: int = Field(gt=0)
    sampling_interval_seconds: Literal[1, 10, 60]
    load_state: LoadState
    cargo_type: Literal["aggregates", "mixed_materials", "none"]

    @field_validator("scheduled_start_time")
    @classmethod
    def require_start_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scheduled_start_time must include timezone information")
        return value


class TelemetryEvent(QualityTelemetry):
    schema_version: Literal["3.2"] = SCHEMA_VERSION
    event_id: UUID
    asset_id: str = Field(pattern=r"^FG-WGN-\d{4}$")
    journey_id: str = Field(pattern=r"^FG-JNY-\d{8}-\d{4}$")
    route_id: str = Field(pattern=r"^FG-RTE-[A-Z0-9-]+$")
    event_time: datetime
    generated_at: datetime
    sampling_interval_seconds: Literal[1, 10, 60]
    travel_direction: TravelDirection
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
    rail_condition: RailCondition
    estimated_adhesion_coefficient: float = Field(ge=0, le=0.6)
    brake_pipe_pressure_bar: float | None = Field(ge=0, le=6)
    auxiliary_reservoir_pressure_bar: float | None = Field(ge=0, le=6)
    secondary_reservoir_pressure_bar: float | None = Field(ge=0, le=6)
    battery_voltage_v: float = Field(ge=3.0, le=4.2)
    power_source: PowerSource
    available_axle_generators: int = Field(default=4, ge=0, le=4)
    brake_demand: Literal["apply", "release"] = "release"
    bogies: tuple[BogieTelemetry, BogieTelemetry]
    controller: ControllerTelemetry

    @field_validator("event_time", "generated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include timezone information")
        return value

    @model_validator(mode="after")
    def validate_relationships(self) -> Self:
        if self.generated_at < self.event_time:
            raise ValueError("generated_at cannot precede event_time")
        if self.operating_state == OperatingState.STATIONARY and self.speed_kph > 1:
            raise ValueError("stationary events cannot have speed above 1 km/h")
        if {bogie.bogie_id for bogie in self.bogies} != {1, 2}:
            raise ValueError("telemetry requires bogies 1 and 2")
        return self


class ComponentObservation(QualityTelemetry):
    schema_version: Literal["3.2"] = SCHEMA_VERSION
    event_id: UUID
    event_time: datetime
    asset_id: str = Field(pattern=r"^FG-WGN-\d{4}$")
    journey_id: str = Field(pattern=r"^FG-JNY-\d{8}-\d{4}$")
    route_id: str = Field(pattern=r"^FG-RTE-[A-Z0-9-]+$")


class BogieObservation(ComponentObservation):
    bogie_id: Literal[1, 2]
    handbrake_equipped: bool
    speed_kph: float
    rail_condition: RailCondition
    estimated_adhesion_coefficient: float
    brake_pipe_pressure_bar: float | None
    auxiliary_reservoir_pressure_bar: float | None
    secondary_reservoir_pressure_bar: float | None
    brake_cylinder_pressure_bar: float | None


class AxleObservation(ComponentObservation):
    bogie_id: Literal[1, 2]
    axle_position: AxlePosition
    rotational_speed_rpm: float | None
    wheel_speed_kph: float | None
    axle_load_tonnes: float
    vibration_rms_g: float


class WheelObservation(ComponentObservation):
    bogie_id: Literal[1, 2]
    axle_position: AxlePosition
    wheel_side: WheelSide
    diameter_mm: float
    bearing_temp_c: float


class AnomalyTruth(ContractModel):
    schema_version: Literal["3.2"] = SCHEMA_VERSION
    event_id: UUID
    asset_id: str = Field(pattern=r"^FG-WGN-\d{4}$")
    true_adhesion_coefficient: float = Field(ge=0, le=0.6)
    is_anomaly: bool
    anomaly_type: AnomalyType
    anomaly_severity: AnomalySeverity
    affected_component: str | None = None
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
    def validate_consistency(self) -> Self:
        if self.is_anomaly:
            if self.anomaly_type == AnomalyType.NONE:
                raise ValueError("anomalous records require an anomaly type")
            if self.anomaly_severity == AnomalySeverity.NONE:
                raise ValueError("anomalous records require a severity")
            if self.affected_signal is None or self.anomaly_start_time is None:
                raise ValueError("anomalous records require an affected signal and start time")
        elif any(
            (
                self.anomaly_type != AnomalyType.NONE,
                self.anomaly_severity != AnomalySeverity.NONE,
                self.affected_component is not None,
                self.affected_signal is not None,
                self.anomaly_start_time is not None,
                self.anomaly_progress != 0,
            )
        ):
            raise ValueError("healthy records require empty anomaly fields and zero progress")
        return self


class MissingReportTruth(ContractModel):
    """Synthetic truth only: an expected report that was never emitted."""

    schema_version: Literal["3.2"] = SCHEMA_VERSION
    event_id: UUID
    asset_id: str
    expected_at: datetime
    scenario_id: str
    anomaly_type: AnomalyType
    anomaly_severity: AnomalySeverity

    @field_validator("expected_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("expected_at must be timezone-aware")
        return value


class OutageTruth(ContractModel):
    """Half-open [start, end) missing-report interval within this dataset."""

    schema_version: Literal["3.2"] = SCHEMA_VERSION
    asset_id: str
    scenario_id: str
    anomaly_type: AnomalyType
    start_time: datetime
    end_time_exclusive: datetime
    recovered: bool
    missing_reports: int = Field(gt=0)

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if self.start_time.utcoffset() is None or self.end_time_exclusive.utcoffset() is None:
            raise ValueError("outage timestamps must be timezone-aware")
        if self.end_time_exclusive <= self.start_time:
            raise ValueError("outage end must follow start")
        return self
