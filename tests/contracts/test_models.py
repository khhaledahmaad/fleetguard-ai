from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from fleetguard.contracts import (
    AnomalySeverity,
    AnomalyTruth,
    AnomalyType,
    AssetMetadata,
    OperatingState,
    TelemetryEvent,
)


def valid_asset() -> dict:
    return {
        "asset_id": "FG-WGN-0001",
        "fleet_id": "FG-DEMO-01",
        "commissioning_age_years": 7.4,
        "nominal_load_tonnes": 62.0,
        "bearing_baseline_temp_c": 42.5,
        "vibration_baseline_g": 0.18,
        "brake_pressure_baseline_bar": 5.0,
        "generator_seed": 1042,
    }


def valid_event() -> dict:
    event_time = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    return {
        "event_id": uuid4(),
        "asset_id": "FG-WGN-0001",
        "event_time": event_time,
        "generated_at": event_time,
        "operating_state": OperatingState.MOVING,
        "speed_kph": 72.0,
        "ambient_temp_c": 16.0,
        "axle_load_tonnes": 18.5,
        "bearing_temp_c": 48.2,
        "vibration_rms_g": 0.24,
        "brake_pipe_pressure_bar": 5.0,
        "brake_cylinder_pressure_bar": 0.1,
        "battery_voltage_v": 25.1,
    }


def test_valid_asset_metadata() -> None:
    asset = AssetMetadata(**valid_asset())

    assert asset.asset_id == "FG-WGN-0001"
    assert asset.schema_version == "1.0"


def test_asset_id_must_follow_contract() -> None:
    data = valid_asset()
    data["asset_id"] = "REAL-ASSET-123"

    with pytest.raises(ValidationError):
        AssetMetadata(**data)


def test_valid_telemetry_event() -> None:
    event = TelemetryEvent(**valid_event())

    assert isinstance(event.event_id, UUID)
    assert event.operating_state == OperatingState.MOVING


def test_naive_timestamp_is_rejected() -> None:
    data = valid_event()
    data["event_time"] = datetime(2026, 1, 1, 12, 0)

    with pytest.raises(
        ValidationError,
        match="timestamp must include timezone information",
    ):
        TelemetryEvent(**data)


def test_generated_at_cannot_precede_event_time() -> None:
    data = valid_event()
    data["generated_at"] = datetime(2025, 12, 31, 23, 59, tzinfo=UTC)

    with pytest.raises(
        ValidationError,
        match="generated_at cannot precede event_time",
    ):
        TelemetryEvent(**data)


def test_stationary_event_cannot_have_moving_speed() -> None:
    data = valid_event()
    data["operating_state"] = OperatingState.STATIONARY
    data["speed_kph"] = 30.0

    with pytest.raises(
        ValidationError,
        match="stationary events cannot have speed above 1 km/h",
    ):
        TelemetryEvent(**data)


def test_unknown_field_is_rejected() -> None:
    data = valid_event()
    data["unknown_sensor"] = 123.0

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TelemetryEvent(**data)


def test_valid_healthy_ground_truth() -> None:
    truth = AnomalyTruth(
        event_id=uuid4(),
        asset_id="FG-WGN-0001",
        is_anomaly=False,
        anomaly_type=AnomalyType.NONE,
        anomaly_severity=AnomalySeverity.NONE,
        affected_signal=None,
        anomaly_start_time=None,
        anomaly_progress=0.0,
    )

    assert truth.is_anomaly is False


def test_valid_bearing_anomaly_ground_truth() -> None:
    truth = AnomalyTruth(
        event_id=uuid4(),
        asset_id="FG-WGN-0001",
        is_anomaly=True,
        anomaly_type=AnomalyType.BEARING_DEGRADATION,
        anomaly_severity=AnomalySeverity.MEDIUM,
        affected_signal="bearing_temp_c",
        anomaly_start_time=datetime(2026, 1, 1, tzinfo=UTC),
        anomaly_progress=0.55,
    )

    assert truth.anomaly_progress == 0.55


def test_inconsistent_anomaly_ground_truth_is_rejected() -> None:
    with pytest.raises(
        ValidationError,
        match="anomalous records require an anomaly type",
    ):
        AnomalyTruth(
            event_id=uuid4(),
            asset_id="FG-WGN-0001",
            is_anomaly=True,
            anomaly_type=AnomalyType.NONE,
            anomaly_severity=AnomalySeverity.HIGH,
            affected_signal="bearing_temp_c",
            anomaly_start_time=datetime(2026, 1, 1, tzinfo=UTC),
            anomaly_progress=0.9,
        )
