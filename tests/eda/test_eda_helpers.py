import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "nbs"))
import fleetguard_eda as eda  # noqa: E402


def test_test_split_is_rejected_before_any_signal_loading():
    ws = object.__new__(eda.Workspace)
    with pytest.raises(ValueError, match="Test: inventory only"):
        ws.select("test")


def test_component_keys_keep_parent_identity():
    data = pd.DataFrame(
        {
            "asset_id": ["A", "A"],
            "bogie_id": [1, 2],
            "axle_position": ["inner", "inner"],
            "wheel_side": ["left", "left"],
        }
    )
    assert eda.component_keys(data, "wheel").tolist() == [
        "A/B1/inner/left",
        "A/B2/inner/left",
    ]


def test_axle_fault_does_not_claim_an_individual_wheel():
    row = {
        "is_anomaly": True,
        "anomaly_type": "locked_axle",
        "affected_component": "bogie:1/axle:inner",
        "bogie_id": 1,
        "axle_position": "inner",
        "wheel_side": "left",
    }
    assert eda.target_match(row, "axle")
    assert not eda.target_match(row, "wheel")


def test_timeline_inserts_null_at_absent_reporting_slots():
    data = pd.DataFrame(
        {
            "component": ["A"] * 2,
            "event_time": pd.to_datetime(
                ["2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z"]
            ),
            "sampling_interval_seconds": [10, 10],
            "speed_kph": [20, 25],
        }
    )
    plotted = eda.timeline_data(data, "speed_kph")
    assert len(plotted) == 3
    assert plotted.speed_kph.isna().sum() == 1
    assert len(data) == 2


def test_distribution_gallery_keeps_bins_independent_between_units():
    class ExampleWorkspace:
        def load(self, *args, **kwargs):
            data = {name: [i, i + 1] for i, name in enumerate(eda.NUMERIC["wagon"])}
            data["controller_uptime_seconds"] = [1000, 10000]
            return pd.DataFrame(
                {"asset_id": ["A", "A"], "component": ["A", "A"], **data}
            )

    chart = eda.distribution_gallery(ExampleWorkspace())
    assert len({trace.bingroup for trace in chart.data}) == len(eda.NUMERIC["wagon"])
    progress = chart.data[0]
    assert progress.xbins.end < 2


def test_shared_pressure_context_is_not_lost_to_nan_bogie_id():
    row = {
        "is_anomaly": True,
        "anomaly_type": "pressure_transducer_failure",
        "affected_component": "wagon:pneumatic_system",
        "bogie_id": 1,
        "target_bogie_id": float("nan"),
    }
    assert eda.target_match(row, "bogie")
