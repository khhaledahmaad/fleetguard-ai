from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from importlib.metadata import version
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from fleetguard.contracts import (
    FEATURE_WINDOW_SECONDS,
    SCHEMA_VERSION,
    JourneyMetadata,
)
from fleetguard.generator.fleet import FleetBatch
from fleetguard.generator.normalise import normalise_event


def _write_jsonl(path: Path, records: Iterable[BaseModel]) -> int:
    count = 0

    with path.open("w", encoding="utf-8", newline="\n") as output:
        for record in records:
            output.write(record.model_dump_json())
            output.write("\n")
            count += 1

    return count


def _write_json(path: Path, value: BaseModel | dict[str, Any]) -> None:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value

    with path.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(payload, output, indent=2, sort_keys=True)
        output.write("\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _file_entry(path: Path, records: int) -> dict[str, str | int]:
    return {
        "sha256": _sha256(path),
        "records": records,
    }


def write_generation_run(
    output_dir: Path,
    fleet_batch: FleetBatch,
    journey_metadata: JourneyMetadata,
    seed: int,
    anomaly_profile: str = "none",
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    if any(output_dir.iterdir()):
        raise ValueError(f"output directory is not empty: {output_dir}")

    if len(fleet_batch.events) != len(fleet_batch.truth):
        raise ValueError("telemetry and truth record counts must match")

    assets_by_id = {asset.asset_id: asset for asset in fleet_batch.assets}

    if any(event.asset_id not in assets_by_id for event in fleet_batch.events):
        raise ValueError("every event must reference an asset in the batch")

    paths = {
        "assets": output_dir / "asset_metadata.jsonl",
        "journey": output_dir / "journey_metadata.json",
        "telemetry": output_dir / "telemetry.jsonl",
        "truth": output_dir / "anomaly_truth.jsonl",
        "bogies": output_dir / "bogie_observations.jsonl",
        "axles": output_dir / "axle_observations.jsonl",
        "wheels": output_dir / "wheel_observations.jsonl",
    }

    asset_count = _write_jsonl(
        paths["assets"],
        fleet_batch.assets,
    )

    _write_json(
        paths["journey"],
        journey_metadata,
    )

    telemetry_count = _write_jsonl(
        paths["telemetry"],
        fleet_batch.events,
    )

    truth_count = _write_jsonl(
        paths["truth"],
        fleet_batch.truth,
    )

    bogie_count = 0
    axle_count = 0
    wheel_count = 0

    with (
        paths["bogies"].open(
            "w",
            encoding="utf-8",
            newline="\n",
        ) as bogie_output,
        paths["axles"].open(
            "w",
            encoding="utf-8",
            newline="\n",
        ) as axle_output,
        paths["wheels"].open(
            "w",
            encoding="utf-8",
            newline="\n",
        ) as wheel_output,
    ):
        for event in fleet_batch.events:
            rows = normalise_event(
                event,
                assets_by_id[event.asset_id],
            )

            for row in rows.bogies:
                bogie_output.write(row.model_dump_json() + "\n")
                bogie_count += 1

            for row in rows.axles:
                axle_output.write(row.model_dump_json() + "\n")
                axle_count += 1

            for row in rows.wheels:
                wheel_output.write(row.model_dump_json() + "\n")
                wheel_count += 1

    record_counts = {
        "assets": asset_count,
        "telemetry_events": telemetry_count,
        "truth_records": truth_count,
        "bogie_observations": bogie_count,
        "axle_observations": axle_count,
        "wheel_observations": wheel_count,
    }

    file_records = {
        "asset_metadata.jsonl": asset_count,
        "journey_metadata.json": 1,
        "telemetry.jsonl": telemetry_count,
        "anomaly_truth.jsonl": truth_count,
        "bogie_observations.jsonl": bogie_count,
        "axle_observations.jsonl": axle_count,
        "wheel_observations.jsonl": wheel_count,
    }

    files = {
        filename: _file_entry(
            output_dir / filename,
            records,
        )
        for filename, records in file_records.items()
    }

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generator_version": version("fleetguard-ai"),
        "seed": seed,
        "anomaly_profile": anomaly_profile,
        "sampling_interval_seconds": (journey_metadata.sampling_interval_seconds),
        "feature_window_seconds": FEATURE_WINDOW_SECONDS,
        "journey_id": journey_metadata.journey_id,
        "route_id": journey_metadata.route_id,
        "counts": record_counts,
        "files": files,
    }

    # The manifest is deliberately written last. Its presence means
    # all other output files were completed and checksummed.
    _write_json(
        output_dir / "manifest.json",
        manifest,
    )

    return manifest
