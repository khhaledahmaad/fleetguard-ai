"""Describe validated datasets without constructing model inputs or labels."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from fleetguard.features.hierarchical_dataset import validate_feature_dataset
from fleetguard.features.hierarchical_models import LEVELS
from fleetguard.portfolio.planning import SPLITS
from fleetguard.portfolio.validation import read_json, sha256, validate_portfolio


def iter_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def summarise_windows(rows):
    """Separate absent reports from unavailable sensors in received reports."""
    counts = Counter()
    quality = defaultdict(Counter)
    for row in rows:
        counts["rows"] += 1
        received, expected = row["received_reports"], row["expected_reports"]
        counts["expected_component_reports"] += expected
        counts["received_component_reports"] += received
        counts["missing_component_reports"] += expected - received
        state = (
            "silent"
            if not received
            else "complete"
            if received == expected
            else "partial"
        )
        counts[state + "_windows"] += 1
        for name, summary in row["numeric"].items():
            for kind in ("valid", "missing", "invalid"):
                quality[name][kind] += summary[kind + "_count"]
            quality[name]["windows_without_valid_readings"] += (
                summary["valid_count"] == 0
            )
    return {
        "counts": dict(counts),
        "numeric_quality": {
            name: dict(values) for name, values in sorted(quality.items())
        },
    }


def audit_dataset(source: Path, features: Path) -> dict:
    """Validate both datasets and require feature provenance to match this source."""
    source_report = validate_portfolio(source)
    feature_report = validate_feature_dataset(features)
    manifest = read_json(features / "feature_manifest.json")
    for field, filename in (
        ("source_plan_sha256", "cohort_plan.json"),
        ("source_manifest_sha256", "cohort_manifest.json"),
    ):
        if manifest[field] != sha256(source / filename):
            raise ValueError("features do not belong to the supplied portfolio")
    plan = read_json(source / "cohort_plan.json")
    result = {
        "audit_version": "1.0",
        "validation": {
            "portfolio": source_report["status"],
            "features": feature_report["status"],
        },
        "source_plan_sha256": manifest["source_plan_sha256"],
        "source_manifest_sha256": manifest["source_manifest_sha256"],
        "splits": {},
        "interpretation": [
            "Coverage is deliberate, not natural fault prevalence.",
            "Assigned fault assets can contain healthy observed reports.",
            "Silent windows are separate from invalid/missing sensor readings.",
            "Component counts must not be summed as independent wagon reports.",
            "Truth, scenario configuration, IDs and split names are not predictive inputs.",
            "No model readiness threshold or detection performance is asserted.",
        ],
    }
    for split in SPLITS:
        assigned, labels, routes = Counter(), Counter(), Counter()
        missing, out = 0, 0
        for run in plan["runs"]:
            if run["split"] != split:
                continue
            assigned[run["variant"]] += 1
            folder = source / run["relative_directory"]
            routes[read_json(folder / "journey_metadata.json")["route_id"]] += 1
            for row in iter_jsonl(folder / "anomaly_truth.jsonl"):
                labels[row["anomaly_type"]] += 1
            missing += sum(1 for _ in iter_jsonl(folder / "missing_report_truth.jsonl"))
            out += sum(1 for _ in iter_jsonl(folder / "outage_truth.jsonl"))
        result["splits"][split] = {
            "assigned_assets_by_variant": dict(sorted(assigned.items())),
            "assets_by_route": dict(sorted(routes.items())),
            "observed_truth_reports_by_type": dict(sorted(labels.items())),
            "missing_wagon_reports": missing,
            "outage_intervals": out,
            "features": {
                level: summarise_windows(
                    iter_jsonl(features / f"{split}_{level}_features.jsonl")
                )
                for level in LEVELS
            },
        }
    return result


def markdown_report(report):
    lines = [
        "# FleetGuard dataset audit",
        "",
        "Source and feature validation passed.",
        "",
    ]
    lines += ["## Interpretation", ""] + [
        "- " + item for item in report["interpretation"]
    ]
    for split, info in report["splits"].items():
        lines += [
            "",
            f"## {split.title()}",
            "",
            "### Assigned wagons",
            "",
            "| Variant | Wagons |",
            "| --- | --- |",
        ]
        lines += [
            f"| {name} | {count} |"
            for name, count in info["assigned_assets_by_variant"].items()
        ]
        lines += [
            "",
            f"Missing wagon reports: {info['missing_wagon_reports']}. "
            f"Outage intervals: {info['outage_intervals']}.",
            "",
            "### Feature windows",
            "",
            "| Level | Rows | Complete | Partial | Silent |",
            "| --- | --- | --- | --- | --- |",
        ]
        for level, summary in info["features"].items():
            c = summary["counts"]
            lines.append(
                f"| {level} | {c.get('rows', 0)} | {c.get('complete_windows', 0)} "
                f"| {c.get('partial_windows', 0)} | {c.get('silent_windows', 0)} |"
            )
        lines += [
            "",
            "Route coverage, observed truth counts and per-signal quality totals "
            "are in `audit.json`. Counts describe coverage, not model accuracy.",
        ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--feature-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = args.output_dir.resolve()
        for dataset in (args.source_dir.resolve(), args.feature_dir.resolve()):
            if output == dataset or dataset in output.parents:
                raise ValueError("audit output must be outside both datasets")
        if output.exists() and any(output.iterdir()):
            raise ValueError("audit output directory must be empty")
        report = audit_dataset(args.source_dir, args.feature_dir)
        output.mkdir(parents=True, exist_ok=True)
        (output / "audit.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        (output / "audit.md").write_text(markdown_report(report), encoding="utf-8")
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"FAILED: {error}")
        return 1
    print(f"Audit complete: {output / 'audit.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
