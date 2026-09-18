from datetime import UTC, datetime, timedelta

import pytest

from fleetguard.generator.anomalies import (
    AnomalyScenario,
    AnomalySeverity,
    AnomalyType,
    ComponentTarget,
)


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
            anomaly_type=AnomalyType.SENSOR_DRIFT,
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
            anomaly_type=AnomalyType.SENSOR_DRIFT,
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
