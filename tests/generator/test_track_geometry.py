import json
from datetime import UTC, datetime
from importlib.resources import files

import pytest

from fleetguard.generator import (
    generate_fleet_assets,
    generate_healthy_batch,
    generate_healthy_journey,
)
from fleetguard.generator.route import (
    DEFAULT_ROUTES,
    create_journey_plan,
    interpolate_route,
    journey_speed_at,
    journey_state_at,
)


@pytest.mark.parametrize("route", DEFAULT_ROUTES, ids=lambda r: r.route_id)
@pytest.mark.parametrize("reverse", [False, True])
def test_motion_integral_matches_track_distance_and_dwells(route, reverse):
    plan = create_journey_plan(42, route=route, allow_reverse=False)
    if reverse:
        from dataclasses import replace

        plan = replace(plan, reverse=True)
    travelled = 0.0
    for second in range(plan.duration_seconds - 1):
        v0 = journey_speed_at(plan, second)
        v1 = journey_speed_at(plan, second + 1)
        travelled += 0.5 * (v0 + v1) / 3600
        _, state, progress, _ = journey_state_at(plan, second + 1)
        assert progress * route.distance_km == pytest.approx(travelled, abs=1e-7)
        if state == "stationary":
            assert v1 == 0
    assert travelled == pytest.approx(route.distance_km, abs=1e-7)
    assert plan.duration_seconds % 60 == 0
    assert interpolate_route(route, 0, reverse) == (
        route.points[-1 if reverse else 0].latitude,
        route.points[-1 if reverse else 0].longitude,
    )


def test_fixture_is_attributed_and_routes_preserve_endpoints():
    data = json.loads(
        files("fleetguard.generator")
        .joinpath("data/uk_rail_routes.geojson")
        .read_text(encoding="utf-8")
    )
    assert data["metadata"]["source_commit"] == "a7c2cece9df7770e68a78cd716604c96ae38cd1a"
    expected = [
        ("London Aggregate Terminal", "Avonmouth Freight Terminal"),
        ("Avonmouth Freight Terminal", "Cardiff"),
        ("Cardiff", "Swansea Materials Terminal"),
        ("London Aggregate Terminal", "Swansea Materials Terminal"),
    ]
    for route, terminals in zip(DEFAULT_ROUTES, expected, strict=True):
        assert (route.points[0].name, route.points[-1].name) == terminals
        assert len(route.points) > 1000
        assert all(
            b > a for a, b in zip(route.cumulative_km, route.cumulative_km[1:], strict=False)
        )
        assert all(0 < i < len(route.points) - 1 for i in route.intermediate_stop_indices)


def test_operational_telemetry_uses_the_same_motion_profile():
    route = DEFAULT_ROUTES[1]
    plan = create_journey_plan(42, route=route)
    asset = generate_fleet_assets(1, 42)[0]
    batch = generate_healthy_journey(
        asset, datetime(2026, 1, 1, tzinfo=UTC), plan, sampling_interval_seconds=10
    )
    for event in batch.events:
        second = int((event.event_time - batch.events[0].event_time).total_seconds())
        assert event.speed_kph == pytest.approx(journey_speed_at(plan, second), abs=0.00051)
        _, _, progress, _ = journey_state_at(plan, second)
        lat, lon = interpolate_route(route, progress, plan.reverse)
        assert event.latitude == pytest.approx(lat, abs=0.00000051)
        assert event.longitude == pytest.approx(lon, abs=0.00000051)


def test_fixed_period_helper_no_longer_moves_while_initially_stationary():
    asset = generate_fleet_assets(1, 42)[0]
    batch = generate_healthy_batch(
        asset, datetime(2026, 1, 1, tzinfo=UTC), 6, sampling_interval_seconds=10
    )
    assert len({(e.latitude, e.longitude) for e in batch.events}) == 1
    assert all(e.route_progress == 0 for e in batch.events)


def test_route_provenance_fingerprints_the_bundled_geometry():
    import hashlib

    from fleetguard.generator.route import route_provenance

    payload = files("fleetguard.generator").joinpath("data/uk_rail_routes.geojson").read_bytes()
    provenance = route_provenance()
    assert provenance["route_geometry_version"] == "2.0"
    assert provenance["motion_model_version"] == "2.0"
    assert provenance["route_geometry_sha256"] == hashlib.sha256(payload).hexdigest()
