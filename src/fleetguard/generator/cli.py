from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

from fleetguard.contracts import (
    AnomalySeverity,
    AnomalyType,
)
from fleetguard.generator.anomalies import (
    AnomalyScenario,
    ComponentTarget,
)
from fleetguard.generator.fleet import (
    generate_fleet_assets,
    generate_healthy_journey_fleet,
    inject_fleet_anomaly_scenarios,
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


def _build_bearing_demo_scenario(
    asset_id: str,
    start_time: datetime,
    journey_duration_seconds: int,
) -> AnomalyScenario:
    anomaly_start = start_time + timedelta(seconds=int(journey_duration_seconds * 0.35))

    peak_time = start_time + timedelta(seconds=int(journey_duration_seconds * 0.70))

    return AnomalyScenario(
        scenario_id="FG-ANO-BEARING-DEMO-0001",
        anomaly_type=AnomalyType.BEARING_DEGRADATION,
        target=ComponentTarget(
            asset_id=asset_id,
            bogie_id=1,
            axle_position="outer",
            wheel_side="left",
        ),
        start_time=anomaly_start,
        end_time=peak_time,
        peak_severity=AnomalySeverity.HIGH,
    )


def _build_brake_leak_demo_scenario(
    asset_id: str,
    start_time: datetime,
    journey_duration_seconds: int,
) -> AnomalyScenario:
    anomaly_start = start_time + timedelta(seconds=int(journey_duration_seconds * 0.45))

    peak_time = start_time + timedelta(seconds=int(journey_duration_seconds * 0.75))

    return AnomalyScenario(
        scenario_id="FG-ANO-BRAKE-LEAK-DEMO-0001",
        anomaly_type=AnomalyType.BRAKE_PRESSURE_LEAK,
        target=ComponentTarget(
            asset_id=asset_id,
            signal_name="brake_pipe_pressure_bar",
        ),
        start_time=anomaly_start,
        end_time=peak_time,
        peak_severity=AnomalySeverity.HIGH,
    )


def _build_sensor_drift_demo_scenario(
    asset_id: str,
    start_time: datetime,
    journey_duration_seconds: int,
) -> AnomalyScenario:
    anomaly_start = start_time + timedelta(seconds=int(journey_duration_seconds * 0.30))

    peak_time = start_time + timedelta(seconds=int(journey_duration_seconds * 0.60))

    return AnomalyScenario(
        scenario_id="FG-ANO-SENSOR-DRIFT-DEMO-0001",
        anomaly_type=AnomalyType.SENSOR_FAULT,
        target=ComponentTarget(
            asset_id=asset_id,
            bogie_id=2,
            axle_position="inner",
            wheel_side="right",
            signal_name="bearing_temp_c",
        ),
        start_time=anomaly_start,
        end_time=peak_time,
        peak_severity=AnomalySeverity.HIGH,
    )


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

    parser.add_argument(
        "--anomaly-profile",
        choices=("none", "bearing-demo", "brake-leak-demo", "sensor-drift-demo"),
        default="none",
        help="Optional reproducible anomaly profile.",
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
        sampling_interval_seconds=arguments.sampling_interval_seconds,
    )

    if arguments.anomaly_profile == "bearing-demo":
        scenario = _build_bearing_demo_scenario(
            asset_id=assets[0].asset_id,
            start_time=arguments.start_time,
            journey_duration_seconds=journey.duration_seconds,
        )

        fleet_batch = inject_fleet_anomaly_scenarios(
            fleet_batch,
            scenarios=(scenario,),
        )

    elif arguments.anomaly_profile == "brake-leak-demo":
        scenario = _build_brake_leak_demo_scenario(
            asset_id=assets[0].asset_id,
            start_time=arguments.start_time,
            journey_duration_seconds=journey.duration_seconds,
        )

        fleet_batch = inject_fleet_anomaly_scenarios(
            fleet_batch,
            scenarios=(scenario,),
        )

    elif arguments.anomaly_profile == "sensor-drift-demo":
        scenario = _build_sensor_drift_demo_scenario(
            asset_id=assets[0].asset_id,
            start_time=arguments.start_time,
            journey_duration_seconds=journey.duration_seconds,
        )

        fleet_batch = inject_fleet_anomaly_scenarios(
            fleet_batch,
            scenarios=(scenario,),
        )

    manifest = write_generation_run(
        arguments.output_dir,
        fleet_batch,
        journey_metadata,
        arguments.seed,
        anomaly_profile=arguments.anomaly_profile,
    )

    print(f"Journey: {journey.origin} -> " f"{journey.destination}")
    print(f"Journey ID: {journey.journey_id}")
    print(f"Sampling: " f"{arguments.sampling_interval_seconds} seconds")
    print(f"Telemetry events: " f"{manifest['counts']['telemetry_events']}")
    print(f"Output: {arguments.output_dir}")
    print(f"Anomaly Profile: {arguments.anomaly_profile}")

    return 0
