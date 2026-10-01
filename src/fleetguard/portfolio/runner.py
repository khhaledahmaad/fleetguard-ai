"""Generate each wagon independently; publish a completion manifest only after validation."""

from __future__ import annotations

import json
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path

from fleetguard.contracts import SCHEMA_VERSION
from fleetguard.generator.fleet import (
    generate_healthy_journey_fleet,
    inject_fleet_anomaly_scenarios,
)
from fleetguard.generator.output import write_generation_run
from fleetguard.generator.route import build_journey_metadata
from fleetguard.portfolio.planning import (
    PLAN_VERSION,
    PortfolioConfig,
    choose_scenario,
    plan_assignments,
    plan_journey,
    serialise_scenario,
)
from fleetguard.portfolio.validation import sha256, validate_portfolio


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


def generate_portfolio(
    config: PortfolioConfig, root: Path, progress: Callable[[str], None] | None = None
) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError(f"output directory must be empty: {root}")
    assignments = plan_assignments(config)
    write_json(root / "generation_config.json", config.model_dump(mode="json"))
    entries = []
    for index, assignment in enumerate(assignments, 1):
        journey = plan_journey(assignment, config)
        batch = generate_healthy_journey_fleet(
            (assignment.asset,), config.start_time, journey, config.sampling_interval_seconds
        )
        scenario = choose_scenario(assignment, batch.events)
        if scenario:
            batch = inject_fleet_anomaly_scenarios(batch, (scenario,))
        write_generation_run(
            root / assignment.relative_directory,
            batch,
            build_journey_metadata(journey, config.start_time, config.sampling_interval_seconds),
            config.seed,
            anomaly_profile=assignment.variant,
        )
        entries.append(
            {
                "asset_id": assignment.asset.asset_id,
                "split": assignment.split,
                "variant": assignment.variant,
                "relative_directory": assignment.relative_directory,
                "journey_seed": assignment.journey_seed,
                "scenario_seed": assignment.scenario_seed,
                "scenario": serialise_scenario(scenario),
            }
        )
        if progress:
            progress(
                f"[{index}/{len(assignments)}] {assignment.split} "
                f"{assignment.asset.asset_id}: {assignment.variant}"
            )
    write_json(
        root / "cohort_plan.json",
        {"plan_version": PLAN_VERSION, "config": config.model_dump(mode="json"), "runs": entries},
    )
    if progress:
        progress("Validating every saved event, truth row, component row and checksum...")
    report = validate_portfolio(root, require_manifest=False)
    write_json(root / "validation_report.json", report)
    write_json(
        root / "cohort_manifest.json",
        {
            "plan_version": PLAN_VERSION,
            "schema_version": SCHEMA_VERSION,
            "generator_version": version("fleetguard-ai"),
            "plan_sha256": sha256(root / "cohort_plan.json"),
            "run_manifests": {
                a.relative_directory: sha256(root / a.relative_directory / "manifest.json")
                for a in assignments
            },
        },
    )
    return report
