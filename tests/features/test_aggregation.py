from datetime import UTC, datetime, timedelta
from statistics import mean

import pytest

from fleetguard.contracts.models import TelemetryEvent
from fleetguard.features.aggregation import aggregate_window
from fleetguard.generator import generate_fleet_assets, generate_healthy_batch

START = datetime(2026, 1, 1, 6, 0, tzinfo=UTC)


@pytest.fixture
def events() -> tuple[TelemetryEvent, ...]:
    asset = generate_fleet_assets(1, 42)[0]

    return generate_healthy_batch(
        asset=asset,
        start_time=START,
        periods=6,
        sampling_interval_seconds=10,
    ).events


def aggregate(events: tuple[TelemetryEvent, ...]):
    return aggregate_window(
        events,
        asset_id="FG-WGN-0001",
        journey_id=events[0].journey_id,
        split="train",
        window_start=START,
        sampling_interval_seconds=10,
    )


def test_calculates_complete_window(events) -> None:
    result = aggregate(events)

    temperatures = [
        wheel.bearing_temp_c - event.ambient_temp_c
        for event in events
        for bogie in event.bogies
        for axle in bogie.axles
        for wheel in axle.wheels
    ]

    vibrations = [
        axle.vibration_rms_g
        for event in events
        for bogie in event.bogies
        for axle in bogie.axles
    ]

    assert result.received_reports == 6
    assert result.report_completeness == 1.0
    assert result.speed_mean_kph == pytest.approx(
        mean(event.speed_kph for event in events)
    )
    assert result.bearing_temp_above_ambient_max_c == max(temperatures)
    assert result.vibration_max_g == max(vibrations)
    assert result.unavailable_axle_speed_fraction == 0.0
    assert result.unavailable_pressure_fraction == 0.0


def test_calculates_incomplete_window(events) -> None:
    result = aggregate(events[:4])

    assert result.received_reports == 4
    assert result.report_completeness == pytest.approx(4 / 6)
    assert result.speed_mean_kph == pytest.approx(
        mean(event.speed_kph for event in events[:4])
    )


def test_empty_window_contains_no_invented_measurements(events) -> None:
    result = aggregate_window(
        (),
        asset_id=events[0].asset_id,
        journey_id=events[0].journey_id,
        split="train",
        window_start=START,
        sampling_interval_seconds=10,
    )

    assert result.received_reports == 0
    assert result.report_completeness == 0.0
    assert result.speed_mean_kph is None
    assert result.brake_pipe_pressure_min_bar is None
    assert result.unavailable_pressure_fraction is None


def test_unavailable_pressure_is_excluded_from_minimum(events) -> None:
    changed = []

    for event in events:
        data = event.model_dump(mode="json")
        data["brake_pipe_pressure_bar"] = None
        data["signal_quality"]["brake_pipe_pressure_bar"] = {
            "status": "invalid",
            "raw_value": 255,
        }
        changed.append(TelemetryEvent.model_validate(data))

    result = aggregate(tuple(changed))

    assert result.brake_pipe_pressure_min_bar is None
    assert result.unavailable_pressure_fraction == pytest.approx(1 / 5)


def test_unavailable_axle_speed_is_excluded_from_comparison(events) -> None:
    changed = []

    for event in events:
        data = event.model_dump(mode="json")
        axle = data["bogies"][0]["axles"][0]

        axle["wheel_speed_kph"] = None
        axle["rotational_speed_rpm"] = None
        axle["signal_quality"].update(
            {
                "wheel_speed_kph": {"status": "missing"},
                "rotational_speed_rpm": {"status": "missing"},
            }
        )
        changed.append(TelemetryEvent.model_validate(data))

    result = aggregate(tuple(changed))

    assert result.unavailable_axle_speed_fraction == pytest.approx(1 / 4)
    assert result.axle_speed_difference_max_kph is not None


def test_rejects_duplicate_report(events) -> None:
    with pytest.raises(ValueError, match="duplicate report"):
        aggregate((events[0], events[0]))


def test_excludes_next_minute_boundary(events) -> None:
    boundary_event = events[0].model_copy(
        update={"event_time": START + timedelta(minutes=1)}
    )

    with pytest.raises(ValueError, match="outside the window"):
        aggregate((boundary_event,))


def test_rejects_off_grid_report(events) -> None:
    off_grid = events[0].model_copy(update={"event_time": START + timedelta(seconds=5)})

    with pytest.raises(ValueError, match="off the sampling grid"):
        aggregate((off_grid,))


def test_rejects_different_wagon(events) -> None:
    other_wagon = events[0].model_copy(update={"asset_id": "FG-WGN-0002"})

    with pytest.raises(ValueError, match="requested wagon and journey"):
        aggregate((other_wagon,))


def test_report_order_does_not_change_features(events) -> None:
    assert aggregate(events) == aggregate(tuple(reversed(events)))
