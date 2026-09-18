from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from fleetguard.generator.fleet import (
    generate_fleet_assets,
    generate_healthy_journey_fleet,
)
from fleetguard.generator.output import write_generation_run
from fleetguard.generator.route import (
    build_journey_metadata,
    create_random_journey_plan,
)


def _aware_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("start time must be ISO 8601") from error

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("start time must include a UTC offset")

    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a FleetGuard telemetry dataset."
    )

    parser.add_argument(
        "--assets",
        type=int,
        default=3,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )

    parser.add_argument(
        "--start-time",
        type=_aware_datetime,
        required=True,
    )

    parser.add_argument(
        "--sampling-interval-seconds",
        type=int,
        choices=(1, 10, 60),
        default=10,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)

    assets = generate_fleet_assets(
        arguments.assets,
        arguments.seed,
    )

    journey = create_random_journey_plan(
        arguments.seed,
        service_date=arguments.start_time.date(),
    )

    journey_metadata = build_journey_metadata(
        journey,
        arguments.start_time,
        arguments.sampling_interval_seconds,
    )

    fleet_batch = generate_healthy_journey_fleet(
        assets,
        arguments.start_time,
        journey,
        sampling_interval_seconds=(arguments.sampling_interval_seconds),
    )

    manifest = write_generation_run(
        arguments.output_dir,
        fleet_batch,
        journey_metadata,
        arguments.seed,
    )

    print(f"Journey: {journey.origin} -> " f"{journey.destination}")
    print(f"Journey ID: {journey.journey_id}")
    print(f"Sampling: " f"{arguments.sampling_interval_seconds} seconds")
    print(f"Telemetry events: " f"{manifest['counts']['telemetry_events']}")
    print(f"Output: {arguments.output_dir}")

    return 0
