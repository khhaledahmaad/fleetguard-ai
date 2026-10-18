# FleetGuard AI — current development snapshot

This complete source archive is based on your latest GitHub ZIP. It includes
mapped railway geometry, distance-consistent simulated duties, documentation,
the rebuilt offline atlas, notebook refinements and the existing audit tools.
Assets and wordmark are preserved. Historical session notes live in docs/history;
use docs/data_workflow.md for current commands.

## Install and verify (Windows CMD)

Extract this archive first. Copy its contents into your existing project while
keeping your .git directory and .venv. Files in docs/history replace the older
session notes at the top level; remove those duplicate top-level session notes
if you merge folders rather than use a clean extracted source tree.

```cmd
cd /d C:\Users\khhal\fleetguard-ai
.venv\Scripts\activate.bat
python -m pip install -e ".[dev]"
python -m pip install -r nbs\requirements-eda.txt
python -m ruff check .
python -m pytest -v
```

## Generate data

Large generated datasets are not bundled or committed. Use empty output folders:

```cmd
scripts\generate_portfolio.cmd
```

This writes data/generated/portfolio-v1, data/features/portfolio-v1 and
its audit. Existing outputs from the earlier geometry must be regenerated;
renaming them does not update their coordinates or provenance. Remove only
those disposable generated output folders if they already contain old data.
The script never deletes files and stops if a command fails.

## Open

- Atlas: atlas/_site/index.html (already rebuilt; Mermaid works offline).
- Notebooks: python -m jupyterlab nbs, starting with 01_dataset_overview.ipynb.
- Current data guide: docs/data_workflow.md.
- Route provenance and limitations: docs/route_data.md.

Package 0.4.0, telemetry schema 3.2, feature schema 2.0. Dataset folder naming
is independent of those versions. Journey timing is simulated from mapped
track distance, not a railway timetable.

## Commit

```cmd
git add .
git status
git commit -m "Align railway routes, documentation, atlas and EDA notebooks"
git push
```

Verification: 179 Python tests passed; Ruff passed; all three notebooks executed
in-process against the full 48-wagon, 10-second fixture. A normal live Jupyter
kernel could not start in the QA environment because TCP socket access is blocked.
Check local notebook controls and map tiles when opening your first EDA session.
