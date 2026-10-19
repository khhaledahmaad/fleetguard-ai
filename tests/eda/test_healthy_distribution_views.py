import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "nbs"))
import fleetguard_eda as eda  # noqa: E402


class ExampleWorkspace:
    def __init__(self, frame):
        self.frame = frame

    def load(self, level, split, variants):
        assert variants == ["healthy"]
        return self.frame


def test_density_view_preserves_constants_discrete_values_and_point_masses(monkeypatch):
    fields = ("available_axle_generators", "longitudinal_acceleration_mps2", "speed_kph")
    monkeypatch.setattr(eda, "NUMERIC", {"wagon": fields})
    frame = pd.DataFrame(
        {
            fields[0]: np.full(200, 4),
            fields[1]: np.tile([0, 1], 100),
            fields[2]: np.r_[np.zeros(100), np.arange(1, 101)],
        }
    )
    fig = eda.distribution_gallery(ExampleWorkspace(frame), view="Density / exact values")
    constant, discrete, cumulative = fig.data
    assert list(constant.x) == [4]
    assert list(constant.y) == [1]
    assert discrete.type == "bar"
    assert sum(discrete.y) == 1
    assert cumulative.y[0] == 0.5
    assert cumulative.y[-1] == 1
    assert np.all(np.diff(cumulative.y) >= 0)


def test_kde_is_reproducible_and_normalised_over_displayed_range(monkeypatch):
    monkeypatch.setattr(eda, "NUMERIC", {"wagon": ("battery_voltage_v",)})
    frame = pd.DataFrame({"battery_voltage_v": np.linspace(3, 4.2, 5000)})
    ws = ExampleWorkspace(frame)
    first = eda.distribution_gallery(ws, view="Density / exact values")
    second = eda.distribution_gallery(ws, view="Density / exact values")
    assert np.array_equal(first.data[0].y, second.data[0].y)
    assert np.all(np.asarray(first.data[0].y) >= 0)
    x, y = np.asarray(first.data[0].x), np.asarray(first.data[0].y)
    area = np.sum((y[:-1] + y[1:]) / 2 * np.diff(x))
    assert abs(area - 1) < 0.01
