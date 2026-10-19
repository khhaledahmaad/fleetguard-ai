"""Shared loading and visual controls for FleetGuard's three EDA sessions."""

from __future__ import annotations

import html
import json
import os
from pathlib import Path

import folium
import holoviews as hv
import numpy as np
import pandas as pd
import panel as pn
import plotly.express as px
import plotly.graph_objects as go
from folium.plugins import HeatMap, HeatMapWithTime, MarkerCluster
from plotly.subplots import make_subplots
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.spatial.distance import squareform
from scipy.stats import gaussian_kde

from fleetguard.features.hierarchical_aggregation import CATEGORICAL, NUMERIC
from fleetguard.portfolio.validation import sha256

COLOURS = {
    "Healthy control": "#087c79",
    "Before / no observed signature": "#627887",
    "Target / parent context": "#ba4a3d",
    "Other component during fault": "#b47727",
}
PALETTE = ["#087c79", "#4f768e", "#b47727", "#7766a0", "#ba4a3d"]
UNITS = {
    "speed_kph": "km/h",
    "wheel_speed_kph": "km/h",
    "rotational_speed_rpm": "rpm",
    "bearing_temp_c": "°C",
    "ambient_temp_c": "°C",
    "controller_temperature_c": "°C",
    "vibration_rms_g": "g",
    "axle_load_tonnes": "tonnes",
    "route_progress": "fraction",
    "estimated_adhesion_coefficient": "coefficient",
    "battery_voltage_v": "V",
    "controller_supply_voltage_v": "V",
    "available_axle_generators": "count",
}
LABELS = {
    "brake_pipe_pressure_bar": "Brake-pipe pressure",
    "brake_cylinder_pressure_bar": "Brake-cylinder pressure",
    "auxiliary_reservoir_pressure_bar": "Auxiliary reservoir",
    "secondary_reservoir_pressure_bar": "Secondary reservoir",
    "wheel_speed_kph": "Wheelset speed",
    "speed_kph": "Wagon speed",
    "vibration_rms_g": "Axle vibration",
    "bearing_temp_c": "Bearing temperature",
    "rotational_speed_rpm": "Axle rotation",
}
ESRI_STREET = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"
ESRI_AERIAL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ESRI_ATTR = "Tiles © Esri — Esri, HERE, Garmin, USGS and imagery providers"


def label(name):
    if name in LABELS:
        return LABELS[name]
    friendly = name
    for suffix in (
        "_mps2",
        "_kph",
        "_rpm",
        "_bar",
        "_tonnes",
        "_mm",
        "_seconds",
        "_v",
        "_c",
        "_g",
    ):
        if friendly.endswith(suffix):
            friendly = friendly[: -len(suffix)]
            break
    return " ".join(
        "temperature" if word == "Temp" else word
        for word in friendly.replace("_", " ").title().split()
    )


def unit(name):
    return UNITS.get(
        name,
        (
            "bar"
            if name.endswith("_bar")
            else (
                "m/s²"
                if name.endswith("_mps2")
                else "seconds" if name.endswith("_seconds") else "count"
            )
        ),
    )


def setup():
    pn.extension("plotly", "tabulator")
    hv.extension("bokeh")
    px.defaults.template = "plotly_white"
    px.defaults.color_discrete_sequence = PALETTE


def project_root():
    override = os.environ.get("FLEETGUARD_PROJECT_ROOT")
    if override:
        return Path(override).resolve()
    for p in (Path.cwd(), *Path.cwd().parents):
        if (p / "src/fleetguard/contracts/models.py").exists():
            return p
    raise FileNotFoundError(
        "Open Jupyter from your FleetGuard repository root or nbs folder."
    )


def figure(fig, title=None):
    fig.update_layout(
        font=dict(family="Segoe UI, Arial", size=13, color="#243b48"),
        paper_bgcolor="white",
        plot_bgcolor="white",
        height=fig.layout.height or 440,
        margin=dict(l=65, r=25, t=75, b=70),
        legend=dict(orientation="h", y=1.12),
    )
    if title:
        fig.update_layout(title=title)
    return fig


def pane(fig):
    return pn.pane.Plotly(
        fig, sizing_mode="stretch_width", config={"displaylogo": False}
    )


def table(frame):
    return pn.widgets.Tabulator(
        frame,
        show_index=False,
        pagination="local",
        page_size=10,
        disabled=True,
        sizing_mode="stretch_width",
    )


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


class Workspace:
    def __init__(self, source, features):
        self.source, self.features = Path(source), Path(features)
        plan = read_json(self.source / "cohort_plan.json")
        self.plan = plan
        self.manifest = read_json(self.features / "feature_manifest.json")
        if self.manifest["source_plan_sha256"] != sha256(
            self.source / "cohort_plan.json"
        ):
            raise ValueError("Feature plan does not match supplied source.")
        if self.manifest["source_manifest_sha256"] != sha256(
            self.source / "cohort_manifest.json"
        ):
            raise ValueError("Feature source hash does not match supplied source.")
        if self.manifest["feature_schema_version"] != "2.0":
            raise ValueError("These notebooks require feature schema 2.0.")
        self.assignments = pd.DataFrame(plan["runs"])

    def validate(self):
        from fleetguard.features.hierarchical_dataset import validate_feature_dataset
        from fleetguard.portfolio.validation import validate_portfolio

        return {
            "portfolio": validate_portfolio(self.source)["status"],
            "features": validate_feature_dataset(self.features)["status"],
        }

    def inventory(self):
        records = []
        for run in self.plan["runs"]:
            folder = self.source / run["relative_directory"]
            manifest = read_json(folder / "manifest.json")
            journey = read_json(folder / "journey_metadata.json")
            records.append(
                {
                    "split": run["split"],
                    "asset_id": run["asset_id"],
                    "variant": run["variant"],
                    "route_id": journey["route_id"],
                    "journey_id": journey["journey_id"],
                    "duration_minutes": journey["estimated_duration_seconds"] / 60,
                    "interval_seconds": journey["sampling_interval_seconds"],
                    **manifest["counts"],
                }
            )
        return pd.DataFrame(records)

    def select(self, split="train", variants=None, assets=None):
        if split not in ("train", "validation"):
            raise ValueError(
                "Exploration is limited to train/validation. Test: inventory only."
            )
        selected = self.assignments[self.assignments.split == split]
        if variants is not None:
            selected = selected[selected.variant.isin(variants)]
        if assets is not None:
            selected = selected[selected.asset_id.isin(assets)]
        return selected.to_dict("records")

    def load(self, level="wagon", split="train", variants=None, assets=None):
        records = []
        for run in self.select(split, variants, assets):
            folder = self.source / run["relative_directory"]
            truth = {r["event_id"]: r for r in rows(folder / "anomaly_truth.jsonl")}
            filename = (
                "telemetry.jsonl" if level == "wagon" else f"{level}_observations.jsonl"
            )
            for item in rows(folder / filename):
                if level == "wagon":
                    item.pop("bogies")
                    controller = item.pop("controller")
                    item.update({"controller_" + k: v for k, v in controller.items()})
                quality = item.pop("signal_quality", {})
                item.update(
                    {
                        name + "__quality": quality.get(name, {}).get("status", "valid")
                        for name in NUMERIC[level]
                    }
                )
                item.update({"split": split, "variant": run["variant"]})
                item["sampling_interval_seconds"] = self.plan["config"][
                    "sampling_interval_seconds"
                ]
                target = (run.get("scenario") or {}).get("target", {})
                item.update(
                    {
                        "target_" + k: target.get(k)
                        for k in (
                            "bogie_id",
                            "axle_position",
                            "wheel_side",
                            "signal_name",
                        )
                    }
                )
                t = truth[item["event_id"]]
                item.update(
                    {
                        k: t[k]
                        for k in [
                            "is_anomaly",
                            "anomaly_type",
                            "affected_component",
                            "affected_signal",
                            "anomaly_progress",
                        ]
                    }
                )
                records.append(item)
        frame = pd.DataFrame(records)
        if frame.empty:
            return frame
        frame["event_time"] = pd.to_datetime(frame.event_time, utc=True)
        frame["component"] = component_keys(frame, level)
        frame["level"] = level
        for name in NUMERIC[level]:
            frame[name] = pd.to_numeric(frame[name], errors="coerce")
        frame["context"] = context_labels(frame, level)
        return frame

    def summaries(self, level="wagon", split="train", assets=None):
        self.select(split)
        records = []
        for item in rows(self.features / f"{split}_{level}_features.jsonl"):
            if assets is not None and item["asset_id"] not in assets:
                continue
            result = {
                k: v
                for k, v in item.items()
                if k
                not in (
                    "numeric",
                    "categorical",
                    "static_attributes",
                    "source_event_ids",
                    "location",
                )
            }
            for name, summary in item["numeric"].items():
                result.update(
                    {
                        name + "__" + k: v
                        for k, v in summary.items()
                        if not isinstance(v, dict)
                    }
                )
            for name, summary in item["categorical"].items():
                result[name] = summary["last"]
            result.update(item["static_attributes"])
            records.append(result)
        frame = pd.DataFrame(records)
        if not frame.empty:
            frame["window_start"] = pd.to_datetime(frame.window_start, utc=True)
            frame["component"] = component_keys(frame, level)
        return frame

    def missing(self, split="train", assets=None):
        data = []
        for run in self.select(split, assets=assets):
            for item in rows(
                self.source / run["relative_directory"] / "missing_report_truth.jsonl"
            ):
                data.append({**item, "variant": run["variant"]})
        frame = pd.DataFrame(data)
        if not frame.empty:
            frame["expected_at"] = pd.to_datetime(frame.expected_at, utc=True)
        return frame


def component_keys(frame, level):
    keys = frame.asset_id.astype(str)
    for name, prefix in [
        ("bogie_id", "/B"),
        ("axle_position", "/"),
        ("wheel_side", "/"),
    ]:
        if level == "wagon" or name not in frame:
            continue
        keys += prefix + frame[name].astype(str)
    return keys


def target_match(row, level):
    """EDA evidence localisation, not a production model-label policy."""
    if not row["is_anomaly"]:
        return False
    if level == "wagon":
        return True  # wagon snapshot context, not every wagon signal changed
    target = str(row.get("affected_component") or "")
    if target.startswith("wagon:"):
        if level == "bogie" and row["anomaly_type"] in {
            "brake_release_failure",
            "undemanded_brake_application",
            "brake_pressure_leak",
            "pressure_transducer_failure",
        }:
            if row["anomaly_type"] == "brake_release_failure":
                return row.get("target_bogie_id") == row["bogie_id"]
            if row["anomaly_type"] == "pressure_transducer_failure" and pd.notna(
                row.get("target_bogie_id")
            ):
                return row["target_bogie_id"] == row["bogie_id"]
            return True  # shared pneumatic context
        return False
    expected = [f"bogie:{int(row['bogie_id'])}"]
    if level in ("axle", "wheel"):
        expected += [f"axle:{row['axle_position']}"]
    if level == "wheel":
        expected += [f"wheel:{row['wheel_side']}"]
    # axle faults have no wheel-side evidence and remain axle-level
    return all(part in target.split("/") for part in expected)


def context_labels(frame, level):
    return frame.apply(
        lambda row: (
            "Healthy control"
            if row.variant == "healthy"
            else (
                "Before / no observed signature"
                if not row.is_anomaly
                else (
                    "Target / parent context"
                    if target_match(row, level)
                    else "Other component during fault"
                )
            )
        ),
        axis=1,
    )


def overview_views(ws):
    data = ws.inventory()
    variants = data.groupby(["split", "variant"]).size().reset_index(name="Wagons")
    duration = px.box(
        data,
        x="split",
        y="duration_minutes",
        points="all",
        color="split",
        hover_data=["asset_id", "route_id"],
        labels={"duration_minutes": "Duty duration (min)"},
    )
    coverage = px.bar(variants, x="variant", y="Wagons", color="split", barmode="group")
    coverage.update_xaxes(tickangle=-35)
    routes = data.groupby(["split", "route_id"]).size().unstack(fill_value=0)
    heat = px.imshow(
        routes,
        text_auto=True,
        color_continuous_scale="Teal",
        aspect="auto",
        labels={"color": "Assigned wagons"},
    )
    identities = []
    for run in ws.plan["runs"]:
        asset = next(
            rows(ws.source / run["relative_directory"] / "asset_metadata.jsonl")
        )
        for bogie in asset["bogies"]:
            for axle in bogie["axles"]:
                for wheel in axle["wheels"]:
                    identities.append(
                        {
                            "split": run["split"],
                            "asset": asset["asset_id"],
                            "bogie": f"{asset['asset_id']}/B{bogie['bogie_id']}",
                            "axle": (
                                f"{asset['asset_id']}/B{bogie['bogie_id']}/{axle['axle_position']}"
                            ),
                            "wheel": (
                                f"{asset['asset_id']}/B{bogie['bogie_id']}"
                                f"/{axle['axle_position']}/{wheel['wheel_side']}"
                            ),
                        }
                    )
    unique = pd.DataFrame(identities).groupby("split").nunique().reset_index()
    return pn.Tabs(
        (
            "Coverage",
            pane(figure(coverage, "Assigned wagons — coverage, not prevalence")),
        ),
        ("Exposure", pane(figure(duration, "Journey length differs between wagons"))),
        ("Routes", pane(figure(heat, "Route coverage by split"))),
        ("Identity counts", table(unique)),
        ("Run inventory", table(data)),
    )


def completeness_view(ws, split="train"):
    data = ws.summaries("wagon", split)
    grid = data.pivot(
        index="asset_id", columns="window_start", values="report_completeness"
    )
    fig = px.imshow(
        grid,
        aspect="auto",
        zmin=0,
        zmax=1,
        color_continuous_scale="Teal",
        labels={"x": "Minute start (UTC)", "y": "Wagon", "color": "Completeness"},
    )
    return figure(
        fig,
        f"{split.title()} — missing reports remain visible; outside-duty cells are blank",
    )


def _histogram_gallery(ws, level="wagon", split="train"):
    data = ws.load(level, split, variants=["healthy"])
    numeric = list(NUMERIC[level])
    long = data.melt(
        id_vars=["asset_id", "component"],
        value_vars=numeric,
        var_name="Signal",
        value_name="Reading",
    )
    long["Signal"] = long.Signal.map(lambda x: f"{label(x)} ({unit(x)})")
    fig = px.histogram(
        long.dropna(subset=["Reading"]),
        x="Reading",
        facet_col="Signal",
        facet_col_wrap=3,
        nbins=35,
        histnorm="probability density",
        hover_data=["asset_id"],
        labels={"Reading": "Valid reading"},
    )
    # Independent units require independent histogram bins, not a shared bin group.
    for index, trace in enumerate(fig.data):
        values = np.asarray(trace.x, dtype=float)
        low, high = float(values.min()), float(values.max())
        width = (high - low) / 35 if high > low else max(0.02, abs(low) * 0.01)
        if high == low:
            low, high = low - width / 2, high + width / 2
        trace.bingroup = f"signal-{index}"
        trace.xbins = dict(start=low, end=high + width * 0.001, size=width)
    fig.update_xaxes(matches=None, showticklabels=True, title_text="")
    fig.update_yaxes(matches=None, title_text="Density")
    for trace in fig.data:
        values = np.asarray(trace.x, dtype=float)
        if np.unique(values).size == 1:
            trace.histnorm = "probability"
            trace.opacity = 0.18
            axis = trace.yaxis.replace("y", "yaxis", 1)
            fig.layout[axis].title = "Sample share"
            fig.add_annotation(
                x=0.5,
                y=0.5,
                xref=trace.xaxis + " domain",
                yref=trace.yaxis + " domain",
                text=f"Constant value: {values[0]:g}",
                showarrow=False,
            )
    for annotation in fig.layout.annotations:
        text = annotation.text.replace("Signal=", "")
        if len(text) > 45:
            middle = text.rfind(" ", 0, 38)
            text = text[:middle] + "<br>" + text[middle + 1 :]
        annotation.text = text
    fig = figure(
        fig, f"{split.title()} healthy controls — every {level} numerical signal"
    )
    fig.update_layout(height=max(440, 260 * int(np.ceil(len(numeric) / 3))))
    return fig


def distribution_gallery(ws, level="wagon", split="train", view="Histogram"):
    """Use KDE for continuous spread; preserve discrete values and point masses."""
    if view == "Histogram":
        return _histogram_gallery(ws, level, split)
    if view not in {"Density / exact values", "ECDF"}:
        raise ValueError("Choose Histogram, Density / exact values or ECDF")
    data = ws.load(level, split, variants=["healthy"])
    names = list(NUMERIC[level])
    fig = make_subplots(
        rows=int(np.ceil(len(names) / 3)),
        cols=3,
        subplot_titles=[f"{label(name)} ({unit(name)})" for name in names],
        vertical_spacing=min(0.08, 0.3 / max(1, int(np.ceil(len(names) / 3)))),
    )
    for index, name in enumerate(names):
        row, col = divmod(index, 3)
        row, col = row + 1, col + 1
        values = pd.to_numeric(data[name], errors="coerce").dropna().to_numpy()
        values = values[np.isfinite(values)]
        unique, counts = np.unique(values, return_counts=True)
        if not len(values):
            fig.add_annotation(
                text="No valid readings", showarrow=False, row=row, col=col
            )
            continue
        if len(unique) == 1:
            fig.add_trace(
                go.Scatter(
                    x=unique,
                    y=[1],
                    mode="markers",
                    marker=dict(color="#087c79", size=10),
                    hovertemplate="Value %{x}<br>Sample share 100%<extra></extra>",
                ),
                row=row,
                col=col,
            )
            fig.add_annotation(
                text=f"Constant: {unique[0]:g}",
                showarrow=False,
                x=unique[0],
                y=0.78,
                row=row,
                col=col,
            )
            ylabel = "Sample share"
        elif view == "ECDF" or (len(unique) > 24 and counts.max() / len(values) >= 0.1):
            fig.add_trace(
                go.Scatter(
                    x=unique,
                    y=np.cumsum(counts) / len(values),
                    mode="lines",
                    line=dict(color="#087c79", shape="hv"),
                    hovertemplate="Value %{x}<br>At or below %{y:.1%}<extra></extra>",
                ),
                row=row,
                col=col,
            )
            ylabel = "Cumulative share"
        elif len(unique) <= 24:
            fig.add_trace(
                go.Bar(
                    x=unique,
                    y=counts / len(values),
                    width=(unique[-1] - unique[0]) / len(unique) * 0.7,
                    marker_color="#087c79",
                    hovertemplate="Value %{x}<br>Sample share %{y:.1%}<extra></extra>",
                ),
                row=row,
                col=col,
            )
            ylabel = "Sample share"
        else:
            # Bound KDE cost and make approximation reproducible across callbacks.
            sample = values
            if len(sample) > 4000:
                sample = np.random.default_rng(42).choice(sample, 4000, replace=False)
            grid = np.linspace(unique[0], unique[-1], 220)
            kde = gaussian_kde(sample)
            density = kde(grid) / kde.integrate_box_1d(unique[0], unique[-1])
            fig.add_trace(
                go.Scatter(
                    x=grid,
                    y=density,
                    mode="lines",
                    fill="tozeroy",
                    line=dict(color="#087c79", width=2),
                    hovertemplate="Value %{x}<br>Density %{y:.4g}<extra></extra>",
                ),
                row=row,
                col=col,
            )
            ylabel = "KDE density"
        fig.update_yaxes(title_text=ylabel, row=row, col=col)
        if ylabel != "KDE density":
            fig.update_yaxes(range=[0, 1.12], tickformat=".0%", row=row, col=col)
    for annotation in fig.layout.annotations:
        if len(annotation.text) > 44:
            words = annotation.text.split()
            middle = len(words) // 2
            annotation.text = (
                " ".join(words[:middle]) + "<br>" + " ".join(words[middle:])
            )
    fig = figure(fig, f"{split.title()} healthy controls — {level}: {view}")
    fig.update_layout(
        showlegend=False, height=max(440, 290 * int(np.ceil(len(names) / 3)))
    )
    return fig


def state_gallery(ws, level="wagon", split="train"):
    data = ws.load(level, split, variants=["healthy"])
    names = list(CATEGORICAL[level])
    if not names:
        return pn.pane.Markdown("No categorical measurements at this component level.")
    parts = []
    for name in names:
        counts = (
            data[name]
            .value_counts(dropna=False)
            .rename_axis("State")
            .reset_index(name="Reports")
        )
        counts["State"] = (
            counts.State.astype(str)
            .str.replace("_", " ", regex=False)
            .str.replace(" dwell", "<br>dwell", regex=False)
            .str.replace("leaf contaminated", "leaf<br>contaminated", regex=False)
            .str.replace("axle generators", "axle<br>generators", regex=False)
        )
        counts["Signal"] = label(name)
        parts.append(counts)
    long = pd.concat(parts, ignore_index=True)
    fig = px.bar(
        long,
        x="State",
        y="Reports",
        facet_col="Signal",
        facet_col_wrap=3,
        facet_row_spacing=0.16,
        text="Reports",
        color_discrete_sequence=["#087c79"],
    )
    fig.update_xaxes(matches=None, showticklabels=True, title_text="")
    fig.update_traces(
        texttemplate="%{text:,}", textposition="outside", cliponaxis=False
    )
    for annotation in fig.layout.annotations:
        annotation.text = annotation.text.replace("Signal=", "")
    fig = figure(fig, "Healthy wagon states — shared context shown once")
    fig.update_layout(height=max(440, 330 * int(np.ceil(len(names) / 3))))
    return pane(fig)


def quality_profile(ws, split="train", variants=None):
    result = []
    for level in NUMERIC:
        data = ws.load(level, split, variants=variants)
        for name in NUMERIC[level]:
            values = data[name].dropna()
            result.append(
                {
                    "Level": level,
                    "Signal": label(name),
                    "Unit": unit(name),
                    "Reports": len(data),
                    "Valid": len(values),
                    "Missing": int((data[name + "__quality"] == "missing").sum()),
                    "Invalid": int((data[name + "__quality"] == "invalid").sum()),
                    "Distinct": values.nunique(),
                    "Minimum": values.min(),
                    "Median": values.median(),
                    "p95": values.quantile(0.95),
                    "Maximum": values.max(),
                    "Std": values.std(),
                }
            )
    return pd.DataFrame(result)


def choose(frame, asset="All", component="All", state="All"):
    selected = frame
    if asset != "All":
        selected = selected[selected.asset_id == asset]
    if component != "All":
        selected = selected[selected.component == component]
    if state != "All" and "operating_state" in selected:
        selected = selected[selected.operating_state == state]
    return selected


def healthy_explorer(ws, level="wagon", split="train"):
    data = ws.load(level, split, variants=["healthy"])
    signal = pn.widgets.Select(
        name="Signal", options={label(n) + f" ({unit(n)})": n for n in NUMERIC[level]}
    )
    asset = pn.widgets.Select(
        name="Wagon", options=["All", *sorted(data.asset_id.unique())]
    )
    component = pn.widgets.Select(
        name="Component", options=["All", *sorted(data.component.unique())]
    )
    state = pn.widgets.Select(
        name="Operating state",
        options=(
            ["All", *sorted(data.operating_state.unique())]
            if "operating_state" in data
            else ["All"]
        ),
    )

    distribution_view = pn.widgets.Select(
        name="Distribution view", options=["ECDF", "Histogram"]
    )

    def view(name, wagon, comp, operating, distribution_mode):
        selected = choose(data, wagon, comp, operating)
        if selected.empty:
            return pn.pane.Markdown("No observations for this selection.")
        if distribution_mode == "ECDF":
            distribution = px.ecdf(selected, x=name, color="asset_id")
            distribution_y = "Cumulative sample share"
        else:
            distribution = px.histogram(
                selected,
                x=name,
                color="asset_id",
                nbins=45,
                histnorm="probability density",
                barmode="overlay",
                opacity=0.6,
            )
            distribution_y = "Density"
        box = px.box(selected, x="component", y=name, points=False)
        timeline = px.line(
            timeline_data(selected, name),
            x="event_time",
            y=name,
            color="component",
            line_group="component",
        )
        timeline.update_traces(connectgaps=False)
        for f in [distribution, box, timeline]:
            f.update_layout(
                xaxis_title=(
                    f"{label(name)} ({unit(name)})"
                    if f is distribution
                    else "Component" if f is box else "Observation time (UTC)"
                ),
                yaxis_title=(
                    distribution_y
                    if f is distribution
                    else f"{label(name)} ({unit(name)})"
                ),
            )
        return pn.Tabs(
            (
                "Distribution",
                pane(
                    figure(
                        distribution,
                        f"Healthy controls · {len(selected):,} received component reports",
                    )
                ),
            ),
            (
                "Components",
                pane(figure(box, "Component spread — same signal and units")),
            ),
            (
                "Timeline",
                pane(
                    figure(
                        timeline,
                        "Chronological readings; no connection across null readings",
                    )
                ),
            ),
        )

    return pn.Column(
        pn.Row(signal, asset, component, state, distribution_view),
        pn.bind(view, signal, asset, component, state, distribution_view),
        sizing_mode="stretch_width",
    )


def linked_relationship(ws, level="axle", split="train"):
    data = ws.load(level, split, variants=["healthy"])
    # One grain across both plots; selection links the same row identities.
    if level == "axle":
        x, y = "wheel_speed_kph", "vibration_rms_g"
    else:
        x, y = "speed_kph", "brake_pipe_pressure_bar"
    data = data.reset_index(drop=True).dropna(subset=[x, y])
    if len(data) > 12000:
        data = data.iloc[np.linspace(0, len(data) - 1, 12000).astype(int)]
    points = hv.Points(
        data, kdims=[x, y], vdims=["asset_id", "component", "event_time"]
    ).opts(
        width=560,
        height=350,
        tools=["hover", "box_select", "lasso_select"],
        xlabel=f"{label(x)} ({unit(x)})",
        ylabel=f"{label(y)} ({unit(y)})",
        color="#087c79",
        size=5,
        alpha=0.35,
        title="Brush a region: selection links both plots",
    )
    time = hv.Points(
        data, kdims=["event_time", y], vdims=["asset_id", "component", x]
    ).opts(
        width=560,
        height=350,
        tools=["hover", "box_select"],
        color="#087c79",
        size=4,
        xlabel="Observation time (UTC)",
        ylabel=f"{label(y)} ({unit(y)})",
        title="Same sampled rows over time",
    )
    return hv.link_selections.instance()(points + time).cols(1)


def correlation_view(ws, level="wagon", split="train", clustered=False):
    data = ws.load(level, split, variants=["healthy"])
    names = [n for n in NUMERIC[level] if data[n].nunique() > 1]
    corr = data[names].corr(method="spearman")
    corr = corr.dropna(how="all").dropna(axis=1, how="all")
    if len(corr) < 2:
        return pane(
            figure(go.Figure(), "Not enough varying signals for a correlation matrix")
        )
    if clustered:
        distance = (1 - corr.abs()).fillna(1).clip(0, 1)
        np.fill_diagonal(distance.values, 0)
        order = leaves_list(
            linkage(squareform(distance.values, checks=False), method="average")
        )
        corr = corr.iloc[order, order]
    corr.index = [f"{label(n)} ({unit(n)})" for n in corr.index]
    corr.columns = list(corr.index)
    fig = px.imshow(
        corr,
        zmin=-1,
        zmax=1,
        color_continuous_scale="RdBu_r",
        aspect="auto",
        labels={"color": "Spearman ρ"},
    )
    fig.update_xaxes(tickangle=-45)
    fig.update_layout(height=max(520, len(corr) * 32))
    return pane(
        figure(
            fig,
            "Healthy correlations — exploratory, not causal; pooled operating states",
        )
    )


def folium_map(data, faults=False):
    if data.empty:
        return pn.pane.Markdown("No received wagon positions.")
    base = folium.Map(
        location=[float(data.latitude.mean()), float(data.longitude.mean())],
        zoom_start=7,
        tiles=None,
        control_scale=True,
    )
    folium.TileLayer(ESRI_STREET, attr=ESRI_ATTR, name="Esri street").add_to(base)
    folium.TileLayer(
        ESRI_AERIAL, attr=ESRI_ATTR, name="Esri aerial", show=False
    ).add_to(base)
    folium.TileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        attr=ESRI_ATTR,
        name="Esri terrain / topographic",
        show=False,
    ).add_to(base)
    cluster = MarkerCluster(
        name="Sampled wagon reports (maximum 600 markers)", show=False
    ).add_to(base)
    sample = data.sort_values(["asset_id", "event_time"])
    sample = sample.iloc[
        np.linspace(0, len(sample) - 1, min(600, len(sample))).astype(int)
    ]
    for asset, group in data.groupby("asset_id"):
        coords = group.sort_values("event_time")[
            ["latitude", "longitude"]
        ].values.tolist()
        step = max(1, len(coords) // 800)
        folium.PolyLine(
            coords[::step],
            weight=2,
            opacity=0.5,
            color="#087c79",
            tooltip=f"{asset} — mapped railway geometry; simulated duty",
        ).add_to(base)
    for row in sample.itertuples():
        text = f"{row.asset_id} | {row.event_time} | {row.speed_kph:.1f} km/h"
        folium.Marker(
            [row.latitude, row.longitude],
            tooltip=html.escape(text),
            popup=html.escape(text),
        ).add_to(cluster)
    # Every wagon report contributes once, regardless of wheel count.
    cells = (
        data.assign(lat_bin=data.latitude.round(2), lon_bin=data.longitude.round(2))
        .groupby(["lat_bin", "lon_bin"])
        .agg(reports=("asset_id", "size"), anomalies=("is_anomaly", "sum"))
        .reset_index()
    )
    intensity = cells.anomalies if faults else cells.reports
    denominator = max(1, int(intensity.max()))
    HeatMap(
        [
            [r.lat_bin, r.lon_bin, float(intensity.iloc[i]) / denominator]
            for i, r in enumerate(cells.itertuples())
            if intensity.iloc[i] > 0
        ],
        name=(
            "Observed anomalous-report density" if faults else "Received-report density"
        ),
        show=False,
        radius=18,
    ).add_to(base)
    if faults:
        share = folium.FeatureGroup(
            name="Observed anomaly share per rounded cell", show=True
        )
        for row in cells.itertuples():
            if row.anomalies:
                folium.CircleMarker(
                    [row.lat_bin, row.lon_bin],
                    radius=4 + 9 * row.anomalies / row.reports,
                    color="#ba4a3d",
                    fill=True,
                    fill_opacity=0.6,
                    tooltip=f"{row.anomalies}/{row.reports} received reports anomalous "
                    f"({row.anomalies / row.reports:.1%}); synthetic coverage, not risk",
                ).add_to(share)
        share.add_to(base)
    buckets = data.assign(bucket=data.event_time.dt.floor("30min"))
    frames, times = [], []
    for when, group in buckets.groupby("bucket"):
        grid = group.groupby([group.latitude.round(2), group.longitude.round(2)]).size()
        frames.append(
            [
                [lat, lon, min(1, count / denominator)]
                for (lat, lon), count in grid.items()
            ]
        )
        times.append(when.strftime("%H:%M UTC"))
    HeatMapWithTime(
        frames,
        index=times,
        name="Received-report density replay (30-minute bins)",
        auto_play=False,
        show=False,
        radius=15,
    ).add_to(base)
    folium.LayerControl(collapsed=False).add_to(base)
    return base


def fault_evidence(ws, variant, level="axle", signal="wheel_speed_kph", split="train"):
    data = ws.load(level, split, variants=["healthy", variant])
    # Operating state belongs to wagon; join observed context using event identity.
    wagon = ws.load("wagon", split, variants=["healthy", variant])
    context = wagon[
        ["event_id", "asset_id", "speed_kph", "brake_demand", "operating_state"]
    ]
    if level != "wagon":
        data = data.merge(
            context.rename(columns={"speed_kph": "wagon_speed_kph"}),
            on=["event_id", "asset_id"],
            how="left",
            validate="many_to_one",
        )
    else:
        data["wagon_speed_kph"] = data.speed_kph
    data["speed_band"] = pd.cut(
        data.wagon_speed_kph,
        [-1, 1, 20, 60, 121],
        labels=["Stationary", "1–20", "20–60", "60–120"],
    )
    data["condition"] = (
        data.brake_demand.astype(str) + " · " + data.speed_band.astype(str)
    )
    return data


def anomaly_explorer(ws, split="train"):
    variants = sorted(
        ws.assignments.query(
            "split == @split and variant != 'healthy'"
        ).variant.unique()
    )
    variant = pn.widgets.Select(name="Assigned fault", options=variants)
    level = pn.widgets.Select(name="Component level", options=list(NUMERIC))
    signal = pn.widgets.Select(name="Signal", options=list(NUMERIC["wagon"]))
    level.value = "wagon"
    condition = pn.widgets.Select(name="Match operating context", options=["All"])
    cache = {}

    def refresh(event):
        signal.options = {label(n) + f" ({unit(n)})": n for n in NUMERIC[level.value]}
        signal.value = NUMERIC[level.value][0]

    level.param.watch(refresh, "value")
    refresh(None)

    def view(kind, scope, name, operating):
        if name not in NUMERIC[scope]:
            return pn.pane.Markdown("Choose a signal for this level.")
        key = (kind, scope)
        if key not in cache:
            cache.clear()
            cache[key] = fault_evidence(ws, kind, scope, name, split)
        data = cache[key]
        options = ["All", *sorted(data.condition.dropna().unique())]
        if condition.options != options:
            condition.options = options
        if operating != "All":
            data = data[data.condition == operating]
        if data.empty:
            return pn.pane.Markdown("No data in this operating context.")
        distributions = px.histogram(
            data,
            x=name,
            color="context",
            color_discrete_map=COLOURS,
            histnorm="probability density",
            barmode="overlay",
            opacity=0.65,
        )
        boxes = px.box(
            data,
            x="context",
            y=name,
            color="context",
            color_discrete_map=COLOURS,
            points=False,
            hover_data=["component"],
        )
        fault = data[data.variant == kind].sort_values("event_time")
        trace = px.line(
            timeline_data(fault, name),
            x="event_time",
            y=name,
            color="component",
            line_group="component",
        )
        trace.update_traces(connectgaps=False)
        profile = (
            data.groupby(["context", name + "__quality"], observed=True)
            .size()
            .reset_index(name="Reports")
        )
        for f in [distributions, boxes, trace]:
            f.update_yaxes(
                title=(
                    "Density" if f is distributions else f"{label(name)} ({unit(name)})"
                )
            )
        return pn.Tabs(
            (
                "Distribution",
                pane(
                    figure(
                        distributions,
                        f"{label(name)} ({unit(name)}) · received samples · context-filtered",
                    )
                ),
            ),
            (
                "Component comparison",
                pane(
                    figure(boxes, "EDA localisation groups, not final training labels")
                ),
            ),
            (
                "Fault wagon replay",
                pane(figure(trace, "Inspect selected and neighbouring components")),
            ),
            ("Sensor availability", table(profile)),
        )

    return pn.Column(
        pn.Row(variant, level, signal, condition),
        pn.bind(view, variant, level, signal, condition),
        sizing_mode="stretch_width",
    )


def resolution_view(
    ws, variant="wheel_slide", level="axle", signal="wheel_speed_kph", split="train"
):
    assigned = ws.select(split, variants=[variant])
    assets = [r["asset_id"] for r in assigned]
    raw = ws.load(level, split, assets=assets)
    minute = ws.summaries(level, split, assets=assets)
    target = assigned[0]["scenario"]["target"]
    for key in ("bogie_id", "axle_position", "wheel_side"):
        if target.get(key) is not None and key in raw:
            raw = raw[raw[key] == target[key]]
            minute = minute[minute[key] == target[key]]
    asset = assets[0]
    raw, minute = raw[raw.asset_id == asset], minute[minute.asset_id == asset]
    scenario = assigned[0]["scenario"]
    start = pd.Timestamp(scenario["start_time"])
    end = pd.Timestamp(scenario["end_time"])
    low, high = start - pd.Timedelta(minutes=3), end + pd.Timedelta(minutes=3)
    raw = raw[raw.event_time.between(low, high)]
    minute = minute[minute.window_start.between(low - pd.Timedelta(minutes=1), high)]
    fig = go.Figure()
    raw = timeline_data(raw, signal)
    fig.add_trace(
        go.Scatter(
            x=raw.event_time,
            y=raw[signal],
            mode="lines+markers",
            name="Raw received reading",
            line=dict(color="#243b48"),
            connectgaps=False,
        )
    )
    for stat, colour, dash in [
        ("mean", "#087c79", "solid"),
        ("minimum", "#4f768e", "dash"),
        ("maximum", "#b47727", "dot"),
    ]:
        fig.add_trace(
            go.Scatter(
                x=minute.window_start,
                y=minute[signal + "__" + stat],
                mode="lines+markers",
                name=f"Minute {stat} (at window start)",
                line=dict(color=colour, dash=dash),
                connectgaps=False,
            )
        )
    fig.add_vrect(x0=start, x1=end, fillcolor="#ba4a3d", opacity=0.12, line_width=0)
    fig.update_layout(
        xaxis_title="Observation / window-start time (UTC)",
        yaxis_title=f"{label(signal)} ({unit(signal)})",
    )
    return figure(
        fig,
        f"{asset} · {variant} · raw versus minute summaries; shading = configured ramp/interval",
    )


def outage_view(ws, split="train"):
    assets = [
        r["asset_id"]
        for r in ws.select(split)
        if r["variant"].startswith("controller_supply_failure")
        or r["variant"] == "premature_battery_depletion"
    ]
    observed = ws.load("wagon", split, assets=assets)
    absent = ws.missing(split, assets)
    available = observed[["asset_id", "event_time"]].assign(status="Received")
    missing = (
        absent[["asset_id", "expected_at"]]
        .rename(columns={"expected_at": "event_time"})
        .assign(status="Missing expected report")
    )
    slots = pd.concat([available, missing], ignore_index=True)
    fig = px.scatter(
        slots,
        x="event_time",
        y="asset_id",
        color="status",
        color_discrete_map={
            "Received": "#087c79",
            "Missing expected report": "#ba4a3d",
        },
    )
    fig.update_traces(marker_size=4)
    fig.update_layout(xaxis_title="Scheduled report time (UTC)", yaxis_title="Wagon")
    return figure(
        fig,
        "Observed reports and known synthetic missing slots — no invented voltage during silence",
    )


def artefact_views(ws, split="train"):
    records = []
    for run in ws.select(split):
        if run["scenario"] is None:
            continue
        s = run["scenario"]
        journey = read_json(
            ws.source / run["relative_directory"] / "journey_metadata.json"
        )
        start = pd.Timestamp(journey["scheduled_start_time"])
        onset = (pd.Timestamp(s["start_time"]) - start).total_seconds()
        records.append(
            {
                "variant": run["variant"],
                "asset_id": run["asset_id"],
                "onset_fraction": onset / journey["estimated_duration_seconds"],
                "severity": s["peak_severity"],
                "route_id": journey["route_id"],
            }
        )
    data = pd.DataFrame(records)
    fig = px.scatter(
        data,
        x="onset_fraction",
        y="variant",
        color="severity",
        hover_data=["asset_id", "route_id"],
    )
    fig.update_xaxes(range=[0, 1], title="Configured onset / duty duration")
    return pane(
        figure(
            fig,
            "Synthetic design audit — timing metadata, excluded from predictive inputs",
        )
    )


def timeline_data(data, signal):
    """Insert null separators; never imply measurements across absent time slots."""
    if data.empty:
        return data
    pieces = []
    for _, group in data.groupby("component"):
        group = group.sort_values("event_time")
        expected = (
            float(group.sampling_interval_seconds.iloc[0])
            if "sampling_interval_seconds" in group
            else None
        )
        if expected is None:
            # Normalised tables omit sampling; event spacing is measured, not a gap-filled value.
            diffs = group.event_time.diff().dt.total_seconds().dropna()
            expected = float(diffs.min()) if len(diffs) else 10.0
        gaps = group.event_time.diff().dt.total_seconds() > expected * 1.01
        separators = group.loc[gaps].copy()
        separators["event_time"] = separators.event_time - pd.Timedelta(milliseconds=1)
        separators[signal] = np.nan
        pieces.append(pd.concat([group, separators]).sort_values("event_time"))
    return pd.concat(pieces, ignore_index=True)


def identity_frequency(ws, split="train"):
    frames = []
    for level in NUMERIC:
        data = ws.load(level, split)
        counts = (
            data.groupby(["asset_id", "component"])
            .size()
            .reset_index(name="Received reports")
        )
        counts["Level"] = level
        frames.append(counts)
    return table(pd.concat(frames, ignore_index=True))


def engineering_relationships(ws, split="train"):
    wagon = ws.load("wagon", split, variants=["healthy"])
    bogie = ws.load("bogie", split, variants=["healthy"])
    brakes = bogie.merge(
        wagon[["asset_id", "event_id", "brake_demand"]],
        on=["asset_id", "event_id"],
        validate="many_to_one",
    )
    brake_chart = px.scatter(
        brakes,
        x="brake_pipe_pressure_bar",
        y="brake_cylinder_pressure_bar",
        color="brake_demand",
        facet_col="bogie_id",
        opacity=0.3,
        hover_data=["asset_id", "event_time"],
    )
    brake_chart.update_layout(xaxis_title="BPP (bar)", yaxis_title="BCP (bar)")
    axle = ws.load("axle", split, variants=["healthy"])
    wheel = ws.load("wheel", split, variants=["healthy"])
    thermal = wheel.merge(
        wagon[["asset_id", "event_id", "ambient_temp_c", "speed_kph"]],
        on=["asset_id", "event_id"],
        validate="many_to_one",
    )
    thermal = thermal.merge(
        axle[["asset_id", "event_id", "bogie_id", "axle_position", "axle_load_tonnes"]],
        on=["asset_id", "event_id", "bogie_id", "axle_position"],
        validate="many_to_one",
    )
    thermal["above_ambient_c"] = thermal.bearing_temp_c - thermal.ambient_temp_c
    heat_chart = px.scatter(
        thermal,
        x="speed_kph",
        y="above_ambient_c",
        color="axle_load_tonnes",
        opacity=0.35,
        hover_data=["component", "event_time"],
        labels={
            "speed_kph": "Wagon speed (km/h)",
            "above_ambient_c": "Bearing temperature above ambient (°C)",
            "axle_load_tonnes": "Axle load (tonnes)",
        },
    )
    return pn.Tabs(
        (
            "Brake demand and response",
            pane(
                figure(brake_chart, "Healthy braking — demand is independent context")
            ),
        ),
        (
            "Thermal context",
            pane(
                figure(heat_chart, "Healthy bearing heat — speed, load and thermal lag")
            ),
        ),
    )


def static_properties(ws, split="train"):
    assets, bogies, wheels = [], [], []
    for run in ws.select(split, variants=["healthy"]):
        asset = next(
            rows(ws.source / run["relative_directory"] / "asset_metadata.jsonl")
        )
        assets.append(
            {k: v for k, v in asset.items() if k not in ("bogies", "generator_seed")}
        )
        for bogie in asset["bogies"]:
            bogies.append(
                {
                    "asset_id": asset["asset_id"],
                    "bogie_id": bogie["bogie_id"],
                    "handbrake_equipped": bogie["handbrake_equipped"],
                }
            )
            for axle in bogie["axles"]:
                for wheel in axle["wheels"]:
                    wheels.append(
                        {
                            "asset_id": asset["asset_id"],
                            "bogie_id": bogie["bogie_id"],
                            "axle_position": axle["axle_position"],
                            **wheel,
                        }
                    )
    wheel_frame = pd.DataFrame(wheels)
    diameter = px.box(
        wheel_frame,
        x="asset_id",
        y="diameter_mm",
        points="all",
        hover_data=["bogie_id", "axle_position", "wheel_side"],
        labels={"asset_id": "Wagon", "diameter_mm": "Known wheel diameter (mm)"},
    )
    return pn.Tabs(
        ("Asset properties", table(pd.DataFrame(assets))),
        ("Handbrake position", table(pd.DataFrame(bogies))),
        (
            "Wheel diameters",
            pane(
                figure(diameter, "One value per known wheel, not weighted by reports")
            ),
        ),
    )
