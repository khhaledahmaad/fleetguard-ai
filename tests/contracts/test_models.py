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
from fleetguard.generator import generate_fleet_assets, generate_healthy_batch


def valid_asset() -> dict:
    return generate_fleet_assets(1, 42)[0].model_dump()


def valid_event() -> dict:
    event_time = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    asset = generate_fleet_assets(1, 42)[0]
    return generate_healthy_batch(asset, event_time, 60).events[15].model_dump()


def test_valid_asset_metadata() -> None:
    asset = AssetMetadata(**valid_asset())

    assert asset.asset_id == "FG-WGN-0001"
    assert asset.schema_version == "2.0"


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
