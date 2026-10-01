import json
import shutil
from collections import Counter
from datetime import UTC, datetime

import pytest

from fleetguard.generator.fleet import (
    generate_healthy_journey_fleet,
    inject_fleet_anomaly_scenarios,
)
from fleetguard.generator.output import write_generation_run
from fleetguard.generator.route import build_journey_metadata
from fleetguard.portfolio.__main__ import main
from fleetguard.portfolio.planning import (
    SPLITS,
    VARIANTS,
    PortfolioConfig,
    choose_scenario,
    plan_assignments,
    plan_journey,
    serialise_scenario,
)
from fleetguard.portfolio.runner import generate_portfolio, write_json
from fleetguard.portfolio.validation import read_json, sha256, validate_portfolio, validate_run


@pytest.fixture(scope="module")
def cohort(tmp_path_factory):
    config = PortfolioConfig(
        start_time=datetime(2026, 1, 1, 6, tzinfo=UTC),
        sampling_interval_seconds=60,
        healthy_per_split=1,
    )
    root = tmp_path_factory.mktemp("portfolio")
    report = generate_portfolio(config, root)
    return config, root, report


def test_seeded_assignment_coverage_and_no_asset_leakage():
    config = PortfolioConfig(start_time=datetime(2026, 1, 1, 6, tzinfo=UTC))
    plan = plan_assignments(config)
    assert plan == plan_assignments(config)
    assert len(plan) == 48
    assert len({a.asset.asset_id for a in plan}) == 48
    assert plan != plan_assignments(config.model_copy(update={"seed": 43}))
    memberships = []
    for split in SPLITS:
        assignments = [a for a in plan if a.split == split]
        assert Counter(a.variant for a in assignments) == Counter(
            {**dict.fromkeys(VARIANTS, 1), "healthy": 3}
        )
        memberships.append({a.asset.asset_id for a in assignments})
    assert memberships[0].isdisjoint(memberships[1])
    assert memberships[0].isdisjoint(memberships[2])
    assert memberships[1].isdisjoint(memberships[2])
    assert [a.asset.asset_id for a in plan] != sorted(a.asset.asset_id for a in plan)


def test_config_rejects_naive_time_and_invalid_sizes():
    with pytest.raises(ValueError, match="UTC offset"):
        PortfolioConfig(start_time=datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        PortfolioConfig(start_time=datetime(2026, 1, 1, tzinfo=UTC), healthy_per_split=0)


def test_full_generated_cohort_passes_independent_validation(cohort):
    config, root, original = cohort
    assert validate_portfolio(root) == original
    assert original["counts"]["assets"] == 42
    assert original["counts"]["missing_reports"] > 0
    assert (
        original["counts"]["telemetry_events"] + original["counts"]["missing_reports"]
        == original["counts"]["expected_reports"]
    )
    assert len(read_json(root / "cohort_plan.json")["runs"]) == 42
    assert config.sampling_interval_seconds == 60


def test_components_are_varied_and_eligible(cohort):
    config, root, _ = cohort
    entries = read_json(root / "cohort_plan.json")["runs"]
    targets = [e["scenario"]["target"] for e in entries if e["scenario"]]
    assert {t["bogie_id"] for t in targets if t["bogie_id"]} == {1, 2}
    assert {t["axle_position"] for t in targets if t["axle_position"]} == {"inner", "outer"}
    assert {t["wheel_side"] for t in targets if t["wheel_side"]} == {"left", "right"}
    severities = {e["scenario"]["peak_severity"] for e in entries if e["scenario"]}
    assert severities == {"low", "medium", "high"}
    for assignment, entry in zip(plan_assignments(config), entries, strict=True):
        if assignment.variant not in ("wheel_slide", "brake_release_failure", "healthy"):
            continue
        journey = plan_journey(assignment, config)
        baseline = generate_healthy_journey_fleet(
            (assignment.asset,), config.start_time, journey, 60
        )
        selected = choose_scenario(assignment, baseline.events)
        assert serialise_scenario(selected) == entry["scenario"]
        if selected is None:
            continue
        idx = next(i for i, e in enumerate(baseline.events) if e.event_time == selected.start_time)
        event = baseline.events[idx]
        if assignment.variant == "wheel_slide":
            assert event.brake_demand == "apply" and event.speed_kph > 5
            assert selected.target.wheel_side is None
        else:
            assert baseline.events[idx - 1].brake_demand == "apply"
            assert event.brake_demand == "release"


@pytest.mark.parametrize(
    "variant", ["healthy", "bearing_degradation", "controller_supply_failure:bounded"]
)
def test_regenerating_run_is_byte_identical(cohort, tmp_path, variant):
    config, root, _ = cohort
    assignment = next(a for a in plan_assignments(config) if a.variant == variant)
    journey = plan_journey(assignment, config)
    baseline = generate_healthy_journey_fleet((assignment.asset,), config.start_time, journey, 60)
    scenario = choose_scenario(assignment, baseline.events)
    batch = inject_fleet_anomaly_scenarios(baseline, (scenario,)) if scenario else baseline
    write_generation_run(
        tmp_path,
        batch,
        build_journey_metadata(journey, config.start_time, 60),
        config.seed,
        variant,
    )
    for original in (root / assignment.relative_directory).iterdir():
        assert original.read_bytes() == (tmp_path / original.name).read_bytes()


def copied_run(cohort, tmp_path, variant="bearing_degradation"):
    config, root, _ = cohort
    assignment = next(a for a in plan_assignments(config) if a.variant == variant)
    entry = next(
        e
        for e in read_json(root / "cohort_plan.json")["runs"]
        if e["asset_id"] == assignment.asset.asset_id
    )
    folder = tmp_path / "run"
    shutil.copytree(root / assignment.relative_directory, folder)
    return config, assignment, entry, folder


def edit_first_row(folder, filename, mutate, rehash=True):
    path = folder / filename
    lines = path.read_text().splitlines()
    row = json.loads(lines[0])
    mutate(row)
    lines[0] = json.dumps(row)
    path.write_text("\n".join(lines) + "\n")
    if rehash:
        manifest = read_json(folder / "manifest.json")
        manifest["files"][filename]["sha256"] = sha256(path)
        write_json(folder / "manifest.json", manifest)


def test_detects_corrupted_file_checksum(cohort, tmp_path):
    config, assignment, entry, folder = copied_run(cohort, tmp_path)
    edit_first_row(folder, "telemetry.jsonl", lambda r: r.update(speed_kph=0.1), rehash=False)
    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_run(folder, assignment, config, entry)


def test_detects_component_mismatch_even_with_updated_checksum(cohort, tmp_path):
    config, assignment, entry, folder = copied_run(cohort, tmp_path)
    edit_first_row(folder, "wheel_observations.jsonl", lambda r: r.update(bearing_temp_c=100))
    with pytest.raises(ValueError, match="component lineage"):
        validate_run(folder, assignment, config, entry)


def test_detects_truth_identity_mismatch_even_with_updated_checksum(cohort, tmp_path):
    config, assignment, entry, folder = copied_run(cohort, tmp_path)
    edit_first_row(
        folder,
        "anomaly_truth.jsonl",
        lambda r: r.update(event_id="00000000-0000-0000-0000-000000000000"),
    )
    with pytest.raises(ValueError, match="ID mismatch"):
        validate_run(folder, assignment, config, entry)


def test_detects_outage_boundary_mismatch(cohort, tmp_path):
    config, assignment, entry, folder = copied_run(
        cohort, tmp_path, "controller_supply_failure:bounded"
    )
    edit_first_row(folder, "outage_truth.jsonl", lambda r: r.update(missing_reports=999))
    with pytest.raises(ValueError, match="outage missing count"):
        validate_run(folder, assignment, config, entry)


def test_refuses_existing_outputs(cohort):
    config, root, _ = cohort
    original_hash = sha256(root / "cohort_plan.json")
    with pytest.raises(ValueError, match="empty"):
        generate_portfolio(config, root)
    assert sha256(root / "cohort_plan.json") == original_hash


def test_incomplete_cohort_cannot_validate(tmp_path):
    assert main(["validate", "--input-dir", str(tmp_path)]) == 1


def test_changed_split_plan_rejected(cohort, tmp_path):
    config, root, _ = cohort
    plan = read_json(root / "cohort_plan.json")
    plan["runs"][0]["split"] = "test"
    write_json(tmp_path / "cohort_plan.json", plan)
    with pytest.raises(ValueError, match="asset/split assignment"):
        validate_portfolio(tmp_path, require_manifest=False)


def test_wrong_component_truth_rejected_even_when_checksums_match(cohort, tmp_path):
    config, assignment, entry, folder = copied_run(cohort, tmp_path)
    path = folder / "anomaly_truth.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    row = next(row for row in records if row["is_anomaly"])
    row["affected_component"] = "bogie:99/axle:outer/wheel:left"
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    manifest = read_json(folder / "manifest.json")
    manifest["files"][path.name]["sha256"] = sha256(path)
    write_json(folder / "manifest.json", manifest)
    with pytest.raises(ValueError, match="component/signal"):
        validate_run(folder, assignment, config, entry)


def test_empty_expected_report_slot_rejected(cohort, tmp_path):
    config, assignment, entry, folder = copied_run(cohort, tmp_path)
    # Remove the final observed timestamp and corresponding truth and all component rows.
    for filename, count in [
        ("telemetry.jsonl", 1),
        ("anomaly_truth.jsonl", 1),
        ("bogie_observations.jsonl", 2),
        ("axle_observations.jsonl", 4),
        ("wheel_observations.jsonl", 8),
    ]:
        path = folder / filename
        path.write_text("\n".join(path.read_text().splitlines()[:-count]) + "\n")
    manifest = read_json(folder / "manifest.json")
    for filename in manifest["files"]:
        manifest["files"][filename]["sha256"] = sha256(folder / filename)
    write_json(folder / "manifest.json", manifest)
    with pytest.raises(ValueError, match="grid is incomplete"):
        validate_run(folder, assignment, config, entry)
