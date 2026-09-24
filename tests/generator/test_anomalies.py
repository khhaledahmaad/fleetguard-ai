from datetime import UTC, datetime, timedelta

import pytest

from fleetguard.generator.anomalies import (
    AnomalyScenario,
    AnomalySeverity,
    AnomalyType,
    ComponentTarget,
    InjectedBatch,
    inject_anomaly_scenarios,
    inject_bearing_degradation,
    inject_brake_pressure_leak,
)
from fleetguard.generator.fleet import generate_fleet_assets
from fleetguard.generator.healthy import generate_healthy_batch


def make_bearing_scenario() -> AnomalyScenario:
    start = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)

    return AnomalyScenario(
        scenario_id="FG-ANO-0001",
        anomaly_type=AnomalyType.BEARING_DEGRADATION,
        target=ComponentTarget(
            asset_id="FG-WGN-0001",
            bogie_id=1,
            axle_position="outer",
            wheel_side="left",
        ),
        start_time=start,
        end_time=start + timedelta(hours=2),
        peak_severity=AnomalySeverity.HIGH,
    )


def make_brake_leak_scenario() -> AnomalyScenario:
    start = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)

    return AnomalyScenario(
        scenario_id="FG-ANO-0002",
        anomaly_type=AnomalyType.BRAKE_PRESSURE_LEAK,
        target=ComponentTarget(
            asset_id="FG-WGN-0001",
            signal_name="brake_pipe_pressure_bar",
        ),
        start_time=start,
        end_time=start + timedelta(hours=2),
        peak_severity=AnomalySeverity.HIGH,
    )


def test_bearing_scenario_requires_full_component_target() -> None:
    start = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)

    with pytest.raises(
        ValueError,
        match="Bearing degradation requires bogie, axle and wheel targeting",
    ):
        AnomalyScenario(
            scenario_id="FG-ANO-0001",
            anomaly_type=AnomalyType.BEARING_DEGRADATION,
            target=ComponentTarget(asset_id="FG-WGN-0001", bogie_id=1),
            start_time=start,
            end_time=start + timedelta(hours=2),
            peak_severity=AnomalySeverity.HIGH,
        )


def test_scenario_requires_timezone_aware_timestamps() -> None:
    start = datetime(2026, 1, 1, 8, 0)

    with pytest.raises(
        ValueError,
        match="Scenario timestamps must be timezone-aware",
    ):
        AnomalyScenario(
            scenario_id="FG-ANO-0001",
            anomaly_type=AnomalyType.SENSOR_FAULT,
            target=ComponentTarget(
                asset_id="FG-WGN-0001",
                signal_name="ambient_temp_c",
            ),
            start_time=start,
            end_time=start + timedelta(hours=1),
            peak_severity=AnomalySeverity.MEDIUM,
        )


def test_scenario_end_must_follow_start() -> None:
    start = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)

    with pytest.raises(
        ValueError,
        match="Scenario end_time must be after start_time",
    ):
        AnomalyScenario(
            scenario_id="FG-ANO-0001",
            anomaly_type=AnomalyType.SENSOR_FAULT,
            target=ComponentTarget(
                asset_id="FG-WGN-0001",
                signal_name="ambient_temp_c",
            ),
            start_time=start,
            end_time=start,
            peak_severity=AnomalySeverity.MEDIUM,
        )


@pytest.mark.parametrize(
    ("minutes_after_start", "expected_progress"),
    [
        (-1, 0.0),
        (0, 0.0),
        (30, 0.25),
        (60, 0.5),
        (90, 0.75),
        (120, 1.0),
        (121, 1.0),
    ],
)
def test_progress_is_clamped_between_zero_and_one(
    minutes_after_start: int,
    expected_progress: float,
) -> None:
    scenario = make_bearing_scenario()
    event_time = scenario.start_time + timedelta(minutes=minutes_after_start)

    assert scenario.progress_at(event_time) == pytest.approx(expected_progress)


def test_active_interval_includes_boundaries() -> None:
    scenario = make_bearing_scenario()

    assert scenario.is_active(scenario.start_time)
    assert scenario.is_active(scenario.end_time)
    assert not scenario.is_active(scenario.start_time - timedelta(seconds=1))
    assert not scenario.is_active(scenario.end_time + timedelta(seconds=1))


def make_event_and_truth(minutes_after_start: int = 60):
    scenario = make_bearing_scenario()
    batch = generate_healthy_batch(
        asset=generate_fleet_assets(1, 42)[0],
        start_time=scenario.start_time,
        periods=max(121, minutes_after_start + 1),
    )
    return batch.events[minutes_after_start], batch.truth[minutes_after_start]


def test_bearing_degradation_changes_only_target_wheel_and_axle() -> None:
    scenario = make_bearing_scenario()
    event, truth = make_event_and_truth()

    updated_event, updated_truth = inject_bearing_degradation(event, truth, scenario)

    target_axle_before = event.bogies[0].axles[0]
    target_axle_after = updated_event.bogies[0].axles[0]
    assert target_axle_before.axle_position == "outer"
    assert target_axle_after.vibration_rms_g == pytest.approx(
        target_axle_before.vibration_rms_g + 0.35
    )
    assert target_axle_after.wheels[0].bearing_temp_c == pytest.approx(
        target_axle_before.wheels[0].bearing_temp_c + 17.5
    )
    assert target_axle_after.wheels[1] == target_axle_before.wheels[1]
    assert updated_event.bogies[0].axles[1] == event.bogies[0].axles[1]
    assert updated_event.bogies[1] == event.bogies[1]
    assert updated_event.model_copy(update={"bogies": event.bogies}) == event
    assert updated_truth.is_anomaly is True
    assert updated_truth.anomaly_type is AnomalyType.BEARING_DEGRADATION
    assert updated_truth.affected_signal == "bearing_temp_c"
    assert updated_truth.anomaly_progress == pytest.approx(0.5)


def test_injection_does_not_mutate_healthy_baseline() -> None:
    scenario = make_bearing_scenario()
    event, truth = make_event_and_truth()
    event_before = event.model_dump(mode="json")
    truth_before = truth.model_dump(mode="json")

    inject_bearing_degradation(event, truth, scenario)

    assert event.model_dump(mode="json") == event_before
    assert truth.model_dump(mode="json") == truth_before


def test_injection_outside_scenario_returns_original_records() -> None:
    scenario = make_bearing_scenario()
    event, truth = make_event_and_truth()
    future_scenario = AnomalyScenario(
        scenario_id="FG-ANO-0002",
        anomaly_type=AnomalyType.BEARING_DEGRADATION,
        target=scenario.target,
        start_time=scenario.end_time + timedelta(hours=1),
        end_time=scenario.end_time + timedelta(hours=2),
        peak_severity=AnomalySeverity.HIGH,
    )

    assert inject_bearing_degradation(event, truth, future_scenario) == (event, truth)


def test_injection_rejects_mismatched_event_and_truth() -> None:
    scenario = make_bearing_scenario()
    event, _ = make_event_and_truth()
    _, other_truth = make_event_and_truth(minutes_after_start=61)

    with pytest.raises(ValueError, match="event and truth identities must match"):
        inject_bearing_degradation(event, other_truth, scenario)


def test_bearing_degradation_persists_at_peak_after_end_time() -> None:
    scenario = make_bearing_scenario()
    event, truth = make_event_and_truth(minutes_after_start=150)

    updated_event, updated_truth = inject_bearing_degradation(
        event,
        truth,
        scenario,
    )

    target_axle_before = event.bogies[0].axles[0]
    target_axle_after = updated_event.bogies[0].axles[0]

    assert target_axle_after.vibration_rms_g == pytest.approx(
        target_axle_before.vibration_rms_g + 0.70
    )

    assert target_axle_after.wheels[0].bearing_temp_c == pytest.approx(
        target_axle_before.wheels[0].bearing_temp_c + 35.0
    )

    assert updated_truth.is_anomaly is True
    assert updated_truth.anomaly_progress == pytest.approx(1.0)


def test_batch_injection_applies_scenario_across_matching_events() -> None:
    scenario = make_bearing_scenario()

    healthy_batch = generate_healthy_batch(
        asset=generate_fleet_assets(1, 42)[0],
        start_time=scenario.start_time,
        periods=151,
    )

    injected_batch = inject_anomaly_scenarios(
        events=healthy_batch.events,
        truth=healthy_batch.truth,
        scenarios=(scenario,),
    )

    assert isinstance(injected_batch, InjectedBatch)
    assert len(injected_batch.events) == len(healthy_batch.events)
    assert len(injected_batch.truth) == len(healthy_batch.truth)

    assert injected_batch.events[0] == healthy_batch.events[0]
    assert injected_batch.truth[0] == healthy_batch.truth[0]

    halfway_truth = injected_batch.truth[60]
    peak_truth = injected_batch.truth[120]
    post_peak_truth = injected_batch.truth[150]

    assert halfway_truth.is_anomaly is True
    assert halfway_truth.anomaly_progress == pytest.approx(0.5)

    assert peak_truth.is_anomaly is True
    assert peak_truth.anomaly_progress == pytest.approx(1.0)

    assert post_peak_truth.is_anomaly is True
    assert post_peak_truth.anomaly_progress == pytest.approx(1.0)

    assert healthy_batch.truth[60].is_anomaly is False
    assert healthy_batch.truth[120].is_anomaly is False
    assert healthy_batch.truth[150].is_anomaly is False


def test_batch_injection_rejects_mismatched_record_counts() -> None:
    scenario = make_bearing_scenario()
    healthy_batch = generate_healthy_batch(
        asset=generate_fleet_assets(1, 42)[0],
        start_time=scenario.start_time,
        periods=2,
    )

    with pytest.raises(
        ValueError,
        match="events and truth must contain the same number of records",
    ):
        inject_anomaly_scenarios(
            events=healthy_batch.events,
            truth=healthy_batch.truth[:1],
            scenarios=(scenario,),
        )


def test_brake_leak_requires_brake_pipe_signal_target() -> None:
    start = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)

    with pytest.raises(
        ValueError,
        match="Brake-pressure leakage requires",
    ):
        AnomalyScenario(
            scenario_id="FG-ANO-0002",
            anomaly_type=AnomalyType.BRAKE_PRESSURE_LEAK,
            target=ComponentTarget(
                asset_id="FG-WGN-0001",
                signal_name="bearing_temp_c",
            ),
            start_time=start,
            end_time=start + timedelta(hours=2),
            peak_severity=AnomalySeverity.HIGH,
        )


def test_brake_leak_changes_only_shared_pneumatic_signals() -> None:
    scenario = make_brake_leak_scenario()
    event, truth = make_event_and_truth()

    updated_event, updated_truth = inject_brake_pressure_leak(
        event,
        truth,
        scenario,
    )

    assert updated_event.brake_pipe_pressure_bar == pytest.approx(
        event.brake_pipe_pressure_bar - 0.40
    )

    assert updated_event.auxiliary_reservoir_pressure_bar == pytest.approx(
        event.auxiliary_reservoir_pressure_bar - 0.175
    )

    assert (
        updated_event.secondary_reservoir_pressure_bar
        == event.secondary_reservoir_pressure_bar
    )

    assert updated_event.bogies == event.bogies
    assert updated_event.speed_kph == event.speed_kph
    assert updated_event.operating_state == event.operating_state

    assert updated_truth.is_anomaly is True
    assert updated_truth.anomaly_type is AnomalyType.BRAKE_PRESSURE_LEAK
    assert updated_truth.affected_component == "wagon:pneumatic_system"
    assert updated_truth.affected_signal == "brake_pipe_pressure_bar"
    assert updated_truth.anomaly_progress == pytest.approx(0.5)


def test_brake_leak_persists_at_peak_after_end_time() -> None:
    scenario = make_brake_leak_scenario()
    event, truth = make_event_and_truth(minutes_after_start=150)

    updated_event, updated_truth = inject_brake_pressure_leak(
        event,
        truth,
        scenario,
    )

    assert updated_event.brake_pipe_pressure_bar == pytest.approx(
        event.brake_pipe_pressure_bar - 0.80
    )

    assert updated_event.auxiliary_reservoir_pressure_bar == pytest.approx(
        event.auxiliary_reservoir_pressure_bar - 0.35
    )

    assert updated_truth.anomaly_progress == pytest.approx(1.0)
