from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from fleetguard.features.models import WindowFeatures


def window_data() -> dict:
    start = datetime(2026, 1, 1, 6, 0, tzinfo=UTC)

    return {
        "asset_id": "FG-WGN-0001",
        "journey_id": "FG-JNY-20260101-0001",
        "split": "train",
        "window_start": start,
        "window_end": start + timedelta(seconds=60),
        "sampling_interval_seconds": 10,
        "expected_reports": 6,
        "received_reports": 6,
        "report_completeness": 1.0,
        "speed_mean_kph": 45.0,
        "bearing_temp_above_ambient_max_c": 30.0,
        "vibration_max_g": 0.3,
        "axle_speed_difference_max_kph": 0.5,
    }


def test_accepts_complete_window() -> None:
    window = WindowFeatures(**window_data())

    assert window.received_reports == 6
    assert window.report_completeness == 1.0


@pytest.mark.parametrize(
    ("interval", "expected"),
    [(1, 60), (10, 6), (60, 1)],
)
def test_supports_sampling_profiles(interval: int, expected: int) -> None:
    data = window_data()
    data.update(
        sampling_interval_seconds=interval,
        expected_reports=expected,
        received_reports=expected,
    )

    assert WindowFeatures(**data).expected_reports == expected


def test_accepts_incomplete_window() -> None:
    data = window_data()
    data.update(received_reports=4, report_completeness=4 / 6)

    assert WindowFeatures(**data).received_reports == 4


def test_accepts_empty_window_without_measurements() -> None:
    data = window_data()
    data.update(received_reports=0, report_completeness=0.0)

    for name in (
        "speed_mean_kph",
        "bearing_temp_above_ambient_max_c",
        "vibration_max_g",
        "axle_speed_difference_max_kph",
    ):
        data[name] = None

    window = WindowFeatures(**data)

    assert window.speed_mean_kph is None
    assert window.report_completeness == 0.0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expected_reports", 5),
        ("received_reports", 7),
        ("report_completeness", 0.5),
        ("unavailable_axle_speed_fraction", 1.1),
        ("split", "unknown"),
        ("is_anomaly", True),
        ("anomaly_type", "locked_axle"),
        ("scenario_id", "FG-ANO-001"),
    ],
)
def test_rejects_invalid_counts_and_truth_fields(
    field: str,
    value: object,
) -> None:
    data = window_data()
    data[field] = value

    with pytest.raises(ValidationError):
        WindowFeatures(**data)


def test_rejects_empty_window_with_measurements() -> None:
    data = window_data()
    data.update(received_reports=0, report_completeness=0.0)

    with pytest.raises(ValidationError):
        WindowFeatures(**data)


def test_rejects_wrong_window_duration() -> None:
    data = window_data()
    data["window_end"] = data["window_start"] + timedelta(seconds=90)

    with pytest.raises(ValidationError):
        WindowFeatures(**data)


def test_rejects_unaligned_window() -> None:
    data = window_data()
    data["window_start"] += timedelta(seconds=10)
    data["window_end"] += timedelta(seconds=10)

    with pytest.raises(ValidationError):
        WindowFeatures(**data)


def test_rejects_naive_timestamp() -> None:
    data = window_data()
    data["window_start"] = data["window_start"].replace(tzinfo=None)

    with pytest.raises(ValidationError):
        WindowFeatures(**data)
