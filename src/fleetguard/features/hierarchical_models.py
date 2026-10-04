"""Version 2: minute summaries with explicit component identities and quality."""

from datetime import datetime, timedelta
from typing import Literal, Self
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from fleetguard.contracts.models import ContractModel

FEATURE_SCHEMA_VERSION = "2.0"
LEVELS = ("wagon", "bogie", "axle", "wheel")


class NumericSummary(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    valid_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    invalid_count: int = Field(ge=0)
    invalid_raw_value_counts: dict[str, int] = Field(default_factory=dict)
    mean: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    first: float | None = None
    last: float | None = None
    # Counter-only summaries. Changes are between valid observations in this window.
    observed_positive_change: float | None = None
    decrease_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_statistics(self) -> Self:
        values = (self.mean, self.minimum, self.maximum, self.first, self.last)
        if self.valid_count == 0:
            if any(v is not None for v in values):
                raise ValueError("no valid readings means no numerical statistics")
            if self.observed_positive_change is not None or self.decrease_count is not None:
                raise ValueError("unobserved counters cannot have changes")
        else:
            if any(v is None for v in values):
                raise ValueError("valid readings require numerical statistics")
            if not self.minimum <= self.mean <= self.maximum:
                raise ValueError("mean must be within the observed range")
            if any(not self.minimum <= v <= self.maximum for v in (self.first, self.last)):
                raise ValueError("first and last must be within the observed range")
        if any(count <= 0 for count in self.invalid_raw_value_counts.values()):
            raise ValueError("raw-code counts must be positive")
        if sum(self.invalid_raw_value_counts.values()) > self.invalid_count:
            raise ValueError("raw-code counts cannot exceed invalid readings")
        return self


class CategoricalSummary(ContractModel):
    last: str | None
    counts: dict[str, int]
    fractions: dict[str, float]
    transition_count: int = Field(ge=0)

    @model_validator(mode="after")
    def valid_categories(self) -> Self:
        total = sum(self.counts.values())
        if any(v <= 0 for v in self.counts.values()):
            raise ValueError("category counts must be positive")
        if set(self.counts) != set(self.fractions):
            raise ValueError("category counts and fractions must have the same keys")
        if not total:
            if self.last is not None or self.transition_count:
                raise ValueError("unobserved categories must be empty")
        else:
            if self.last not in self.counts or self.transition_count >= total:
                raise ValueError("invalid last category or transition count")
            if any(abs(self.fractions[k] - v / total) > 1e-9 for k, v in self.counts.items()):
                raise ValueError("category fractions must match counts")
        return self


class LocationSummary(ContractModel):
    latitude_last: float | None = Field(ge=-90, le=90)
    longitude_last: float | None = Field(ge=-180, le=180)
    observed_at: datetime | None

    @model_validator(mode="after")
    def paired_coordinates(self) -> Self:
        present = tuple(
            v is not None for v in (self.latitude_last, self.longitude_last, self.observed_at)
        )
        if len(set(present)) != 1:
            raise ValueError("coordinates and observation time must be present together")
        return self


class ComponentWindow(ContractModel):
    feature_schema_version: Literal["2.0"] = FEATURE_SCHEMA_VERSION
    source_schema_version: Literal["3.2"] = "3.2"
    level: Literal["wagon", "bogie", "axle", "wheel"]
    split: Literal["train", "validation", "test"]
    asset_id: str = Field(pattern=r"^FG-WGN-\d{4}$")
    journey_id: str = Field(pattern=r"^FG-JNY-\d{8}-\d{4}$")
    route_id: str
    bogie_id: Literal[1, 2] | None = None
    axle_position: Literal["inner", "outer"] | None = None
    wheel_side: Literal["left", "right"] | None = None
    window_start: datetime
    window_end: datetime
    sampling_interval_seconds: Literal[1, 10, 60]
    expected_reports: int = Field(gt=0)
    received_reports: int = Field(ge=0)
    report_completeness: float = Field(ge=0, le=1)
    source_event_ids: tuple[UUID, ...]
    event_time_first: datetime | None
    event_time_last: datetime | None
    generated_at_first: datetime | None
    generated_at_last: datetime | None
    numeric: dict[str, NumericSummary]
    categorical: dict[str, CategoricalSummary]
    static_attributes: dict[str, float | bool]
    location: LocationSummary | None = None

    @model_validator(mode="after")
    def valid_window(self) -> Self:
        from fleetguard.features.hierarchical_aggregation import CATEGORICAL, NUMERIC, STATIC

        if self.window_start.utcoffset() is None or self.window_end.utcoffset() is None:
            raise ValueError("window timestamps must be timezone-aware")
        if self.window_start.second or self.window_start.microsecond:
            raise ValueError("window must align to a minute boundary")
        if self.window_end - self.window_start != timedelta(seconds=60):
            raise ValueError("window must span 60 seconds")
        if self.expected_reports != 60 // self.sampling_interval_seconds:
            raise ValueError("unexpected report count for sampling interval")
        if self.received_reports > self.expected_reports:
            raise ValueError("too many reports")
        if abs(self.report_completeness - self.received_reports / self.expected_reports) > 1e-9:
            raise ValueError("completeness does not match counts")
        identities = (
            self.bogie_id is not None,
            self.axle_position is not None,
            self.wheel_side is not None,
        )
        if (
            identities
            != {
                "wagon": (False, False, False),
                "bogie": (True, False, False),
                "axle": (True, True, False),
                "wheel": (True, True, True),
            }[self.level]
        ):
            raise ValueError("component identity does not match level")
        if set(self.numeric) != set(NUMERIC[self.level]):
            raise ValueError("numeric signals do not match level contract")
        if set(self.categorical) != set(CATEGORICAL[self.level]):
            raise ValueError("categorical signals do not match level contract")
        if set(self.static_attributes) != set(STATIC[self.level]):
            raise ValueError("static attributes do not match level contract")
        if len(self.source_event_ids) != self.received_reports:
            raise ValueError("source lineage count mismatch")
        if len(set(self.source_event_ids)) != len(self.source_event_ids):
            raise ValueError("duplicate source lineage")
        for summary in self.numeric.values():
            if (
                summary.valid_count + summary.missing_count + summary.invalid_count
                != self.received_reports
            ):
                raise ValueError("sensor quality counts must equal received reports")
        for summary in self.categorical.values():
            if sum(summary.counts.values()) != self.received_reports:
                raise ValueError("category counts must equal received reports")
        observed = (
            self.event_time_first,
            self.event_time_last,
            self.generated_at_first,
            self.generated_at_last,
        )
        if not self.received_reports:
            if any(t is not None for t in observed):
                raise ValueError("silent window cannot contain observed timestamps")
        else:
            if any(t is None or t.utcoffset() is None for t in observed):
                raise ValueError("observed timestamps must be timezone-aware")
            if (
                not self.window_start
                <= self.event_time_first
                <= self.event_time_last
                < self.window_end
            ):
                raise ValueError("observed timestamps outside window")
        if self.level == "wagon":
            if self.location is None:
                raise ValueError("wagon requires location summary")
            if self.location.observed_at != self.event_time_last:
                raise ValueError("location must come from last report")
        elif self.location is not None:
            raise ValueError("location belongs to wagon level")
        return self
