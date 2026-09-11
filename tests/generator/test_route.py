from datetime import UTC, datetime

from fleetguard.contracts import JourneyPhase, OperatingState
from fleetguard.generator import (
    LONDON_SWANSEA_FREIGHT_ROUTE,
    create_journey_plan,
    create_random_journey_plan,
    generate_fleet_assets,
    generate_healthy_journey,
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


def test_journey_includes_terminals_running_braking_and_intermediate_dwells() -> None:
    asset = generate_fleet_assets(1, 42)[0]
    journey = create_journey_plan(42, allow_reverse=False)
    batch = generate_healthy_journey(asset, datetime(2026, 1, 1, tzinfo=UTC), journey)

    phases = {event.journey_phase for event in batch.events}
    states = {event.operating_state for event in batch.events}

    assert len(batch.events) == journey.duration_minutes
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
        wheelset.rotational_speed_rpm == 0
        for bogie in stationary.bogies
        for wheelset in bogie.wheelsets
    )
    assert all(
        wheelset.rotational_speed_rpm > 0 for bogie in moving.bogies for wheelset in bogie.wheelsets
    )


def test_pneumatic_and_controller_channels_are_present() -> None:
    asset = generate_fleet_assets(1, 42)[0]
    journey = create_journey_plan(42, allow_reverse=False)
    batch = generate_healthy_journey(asset, datetime(2026, 1, 1, tzinfo=UTC), journey)
    braking = [event for event in batch.events if event.operating_state == "braking"]

    assert braking
    assert all(event.auxiliary_reservoir_pressure_bar > 0 for event in braking)
    assert all(event.secondary_reservoir_pressure_bar > 0 for event in braking)
    assert all(event.controller.health_status == "healthy" for event in batch.events)
