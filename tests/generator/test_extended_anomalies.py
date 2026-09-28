from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from fleetguard.contracts import AnomalySeverity, AnomalyType, TelemetryEvent
from fleetguard.generator import (
    build_journey_metadata,
    create_random_journey_plan,
    generate_fleet_assets,
    generate_healthy_journey_fleet,
    inject_fleet_anomaly_scenarios,
)
from fleetguard.generator.anomalies import (
    AnomalyScenario,
    ComponentTarget,
    inject_anomaly_scenarios,
)
from fleetguard.generator.normalise import normalise_event
from fleetguard.generator.output import write_generation_run
from fleetguard.generator.profiles import NEW_PROFILES, build_demo_scenario

START = datetime(2026, 1, 1, 6, tzinfo=UTC)


@pytest.fixture(scope="module")
def healthy():
    return generate_healthy_journey_fleet(
        generate_fleet_assets(2, 42), START, create_random_journey_plan(42), 60
    )


def scenario(profile, healthy, **changes):
    return replace(build_demo_scenario(profile, healthy.events), **changes)


def inject(profile, healthy, **changes):
    s = scenario(profile, healthy, **changes)
    return inject_fleet_anomaly_scenarios(healthy, (s,))


def pairs(batch, baseline):
    originals = {e.event_id: e for e in baseline.events}
    return [
        (originals[e.event_id], e, t)
        for e, t in zip(batch.events, batch.truth, strict=True)
        if t.is_anomaly
    ]


@pytest.mark.parametrize("profile", NEW_PROFILES)
def test_all_profiles_preserve_controls_baseline_and_lineage(profile, healthy):
    before = healthy.events
    batch = inject(profile, healthy)
    assert batch.truth != healthy.truth or batch.missing_reports
    assert batch.events == inject(profile, healthy).events
    assert batch.missing_reports == inject(profile, healthy).missing_reports
    assert healthy.events == before
    assert [e for e in batch.events if e.asset_id == "FG-WGN-0002"] == [
        e for e in healthy.events if e.asset_id == "FG-WGN-0002"
    ]
    assert len(batch.events) + len(batch.missing_reports) == len(healthy.events)
    assert {e.event_id for e in batch.events}.isdisjoint(m.event_id for m in batch.missing_reports)
    assert {e.event_id for e in batch.events} | {m.event_id for m in batch.missing_reports} == {
        e.event_id for e in healthy.events
    }
    for event, truth in zip(batch.events, batch.truth, strict=True):
        assert event.event_id == truth.event_id
        assert event.asset_id == truth.asset_id
        assert TelemetryEvent.model_validate_json(event.model_dump_json()) == event
        rows = normalise_event(event, healthy.assets[int(event.asset_id[-4:]) - 1])
        assert (len(rows.bogies), len(rows.axles), len(rows.wheels)) == (2, 4, 8)


@pytest.mark.parametrize("encoding", ["missing", "invalid"])
def test_speed_generator_failure_is_unavailable_not_a_locked_axle(healthy, encoding):
    batch = inject("axle-generator-demo", healthy, failure_encoding=encoding)
    original, event, truth = pairs(batch, healthy)[0]
    axle = event.bogies[0].axles[0]
    assert axle.wheel_speed_kph is None and axle.rotational_speed_rpm is None
    assert axle.signal_quality["wheel_speed_kph"].status == encoding
    assert axle.signal_quality["wheel_speed_kph"].raw_value == (
        255 if encoding == "invalid" else None
    )
    assert axle.wheels == original.bogies[0].axles[0].wheels
    assert axle.vibration_rms_g == original.bogies[0].axles[0].vibration_rms_g
    assert event.bogies[1] == original.bogies[1]
    assert event.bogies[0].axles[1] == original.bogies[0].axles[1]
    assert event.speed_kph == original.speed_kph > 0
    assert event.available_axle_generators == 3
    assert event.controller == original.controller
    assert "wheel:" not in truth.affected_component


def test_slide_and_locked_axle_have_distinct_valid_speeds(healthy):
    for profile in ("wheel-slide-demo", "locked-axle-demo"):
        batch = inject(profile, healthy)
        for original, event, _ in pairs(batch, healthy):
            axle = event.bogies[0].axles[0]
            assert not axle.signal_quality
            assert event.speed_kph == original.speed_kph > 5
            if profile == "wheel-slide-demo":
                assert event.brake_demand == "apply"
                assert 0 < axle.wheel_speed_kph < event.speed_kph
                assert axle.rotational_speed_rpm > 0
            else:
                assert axle.wheel_speed_kph == axle.rotational_speed_rpm == 0
            assert event.bogies[1] == original.bogies[1]
    slide = inject("wheel-slide-demo", healthy)
    end = slide.scenarios[0].end_time
    assert all(
        not t.is_anomaly
        for e, t in zip(slide.events, slide.truth, strict=True)
        if e.event_time >= end
    )


def test_wheel_flat_is_axle_evidence_without_wheel_claim(healthy):
    for original, event, truth in pairs(inject("wheel-flat-demo", healthy), healthy):
        before, after = original.bogies[0].axles[0], event.bogies[0].axles[0]
        assert after.vibration_rms_g > before.vibration_rms_g
        assert after.wheels == before.wheels
        assert after.wheel_speed_kph == before.wheel_speed_kph
        assert "wheel:" not in truth.affected_component


@pytest.mark.parametrize(
    "signal,bogie",
    [
        ("brake_pipe_pressure_bar", None),
        ("auxiliary_reservoir_pressure_bar", None),
        ("secondary_reservoir_pressure_bar", None),
        ("brake_cylinder_pressure_bar", 1),
        ("brake_cylinder_pressure_bar", 2),
    ],
)
def test_transducer_failure_changes_only_target_and_quality(healthy, signal, bogie):
    target = ComponentTarget("FG-WGN-0001", bogie_id=bogie, signal_name=signal)
    batch = inject("pressure-transducer-demo", healthy, target=target)
    original, event, _ = pairs(batch, healthy)[0]
    before = original.model_dump()
    after = event.model_dump()
    node_before = before if bogie is None else before["bogies"][bogie - 1]
    node_after = after if bogie is None else after["bogies"][bogie - 1]
    assert node_after[signal] is None
    assert node_after["signal_quality"][signal] == {"status": "invalid", "raw_value": 255.0}
    node_after[signal] = node_before[signal]
    node_after["signal_quality"] = node_before["signal_quality"]
    assert after == before
    rows = normalise_event(event, healthy.assets[0])
    affected_rows = rows.bogies if bogie is None else (rows.bogies[bogie - 1],)
    assert all(getattr(row, signal) is None for row in affected_rows)
    assert all(row.signal_quality[signal].status == "invalid" for row in affected_rows)


def test_release_failure_needs_prior_brake_application(healthy):
    s = scenario(
        "brake-release-demo", healthy, start_time=START, end_time=START + timedelta(minutes=5)
    )
    batch = inject_fleet_anomaly_scenarios(healthy, (s,))
    first_application = next(e.event_time for e in healthy.events if e.brake_demand == "apply")
    assert all(
        not t.is_anomaly
        for e, t in zip(batch.events, batch.truth, strict=True)
        if e.event_time < first_application
    )
    for original, event, truth in pairs(batch, healthy):
        assert event.brake_demand == "release"
        assert event.brake_pipe_pressure_bar == original.brake_pipe_pressure_bar
        assert event.bogies[0].brake_cylinder_pressure_bar > 0.5
        assert event.bogies[1] == original.bogies[1]
        assert truth.affected_component == "wagon:brake_system"


def test_undemanded_application_combines_demand_bpp_and_both_bcp(healthy):
    for original, event, truth in pairs(inject("undemanded-brake-demo", healthy), healthy):
        assert event.brake_demand == "release"
        assert event.brake_pipe_pressure_bar < original.brake_pipe_pressure_bar
        assert all(b.brake_cylinder_pressure_bar > 0.5 for b in event.bogies)
        assert truth.affected_component == "wagon:brake_system"


def test_persistent_controller_sags_then_never_reports_again(healthy):
    batch = inject("controller-persistent-demo", healthy)
    s = batch.scenarios[0]
    assert len(batch.outages) == 1 and not batch.outages[0].recovered
    sag = [(a, b) for a, b, _ in pairs(batch, healthy)]
    assert sag[-1][1].controller.supply_voltage_v < sag[0][1].controller.supply_voltage_v
    for original, event in sag:
        assert event.battery_voltage_v == original.battery_voltage_v
        assert event.bogies == original.bogies
    assert all(e.event_time < s.end_time for e in batch.events if e.asset_id == s.target.asset_id)


def test_bounded_controller_has_gap_then_one_reboot(healthy):
    batch = inject("controller-bounded-demo", healthy)
    s = batch.scenarios[0]
    assert len(batch.outages) == 1 and batch.outages[0].recovered
    assert all(
        not (s.start_time <= e.event_time < s.recovery_time)
        for e in batch.events
        if e.asset_id == s.target.asset_id
    )
    recovered = [
        e
        for e in batch.events
        if e.asset_id == s.target.asset_id and e.event_time >= s.recovery_time
    ]
    assert recovered[0].controller.uptime_seconds == 0
    assert all(e.controller.reset_count == 1 for e in recovered)
    assert recovered[1].controller.uptime_seconds == 60
    assert all(e.controller.health_status == "healthy" for e in recovered)


def test_battery_depletion_has_real_gaps_and_recharges_on_motion(healthy):
    batch = inject("battery-depletion-demo", healthy)
    assert batch.missing_reports and batch.outages
    assert batch.outages[0].recovered
    assert all(e.battery_voltage_v > 3.0 for e in batch.events)
    target = [e for e in batch.events if e.asset_id == "FG-WGN-0001"]
    assert any(e.battery_voltage_v < 3.2 for e in target)
    first_recovery = next(e for e in target if e.event_time == batch.outages[0].end_time_exclusive)
    assert first_recovery.power_source == "axle_generators"
    assert first_recovery.controller.uptime_seconds == 0
    assert first_recovery.controller.reset_count == 1


def test_null_without_quality_and_sentinel_as_engineering_value_rejected(healthy):
    payload = healthy.events[0].model_dump()
    payload["brake_pipe_pressure_bar"] = None
    with pytest.raises(ValidationError, match="requires quality"):
        TelemetryEvent.model_validate(payload)
    payload["brake_pipe_pressure_bar"] = 255
    with pytest.raises(ValidationError):
        TelemetryEvent.model_validate(payload)
    payload["brake_pipe_pressure_bar"] = 5
    payload["signal_quality"] = {"brake_pipe_pressure_bar": {"status": "invalid", "raw_value": 255}}
    with pytest.raises(ValidationError, match="must be null"):
        TelemetryEvent.model_validate(payload)


def test_multiple_scenarios_on_same_asset_rejected(healthy):
    first = scenario("wheel-flat-demo", healthy)
    second = scenario("locked-axle-demo", healthy)
    with pytest.raises(ValueError, match="one scenario per asset"):
        inject_fleet_anomaly_scenarios(healthy, (first, second))


def test_mismatched_truth_rejected_even_without_scenario(healthy):
    with pytest.raises(ValueError, match="identities must match"):
        inject_anomaly_scenarios(healthy.events[:1], healthy.truth[1:2], ())


def test_invalid_target_and_outage_configuration_rejected(healthy):
    with pytest.raises(ValueError, match="requires bogie and axle"):
        scenario("locked-axle-demo", healthy, target=ComponentTarget("FG-WGN-0001"))
    with pytest.raises(ValueError, match="requires timezone-aware recovery"):
        scenario("controller-bounded-demo", healthy, recovery_time=None)
    with pytest.raises(ValueError, match="non-none severity"):
        scenario("wheel-flat-demo", healthy, peak_severity=AnomalySeverity.NONE)
    with pytest.raises(ValueError, match="absent"):
        inject("controller-persistent-demo", healthy, target=ComponentTarget("FG-WGN-9999"))


def test_output_has_no_phantom_component_rows_during_outage(healthy, tmp_path):
    import json

    batch = inject("controller-bounded-demo", healthy)
    metadata = build_journey_metadata(create_random_journey_plan(42), START, 60)
    manifest = write_generation_run(tmp_path, batch, metadata, 42, "controller-bounded-demo")
    assert manifest["counts"]["expected_reports"] == len(healthy.events)
    assert manifest["counts"]["missing_reports"] == 10
    observed_ids = {str(e.event_id) for e in batch.events}
    for filename, multiplier in [
        ("bogie_observations.jsonl", 2),
        ("axle_observations.jsonl", 4),
        ("wheel_observations.jsonl", 8),
    ]:
        records = [json.loads(line) for line in (tmp_path / filename).read_text().splitlines()]
        assert len(records) == multiplier * len(batch.events)
        assert {row["event_id"] for row in records} == observed_ids
    stored = json.loads((tmp_path / "scenario_metadata.json").read_text())
    assert stored["scenarios"][0]["outage_mode"] == "bounded"


@pytest.mark.parametrize("interval", [1, 10, 60])
def test_controller_outage_uses_time_not_row_count(interval):
    batch = generate_healthy_journey_fleet(
        generate_fleet_assets(1, 42), START, create_random_journey_plan(42), interval
    )
    s = AnomalyScenario(
        "FG-TIME",
        AnomalyType.CONTROLLER_SUPPLY_FAILURE,
        ComponentTarget("FG-WGN-0001"),
        START + timedelta(minutes=5),
        START + timedelta(minutes=6),
        AnomalySeverity.LOW,
        outage_mode="bounded",
        recovery_time=START + timedelta(minutes=7),
    )
    result = inject_fleet_anomaly_scenarios(batch, (s,))
    assert len(result.missing_reports) == 120 // interval
    assert result.outages[0].recovered
