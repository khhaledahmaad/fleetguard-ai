# Session — Randomised portfolio generation and validation

## Goal and stopping point

In 45–60 minutes, apply the planner and validator, understand their roles, and
produce a verified coverage dataset ready for one-minute feature engineering.
The prepared update adds five small package files and a test module. It builds
on the schema-3.2 code you confirmed green. The twelve anomaly signatures are
unchanged, and the asset artwork/builder is outside this update.

## 1. Install and inspect — 5 minutes

Copy the contents of the ZIP's `project` folder into your existing repository,
merging folders. Then use Windows CMD at `C:\Users\khhal\fleetguard-ai`:

```cmd
.venv\Scripts\activate
python -m pip install -e ".[dev]"
python -m ruff check .
python -m pytest -v
```

The reinstall updates generator metadata to 0.3.0. Telemetry schema stays 3.2.
Your previous formatting fix to `assets\build_fleetguard_assets.py` remains in
your repository; this update does not replace that script.

## 2. Understand the planner — 10 minutes

Open `src\fleetguard\portfolio\planning.py`.

| Part | Input | Output / responsibility |
|---|---|---|
| `PortfolioConfig` | Seed, start time, sampling and cohort sizes | Validated configuration |
| `plan_assignments` | Configuration | Unique wagons assigned to splits and fault variants or healthy control |
| `plan_journey` | One assignment and configuration | A seeded route-derived journey |
| `choose_scenario` | Assignment and healthy events | An eligible random target, onset, severity and fault configuration |

The default is 48 wagons: 16 per split. Each split contains three healthy wagons
and one example of each of thirteen fault variants (twelve types, two controller
modes). Wagons are shuffled before assignment. Targets vary at the appropriate
level: bearing wheel, axle/wheelset, bogie pressure sensor, or wagon system.

The planner's random seed makes selection repeatable. The same seed does not
make all wagons alike. Different seeds change the assignments. Component and
severity variation is random; we do not guarantee every combination in 48 wagons.

Read the eligibility branches in `choose_scenario`: this is where randomness is
restricted to sensible operating states. A slide cannot start at a stationary
sample, and a release fault needs a preceding brake application.

## 3. Follow generation and validation — 10 minutes

Open `runner.py`, then `validation.py` in the same folder.

`generate_portfolio` processes one wagon at a time:
healthy journey → selected anomaly → saved run → next wagon.
This limits memory use and keeps each wagon's metadata, telemetry and truth
together. After all runs, it writes the plan and validates the files. Only a
successful validation permits the completion manifest.

`validate_portfolio` can run separately later. It checks the actual saved data,
not just the manifest's claims. Component rows must match their source event;
observed and missing reports must exactly cover the scheduled timeline.

`__main__.py` exposes the `generate` and `validate` commands. `__init__.py`
identifies the package. Existing generator APIs still handle individual journeys
and fault signatures.

## 4. Generate the standard dataset — 10–15 minutes

```cmd
python -m fleetguard.portfolio generate --seed 42 --start-time 2026-01-01T06:00:00+00:00 --sampling-interval-seconds 10 --output-dir data\generated\portfolio-v1
```

Progress lists each wagon, split and variant, then validates the saved files.
Use a new output folder: the runner refuses to overwrite existing output.
The complete reference run produced around half a gigabyte of JSONL files;
allow disk space for the nested and normalised representations.

Run the independent validator:

```cmd
python -m fleetguard.portfolio validate --input-dir data\generated\portfolio-v1
```

For the supplied seed/configuration, the reference result is:

- 48 wagons;
- 76,554 expected reports;
- 73,122 emitted telemetry events and the same number of observed truth rows;
- 3,432 missing reports;
- all thirteen fault variants plus healthy controls present in every split.

A missing report is not an extra zero-valued event. Its component rows are also
absent, and outage truth records the gap.

## 5. Inspect assignments and tests — 10 minutes

```cmd
notepad data\generated\portfolio-v1\cohort_plan.json
notepad data\generated\portfolio-v1\validation_report.json
```

Compare targets, severities and onsets between the same fault in each split.
For example, generator failure is assigned to wagons 0033, 0038 and 0001 in the
reference cohort. Healthy controls also have shuffled identities.

Read `tests\portfolio\test_portfolio.py`. The tests cover stable seeds, changed
seeds, disjoint splits, component variation, onset eligibility and byte-identical
regeneration. Corruption tests alter saved files and ensure validation rejects
wrong hashes, component values, truth identities/targets, missing slots and
outage counts. They even update checksums in some cases to prove structural
checks do more than compare hashes.

For this session, read `docs\portfolio_dataset.md` for assumptions. The default
is deliberately rich in faults to exercise every path; it is not a claim about
real failure rates. Battery depletion remains an accelerated short-journey
fixture. Do not put truth or scenario settings into future model features.

## 6. Commit and stop — 5 minutes

Once your checks and dataset validation pass:

```cmd
git status
git add .
git commit -m "Add seeded portfolio cohorts and dataset validation"
git push
```

The generated files stay under ignored `data\generated`. Commit the planner,
validator, tests and docs. If a push is rejected because GitHub is ahead, use
`git pull --rebase origin main`, then push after resolving any reported conflict.

Stop here. The next session builds leakage-safe one-minute features with a
clear missing-data and quality policy. It will define how event-level truth
becomes window-level labels; it does not assume today's event counts are
already feature-window counts.
