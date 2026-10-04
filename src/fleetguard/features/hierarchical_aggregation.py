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
