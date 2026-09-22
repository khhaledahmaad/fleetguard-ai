import json

import pytest

from fleetguard.generator.cli import main


def test_cli_generates_dataset(tmp_path) -> None:
    output_dir = tmp_path / "cli-run"

    result = main(
        [
            "--assets",
            "1",
            "--seed",
            "42",
            "--start-time",
            "2026-01-01T06:00:00+00:00",
            "--sampling-interval-seconds",
            "60",
            "--output-dir",
            str(output_dir),
        ]
    )

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert result == 0
    assert manifest["counts"]["assets"] == 1
    assert manifest["sampling_interval_seconds"] == 60
    assert manifest["anomaly_profile"] == "none"

    truth_records = [
        json.loads(line)
        for line in (
            output_dir / "anomaly_truth.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]

    assert all(
        record["is_anomaly"] is False
        for record in truth_records
    )


def test_cli_rejects_naive_start_time(tmp_path) -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "--start-time",
                "2026-01-01T06:00:00",
                "--output-dir",
                str(tmp_path / "run"),
            ]
        )


def test_cli_rejects_unsupported_sampling_interval(
    tmp_path,
) -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "--start-time",
                "2026-01-01T06:00:00+00:00",
                "--sampling-interval-seconds",
                "5",
                "--output-dir",
                str(tmp_path / "run"),
            ]
        )


def test_cli_generates_reproducible_bearing_demo_dataset(
    tmp_path,
) -> None:
    output_dir = tmp_path / "bearing-demo"

    result = main(
        [
            "--assets",
            "2",
            "--seed",
            "42",
            "--start-time",
            "2026-01-01T06:00:00+00:00",
            "--sampling-interval-seconds",
            "60",
            "--anomaly-profile",
            "bearing-demo",
            "--output-dir",
            str(output_dir),
        ]
    )

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    truth_records = [
        json.loads(line)
        for line in (output_dir / "anomaly_truth.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]

    anomalous_records = [record for record in truth_records if record["is_anomaly"]]

    assert result == 0
    assert manifest["anomaly_profile"] == "bearing-demo"
    assert anomalous_records

    assert {record["asset_id"] for record in anomalous_records} == {"FG-WGN-0001"}

    assert {record["anomaly_type"] for record in anomalous_records} == {
        "bearing_degradation"
    }

    assert {record["affected_component"] for record in anomalous_records} == {
        "bogie:1/axle:outer/wheel:left"
    }

    assert max(record["anomaly_progress"] for record in anomalous_records) == 1.0

    wagon_two_truth = [
        record for record in truth_records if record["asset_id"] == "FG-WGN-0002"
    ]

    assert all(record["is_anomaly"] is False for record in wagon_two_truth)


def test_cli_rejects_unknown_anomaly_profile(
    tmp_path,
) -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "--start-time",
                "2026-01-01T06:00:00+00:00",
                "--anomaly-profile",
                "unknown",
                "--output-dir",
                str(tmp_path / "run"),
            ]
        )
