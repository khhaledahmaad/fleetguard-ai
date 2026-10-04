"""Hierarchical feature build; raw telemetry is never overwritten."""

from collections import defaultdict
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path

from fleetguard.contracts.models import AssetMetadata, JourneyMetadata, TelemetryEvent
from fleetguard.features.hierarchical_aggregation import aggregate_components, component_catalogue
from fleetguard.features.hierarchical_models import LEVELS, ComponentWindow
from fleetguard.portfolio.planning import SPLITS
from fleetguard.portfolio.runner import write_json
from fleetguard.portfolio.validation import read_json, sha256, validate_portfolio

MULTIPLICITY = {"wagon": 1, "bogie": 2, "axle": 4, "wheel": 8}


def iter_journey_windows(events, asset, journey, split):
    start = journey.scheduled_start_time
    if start.second or start.microsecond:
        raise ValueError("journey start must align to a minute boundary")
    buckets = defaultdict(list)
    ids, times = set(), set()
    for event in events:
        if (event.asset_id, event.journey_id, event.route_id) != (
            asset.asset_id,
            journey.journey_id,
            journey.route_id,
        ):
            raise ValueError("event identity does not match journey")
        if event.sampling_interval_seconds != journey.sampling_interval_seconds:
            raise ValueError("event sampling interval does not match journey")
        elapsed = (event.event_time - start).total_seconds()
        if not 0 <= elapsed < journey.estimated_duration_seconds:
            raise ValueError("event outside journey horizon")
        if elapsed % journey.sampling_interval_seconds:
            raise ValueError("event off sampling grid")
        if event.event_id in ids or event.event_time in times:
            raise ValueError("duplicate journey report")
        ids.add(event.event_id)
        times.add(event.event_time)
        buckets[int(elapsed // 60)].append(event)
    for minute in range(journey.estimated_duration_seconds // 60):
        yield aggregate_components(
            tuple(buckets[minute]),
            asset=asset,
            journey_id=journey.journey_id,
            route_id=journey.route_id,
            split=split,
            window_start=start + timedelta(minutes=minute),
            sampling_interval_seconds=journey.sampling_interval_seconds,
        )


def component_key(row):
    return (row.level, row.bogie_id, row.axle_position, row.wheel_side)


def key_to_json(key, static):
    level, bogie, axle, wheel = key
    return {
        "level": level,
        "bogie_id": bogie,
        "axle_position": axle,
        "wheel_side": wheel,
        "static_attributes": static,
    }


def build_feature_dataset(input_dir: Path, output_dir: Path, progress=None) -> dict:
    source, output = input_dir.resolve(), output_dir.resolve()
    if output == source or source in output.parents:
        raise ValueError("feature output must be outside source dataset")
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty")
    if progress:
        progress("Validating original portfolio before hierarchical aggregation...")
    validate_portfolio(source)
    plan = read_json(source / "cohort_plan.json")
    output.mkdir(parents=True, exist_ok=True)
    entries, files = [], {}
    for split in SPLITS:
        counts = dict.fromkeys(LEVELS, 0)
        with ExitStack() as stack:
            streams = {
                level: stack.enter_context(
                    (output / f"{split}_{level}_features.jsonl").open(
                        "w", encoding="utf-8", newline="\n"
                    )
                )
                for level in LEVELS
            }
            for run in plan["runs"]:
                if run["split"] != split:
                    continue
                directory = source / run["relative_directory"]
                with (directory / "asset_metadata.jsonl").open(encoding="utf-8") as stream:
                    assets = tuple(AssetMetadata.model_validate_json(line) for line in stream)
                if len(assets) != 1 or assets[0].asset_id != run["asset_id"]:
                    raise ValueError("portfolio run must contain its one assigned asset")
                asset = assets[0]
                journey = JourneyMetadata.model_validate(
                    read_json(directory / "journey_metadata.json")
                )
                with (directory / "telemetry.jsonl").open(encoding="utf-8") as stream:
                    events = tuple(TelemetryEvent.model_validate_json(line) for line in stream)
                window_count = complete = partial = silent = used = 0
                for rows in iter_journey_windows(events, asset, journey, split):
                    wagon = rows[0]
                    window_count += 1
                    complete += wagon.report_completeness == 1
                    partial += 0 < wagon.report_completeness < 1
                    silent += wagon.received_reports == 0
                    used += wagon.received_reports
                    for row in rows:
                        streams[row.level].write(row.model_dump_json() + "\n")
                        counts[row.level] += 1
                if not window_count:
                    raise ValueError("journey must contain at least one full minute")
                entries.append(
                    {
                        "asset_id": asset.asset_id,
                        "journey_id": journey.journey_id,
                        "route_id": journey.route_id,
                        "split": split,
                        "window_start": journey.scheduled_start_time.isoformat(),
                        "sampling_interval_seconds": journey.sampling_interval_seconds,
                        "window_count": window_count,
                        "complete_windows": complete,
                        "partial_windows": partial,
                        "silent_windows": silent,
                        "received_reports_used": used,
                        "excluded_tail_seconds": journey.estimated_duration_seconds % 60,
                        "excluded_tail_reports": len(events) - used,
                        "components": [
                            key_to_json(key, static)
                            for key, static in component_catalogue(asset).items()
                        ],
                        "source_run_manifest_sha256": sha256(directory / "manifest.json")
                        if (directory / "manifest.json").exists()
                        else None,
                    }
                )
                if progress:
                    progress(f"{split}: {asset.asset_id} -> {window_count} minutes, 15 rows/minute")
        for level, count in counts.items():
            name = f"{split}_{level}_features.jsonl"
            files[name] = {"records": count, "sha256": sha256(output / name)}
    manifest = {
        "feature_schema_version": "2.0",
        "source_schema_version": "3.2",
        "window_seconds": 60,
        "window_boundary": "[start, end)",
        "tail_policy": "exclude incomplete minute",
        "source_plan_sha256": sha256(source / "cohort_plan.json"),
        "source_manifest_sha256": sha256(source / "cohort_manifest.json"),
        "files": files,
        "journeys": entries,
    }
    report = validate_feature_dataset(output, manifest=manifest)
    write_json(output / "feature_manifest.json", manifest)
    return report


def validate_feature_dataset(root: Path, manifest=None) -> dict:
    if manifest is None:
        manifest = read_json(root / "feature_manifest.json")
    if (manifest["feature_schema_version"], manifest["source_schema_version"]) != ("2.0", "3.2"):
        raise ValueError("unsupported feature manifest; expected version 2.0")
    if manifest["window_seconds"] != 60 or manifest["window_boundary"] != "[start, end)":
        raise ValueError("unsupported window policy")
    expected_files = {f"{split}_{level}_features.jsonl" for split in SPLITS for level in LEVELS}
    if set(manifest["files"]) != expected_files:
        raise ValueError("unexpected feature file list")
    entries, catalogues, assets = {}, {}, set()
    for entry in manifest["journeys"]:
        key = (entry["split"], entry["asset_id"], entry["journey_id"])
        if entry["asset_id"] in assets or key in entries or entry["split"] not in SPLITS:
            raise ValueError("duplicate asset or invalid split")
        catalogue = {}
        for c in entry["components"]:
            ck = (c["level"], c["bogie_id"], c["axle_position"], c["wheel_side"])
            if ck in catalogue:
                raise ValueError("duplicate catalogue component")
            catalogue[ck] = c["static_attributes"]
        if {level: sum(k[0] == level for k in catalogue) for level in LEVELS} != MULTIPLICITY:
            raise ValueError("catalogue must contain 1 wagon, 2 bogies, 4 axles and 8 wheels")
        expected_keys = {("wagon", None, None, None)}
        for b in (1, 2):
            expected_keys.add(("bogie", b, None, None))
            for a in ("inner", "outer"):
                expected_keys.add(("axle", b, a, None))
                for w in ("left", "right"):
                    expected_keys.add(("wheel", b, a, w))
        if set(catalogue) != expected_keys:
            raise ValueError("catalogue component identities are invalid")
        if entry["window_count"] <= 0:
            raise ValueError("journey must contain feature windows")
        entries[key], catalogues[key] = entry, catalogue
        assets.add(entry["asset_id"])
    totals, level_totals = {}, {}
    for split in SPLITS:
        lineage = {}
        level_totals[split] = {}
        observed_journeys = set()
        for level in LEVELS:
            name = f"{split}_{level}_features.jsonl"
            info = manifest["files"][name]
            if sha256(root / name) != info["sha256"]:
                raise ValueError(f"checksum mismatch: {name}")
            previous, stats, keys_seen = {}, defaultdict(CounterState), set()
            count = 0
            with (root / name).open(encoding="utf-8") as stream:
                for line in stream:
                    row = ComponentWindow.model_validate_json(line)
                    jk = (row.split, row.asset_id, row.journey_id)
                    if row.split != split or row.level != level or jk not in entries:
                        raise ValueError("feature identity or split mismatch")
                    entry, catalogue = entries[jk], catalogues[jk]
                    ck = component_key(row)
                    if ck not in catalogue or row.static_attributes != catalogue[ck]:
                        raise ValueError("component metadata mismatch")
                    start = datetime.fromisoformat(entry["window_start"])
                    elapsed = (row.window_start - start).total_seconds()
                    if elapsed % 60 or not 0 <= elapsed < entry["window_count"] * 60:
                        raise ValueError("window outside expected journey grid")
                    if (
                        row.route_id != entry["route_id"]
                        or row.sampling_interval_seconds != entry["sampling_interval_seconds"]
                    ):
                        raise ValueError("route or sampling mismatch")
                    series = (jk, ck)
                    expected_start = previous.get(series, start)
                    if row.window_start != expected_start:
                        raise ValueError("component windows must be consecutive and unique")
                    previous[series] = row.window_end
                    unique = (jk, ck, row.window_start)
                    if unique in keys_seen:
                        raise ValueError("duplicate component window")
                    keys_seen.add(unique)
                    lk = (jk, row.window_start)
                    fingerprint = (
                        row.source_event_ids,
                        row.received_reports,
                        row.event_time_first,
                        row.event_time_last,
                        row.generated_at_first,
                        row.generated_at_last,
                    )
                    if level == "wagon":
                        lineage[lk] = fingerprint
                    elif lineage.get(lk) != fingerprint:
                        raise ValueError("component lineage differs from parent wagon")
                    state = stats[jk]
                    state["rows"] += 1
                    state["used"] += row.received_reports
                    state["complete"] += row.report_completeness == 1
                    state["partial"] += 0 < row.report_completeness < 1
                    state["silent"] += row.received_reports == 0
                    observed_journeys.add(jk)
                    count += 1
            if count != info["records"]:
                raise ValueError("feature record count mismatch")
            for jk, entry in entries.items():
                if jk[0] != split:
                    continue
                multiplier = MULTIPLICITY[level]
                state = stats[jk]
                expected = {
                    "rows": entry["window_count"] * multiplier,
                    "used": entry["received_reports_used"] * multiplier,
                    "complete": entry["complete_windows"] * multiplier,
                    "partial": entry["partial_windows"] * multiplier,
                    "silent": entry["silent_windows"] * multiplier,
                }
                if dict(state) != expected:
                    raise ValueError("journey component counts mismatch")
                for ck in catalogues[jk]:
                    if ck[0] == level and previous.get((jk, ck)) != datetime.fromisoformat(
                        entry["window_start"]
                    ) + timedelta(minutes=entry["window_count"]):
                        raise ValueError("missing component windows")
            level_totals[split][level] = count
        if observed_journeys != {k for k in entries if k[0] == split}:
            raise ValueError("missing journey features")
        totals[split] = level_totals[split]["wagon"]
    return {
        "status": "passed",
        "assets": len(assets),
        "windows_by_split": totals,
        "records_by_split_level": level_totals,
    }


def CounterState():
    return {"rows": 0, "used": 0, "complete": 0, "partial": 0, "silent": 0}
