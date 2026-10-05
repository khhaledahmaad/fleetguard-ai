# FleetGuard AI

FleetGuard AI is a rail-fleet condition intelligence product concept and
technical demonstrator. Its current implementation generates and validates
synthetic freight-wagon telemetry and modelling features. Model services,
operational dashboards and deployment form the next platform milestones.
Commercial potential requires validation with real fleet data, verified hardware
interfaces and customer evaluation. It is not a safety-critical railway product.

Schema 3.2 models two bogies, four axles/wheelsets and eight wheels per wagon,
shared pneumatic signals, controller diagnostics, rail condition, estimated
adhesion, a shared wagon battery supplied by four axle-end generators, and
journey-aware motion along a synthetic UK freight corridor.
Development batches can use a fixed period count; production-shaped generation
uses route-derived journey durations with terminal and intermediate dwell.

Operational journeys default to 10-second sampling. Supported profiles are 60
seconds for development, 10 seconds for the standard portfolio dataset and 1
second for high-resolution experiments. Granular reports remain available for modelling. Additional one-minute summaries
preserve wagon, bogie, axle and wheel identities.

`create_random_journey_plan(seed)` reproducibly selects one of several London,
Avonmouth, Cardiff and Swansea terminal-to-terminal duties and may reverse its
direction. `create_journey_plan(...)` builds a specific duty.

## Generate a healthy portfolio smoke dataset

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
- `missing_report_truth.jsonl` — expected but unreported samples during outages;
- `outage_truth.jsonl` — contiguous missing-report intervals;
- `scenario_metadata.json` — exact injected scenario configuration;
- `manifest.json` — dataset metadata, row counts and SHA-256 file hashes.

For the healthy 330-minute London-to-Avonmouth duty, each wagon produces 1,980
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

The 10-second events remain the auditable source observations. Additional component-level summaries aggregate them into one-minute windows;
these are not the sole modelling representation.

## Twelve anomaly scenarios

All twelve signatures are implemented. See `docs/anomaly_catalogue.md` for the
full catalogue, CLI profiles, targets and modelling limits. Nullable readings
carry quality flags. Controller/battery blackouts produce missing-report truth
instead of fabricated telemetry. The generator is version 0.3.0, schema 3.2.

```cmd
python -m fleetguard.generator --assets 2 --seed 42 --start-time 2026-01-01T06:00:00+00:00 --sampling-interval-seconds 60 --anomaly-profile controller-bounded-demo --output-dir data\generated\controller-bounded-smoke-01
```

Each demo targets wagon 1 and leaves other wagons healthy. One scenario per
asset per batch is enforced. The battery smoke profile intentionally accelerates
discharge; it is not an endurance estimate. Seeded portfolio cohort generation and saved-file validation are available.
Hierarchical feature schema 2.0 is implemented. Model feature selection, labels
and evaluation remain subsequent milestones.

For this implementation session, follow `docs/session_twelve_anomalies.md`.

## Local verification (Windows CMD)

```cmd
python -m pip install -e ".[dev]"
python -m ruff check .
python -m pytest -v
```

See `docs/product_contract.md`, `docs/domain_specification.md` and
`docs/data_contract.md` for scope and modelling decisions.


## Seeded portfolio cohort

The new planner varies wagon assignments, eligible components, onset times and
severity while keeping asset-disjoint train/validation/test splits. The default
48-wagon coverage cohort includes all twelve fault types, both controller modes
and healthy controls in each split. It is a pipeline exercise, not real fault
prevalence or a model-performance result.

```cmd
python -m fleetguard.portfolio generate --seed 42 --start-time 2026-01-01T06:00:00+00:00 --sampling-interval-seconds 10 --output-dir data\generated\portfolio-v1
python -m fleetguard.portfolio validate --input-dir data\generated\portfolio-v1
```

See `docs/session_portfolio_dataset.md` for the guided session and
`docs/portfolio_dataset.md` for design, randomness, file relationships and limits.

## Engineering atlas

Open `atlas\_site\index.html` for the self-contained interactive atlas. It includes
the wagon architecture, actual seeded generator traces, all twelve anomaly
scenarios, portfolio planning, hierarchical feature examples and source references.
It works offline after extracting the full folder.

Rebuild its fixtures and ready-to-open site from Windows CMD:

```cmd
python scripts\build_fleetguard_atlas.py
```

Optional Quarto rendering (if Quarto is installed):

```cmd
quarto render atlas
```

See `atlas/README.md` for sharing and editing instructions.

## Hierarchical feature dataset

```cmd
python -m fleetguard.features build --input-dir data\generated\portfolio-v1 --output-dir data\features\portfolio-v1
python -m fleetguard.features validate --input-dir data\features\portfolio-v1
```

This writes four component tables per split and a manifest. Use a fresh or empty
output directory. Generated datasets and rendered atlas output stay outside Git.
