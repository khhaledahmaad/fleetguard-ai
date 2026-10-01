from datetime import datetime, timedelta
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from fleetguard.contracts.models import ContractModel


class WindowFeatures(ContractModel):
    """Observable telemetry summaries for one wagon and one minute."""

    feature_schema_version: Literal["1.0"] = "1.0"

    asset_id: str = Field(pattern=r"^FG-WGN-\d{4}$")
    journey_id: str = Field(pattern=r"^FG-JNY-\d{8}-\d{4}$")
    split: Literal["train", "validation", "test"]

    window_start: datetime
    window_end: datetime
    sampling_interval_seconds: Literal[1, 10, 60]

    expected_reports: int = Field(gt=0)
    received_reports: int = Field(ge=0)
    report_completeness: float = Field(ge=0, le=1)

    speed_mean_kph: float | None = Field(default=None, ge=0)
    bearing_temp_above_ambient_max_c: float | None = None
    vibration_max_g: float | None = Field(default=None, ge=0)
    axle_speed_difference_max_kph: float | None = Field(default=None, ge=0)

    brake_pipe_pressure_min_bar: float | None = Field(default=None, ge=0)
    brake_cylinder_pressure_max_bar: float | None = Field(default=None, ge=0)
    auxiliary_reservoir_pressure_min_bar: float | None = Field(default=None, ge=0)
    secondary_reservoir_pressure_min_bar: float | None = Field(default=None, ge=0)

    battery_voltage_min_v: float | None = Field(default=None, ge=0)
    controller_supply_voltage_min_v: float | None = Field(default=None, ge=0)

    unavailable_axle_speed_fraction: float | None = Field(default=None, ge=0, le=1)
    unavailable_pressure_fraction: float | None = Field(default=None, ge=0, le=1)

    @field_validator("window_start", "window_end")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("window timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.window_end - self.window_start != timedelta(seconds=60):
            raise ValueError("feature windows must span exactly 60 seconds")

        if self.window_start.second != 0 or self.window_start.microsecond != 0:
            raise ValueError("window_start must align to a minute boundary")

        if self.expected_reports != 60 // self.sampling_interval_seconds:
            raise ValueError("expected_reports must match the sampling interval")

        if self.received_reports > self.expected_reports:
            raise ValueError("received_reports cannot exceed expected_reports")

        expected_completeness = self.received_reports / self.expected_reports

        if abs(self.report_completeness - expected_completeness) > 1e-9:
            raise ValueError("report_completeness must match report counts")

        if self.received_reports == 0:
            measurement_fields = (
                "speed_mean_kph",
                "bearing_temp_above_ambient_max_c",
                "vibration_max_g",
                "axle_speed_difference_max_kph",
                "brake_pipe_pressure_min_bar",
                "brake_cylinder_pressure_max_bar",
                "auxiliary_reservoir_pressure_min_bar",
                "secondary_reservoir_pressure_min_bar",
                "battery_voltage_min_v",
                "controller_supply_voltage_min_v",
                "unavailable_axle_speed_fraction",
                "unavailable_pressure_fraction",
            )

            if any(getattr(self, name) is not None for name in measurement_fields):
                raise ValueError("empty windows cannot contain measurements")

        return self
