from datetime import UTC, datetime

import pytest

from fleetguard.contracts import JourneyPhase, OperatingState
from fleetguard.generator import (
    LONDON_SWANSEA_FREIGHT_ROUTE,
    build_journey_metadata,
    create_journey_plan,
    create_random_journey_plan,
    generate_fleet_assets,
    generate_healthy_journey,
    normalise_event,
)


def test_journey_duration_is_route_driven_and_reproducible() -> None:
    first = create_journey_plan(42)
    second = create_journey_plan(42)

    assert first == second
    assert first.duration_minutes > 60
    assert LONDON_SWANSEA_FREIGHT_ROUTE.distance_km > 250


def test_random_plans_select_different_operational_duties() -> None:
    plans = {create_random_journey_plan(seed).route.route_id for seed in range(20)}

    assert len(plans) > 1


def test_journey_metadata_uses_standard_sampling_profile() -> None:
    journey = create_journey_plan(42)
    metadata = build_journey_metadata(
        journey,
        datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert metadata.schema_version == "3.0"
    assert metadata.sampling_interval_seconds == 10
    assert metadata.estimated_duration_seconds == journey.duration_seconds


def test_journey_includes_terminals_running_braking_and_intermediate_dwells() -> None:
    asset = generate_fleet_assets(1, 42)[0]
    journey = create_journey_plan(42, allow_reverse=False)
    batch = generate_healthy_journey(asset, datetime(2026, 1, 1, tzinfo=UTC), journey)

    phases = {event.journey_phase for event in batch.events}
    states = {event.operating_state for event in batch.events}

    assert len(batch.events) == journey.duration_seconds // 10
    assert phases == {
        JourneyPhase.ORIGIN_DWELL,
        JourneyPhase.RUNNING,
        JourneyPhase.INTERMEDIATE_DWELL,
        JourneyPhase.DESTINATION_DWELL,
    }
    assert states == {
        OperatingState.STATIONARY,
        OperatingState.MOVING,
        OperatingState.BRAKING,
    }
    assert batch.events[0].route_progress == 0
    assert batch.events[-1].route_progress == 1
    assert (batch.events[0].latitude, batch.events[0].longitude) != (
        batch.events[-1].latitude,
        batch.events[-1].longitude,
    )


def test_wheel_rpm_and_stationary_behaviour_are_physically_consistent() -> None:
    asset = generate_fleet_assets(1, 42)[0]
    journey = create_journey_plan(42, allow_reverse=False)
    batch = generate_healthy_journey(asset, datetime(2026, 1, 1, tzinfo=UTC), journey)

    stationary = next(event for event in batch.events if event.operating_state == "stationary")
    moving = next(event for event in batch.events if event.operating_state == "moving")

    assert all(
        axle.rotational_speed_rpm == 0 for bogie in stationary.bogies for axle in bogie.axles
    )
    assert all(axle.rotational_speed_rpm > 0 for bogie in moving.bogies for axle in bogie.axles)


def test_pneumatic_and_controller_channels_are_present() -> None:
    asset = generate_fleet_assets(1, 42)[0]
    journey = create_journey_plan(42, allow_reverse=False)
    batch = generate_healthy_journey(asset, datetime(2026, 1, 1, tzinfo=UTC), journey)
    braking = [event for event in batch.events if event.operating_state == "braking"]

    assert braking
    assert all(event.auxiliary_reservoir_pressure_bar > 0 for event in braking)
    assert all(event.secondary_reservoir_pressure_bar > 0 for event in braking)
    assert all(event.controller.health_status == "healthy" for event in batch.events)


@pytest.mark.parametrize("interval", [1, 10, 60])
def test_supported_sampling_intervals_control_event_count(interval: int) -> None:
    asset = generate_fleet_assets(1, 42)[0]
    journey = create_journey_plan(42, allow_reverse=False)
    batch = generate_healthy_journey(
        asset,
        datetime(2026, 1, 1, tzinfo=UTC),
        journey,
        sampling_interval_seconds=interval,
    )

    assert len(batch.events) == journey.duration_seconds // interval
    assert batch.events[0].sampling_interval_seconds == interval
    assert (batch.events[1].event_time - batch.events[0].event_time).total_seconds() == interval


def test_invalid_sampling_interval_is_rejected() -> None:
    asset = generate_fleet_assets(1, 42)[0]
    journey = create_journey_plan(42)

    with pytest.raises(ValueError, match="must be one of 1, 10 or 60"):
        generate_healthy_journey(
            asset,
            datetime(2026, 1, 1, tzinfo=UTC),
            journey,
            sampling_interval_seconds=5,
        )


def test_event_normalises_to_two_bogies_four_axles_and_eight_wheels() -> None:
    asset = generate_fleet_assets(1, 42)[0]
    journey = create_journey_plan(42)
    event = generate_healthy_journey(
        asset,
        datetime(2026, 1, 1, tzinfo=UTC),
        journey,
        sampling_interval_seconds=60,
    ).events[0]

    rows = normalise_event(event, asset)

    assert len(rows.bogies) == 2
    assert len(rows.axles) == 4
    assert len(rows.wheels) == 8
