import hashlib
import json
from datetime import UTC, datetime

import pytest

from fleetguard.generator import (
    build_journey_metadata,
    create_random_journey_plan,
    generate_fleet_assets,
    generate_healthy_journey_fleet,
)
from fleetguard.generator.output import write_generation_run


def generate_run(output_dir):
    start_time = datetime(2026, 1, 1, 6, tzinfo=UTC)
    assets = generate_fleet_assets(1, 42)

    journey = create_random_journey_plan(
        42,
        service_date=start_time.date(),
    )

    metadata = build_journey_metadata(
        journey,
        start_time,
        60,
    )

    batch = generate_healthy_journey_fleet(
        assets,
        start_time,
        journey,
        sampling_interval_seconds=60,
    )

    return write_generation_run(
        output_dir,
        batch,
        metadata,
        seed=42,
    )


def test_writer_creates_complete_versioned_run(
    tmp_path,
) -> None:
    manifest = generate_run(tmp_path / "run")

    expected = {
        "asset_metadata.jsonl",
        "journey_metadata.json",
        "telemetry.jsonl",
        "anomaly_truth.jsonl",
        "bogie_observations.jsonl",
        "axle_observations.jsonl",
        "wheel_observations.jsonl",
        "manifest.json",
    }

    assert {path.name for path in (tmp_path / "run").iterdir()} == expected

    assert manifest["schema_version"] == "3.0"
    assert manifest["feature_window_seconds"] == 60


def test_manifest_counts_follow_component_hierarchy(
    tmp_path,
) -> None:
    manifest = generate_run(tmp_path / "run")
    event_count = manifest["counts"]["telemetry_events"]

    assert manifest["counts"]["truth_records"] == event_count

    assert manifest["counts"]["bogie_observations"] == event_count * 2

    assert manifest["counts"]["axle_observations"] == event_count * 4

    assert manifest["counts"]["wheel_observations"] == event_count * 8


def test_manifest_hashes_match_written_files(
    tmp_path,
) -> None:
    output_dir = tmp_path / "run"
    manifest = generate_run(output_dir)

    for filename, details in manifest["files"].items():
        actual = hashlib.sha256((output_dir / filename).read_bytes()).hexdigest()

        assert actual == details["sha256"]

    stored_manifest = json.loads(
        (output_dir / "manifest.json").read_text(encoding="utf-8")
    )

    assert stored_manifest == manifest


def test_same_arguments_produce_identical_files(
    tmp_path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    generate_run(first)
    generate_run(second)

    for first_file in first.iterdir():
        second_file = second / first_file.name

        assert first_file.read_bytes() == second_file.read_bytes()


def test_non_empty_output_directory_is_rejected(
    tmp_path,
) -> None:
    output_dir = tmp_path / "run"
    output_dir.mkdir()

    (output_dir / "existing.txt").write_text(
        "keep",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="output directory is not empty",
    ):
        generate_run(output_dir)
