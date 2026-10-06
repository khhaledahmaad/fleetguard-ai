# FleetGuard AI — Portfolio coverage dataset v1

The `fleetguard.portfolio` runner adds reproducible cohort planning and saved-file
validation on top of the twelve-scenario generator. Generator version is 0.3.0;
telemetry remains schema 3.2. There is no new anomaly or telemetry field.

## Purpose and size

The default is a small **coverage dataset**, not a simulation of real fleet
failure prevalence and not a completed model-evaluation study.

| Split | Fault-assigned wagons | Entirely healthy wagons | Total |
|---|---:|---:|---:|
| train | 13 | 3 | 16 |
| validation | 13 | 3 | 16 |
| test | 13 | 3 | 16 |
| Total | 39 | 9 | 48 |

Twelve anomaly types produce thirteen variants because controller supply failure
has persistent and bounded modes. Each variant occurs once in each split.
Equal split sizes make this first integration cohort cover every variant; they
are not a prescribed ratio for the eventual modelling dataset.

Each wagon has one complete route-derived journey and at most one scenario.
A fault-assigned wagon normally includes healthy pre-fault observations; assignment
counts are not anomalous-window prevalence. The validation report exposes actual
anomalous-observation and missing-report fractions per wagon. Window prevalence
will be calculated when one-minute feature windows exist.

Use `--replicates N` to include N copies of each variant per split and
`--healthy-per-split N` to choose the control count per split. Total wagon count
is `3 * (13 * replicates + healthy_per_split)`. For example, 13 healthy wagons per
split gives a 78-wagon cohort with equal healthy/fault-assigned counts. It still
does not establish real-world prevalence.

## What is random, and what is constrained?

The root seed defines independent deterministic streams for split membership,
variant assignment, each wagon's journey and each wagon's scenario. Stable
SHA-256-derived seeds avoid Python's process-dependent `hash()`.

1. Generate persistent wagon metadata once with unique asset IDs.
2. Shuffle wagons into mutually exclusive train, validation and test groups.
3. Shuffle the required variants and healthy assignments within each group.
4. Independently select a route/direction/dwell plan for each wagon.
5. Choose eligible component targets, onset times and severity for each fault.
6. Generate healthy telemetry, then inject the chosen scenario.

The same configuration, generator/dependency versions and seed reproduce the
same assignments and data. Changing the seed changes the cohort. Changing cohort
size can change assignments; prefix stability is not promised for this planner.
Asset IDs are unique within one cohort. Do not combine different seed cohorts
as though identical asset IDs necessarily represent the same physical wagon.

There are no fixed "faulty wagon 1" or "always bogie 1" rules in this planner.
Targeting follows the contract:

- bearing degradation/sensor drift: selected bogie, axle and wheel side;
- generator failure, slide, locked axle, suspected flat: selected bogie and axle;
- pressure failure: selected wagon BPP/AR/SR sensor or either bogie's BCP;
- brake release failure: selected bogie effect, wagon brake-system truth;
- undemanded braking: wagon brake-system truth and both BCP responses;
- battery and controller: whole-wagon power subsystem.

A slide starts only at a moving, brake-applied sample. A release fault starts at
an apply-to-release transition. Locked-axle, suspected-flat and undemanded-braking
onsets use moving samples with release demand. Controller bounded recovery is
kept within the journey. Progressive faults have time to reach their peak.

Component choices and severities are random, not exhaustively balanced. The
small default cohort need not contain every pressure-sensor target or every
severity for every type. Bigger cohorts can broaden that coverage. Tests exercise
all supported pressure target locations in the underlying generator.

Battery discharge is deliberately accelerated to 6–12 extra V/hour in this
short coverage cohort. This is not a realistic battery-life estimate. It allows
cutoff and possible recovery to be tested within a journey. Multi-day parking,
calibrated power behaviour and natural fault prevalence remain future dataset
work. Mechanical injection remains a signature transformation rather than a
coupled simulation of train motion under failure.

## Splits and feature leakage

A wagon appears in only one split and one run. Every record and component from
that wagon belongs to that split. Split before windowing; never randomly split
individual event rows afterwards.

The future unsupervised baseline can fit on healthy-control training wagons.
Supervised experiments can use labelled training windows. Validation selects
thresholds/settings; test assets remain reserved for final evaluation. This
session does not train a model or claim detection performance.

Keep scenario metadata, truth, IDs and split names out of model features. The
same synthetic generator governs all splits, so asset separation does not
prove real-world generalisation. Quality flags are observations; absence of
reports needs an expected-report monitor separately from incoming-window ML.

## Files and completion

At the cohort root:

- `generation_config.json`: requested configuration;
- `cohort_plan.json`: every split, asset, variant, seed, target and scenario time;
- `validation_report.json`: validation results and per-run counts/fractions;
- `cohort_manifest.json`: completion marker with plan and run-manifest hashes;
- `runs/<split>/<asset_id>/`: the existing schema-3.2 output files for that wagon.

The runner writes a completion manifest only after all runs and validation pass.
An interrupted or failed generation may leave partial files but has no completion
manifest. Use a fresh output directory to retry. Existing data is never silently
overwritten and automatic resume is not implemented in v1.

## Validation checks

The independent `validate` command reads disk and checks:

- deterministic asset/split/variant assignment and no shared assets/event IDs;
- schema and seeded asset/journey metadata;
- file checksums and actual counts;
- sampling-grid membership and ordered, unique event times;
- one-to-one event/truth identity and target/severity/onset consistency;
- every normalised component value against its parent event;
- disjoint observed and missing report sets covering the whole expected grid;
- outage boundaries, missing counts and recovery within the observation horizon;
- healthy controls and non-empty evidence for each assigned fault;
- all variants represented in each split.

This validates dataset structure and lineage. Generator unit tests separately
verify physical-signature behaviour and preservation of unaffected components.
It is not an adversarially secure data-signing scheme or a railway certification.

## Commands (Windows CMD)

```cmd
python -m fleetguard.portfolio generate --seed 42 --start-time 2026-01-01T06:00:00+00:00 --sampling-interval-seconds 10 --output-dir data\generated\portfolio-v1
python -m fleetguard.portfolio validate --input-dir data\generated\portfolio-v1
```

For a faster development cohort, use 60-second sampling and a different output
directory. Feature schema 2.0 implements one-minute summaries at wagon, bogie, axle and
wheel levels over the standard 10-second observations; raw data remains available. The old fixed-target smoke demos remain available for
regression checks.

For setup, sizing, all generated files, feature commands and troubleshooting,
use the [dataset generation guide](dataset_generation_guide.md).
