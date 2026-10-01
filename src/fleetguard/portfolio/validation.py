"""Validate saved data, not just successful execution of the generator."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from fleetguard.contracts import (
    SCHEMA_VERSION,
    AnomalySeverity,
    AnomalyTruth,
    AnomalyType,
    AssetMetadata,
    JourneyMetadata,
    MissingReportTruth,
    OutageTruth,
    TelemetryEvent,
)
from fleetguard.generator.anomalies import AnomalyScenario, ComponentTarget
from fleetguard.generator.extended_anomalies import AXLE_TYPES
from fleetguard.generator.normalise import normalise_event
from fleetguard.generator.route import build_journey_metadata
from fleetguard.portfolio.planning import (
    PLAN_VERSION,
    SPLITS,
    VARIANTS,
    PortfolioConfig,
    plan_assignments,
    plan_journey,
)

RUN_FILES = {
    "asset_metadata.jsonl",
    "journey_metadata.json",
    "telemetry.jsonl",
    "anomaly_truth.jsonl",
    "bogie_observations.jsonl",
    "axle_observations.jsonl",
    "wheel_observations.jsonl",
    "missing_report_truth.jsonl",
    "outage_truth.jsonl",
    "scenario_metadata.json",
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def rows(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def parse_scenario(raw: dict) -> AnomalyScenario:
    fields = dict(raw)
    fields["anomaly_type"] = AnomalyType(fields["anomaly_type"])
    fields["peak_severity"] = AnomalySeverity(fields["peak_severity"])
    fields["target"] = ComponentTarget(**fields["target"])
    for key in ("start_time", "end_time", "recovery_time"):
        if fields[key] is not None:
            fields[key] = datetime.fromisoformat(fields[key])
    return AnomalyScenario(**fields)


def expected_label(scenario: AnomalyScenario) -> tuple[str, str]:
    kind, target = scenario.anomaly_type, scenario.target
    axle = f"bogie:{target.bogie_id}/axle:{target.axle_position}"
    if kind in AXLE_TYPES:
        return (
            axle,
            "vibration_rms_g" if kind == AnomalyType.SUSPECTED_WHEEL_FLAT else "wheel_speed_kph",
        )
    if kind in (AnomalyType.BEARING_DEGRADATION, AnomalyType.SENSOR_FAULT):
        suffix = "/sensor:bearing_temp_c" if kind == AnomalyType.SENSOR_FAULT else ""
        return f"{axle}/wheel:{target.wheel_side}{suffix}", "bearing_temp_c"
    if kind == AnomalyType.BRAKE_PRESSURE_LEAK:
        return "wagon:pneumatic_system", "brake_pipe_pressure_bar"
    if kind == AnomalyType.PRESSURE_TRANSDUCER_FAILURE:
        scope = "wagon" if target.bogie_id is None else f"bogie:{target.bogie_id}"
        return (
            f"{scope}:sensor:{target.signal_name}"
            if target.bogie_id is None
            else f"{scope}/sensor:{target.signal_name}",
            target.signal_name,
        )
    if kind in (AnomalyType.BRAKE_RELEASE_FAILURE, AnomalyType.UNDEMANDED_BRAKE_APPLICATION):
        return "wagon:brake_system", "brake_cylinder_pressure_bar"
    if kind == AnomalyType.PREMATURE_BATTERY_DEPLETION:
        return "wagon:battery", "battery_voltage_v"
    return "wagon:controller", "controller_supply_voltage_v"


def validate_run(folder: Path, assignment, config: PortfolioConfig, entry: dict) -> dict:
    manifest = read_json(folder / "manifest.json")
    require(manifest["schema_version"] == SCHEMA_VERSION, "wrong schema version")
    require(manifest["seed"] == config.seed, "wrong run seed")
    require(manifest["anomaly_profile"] == assignment.variant, "run variant differs from plan")
    require(set(manifest["files"]) == RUN_FILES, "missing or unexpected run files")
    for filename, info in manifest["files"].items():
        require(sha256(folder / filename) == info["sha256"], f"checksum mismatch: {filename}")
    assets = [AssetMetadata.model_validate(r) for r in rows(folder / "asset_metadata.jsonl")]
    require(assets == [assignment.asset], "asset metadata differs from seeded plan")
    asset = assets[0]
    journey = JourneyMetadata.model_validate(read_json(folder / "journey_metadata.json"))
    expected_journey = build_journey_metadata(
        plan_journey(assignment, config), config.start_time, config.sampling_interval_seconds
    )
    require(journey == expected_journey, "journey differs from seeded plan")
    require(manifest["journey_id"] == journey.journey_id, "manifest journey mismatch")
    require(manifest["route_id"] == journey.route_id, "manifest route mismatch")
    require(
        manifest["sampling_interval_seconds"] == config.sampling_interval_seconds,
        "manifest sampling mismatch",
    )
    require(manifest["feature_window_seconds"] == 60, "feature-window mismatch")
    scenario_file = read_json(folder / "scenario_metadata.json")
    scenario = entry["scenario"]
    require(
        scenario_file
        == {"schema_version": SCHEMA_VERSION, "scenarios": [] if scenario is None else [scenario]},
        "scenario metadata differs from cohort plan",
    )
    require((scenario is None) == (assignment.variant == "healthy"), "scenario assignment mismatch")
    if scenario:
        require(scenario["target"]["asset_id"] == asset.asset_id, "wrong scenario target asset")
        require(scenario["anomaly_type"] == assignment.variant.split(":")[0], "wrong scenario type")
    parsed = parse_scenario(scenario) if scenario else None
    if parsed and parsed.anomaly_type == AnomalyType.CONTROLLER_SUPPLY_FAILURE:
        require(parsed.outage_mode == assignment.variant.split(":")[1], "controller mode mismatch")
    step = timedelta(seconds=config.sampling_interval_seconds)
    expected_count = math.ceil(journey.estimated_duration_seconds / step.total_seconds())
    expected_times = {config.start_time + i * step for i in range(expected_count)}
    horizon = config.start_time + expected_count * step
    if parsed:
        require(parsed.start_time in expected_times, "scenario onset is off-grid")
        require(parsed.end_time < horizon, "scenario peak is outside journey")
        if parsed.recovery_time:
            require(parsed.recovery_time < horizon, "bounded recovery is outside journey")
    observed_times, event_ids = set(), set()
    anomaly_counts = Counter()
    # Iterators compare every component row, not just aggregate counts.
    components = {
        name: rows(folder / f"{name}_observations.jsonl") for name in ("bogie", "axle", "wheel")
    }
    component_counts = Counter()
    previous = None
    for raw_event, raw_truth in zip(
        rows(folder / "telemetry.jsonl"), rows(folder / "anomaly_truth.jsonl"), strict=True
    ):
        event = TelemetryEvent.model_validate(raw_event)
        truth = AnomalyTruth.model_validate(raw_truth)
        require(event.asset_id == truth.asset_id == asset.asset_id, "event/truth asset mismatch")
        require(event.event_id == truth.event_id, "event/truth ID mismatch")
        require(event.event_id not in event_ids, "duplicate event ID")
        require(event.event_time in expected_times, "off-grid event timestamp")
        require(previous is None or event.event_time > previous, "duplicate/unordered timestamp")
        require(
            event.sampling_interval_seconds == config.sampling_interval_seconds,
            "event sampling mismatch",
        )
        require(
            event.journey_id == journey.journey_id and event.route_id == journey.route_id,
            "event journey/route mismatch",
        )
        event_ids.add(event.event_id)
        observed_times.add(event.event_time)
        previous = event.event_time
        if truth.is_anomaly:
            require(scenario is not None, "healthy control contains anomaly")
            require(
                truth.anomaly_type.value == scenario["anomaly_type"], "unexpected anomaly label"
            )
            require(truth.anomaly_severity.value == scenario["peak_severity"], "severity mismatch")
            require(
                truth.anomaly_start_time.isoformat()
                == scenario["start_time"].replace("Z", "+00:00"),
                "truth onset differs from scenario",
            )
            require(event.event_time >= truth.anomaly_start_time, "anomaly precedes onset")
            require(
                (truth.affected_component, truth.affected_signal) == expected_label(parsed),
                "truth component/signal differs from scenario target",
            )
            anomaly_counts[truth.anomaly_type.value] += 1
        normal = normalise_event(event, asset)
        for name, expected in (
            ("bogie", normal.bogies),
            ("axle", normal.axles),
            ("wheel", normal.wheels),
        ):
            for row in expected:
                actual = next(components[name], None)
                require(actual == row.model_dump(mode="json"), f"{name} component lineage mismatch")
                component_counts[name] += 1
    for name, iterator in components.items():
        require(next(iterator, None) is None, f"extra {name} rows")
    missing = [
        MissingReportTruth.model_validate(r) for r in rows(folder / "missing_report_truth.jsonl")
    ]
    missing_times = {m.expected_at for m in missing}
    missing_ids = {m.event_id for m in missing}
    require(len(missing) == len(missing_times) == len(missing_ids), "duplicate missing reports")
    require(missing_times.isdisjoint(observed_times), "timestamp both observed and missing")
    require(missing_ids.isdisjoint(event_ids), "event ID both observed and missing")
    require(observed_times | missing_times == expected_times, "expected-report grid is incomplete")
    require([m.expected_at for m in missing] == sorted(missing_times), "unordered missing truth")
    for m in missing:
        require(scenario is not None, "healthy control contains an outage")
        require(
            parsed.anomaly_type
            in (AnomalyType.CONTROLLER_SUPPLY_FAILURE, AnomalyType.PREMATURE_BATTERY_DEPLETION),
            "this scenario cannot suppress reports",
        )
        require(m.expected_at >= parsed.start_time, "missing report precedes onset")
        require(
            m.asset_id == asset.asset_id and m.scenario_id == scenario["scenario_id"],
            "missing report target mismatch",
        )
        require(m.anomaly_type.value == scenario["anomaly_type"], "missing report type mismatch")
        require(
            m.anomaly_severity.value == scenario["peak_severity"],
            "missing report severity mismatch",
        )
    outages = [OutageTruth.model_validate(r) for r in rows(folder / "outage_truth.jsonl")]
    groups = []
    for time in sorted(missing_times):
        if not groups or time != groups[-1][-1] + step:
            groups.append([])
        groups[-1].append(time)
    require(len(groups) == len(outages), "outage interval count mismatch")
    for group, outage in zip(groups, outages, strict=True):
        require(
            outage.asset_id == asset.asset_id and outage.scenario_id == scenario["scenario_id"],
            "outage identity mismatch",
        )
        require(outage.anomaly_type.value == scenario["anomaly_type"], "outage type mismatch")
        require(
            outage.start_time == group[0] and outage.end_time_exclusive == group[-1] + step,
            "outage boundaries mismatch",
        )
        require(outage.missing_reports == len(group), "outage missing count mismatch")
        require(outage.recovered == (group[-1] + step < horizon), "outage recovery mismatch")
    counts = {
        "assets": 1,
        "expected_reports": expected_count,
        "telemetry_events": len(event_ids),
        "truth_records": len(event_ids),
        "missing_reports": len(missing),
        "outages": len(outages),
        **{f"{k}_observations": v for k, v in component_counts.items()},
    }
    require(manifest["counts"] == counts, "manifest counts mismatch")
    file_counts = {
        "asset_metadata.jsonl": 1,
        "journey_metadata.json": 1,
        "scenario_metadata.json": int(scenario is not None),
        "telemetry.jsonl": len(event_ids),
        "anomaly_truth.jsonl": len(event_ids),
        "missing_report_truth.jsonl": len(missing),
        "outage_truth.jsonl": len(outages),
        **{f"{k}_observations.jsonl": v for k, v in component_counts.items()},
    }
    require(
        all(manifest["files"][f]["records"] == n for f, n in file_counts.items()),
        "file record counts mismatch",
    )
    require(
        manifest["anomalous_observed_reports_by_type"] == dict(anomaly_counts),
        "anomaly counts mismatch",
    )
    require(
        manifest["scenario_asset_ids"] == ([] if scenario is None else [asset.asset_id]),
        "scenario asset list mismatch",
    )
    require(
        assignment.variant == "healthy" or sum(anomaly_counts.values()) + len(missing) > 0,
        "assigned fault produced no evidence",
    )
    return {
        "asset_id": asset.asset_id,
        "split": assignment.split,
        "variant": assignment.variant,
        "route_id": journey.route_id,
        "travel_direction": journey.travel_direction.value,
        "target": None if scenario is None else scenario["target"],
        "severity": None if scenario is None else scenario["peak_severity"],
        "counts": counts,
        "observed_anomaly_count": sum(anomaly_counts.values()),
        "anomalous_observed_fraction": round(sum(anomaly_counts.values()) / len(event_ids), 6),
        "missing_fraction": round(len(missing) / expected_count, 6),
        "event_ids": event_ids | missing_ids,
    }


def validate_portfolio(root: Path, *, require_manifest: bool = True) -> dict:
    """Raise ValueError on bad data. Reports are returned only after a complete pass."""
    plan = read_json(root / "cohort_plan.json")
    require(plan["plan_version"] == PLAN_VERSION, "unsupported plan version")
    config = PortfolioConfig.model_validate(plan["config"])
    expected = plan_assignments(config)
    require(len(plan["runs"]) == len(expected), "cohort run count mismatch")
    manifest_path = root / "cohort_manifest.json"
    if require_manifest:
        require(manifest_path.is_file(), "cohort is incomplete: no completion manifest")
        cohort_manifest = read_json(manifest_path)
        require(
            cohort_manifest["plan_sha256"] == sha256(root / "cohort_plan.json"),
            "cohort plan checksum mismatch",
        )
    all_ids, assets = set(), set()
    summaries = []
    for assignment, entry in zip(expected, plan["runs"], strict=True):
        require(
            entry["relative_directory"] == assignment.relative_directory,
            "run path/split differs from seeded plan",
        )
        require(
            entry["asset_id"] == assignment.asset.asset_id and entry["split"] == assignment.split,
            "asset/split assignment differs from seeded plan",
        )
        require(
            entry["variant"] == assignment.variant, "variant assignment differs from seeded plan"
        )
        require(
            entry["journey_seed"] == assignment.journey_seed
            and entry["scenario_seed"] == assignment.scenario_seed,
            "seed assignment differs from plan",
        )
        require(entry["asset_id"] not in assets, "asset leakage across runs/splits")
        assets.add(entry["asset_id"])
        folder = root / assignment.relative_directory
        if require_manifest:
            require(
                cohort_manifest["run_manifests"].get(assignment.relative_directory)
                == sha256(folder / "manifest.json"),
                "run manifest checksum mismatch",
            )
        summary = validate_run(folder, assignment, config, entry)
        require(all_ids.isdisjoint(summary["event_ids"]), "event leakage across runs/splits")
        all_ids.update(summary.pop("event_ids"))
        summaries.append(summary)
    if require_manifest:
        require(
            set(cohort_manifest["run_manifests"]) == {a.relative_directory for a in expected},
            "unexpected/missing run manifest entries",
        )
    totals = Counter()
    for summary in summaries:
        totals.update(summary["counts"])
    coverage = {
        split: dict(sorted(Counter(s["variant"] for s in summaries if s["split"] == split).items()))
        for split in SPLITS
    }
    for split in SPLITS:
        require(
            set(coverage[split]) == {*VARIANTS, "healthy"},
            f"incomplete variant coverage in {split}",
        )
    return {
        "status": "passed",
        "plan_version": PLAN_VERSION,
        "schema_version": SCHEMA_VERSION,
        "scope": "synthetic coverage cohort; not operational prevalence or model performance",
        "counts": dict(totals),
        "coverage_by_split": coverage,
        "observed_anomaly_count": sum(s["observed_anomaly_count"] for s in summaries),
        "runs": summaries,
    }
