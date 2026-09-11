from collections import Counter
from datetime import UTC, datetime

import pytest

from fleetguard.contracts import OperatingState
from fleetguard.generator import (
    OperatingCycle,
    generate_fleet_assets,
    generate_healthy_batch,
    generate_healthy_fleet,
)


def test_fleet_assets_are_reproducible() -> None:
    first = generate_fleet_assets(asset_count=5, seed=42)
    second = generate_fleet_assets(asset_count=5, seed=42)

    assert first == second


def test_fleet_assets_have_unique_identities() -> None:
    assets = generate_fleet_assets(asset_count=24, seed=42)

    asset_ids = {asset.asset_id for asset in assets}
    generator_seeds = {asset.generator_seed for asset in assets}

    assert len(assets) == 24
    assert len(asset_ids) == 24
    assert len(generator_seeds) == 24
    assert assets[0].asset_id == "FG-WGN-0001"
    assert assets[-1].asset_id == "FG-WGN-0024"


def test_fleet_contains_controlled_heterogeneity() -> None:
    assets = generate_fleet_assets(asset_count=24, seed=42)

    assert len({asset.commissioning_age_years for asset in assets}) > 1
    assert len({asset.nominal_load_tonnes for asset in assets}) > 1
    assert len({asset.bearing_baseline_temp_c for asset in assets}) > 1
    assert len({asset.vibration_baseline_g for asset in assets}) > 1


def test_each_wagon_has_two_bogies_four_wheelsets_and_one_handbrake_bogie() -> None:
    assets = generate_fleet_assets(asset_count=5, seed=42)

    for asset in assets:
        assert len(asset.bogies) == 2
        assert sum(bogie.handbrake_equipped for bogie in asset.bogies) == 1
        assert sum(len(bogie.wheelsets) for bogie in asset.bogies) == 4
        for bogie in asset.bogies:
            for wheelset in bogie.wheelsets:
                difference = abs(wheelset.left_wheel.diameter_mm - wheelset.right_wheel.diameter_mm)
                assert difference <= 2


def test_healthy_fleet_contains_every_asset_and_event() -> None:
    assets = generate_fleet_assets(asset_count=3, seed=42)

    fleet = generate_healthy_fleet(
        assets=assets,
        start_time=datetime(2026, 1, 1, tzinfo=UTC),
        periods=60,
    )

    assert len(fleet.assets) == 3
    assert len(fleet.events) == 180
    assert len(fleet.truth) == 180

    generated_asset_ids = {event.asset_id for event in fleet.events}
    expected_asset_ids = {asset.asset_id for asset in assets}

    assert generated_asset_ids == expected_asset_ids


def test_custom_cycle_controls_state_durations() -> None:
    cycle = OperatingCycle(
        initial_stationary_minutes=2,
        moving_minutes=5,
        braking_minutes=4,
        recovery_stationary_minutes=4,
    )
    asset = generate_fleet_assets(asset_count=1, seed=42)[0]

    batch = generate_healthy_batch(
        asset=asset,
        start_time=datetime(2026, 1, 1, tzinfo=UTC),
        periods=cycle.total_minutes,
        cycle=cycle,
    )

    state_counts = Counter(event.operating_state for event in batch.events)

    assert cycle.total_minutes == 15
    assert state_counts[OperatingState.STATIONARY] == 6
    assert state_counts[OperatingState.MOVING] == 5
    assert state_counts[OperatingState.BRAKING] == 4


def test_generated_state_transitions_are_valid() -> None:
    asset = generate_fleet_assets(asset_count=1, seed=42)[0]

    batch = generate_healthy_batch(
        asset=asset,
        start_time=datetime(2026, 1, 1, tzinfo=UTC),
        periods=180,
    )

    allowed_transitions = {
        (OperatingState.STATIONARY, OperatingState.STATIONARY),
        (OperatingState.STATIONARY, OperatingState.MOVING),
        (OperatingState.MOVING, OperatingState.MOVING),
        (OperatingState.MOVING, OperatingState.BRAKING),
        (OperatingState.BRAKING, OperatingState.BRAKING),
        (OperatingState.BRAKING, OperatingState.STATIONARY),
    }

    transitions = zip(
        batch.events,
        batch.events[1:],
        strict=False,
    )

    assert all(
        (current.operating_state, following.operating_state) in allowed_transitions
        for current, following in transitions
    )


@pytest.mark.parametrize("asset_count", [0, -1, 10000])
def test_invalid_asset_count_is_rejected(asset_count: int) -> None:
    with pytest.raises(
        ValueError,
        match="asset_count must be between 1 and 9999",
    ):
        generate_fleet_assets(asset_count=asset_count, seed=42)


def test_duplicate_asset_ids_are_rejected() -> None:
    asset = generate_fleet_assets(asset_count=1, seed=42)[0]

    with pytest.raises(ValueError, match="asset IDs must be unique"):
        generate_healthy_fleet(
            assets=(asset, asset),
            start_time=datetime(2026, 1, 1, tzinfo=UTC),
            periods=60,
        )
