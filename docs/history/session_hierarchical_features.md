# FleetGuard hierarchical features — clean implementation

The old wagon-only pipeline has been removed. The active implementation is
hierarchical_models.py, hierarchical_aggregation.py, hierarchical_dataset.py,
and __main__.py. The hierarchical dataset now imports validate_portfolio directly
from portfolio.validation and write_json directly from portfolio.runner. No old
feature module is required.

## Apply and remove obsolete files

Merge the ZIP into C:\Users\khhal\fleetguard-ai, replacing matching files.
A ZIP cannot remove old files from your existing checkout. Then run these CMD
commands from the project root:

```cmd
if exist src\fleetguard\features\models.py del src\fleetguard\features\models.py
if exist src\fleetguard\features\aggregation.py del src\fleetguard\features\aggregation.py
if exist src\fleetguard\features\dataset.py del src\fleetguard\features\dataset.py
if exist tests\features\test_feature_models.py del tests\features\test_feature_models.py
if exist tests\features\test_models.py del tests\features\test_models.py
if exist tests\features\test_aggregation.py del tests\features\test_aggregation.py
if exist tests\features\test_dataset.py del tests\features\test_dataset.py
if exist docs\session_feature_dataset.md del docs\session_feature_dataset.md
```

Only the feature tests are removed. tests\contracts\test_models.py stays.
The conditional test_models.py command covers the original feature-test name;
it will do nothing if you already renamed it to test_feature_models.py.
Keep src\fleetguard\features\__init__.py and the hierarchical tests.
No raw/generated data or generator code is deleted.

## Verify

```cmd
python -m ruff check .
python -m pytest tests\features -v
python -m pytest -v
```

## Build and inspect

```cmd
python -m fleetguard.features build --input-dir data\generated\portfolio-v1 --output-dir data\features\portfolio-v2
python -m fleetguard.features validate --input-dir data\features\portfolio-v2
```

If portfolio-v2 already exists and is complete, validate it; do not rebuild into
the same non-empty folder. To repeat the build, use a fresh output path such as
portfolio-v2-check. The output remains 12 files: four component levels in each
of train, validation and test, plus feature_manifest.json. Every minute yields
1 wagon, 2 bogie, 4 axle and 8 wheel rows. Feature schema remains 2.0; cleanup
does not change the data calculations or output contract.

```cmd
python -c "import json; from pathlib import Path; f=Path(r'data\features\portfolio-v2\train_wheel_features.jsonl').open(encoding='utf-8'); print(json.dumps(json.loads(next(f)), indent=2)); f.close()"
```

The detailed policies and actual smoke example are in
`docs\hierarchical_feature_rules.md` and
`docs\hierarchical_minute_example.json`. Raw 10-second telemetry remains the
source for granular modelling. Minute summaries are an additional representation.
Anomaly truth stays separate; no model is trained by this command.

## Commit after green checks

```cmd
git add .
git commit -m "Remove obsolete wagon-only feature pipeline"
git push
```

## Full active implementation

### src/fleetguard/features/hierarchical_models.py

```python
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
```

### src/fleetguard/features/hierarchical_aggregation.py

```python
"""Explicit field policies and component-preserving minute aggregation."""

from collections import Counter
from datetime import datetime, timedelta
from statistics import mean

from fleetguard.contracts.models import AssetMetadata, TelemetryEvent
from fleetguard.features.hierarchical_models import (
    CategoricalSummary,
    ComponentWindow,
    LocationSummary,
    NumericSummary,
)
from fleetguard.generator.normalise import normalise_event

NUMERIC = {
    "wagon": (
        "route_progress",
        "speed_kph",
        "ambient_temp_c",
        "longitudinal_acceleration_mps2",
        "lateral_acceleration_mps2",
        "vertical_acceleration_mps2",
        "estimated_adhesion_coefficient",
        "brake_pipe_pressure_bar",
        "auxiliary_reservoir_pressure_bar",
        "secondary_reservoir_pressure_bar",
        "battery_voltage_v",
        "available_axle_generators",
        "controller_temperature_c",
        "controller_supply_voltage_v",
        "controller_uptime_seconds",
        "controller_reset_count",
        "controller_sensor_communication_error_count",
    ),
    "bogie": (
        "speed_kph",
        "estimated_adhesion_coefficient",
        "brake_pipe_pressure_bar",
        "auxiliary_reservoir_pressure_bar",
        "secondary_reservoir_pressure_bar",
        "brake_cylinder_pressure_bar",
    ),
    "axle": ("rotational_speed_rpm", "wheel_speed_kph", "axle_load_tonnes", "vibration_rms_g"),
    "wheel": ("bearing_temp_c",),
}
CATEGORICAL = {
    "wagon": (
        "travel_direction",
        "operating_state",
        "journey_phase",
        "rail_condition",
        "power_source",
        "brake_demand",
        "controller_health_status",
    ),
    "bogie": ("rail_condition",),
    "axle": (),
    "wheel": (),
}
STATIC = {"wagon": (), "bogie": ("handbrake_equipped",), "axle": (), "wheel": ("diameter_mm",)}
COUNTERS = {
    "controller_uptime_seconds",
    "controller_reset_count",
    "controller_sensor_communication_error_count",
}
COMMON_SOURCE = {
    "schema_version",
    "event_id",
    "event_time",
    "asset_id",
    "journey_id",
    "route_id",
}


def numeric_summary(values: list, qualities: list, counter: bool = False) -> NumericSummary:
    valid = []
    missing = invalid = 0
    codes = Counter()
    for value, quality in zip(values, qualities, strict=True):
        status = quality.get("status", "valid")
        if status == "invalid":
            invalid += 1
            if quality.get("raw_value") is not None:
                codes[str(quality["raw_value"])] += 1
        elif status == "missing" or value is None:
            missing += 1
        else:
            valid.append(float(value))
    positive = decreases = None
    if counter and valid:
        differences = [b - a for a, b in zip(valid, valid[1:], strict=False)]
        positive = sum(max(d, 0) for d in differences)
        decreases = sum(d < 0 for d in differences)
    return NumericSummary(
        valid_count=len(valid),
        missing_count=missing,
        invalid_count=invalid,
        invalid_raw_value_counts=dict(codes),
        mean=mean(valid) if valid else None,
        minimum=min(valid) if valid else None,
        maximum=max(valid) if valid else None,
        first=valid[0] if valid else None,
        last=valid[-1] if valid else None,
        observed_positive_change=positive,
        decrease_count=decreases,
    )


def categorical_summary(values: list[str]) -> CategoricalSummary:
    counts = dict(Counter(values))
    return CategoricalSummary(
        last=values[-1] if values else None,
        counts=counts,
        fractions={key: value / len(values) for key, value in counts.items()},
        transition_count=sum(a != b for a, b in zip(values, values[1:], strict=False)),
    )


def component_catalogue(asset: AssetMetadata) -> dict[tuple, dict]:
    """Known components and fixed metadata, including during silent windows."""
    components = {("wagon", None, None, None): {}}
    for bogie in sorted(asset.bogies, key=lambda b: b.bogie_id):
        components[("bogie", bogie.bogie_id, None, None)] = {
            "handbrake_equipped": bogie.handbrake_equipped,
        }
        for axle in sorted(bogie.axles, key=lambda a: a.axle_position):
            components[("axle", bogie.bogie_id, axle.axle_position, None)] = {}
            for wheel in sorted(axle.wheels, key=lambda w: w.wheel_side):
                components[("wheel", bogie.bogie_id, axle.axle_position, wheel.wheel_side)] = {
                    "diameter_mm": wheel.diameter_mm,
                }
    return components


def flatten_event(event: TelemetryEvent, asset: AssetMetadata) -> dict[tuple, dict]:
    wagon = event.model_dump(mode="json", exclude={"bogies", "controller"})
    for name, value in event.controller.model_dump(mode="json").items():
        wagon[f"controller_{name}"] = value
    output = {("wagon", None, None, None): wagon}
    normalised = normalise_event(event, asset)
    for level, observations in (
        ("bogie", normalised.bogies),
        ("axle", normalised.axles),
        ("wheel", normalised.wheels),
    ):
        for observation in observations:
            data = observation.model_dump(mode="json")
            key = (level, data["bogie_id"], data.get("axle_position"), data.get("wheel_side"))
            output[key] = data
    return output


def aggregate_components(
    events: tuple[TelemetryEvent, ...],
    *,
    asset: AssetMetadata,
    journey_id: str,
    route_id: str,
    split: str,
    window_start: datetime,
    sampling_interval_seconds: int,
) -> tuple[ComponentWindow, ...]:
    if sampling_interval_seconds not in (1, 10, 60):
        raise ValueError("unsupported sampling interval")
    end = window_start + timedelta(seconds=60)
    ordered = tuple(sorted(events, key=lambda e: e.event_time))
    ids, times = set(), set()
    catalogue = component_catalogue(asset)
    flattened = []
    for event in ordered:
        if (event.asset_id, event.journey_id, event.route_id) != (
            asset.asset_id,
            journey_id,
            route_id,
        ):
            raise ValueError("event identity does not match requested journey")
        if event.sampling_interval_seconds != sampling_interval_seconds:
            raise ValueError("sampling interval mismatch")
        if not window_start <= event.event_time < end:
            raise ValueError("report outside window")
        if (event.event_time - window_start).total_seconds() % sampling_interval_seconds:
            raise ValueError("report off sampling grid")
        if event.event_id in ids or event.event_time in times:
            raise ValueError("duplicate report")
        ids.add(event.event_id)
        times.add(event.event_time)
        data = flatten_event(event, asset)
        if set(data) != set(catalogue):
            raise ValueError("reported components do not match asset metadata")
        for key, static in catalogue.items():
            if any(data[key][name] != value for name, value in static.items()):
                raise ValueError("reported static attribute differs from asset metadata")
        flattened.append(data)
    rows = []
    for key, static in catalogue.items():
        level, bogie, axle, wheel = key
        readings = [data[key] for data in flattened]
        numeric = {
            name: numeric_summary(
                [r[name] for r in readings],
                [r.get("signal_quality", {}).get(name, {}) for r in readings],
                counter=name in COUNTERS,
            )
            for name in NUMERIC[level]
        }
        categorical = {
            name: categorical_summary([r[name] for r in readings]) for name in CATEGORICAL[level]
        }
        rows.append(
            ComponentWindow(
                level=level,
                split=split,
                asset_id=asset.asset_id,
                journey_id=journey_id,
                route_id=route_id,
                bogie_id=bogie,
                axle_position=axle,
                wheel_side=wheel,
                window_start=window_start,
                window_end=end,
                sampling_interval_seconds=sampling_interval_seconds,
                expected_reports=60 // sampling_interval_seconds,
                received_reports=len(ordered),
                report_completeness=len(ordered) / (60 // sampling_interval_seconds),
                source_event_ids=tuple(e.event_id for e in ordered),
                event_time_first=ordered[0].event_time if ordered else None,
                event_time_last=ordered[-1].event_time if ordered else None,
                generated_at_first=ordered[0].generated_at if ordered else None,
                generated_at_last=ordered[-1].generated_at if ordered else None,
                numeric=numeric,
                categorical=categorical,
                static_attributes=static,
                location=LocationSummary(
                    latitude_last=ordered[-1].latitude if ordered else None,
                    longitude_last=ordered[-1].longitude if ordered else None,
                    observed_at=ordered[-1].event_time if ordered else None,
                )
                if level == "wagon"
                else None,
            )
        )
    return tuple(rows)
```

### src/fleetguard/features/hierarchical_dataset.py

```python
"""Hierarchical feature build; raw telemetry is never overwritten."""

from collections import defaultdict
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path

from fleetguard.contracts.models import AssetMetadata, JourneyMetadata, TelemetryEvent
from fleetguard.features.hierarchical_aggregation import aggregate_components, component_catalogue
from fleetguard.features.hierarchical_models import LEVELS, ComponentWindow
from fleetguard.portfolio.planning import SPLITS
from fleetguard.portfolio.runner import write_json
from fleetguard.portfolio.validation import read_json, sha256, validate_portfolio

MULTIPLICITY = {"wagon": 1, "bogie": 2, "axle": 4, "wheel": 8}


def iter_journey_windows(events, asset, journey, split):
    start = journey.scheduled_start_time
    if start.second or start.microsecond:
        raise ValueError("journey start must align to a minute boundary")
    buckets = defaultdict(list)
    ids, times = set(), set()
    for event in events:
        if (event.asset_id, event.journey_id, event.route_id) != (
            asset.asset_id,
            journey.journey_id,
            journey.route_id,
        ):
            raise ValueError("event identity does not match journey")
        if event.sampling_interval_seconds != journey.sampling_interval_seconds:
            raise ValueError("event sampling interval does not match journey")
        elapsed = (event.event_time - start).total_seconds()
        if not 0 <= elapsed < journey.estimated_duration_seconds:
            raise ValueError("event outside journey horizon")
        if elapsed % journey.sampling_interval_seconds:
            raise ValueError("event off sampling grid")
        if event.event_id in ids or event.event_time in times:
            raise ValueError("duplicate journey report")
        ids.add(event.event_id)
        times.add(event.event_time)
        buckets[int(elapsed // 60)].append(event)
    for minute in range(journey.estimated_duration_seconds // 60):
        yield aggregate_components(
            tuple(buckets[minute]),
            asset=asset,
            journey_id=journey.journey_id,
            route_id=journey.route_id,
            split=split,
            window_start=start + timedelta(minutes=minute),
            sampling_interval_seconds=journey.sampling_interval_seconds,
        )


def component_key(row):
    return (row.level, row.bogie_id, row.axle_position, row.wheel_side)


def key_to_json(key, static):
    level, bogie, axle, wheel = key
    return {
        "level": level,
        "bogie_id": bogie,
        "axle_position": axle,
        "wheel_side": wheel,
        "static_attributes": static,
    }


def build_feature_dataset(input_dir: Path, output_dir: Path, progress=None) -> dict:
    source, output = input_dir.resolve(), output_dir.resolve()
    if output == source or source in output.parents:
        raise ValueError("feature output must be outside source dataset")
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty")
    if progress:
        progress("Validating original portfolio before hierarchical aggregation...")
    validate_portfolio(source)
    plan = read_json(source / "cohort_plan.json")
    output.mkdir(parents=True, exist_ok=True)
    entries, files = [], {}
    for split in SPLITS:
        counts = dict.fromkeys(LEVELS, 0)
        with ExitStack() as stack:
            streams = {
                level: stack.enter_context(
                    (output / f"{split}_{level}_features.jsonl").open(
                        "w", encoding="utf-8", newline="\n"
                    )
                )
                for level in LEVELS
            }
            for run in plan["runs"]:
                if run["split"] != split:
                    continue
                directory = source / run["relative_directory"]
                with (directory / "asset_metadata.jsonl").open(encoding="utf-8") as stream:
                    assets = tuple(AssetMetadata.model_validate_json(line) for line in stream)
                if len(assets) != 1 or assets[0].asset_id != run["asset_id"]:
                    raise ValueError("portfolio run must contain its one assigned asset")
                asset = assets[0]
                journey = JourneyMetadata.model_validate(
                    read_json(directory / "journey_metadata.json")
                )
                with (directory / "telemetry.jsonl").open(encoding="utf-8") as stream:
                    events = tuple(TelemetryEvent.model_validate_json(line) for line in stream)
                window_count = complete = partial = silent = used = 0
                for rows in iter_journey_windows(events, asset, journey, split):
                    wagon = rows[0]
                    window_count += 1
                    complete += wagon.report_completeness == 1
                    partial += 0 < wagon.report_completeness < 1
                    silent += wagon.received_reports == 0
                    used += wagon.received_reports
                    for row in rows:
                        streams[row.level].write(row.model_dump_json() + "\n")
                        counts[row.level] += 1
                if not window_count:
                    raise ValueError("journey must contain at least one full minute")
                entries.append(
                    {
                        "asset_id": asset.asset_id,
                        "journey_id": journey.journey_id,
                        "route_id": journey.route_id,
                        "split": split,
                        "window_start": journey.scheduled_start_time.isoformat(),
                        "sampling_interval_seconds": journey.sampling_interval_seconds,
                        "window_count": window_count,
                        "complete_windows": complete,
                        "partial_windows": partial,
                        "silent_windows": silent,
                        "received_reports_used": used,
                        "excluded_tail_seconds": journey.estimated_duration_seconds % 60,
                        "excluded_tail_reports": len(events) - used,
                        "components": [
                            key_to_json(key, static)
                            for key, static in component_catalogue(asset).items()
                        ],
                        "source_run_manifest_sha256": sha256(directory / "manifest.json")
                        if (directory / "manifest.json").exists()
                        else None,
                    }
                )
                if progress:
                    progress(f"{split}: {asset.asset_id} -> {window_count} minutes, 15 rows/minute")
        for level, count in counts.items():
            name = f"{split}_{level}_features.jsonl"
            files[name] = {"records": count, "sha256": sha256(output / name)}
    manifest = {
        "feature_schema_version": "2.0",
        "source_schema_version": "3.2",
        "window_seconds": 60,
        "window_boundary": "[start, end)",
        "tail_policy": "exclude incomplete minute",
        "source_plan_sha256": sha256(source / "cohort_plan.json"),
        "source_manifest_sha256": sha256(source / "cohort_manifest.json"),
        "files": files,
        "journeys": entries,
    }
    report = validate_feature_dataset(output, manifest=manifest)
    write_json(output / "feature_manifest.json", manifest)
    return report


def validate_feature_dataset(root: Path, manifest=None) -> dict:
    if manifest is None:
        manifest = read_json(root / "feature_manifest.json")
    if (manifest["feature_schema_version"], manifest["source_schema_version"]) != ("2.0", "3.2"):
        raise ValueError("unsupported feature manifest; expected version 2.0")
    if manifest["window_seconds"] != 60 or manifest["window_boundary"] != "[start, end)":
        raise ValueError("unsupported window policy")
    expected_files = {f"{split}_{level}_features.jsonl" for split in SPLITS for level in LEVELS}
    if set(manifest["files"]) != expected_files:
        raise ValueError("unexpected feature file list")
    entries, catalogues, assets = {}, {}, set()
    for entry in manifest["journeys"]:
        key = (entry["split"], entry["asset_id"], entry["journey_id"])
        if entry["asset_id"] in assets or key in entries or entry["split"] not in SPLITS:
            raise ValueError("duplicate asset or invalid split")
        catalogue = {}
        for c in entry["components"]:
            ck = (c["level"], c["bogie_id"], c["axle_position"], c["wheel_side"])
            if ck in catalogue:
                raise ValueError("duplicate catalogue component")
            catalogue[ck] = c["static_attributes"]
        if {level: sum(k[0] == level for k in catalogue) for level in LEVELS} != MULTIPLICITY:
            raise ValueError("catalogue must contain 1 wagon, 2 bogies, 4 axles and 8 wheels")
        expected_keys = {("wagon", None, None, None)}
        for b in (1, 2):
            expected_keys.add(("bogie", b, None, None))
            for a in ("inner", "outer"):
                expected_keys.add(("axle", b, a, None))
                for w in ("left", "right"):
                    expected_keys.add(("wheel", b, a, w))
        if set(catalogue) != expected_keys:
            raise ValueError("catalogue component identities are invalid")
        if entry["window_count"] <= 0:
            raise ValueError("journey must contain feature windows")
        entries[key], catalogues[key] = entry, catalogue
        assets.add(entry["asset_id"])
    totals, level_totals = {}, {}
    for split in SPLITS:
        lineage = {}
        level_totals[split] = {}
        observed_journeys = set()
        for level in LEVELS:
            name = f"{split}_{level}_features.jsonl"
            info = manifest["files"][name]
            if sha256(root / name) != info["sha256"]:
                raise ValueError(f"checksum mismatch: {name}")
            previous, stats, keys_seen = {}, defaultdict(CounterState), set()
            count = 0
            with (root / name).open(encoding="utf-8") as stream:
                for line in stream:
                    row = ComponentWindow.model_validate_json(line)
                    jk = (row.split, row.asset_id, row.journey_id)
                    if row.split != split or row.level != level or jk not in entries:
                        raise ValueError("feature identity or split mismatch")
                    entry, catalogue = entries[jk], catalogues[jk]
                    ck = component_key(row)
                    if ck not in catalogue or row.static_attributes != catalogue[ck]:
                        raise ValueError("component metadata mismatch")
                    start = datetime.fromisoformat(entry["window_start"])
                    elapsed = (row.window_start - start).total_seconds()
                    if elapsed % 60 or not 0 <= elapsed < entry["window_count"] * 60:
                        raise ValueError("window outside expected journey grid")
                    if (
                        row.route_id != entry["route_id"]
                        or row.sampling_interval_seconds != entry["sampling_interval_seconds"]
                    ):
                        raise ValueError("route or sampling mismatch")
                    series = (jk, ck)
                    expected_start = previous.get(series, start)
                    if row.window_start != expected_start:
                        raise ValueError("component windows must be consecutive and unique")
                    previous[series] = row.window_end
                    unique = (jk, ck, row.window_start)
                    if unique in keys_seen:
                        raise ValueError("duplicate component window")
                    keys_seen.add(unique)
                    lk = (jk, row.window_start)
                    fingerprint = (
                        row.source_event_ids,
                        row.received_reports,
                        row.event_time_first,
                        row.event_time_last,
                        row.generated_at_first,
                        row.generated_at_last,
                    )
                    if level == "wagon":
                        lineage[lk] = fingerprint
                    elif lineage.get(lk) != fingerprint:
                        raise ValueError("component lineage differs from parent wagon")
                    state = stats[jk]
                    state["rows"] += 1
                    state["used"] += row.received_reports
                    state["complete"] += row.report_completeness == 1
                    state["partial"] += 0 < row.report_completeness < 1
                    state["silent"] += row.received_reports == 0
                    observed_journeys.add(jk)
                    count += 1
            if count != info["records"]:
                raise ValueError("feature record count mismatch")
            for jk, entry in entries.items():
                if jk[0] != split:
                    continue
                multiplier = MULTIPLICITY[level]
                state = stats[jk]
                expected = {
                    "rows": entry["window_count"] * multiplier,
                    "used": entry["received_reports_used"] * multiplier,
                    "complete": entry["complete_windows"] * multiplier,
                    "partial": entry["partial_windows"] * multiplier,
                    "silent": entry["silent_windows"] * multiplier,
                }
                if dict(state) != expected:
                    raise ValueError("journey component counts mismatch")
                for ck in catalogues[jk]:
                    if ck[0] == level and previous.get((jk, ck)) != datetime.fromisoformat(
                        entry["window_start"]
                    ) + timedelta(minutes=entry["window_count"]):
                        raise ValueError("missing component windows")
            level_totals[split][level] = count
        if observed_journeys != {k for k in entries if k[0] == split}:
            raise ValueError("missing journey features")
        totals[split] = level_totals[split]["wagon"]
    return {
        "status": "passed",
        "assets": len(assets),
        "windows_by_split": totals,
        "records_by_split_level": level_totals,
    }


def CounterState():
    return {"rows": 0, "used": 0, "complete": 0, "partial": 0, "silent": 0}
```

### src/fleetguard/features/__main__.py

```python
import argparse
from pathlib import Path

from fleetguard.features.hierarchical_dataset import build_feature_dataset, validate_feature_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="FleetGuard hierarchical minute summaries, schema 2.0"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--input-dir", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--input-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            report = build_feature_dataset(args.input_dir, args.output_dir, progress=print)
        else:
            report = validate_feature_dataset(args.input_dir)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"FAILED: {error}")
        return 1
    print(f"Validation: {report['status']}")
    print(f"Assets: {report['assets']}")
    for split, count in report["windows_by_split"].items():
        print(f"{split}: {count} wagon minutes")
        if "records_by_split_level" in report:
            for level, records in report["records_by_split_level"][split].items():
                print(f"  {level}: {records} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### tests/features/test_hierarchical_features.py

```python
import json
from datetime import UTC, datetime

import pytest

from fleetguard.contracts.models import (
    AxleObservation,
    AxleTelemetry,
    BogieObservation,
    BogieTelemetry,
    ControllerTelemetry,
    JourneyMetadata,
    TelemetryEvent,
    WheelObservation,
    WheelTelemetry,
)
from fleetguard.features.hierarchical_aggregation import (
    CATEGORICAL,
    COMMON_SOURCE,
    NUMERIC,
    STATIC,
    aggregate_components,
)
from fleetguard.features.hierarchical_dataset import (
    build_feature_dataset,
    iter_journey_windows,
    validate_feature_dataset,
)
from fleetguard.generator import generate_fleet_assets, generate_healthy_batch
from fleetguard.portfolio.validation import sha256

START = datetime(2026, 1, 1, 6, tzinfo=UTC)


@pytest.fixture
def example():
    asset = generate_fleet_assets(1, 42)[0]
    events = generate_healthy_batch(asset, START, periods=6, sampling_interval_seconds=10).events
    return asset, events


def aggregate(asset, events):
    return aggregate_components(
        events,
        asset=asset,
        journey_id=events[0].journey_id,
        route_id=events[0].route_id,
        split="train",
        window_start=START,
        sampling_interval_seconds=10,
    )


def row_for(rows, level, bogie=None, axle=None, wheel=None):
    return next(
        r
        for r in rows
        if (r.level, r.bogie_id, r.axle_position, r.wheel_side) == (level, bogie, axle, wheel)
    )


def test_every_original_telemetry_field_has_a_policy():
    wagon_handled = (
        set(NUMERIC["wagon"])
        | set(CATEGORICAL["wagon"])
        | COMMON_SOURCE
        | {
            "generated_at",
            "sampling_interval_seconds",
            "latitude",
            "longitude",
            "signal_quality",
            "bogies",
            "controller",
        }
    )
    wagon_handled = {n for n in wagon_handled if not n.startswith("controller_")}
    assert set(TelemetryEvent.model_fields) == wagon_handled
    controller_handled = {
        n.removeprefix("controller_")
        for n in NUMERIC["wagon"] + CATEGORICAL["wagon"]
        if n.startswith("controller_")
    }
    assert set(ControllerTelemetry.model_fields) == controller_handled
    assert set(BogieTelemetry.model_fields) == {
        "signal_quality",
        "bogie_id",
        "handbrake_equipped",
        "brake_cylinder_pressure_bar",
        "axles",
    }
    assert set(AxleTelemetry.model_fields) == set(NUMERIC["axle"]) | {
        "signal_quality",
        "axle_position",
        "wheels",
    }
    assert set(WheelTelemetry.model_fields) == set(NUMERIC["wheel"]) | {"wheel_side"}
    for level, model, identity in (
        ("bogie", BogieObservation, {"bogie_id"}),
        ("axle", AxleObservation, {"bogie_id", "axle_position"}),
        ("wheel", WheelObservation, {"bogie_id", "axle_position", "wheel_side"}),
    ):
        assert set(model.model_fields) == (
            set(NUMERIC[level])
            | set(CATEGORICAL[level])
            | set(STATIC[level])
            | COMMON_SOURCE
            | identity
            | {"signal_quality"}
        )


def test_exact_component_multiplicity_and_lineage(example):
    asset, events = example
    rows = aggregate(asset, events)
    assert {level: sum(r.level == level for r in rows) for level in NUMERIC} == {
        "wagon": 1,
        "bogie": 2,
        "axle": 4,
        "wheel": 8,
    }
    assert all(r.source_event_ids == tuple(e.event_id for e in events) for r in rows)
    assert all(r.received_reports == 6 and r.report_completeness == 1 for r in rows)


def test_wheel_temperature_is_not_mixed_with_other_wheels(example):
    asset, events = example
    changed = []
    for index, event in enumerate(events):
        data = event.model_dump(mode="json")
        data["bogies"][0]["axles"][0]["wheels"][0]["bearing_temp_c"] = 30 + index * 10
        changed.append(TelemetryEvent.model_validate(data))
    changed = tuple(changed)
    target = events[0].bogies[0].axles[0]
    wheel = target.wheels[0].wheel_side
    rows = aggregate(asset, changed)
    original = aggregate(asset, events)
    selected = row_for(rows, "wheel", 1, target.axle_position, wheel)
    assert selected.numeric["bearing_temp_c"].mean == 55
    assert selected.numeric["bearing_temp_c"].maximum == 80
    assert selected.numeric["bearing_temp_c"].last == 80
    for old, new in zip(original, rows, strict=True):
        if new != selected:
            assert new == old


def test_coordinates_are_last_observed_pair_not_independent_maxima(example):
    asset, events = example
    changed = []
    for index, event in enumerate(events):
        data = event.model_dump(mode="json")
        data.update(latitude=52 - index / 10, longitude=-2 + index / 10)
        changed.append(TelemetryEvent.model_validate(data))
    wagon = aggregate(asset, tuple(changed))[0]
    assert wagon.location.latitude_last == 51.5
    assert wagon.location.longitude_last == -1.5
    assert wagon.location.observed_at == events[-1].event_time


def test_brake_demand_categories_and_counter_decrease(example):
    asset, events = example
    changed = []
    for index, event in enumerate(events):
        data = event.model_dump(mode="json")
        data["brake_demand"] = "apply" if index < 3 else "release"
        data["controller"]["uptime_seconds"] = (100, 110, 120, 0, 10, 20)[index]
        changed.append(TelemetryEvent.model_validate(data))
    wagon = aggregate(asset, tuple(changed))[0]
    demand = wagon.categorical["brake_demand"]
    assert demand.counts == {"apply": 3, "release": 3}
    assert demand.fractions == {"apply": 0.5, "release": 0.5}
    assert demand.last == "release" and demand.transition_count == 1
    counter = wagon.numeric["controller_uptime_seconds"]
    assert counter.decrease_count == 1
    assert counter.observed_positive_change == 40


def test_invalid_pressure_retains_code_counts_and_excludes_code_from_values(example):
    asset, events = example
    data = events[0].model_dump(mode="json")
    data["brake_pipe_pressure_bar"] = None
    data["signal_quality"]["brake_pipe_pressure_bar"] = {"status": "invalid", "raw_value": 255}
    changed = (TelemetryEvent.model_validate(data),) + events[1:]
    rows = aggregate(asset, changed)
    for level, bogie in (("wagon", None), ("bogie", 1), ("bogie", 2)):
        summary = row_for(rows, level, bogie).numeric["brake_pipe_pressure_bar"]
        assert summary.valid_count == 5 and summary.invalid_count == 1
        assert summary.missing_count == 0
        assert sum(summary.invalid_raw_value_counts.values()) == 1
        assert summary.maximum < 6


def test_silent_window_has_no_readings_but_retains_known_component_metadata(example):
    asset, events = example
    rows = aggregate_components(
        (),
        asset=asset,
        journey_id=events[0].journey_id,
        route_id=events[0].route_id,
        split="test",
        window_start=START,
        sampling_interval_seconds=10,
    )
    assert len(rows) == 15
    assert all(r.received_reports == 0 and r.source_event_ids == () for r in rows)
    assert all(s.mean is None and s.missing_count == 0 for r in rows for s in r.numeric.values())
    assert all(s.counts == {} for r in rows for s in r.categorical.values())
    assert rows[0].location.latitude_last is None
    assert all("diameter_mm" in r.static_attributes for r in rows if r.level == "wheel")


def test_reversed_input_gives_same_ordered_features(example):
    asset, events = example
    assert aggregate(asset, events) == aggregate(asset, tuple(reversed(events)))


@pytest.mark.parametrize("interval", [1, 10, 60])
def test_sampling_profiles(interval):
    asset = generate_fleet_assets(1, 42)[0]
    events = generate_healthy_batch(
        asset, START, periods=60 // interval, sampling_interval_seconds=interval
    ).events
    rows = aggregate_components(
        events,
        asset=asset,
        journey_id=events[0].journey_id,
        route_id=events[0].route_id,
        split="train",
        window_start=START,
        sampling_interval_seconds=interval,
    )
    assert all(r.received_reports == 60 // interval for r in rows)


def journey_for(events, duration=130):
    return JourneyMetadata(
        journey_id=events[0].journey_id,
        route_id=events[0].route_id,
        origin_terminal="Origin",
        destination_terminal="Destination",
        travel_direction="forward",
        scheduled_start_time=START,
        estimated_duration_seconds=duration,
        sampling_interval_seconds=10,
        load_state="empty",
        cargo_type="none",
    )


def test_missing_minute_and_final_tail_preserve_hierarchy(example):
    asset, events = example
    journey = journey_for(events)
    rows = list(iter_journey_windows(events, asset, journey, "train"))
    assert len(rows) == 2 and all(len(r) == 15 for r in rows)
    assert all(r.received_reports == 0 for r in rows[1])


@pytest.fixture
def files(tmp_path, monkeypatch):
    source, output = tmp_path / "source", tmp_path / "summary"
    source.mkdir()
    runs = []
    for index, split in enumerate(("train", "validation", "test"), 1):
        asset = generate_fleet_assets(1, 42)[0].model_copy(
            update={"asset_id": f"FG-WGN-{index:04d}"}
        )
        events = generate_healthy_batch(
            asset, START, periods=13, sampling_interval_seconds=10
        ).events
        relative = f"runs/{split}/{asset.asset_id}"
        directory = source / relative
        directory.mkdir(parents=True)
        (directory / "asset_metadata.jsonl").write_text(asset.model_dump_json() + "\n")
        (directory / "journey_metadata.json").write_text(journey_for(events).model_dump_json())
        (directory / "telemetry.jsonl").write_text(
            "".join(e.model_dump_json() + "\n" for e in events)
        )
        runs.append({"asset_id": asset.asset_id, "split": split, "relative_directory": relative})
    (source / "cohort_plan.json").write_text(json.dumps({"runs": runs}))
    (source / "cohort_manifest.json").write_text("{}")
    monkeypatch.setattr(
        "fleetguard.features.hierarchical_dataset.validate_portfolio", lambda _: None
    )
    return source, output


def test_full_file_build_and_validation_preserve_raw_data(files):
    source, output = files
    before = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    report = build_feature_dataset(source, output)
    assert report == validate_feature_dataset(output)
    assert report["windows_by_split"] == {"train": 2, "validation": 2, "test": 2}
    assert all(
        v == {"wagon": 2, "bogie": 4, "axle": 8, "wheel": 16}
        for v in report["records_by_split_level"].values()
    )
    after = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    assert before == after
    manifest = json.loads((output / "feature_manifest.json").read_text())
    assert all(e["excluded_tail_reports"] == 1 for e in manifest["journeys"])


def test_build_is_repeatable(files):
    source, output = files
    build_feature_dataset(source, output)
    repeat = output.parent / "repeat"
    build_feature_dataset(source, repeat)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == {
        p.name: p.read_bytes() for p in repeat.iterdir()
    }


def test_rejects_changed_component_identity_even_after_rehash(files):
    source, output = files
    build_feature_dataset(source, output)
    path = output / "train_wheel_features.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["wheel_side"] = "right"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    mp = output / "feature_manifest.json"
    manifest = json.loads(mp.read_text())
    manifest["files"][path.name]["sha256"] = sha256(path)
    mp.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        validate_feature_dataset(output)


def test_rejects_mixed_parent_lineage_even_after_rehash(files):
    source, output = files
    build_feature_dataset(source, output)
    path = output / "train_axle_features.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["source_event_ids"][0] = "00000000-0000-0000-0000-000000000000"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    mp = output / "feature_manifest.json"
    manifest = json.loads(mp.read_text())
    manifest["files"][path.name]["sha256"] = sha256(path)
    mp.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="lineage"):
        validate_feature_dataset(output)


def test_existing_output_is_not_overwritten(files):
    source, output = files
    build_feature_dataset(source, output)
    with pytest.raises(ValueError, match="must be empty"):
        build_feature_dataset(source, output)
```

