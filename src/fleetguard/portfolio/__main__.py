from __future__ import annotations

import argparse
from pathlib import Path

from fleetguard.generator.cli import _aware_datetime
from fleetguard.portfolio.planning import PortfolioConfig
from fleetguard.portfolio.runner import generate_portfolio, write_json
from fleetguard.portfolio.validation import validate_portfolio


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate or validate a FleetGuard coverage cohort."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate")
    generate.add_argument("--seed", type=int, default=42)
    generate.add_argument("--start-time", type=_aware_datetime, required=True)
    generate.add_argument("--sampling-interval-seconds", type=int, choices=(1, 10, 60), default=10)
    generate.add_argument("--replicates", type=int, default=1)
    generate.add_argument("--healthy-per-split", type=int, default=3)
    generate.add_argument("--output-dir", type=Path, required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--input-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            config = PortfolioConfig(
                seed=args.seed,
                start_time=args.start_time,
                sampling_interval_seconds=args.sampling_interval_seconds,
                replicates=args.replicates,
                healthy_per_split=args.healthy_per_split,
            )
            report = generate_portfolio(config, args.output_dir, progress=print)
        else:
            report = validate_portfolio(args.input_dir)
            write_json(args.input_dir / "validation_report.json", report)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"FAILED: {error}")
        return 1
    print(f"Validation: {report['status']}")
    for name in ("assets", "expected_reports", "telemetry_events", "missing_reports"):
        print(f"{name}: {report['counts'][name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
