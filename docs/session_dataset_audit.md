# Session — Audit the portfolio before model development

Target: about 45 minutes of active work, plus dataset-validation runtime.
Source contract 3.2 and feature contract 2.0 remain unchanged.

## Outcome

Add an audit command producing a readable Markdown report and detailed JSON.
It reads your existing generated portfolio and features; it does not regenerate
or alter them, construct training labels or train a model.

## Step 1 — Add and understand the module (10 minutes)

Merge this pack into your repository, preserving existing files:

- `src/fleetguard/audit.py`: new audit implementation and CLI.
- `tests/audit/test_dataset_audit.py`: new tests.
- `docs/session_dataset_audit.md`: this session guide.

Open these in CMD:

```cmd
notepad src\fleetguard\audit.py
notepad tests\audit\test_dataset_audit.py
```

Read the script in this order:

1. `iter_jsonl`: streams records from disk rather than loading all feature rows.
2. `summarise_windows`: counts complete, partial and silent component minutes;
   separately totals valid, missing and invalid numerical readings.
3. `audit_dataset`: calls both existing validators, verifies feature provenance,
   counts scenario assignments, routes, observed labels and outages per split.
4. `markdown_report`: converts the results into a concise readable summary.
5. `main`: exposes paths as arguments and writes UTF-8 outputs in a fresh directory.

The important distinction is report completeness versus sensor availability.
A minute can have all six reports but all six axle-speed measurements invalid.
Another minute may have no reports, so there are no received sensor readings to
classify as invalid. Their handling in the report is deliberately different.

## Step 2 — Verify the new behaviour (5 minutes)

Run from the project root with your environment activated:

```cmd
python -m ruff check .
python -m pytest tests\audit\test_dataset_audit.py -v
```

Tests cover missing reports versus unavailable sensors, complete reports with a
failed sensor, output-directory protection and rejection of mismatched provenance.

## Step 3 — Audit your current dataset (10 minutes, plus runtime)

Use your existing `portfolio-v1` dataset and its hierarchical features:

```cmd
python -m fleetguard.audit --source-dir data\generated\portfolio-v1 --feature-dir data\features\portfolio-v1 --output-dir data\features\portfolio-v1-audit
```

The output directory is a sibling of the feature dataset, not inside it. It must
be empty. Use a fresh name, such as `portfolio-v1-audit-02`, for later audits.

The command revalidates both datasets before summarising. If you have not yet
created one of them, follow `docs/dataset_generation_guide.md` first. Do not
regenerate valid existing data simply to repeat this session.

```cmd
notepad data\features\portfolio-v1-audit\audit.md
notepad data\features\portfolio-v1-audit\audit.json
```

`audit.md` shows scenario coverage and component-window completeness per split.
`audit.json` additionally contains route counts, observed truth counts, outage
counts, provenance hashes and numerical quality totals for every split/level.
Validation success establishes structural integrity, not model accuracy or a
claim that the dataset represents natural fault prevalence.

## Step 4 — Review the results (15 minutes)

Work through these questions using your actual output:

1. Does each split have the expected assigned variants and healthy controls?
   Default: 13 fault variants plus 3 controls per split. Controller persistent
   and bounded count separately in assignments, but share an anomaly truth type.
2. Are the actual selected routes represented? The small cohort does not promise
   every route in each split; do not invent missing coverage.
3. Which splits contain silent/partial windows? Compare wagon missing reports
   and outage intervals with the observed truth counts.
4. Which signals have invalid or missing received readings? Compare axle speed
   and pressures. Remember valid zero speed can represent a locked axle.
5. Which signal windows have no valid readings? These include silent windows
   and received windows with all readings unavailable; examine both counts.
6. Do the row counts follow 1 wagon, 2 bogie, 4 axle and 8 wheel summaries per
   scheduled full minute? Component report counts repeat the parent reporting
   slots; do not add them together as independent wagon observations.

Do not require exact event totals from a previous example: route durations,
selected faults and outages affect the totals. Assigned fault-wagon counts
are not identical to anomalous-report counts. Reports before onset or without
eligible fault evidence can be labelled healthy.

## Model-input decisions for the following session

This audit does not automatically pick features or derive labels. The next
session should establish explicit model-input and evaluation contracts:

- Keep raw 10-second inputs and minute summaries available for comparison.
- Preserve component identity for grouping, localisation and joins.
- Exclude scenario configuration, synthetic truth, asset IDs and split names
  from predictive values.
- Decide which observed quality and missingness fields belong to each task.
- Handle missing-report detection separately from scoring nonexistent reports.
- Derive evaluation labels using explicit time/target rules, rather than
  labelling every minute of a fault-assigned wagon anomalous.
- Fit preprocessing only on training data; use validation for settings and
  reserve test assets for final evaluation.

## Step 5 — Verify and commit (5 minutes)

```cmd
python -m ruff check .
python -m pytest -v
git add .
git commit -m "Add portfolio coverage and feature quality audit"
git push
git status
```

The audit output under `data/features/` is ignored by the existing ignore rule
unless files were previously tracked. Commit the new source, tests and session
reference. Do not assume ignore rules untrack existing datasets.

Stop with a successful audit, reviewed report, passing checks and clean Git
state. Send the Markdown report or its counts if you want to review findings
before selecting the first model inputs.
