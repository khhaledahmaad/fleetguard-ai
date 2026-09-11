from datetime import UTC, datetime
from statistics import mean

import pytest

from fleetguard.contracts import (
    AnomalySeverity,
    AnomalyType,
    OperatingState,
)
from fleetguard.generator import generate_fleet_assets, generate_healthy_batch


def make_asset():
    return generate_fleet_assets(1, 42)[0]


def test_generates_requested_number_of_records() -> None:
    batch = generate_healthy_batch(
        asset=make_asset(),
        start_time=datetime(2026, 1, 1, tzinfo=UTC),
        periods=60,
    )

    assert len(batch.events) == 60
    assert len(batch.truth) == 60


def test_events_are_one_minute_apart() -> None:
    batch = generate_healthy_batch(
        asset=make_asset(),
        start_time=datetime(2026, 1, 1, tzinfo=UTC),
        periods=3,
    )

    gap = batch.events[1].event_time - batch.events[0].event_time

    assert gap.total_seconds() == 60


def test_same_seed_produces_identical_batch() -> None:
    arguments = {
        "asset": make_asset(),
        "start_time": datetime(2026, 1, 1, tzinfo=UTC),
        "periods": 60,
        "seed": 500,
    }

    first_batch = generate_healthy_batch(**arguments)
    second_batch = generate_healthy_batch(**arguments)

    assert first_batch == second_batch


def test_different_seed_changes_generated_values() -> None:
    asset = make_asset()
    start_time = datetime(2026, 1, 1, tzinfo=UTC)

    first_batch = generate_healthy_batch(
        asset,
        start_time,
        periods=60,
        seed=500,
    )
    second_batch = generate_healthy_batch(
        asset,
        start_time,
        periods=60,
        seed=501,
    )

    assert first_batch != second_batch


def test_operating_cycle_contains_all_states() -> None:
    batch = generate_healthy_batch(
        asset=make_asset(),
        start_time=datetime(2026, 1, 1, tzinfo=UTC),
        periods=60,
    )

    states = {event.operating_state for event in batch.events}

    assert states == {
        OperatingState.STATIONARY,
        OperatingState.MOVING,
        OperatingState.BRAKING,
    }

    stationary_events = [
        event for event in batch.events if event.operating_state == OperatingState.STATIONARY
    ]

    assert all(event.speed_kph <= 1 for event in stationary_events)


def test_braking_signals_follow_expected_relationships() -> None:
    batch = generate_healthy_batch(
        asset=make_asset(),
        start_time=datetime(2026, 1, 1, tzinfo=UTC),
        periods=60,
    )

    moving_events = [
        event for event in batch.events if event.operating_state == OperatingState.MOVING
    ]
    braking_events = [
        event for event in batch.events if event.operating_state == OperatingState.BRAKING
    ]

    assert mean(event.brake_pipe_pressure_bar for event in braking_events) < mean(
        event.brake_pipe_pressure_bar for event in moving_events
    )

    assert mean(event.bogies[0].brake_cylinder_pressure_bar for event in braking_events) > mean(
        event.bogies[0].brake_cylinder_pressure_bar for event in moving_events
    )


def test_ground_truth_matches_every_event() -> None:
    batch = generate_healthy_batch(
        asset=make_asset(),
        start_time=datetime(2026, 1, 1, tzinfo=UTC),
        periods=60,
    )

    for event, truth in zip(batch.events, batch.truth, strict=True):
        assert truth.event_id == event.event_id
        assert truth.asset_id == event.asset_id
        assert truth.is_anomaly is False
        assert truth.anomaly_type == AnomalyType.NONE
        assert truth.anomaly_severity == AnomalySeverity.NONE


@pytest.mark.parametrize("periods", [0, -1])
def test_periods_must_be_positive(periods: int) -> None:
    with pytest.raises(ValueError, match="periods must be at least 1"):
        generate_healthy_batch(
            asset=make_asset(),
            start_time=datetime(2026, 1, 1, tzinfo=UTC),
            periods=periods,
        )


def test_start_time_must_have_timezone() -> None:
    with pytest.raises(
        ValueError,
        match="start_time must include timezone information",
    ):
        generate_healthy_batch(
            asset=make_asset(),
            start_time=datetime(2026, 1, 1),
            periods=1,
        )
