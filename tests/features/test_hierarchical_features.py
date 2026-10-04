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
