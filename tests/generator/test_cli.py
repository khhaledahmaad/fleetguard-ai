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
