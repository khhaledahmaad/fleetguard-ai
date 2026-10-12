from fleetguard.audit import main, summarise_windows


def window(received, valid, missing=0, invalid=0):
    return {
        "received_reports": received,
        "expected_reports": 6,
        "numeric": {
            "wheel_speed_kph": {
                "valid_count": valid,
                "missing_count": missing,
                "invalid_count": invalid,
            }
        },
    }


def test_report_silence_is_not_sensor_missingness():
    report = summarise_windows([window(0, 0), window(4, 2, missing=1, invalid=1)])
    assert report["counts"]["missing_component_reports"] == 8
    assert report["counts"]["silent_windows"] == 1
    assert report["counts"]["partial_windows"] == 1
    assert report["numeric_quality"]["wheel_speed_kph"]["missing"] == 1
    assert report["numeric_quality"]["wheel_speed_kph"]["invalid"] == 1
    assert report["numeric_quality"]["wheel_speed_kph"]["valid"] == 2


def test_complete_reports_can_have_failed_sensor():
    report = summarise_windows([window(6, 0, invalid=6)])
    assert report["counts"]["complete_windows"] == 1
    assert report["counts"]["missing_component_reports"] == 0
    assert (
        report["numeric_quality"]["wheel_speed_kph"]["windows_without_valid_readings"]
        == 1
    )


def test_cli_rejects_output_inside_source_before_reading(tmp_path):
    source = tmp_path / "source"
    assert (
        main(
            [
                "--source-dir",
                str(source),
                "--feature-dir",
                str(tmp_path / "features"),
                "--output-dir",
                str(source / "audit"),
            ]
        )
        == 1
    )
    assert not source.exists()


def test_audit_rejects_features_from_another_portfolio(monkeypatch, tmp_path):
    import pytest

    from fleetguard import audit

    monkeypatch.setattr(audit, "validate_portfolio", lambda _: {"status": "passed"})
    monkeypatch.setattr(
        audit, "validate_feature_dataset", lambda _: {"status": "passed"}
    )
    monkeypatch.setattr(audit, "read_json", lambda _: {"source_plan_sha256": "other"})
    monkeypatch.setattr(audit, "sha256", lambda _: "current")
    with pytest.raises(ValueError, match="do not belong"):
        audit.audit_dataset(tmp_path / "source", tmp_path / "features")
