from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_core import to_jsonable_python

from fleetguard.contracts import (
    FEATURE_WINDOW_SECONDS,
    SCHEMA_VERSION,
    JourneyMetadata,
)
from fleetguard.generator.fleet import FleetBatch
from fleetguard.generator.normalise import normalise_event
from fleetguard.generator.route import route_provenance


def _atomic_text(path: Path, text: str) -> None:
    """Publish a completed UTF-8 file once, before a manifest can refer to it."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write_jsonl(path: Path, records: Iterable[BaseModel]) -> int:
    lines = [record.model_dump_json() + "\n" for record in records]
    _atomic_text(path, "".join(lines))
    return len(lines)


def _write_json(path: Path, value: BaseModel | dict[str, Any]) -> None:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    _atomic_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


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

    for event, truth in zip(fleet_batch.events, fleet_batch.truth, strict=True):
        if (event.event_id, event.asset_id) != (truth.event_id, truth.asset_id):
            raise ValueError("telemetry and truth identities must match")
    event_ids = {event.event_id for event in fleet_batch.events}
    missing_ids = {row.event_id for row in fleet_batch.missing_reports}
    if len(event_ids) != len(fleet_batch.events) or len(missing_ids) != len(
        fleet_batch.missing_reports
    ):
        raise ValueError("duplicate report identity")
    if event_ids & missing_ids:
        raise ValueError("a missing report cannot also be observed")

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

    # The batch is already in memory. Serialise component projections per run,
    # then atomically publish each file rather than exposing partial append writes.
    component_lines: dict[str, list[str]] = {"bogies": [], "axles": [], "wheels": []}
    for event in fleet_batch.events:
        observations = normalise_event(event, assets_by_id[event.asset_id])
        for name in component_lines:
            component_lines[name].extend(
                row.model_dump_json() + "\n" for row in getattr(observations, name)
            )
    for name, lines in component_lines.items():
        _atomic_text(paths[name], "".join(lines))
    bogie_count = len(component_lines["bogies"])
    axle_count = len(component_lines["axles"])
    wheel_count = len(component_lines["wheels"])

    missing_count = _write_jsonl(
        output_dir / "missing_report_truth.jsonl", fleet_batch.missing_reports
    )
    outage_count = _write_jsonl(output_dir / "outage_truth.jsonl", fleet_batch.outages)
    _write_json(
        output_dir / "scenario_metadata.json",
        {
            "schema_version": SCHEMA_VERSION,
            "scenarios": to_jsonable_python([asdict(s) for s in fleet_batch.scenarios]),
        },
    )

    record_counts = {
        "expected_reports": telemetry_count + missing_count,
        "missing_reports": missing_count,
        "outages": outage_count,
        "assets": asset_count,
        "telemetry_events": telemetry_count,
        "truth_records": truth_count,
        "bogie_observations": bogie_count,
        "axle_observations": axle_count,
        "wheel_observations": wheel_count,
    }

    file_records = {
        "missing_report_truth.jsonl": missing_count,
        "outage_truth.jsonl": outage_count,
        "scenario_metadata.json": len(fleet_batch.scenarios),
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
        **route_provenance(),
        "seed": seed,
        "anomaly_profile": anomaly_profile,
        "sampling_interval_seconds": (journey_metadata.sampling_interval_seconds),
        "feature_window_seconds": FEATURE_WINDOW_SECONDS,
        "journey_id": journey_metadata.journey_id,
        "route_id": journey_metadata.route_id,
        "counts": record_counts,
        "anomalous_observed_reports_by_type": dict(
            sorted(
                Counter(
                    row.anomaly_type.value for row in fleet_batch.truth if row.is_anomaly
                ).items()
            )
        ),
        "scenario_asset_ids": sorted({s.target.asset_id for s in fleet_batch.scenarios}),
        "files": files,
    }

    # The manifest is deliberately written last. Its presence means
    # all other output files were completed and checksummed.
    _write_json(
        output_dir / "manifest.json",
        manifest,
    )

    return manifest
