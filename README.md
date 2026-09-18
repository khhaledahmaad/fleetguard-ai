# FleetGuard AI

FleetGuard AI is a production-shaped MLOps platform for anomaly detection on
synthetic freight-wagon telemetry. It is a portfolio and learning system, not a
safety-critical railway product.

Schema 3.0 models two bogies, four axles/wheelsets and eight wheels per wagon,
shared pneumatic signals, controller diagnostics, rail condition, estimated
adhesion and journey-aware motion along a synthetic UK freight corridor.
Development batches can use a fixed period count; production-shaped generation
uses route-derived journey durations with terminal and intermediate dwell.

Operational journeys default to 10-second sampling. Supported profiles are 60
seconds for development, 10 seconds for the standard portfolio dataset and 1
second for high-resolution experiments. Model features use one-minute windows.

`create_random_journey_plan(seed)` reproducibly selects one of several London,
Avonmouth, Cardiff and Swansea terminal-to-terminal duties and may reverse its
direction. `create_journey_plan(...)` builds a specific duty.

## Generate the standard portfolio dataset

The standard profile uses three wagons, reproducible seed `42`, 10-second
sampling and route-derived journey durations:

```cmd
python -m fleetguard.generator --assets 3 --seed 42 --start-time 2026-01-01T06:00:00+00:00 --sampling-interval-seconds 10 --output-dir data\generated\portfolio-demo
```

The output directory must be empty before generation. A successful run writes:

- `asset_metadata.jsonl` — stable wagon configuration and dimensions;
- `journey_metadata.json` — route, direction, timing and dwell plan;
- `telemetry.jsonl` — one wagon-level event per sampling timestamp;
- `bogie_observations.jsonl` — two bogie records per telemetry event;
- `axle_observations.jsonl` — four axle records per telemetry event;
- `wheel_observations.jsonl` — eight wheel records per telemetry event;
- `anomaly_truth.jsonl` — injected-anomaly ground truth for evaluation;
- `manifest.json` — dataset metadata, row counts and SHA-256 file hashes.

For the 330-minute London-to-Avonmouth duty, each wagon produces 1,980
telemetry events. With three wagons, the expected normalised record counts are:

| Dataset | Expected records |
| --- | ---: |
| Telemetry events | 5,940 |
| Anomaly-truth records | 5,940 |
| Bogie observations | 11,880 |
| Axle observations | 23,760 |
| Wheel observations | 47,520 |

Inspect the generated manifest from Windows CMD:

```cmd
type data\generated\portfolio-demo\manifest.json
```

The 10-second events remain the auditable source observations. Downstream model
features aggregate them into leakage-safe one-minute windows.

## Local verification (Windows CMD)

```cmd
python -m pip install -e ".[dev]"
python -m ruff check .
python -m pytest -v
```

See `docs/product_contract.md`, `docs/domain_specification.md` and
`docs/data_contract.md` for scope and modelling decisions.
