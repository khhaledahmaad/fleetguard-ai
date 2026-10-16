# FleetGuard — Three EDA sessions

One notebook per session. Use your existing `portfolio-v1` source and hierarchical
features. Do not regenerate valid datasets for these notebooks.

| Session | Notebook | Story |
| --- | --- | --- |
| 1 | `01_dataset_overview.ipynb` | Cohort → identities → exposure → gaps → route maps |
| 2 | `02_healthy_signal_behaviour.ipynb` | Signal spread → states → component behaviour → engineering relationships |
| 3 | `03_anomaly_signal_behaviour.ipynb` | Fault evidence → neighbours → matched context → raw/minute comparison → artefacts |

## Apply and open (Windows CMD)

Merge this pack's `nbs` and `tests` into your repository. Keep the existing files.
The source generator, contracts and feature aggregation are unchanged.

```cmd
cd /d C:\Users\khhal\fleetguard-ai
.venv\Scripts\activate.bat
python -m pip install -e ".[dev]"
python -m pip install -r nbs\requirements-eda.txt
python -m ipykernel install --user --name fleetguard --display-name "FleetGuard AI"
python -m jupyterlab nbs
```

Choose the **FleetGuard AI** kernel. Open notebook 01 first. Trust your own
notebooks when Jupyter asks, then run the cells in order. Controls and linked
selections need the running kernel. Panel/HoloViews output does not turn a saved
static notebook into a working Python dashboard.

The two paths are visible near the top of every notebook:

```python
SOURCE = ROOT / "data/generated/portfolio-v1"
FEATURES = ROOT / "data/features/portfolio-v1"
```

The actual setup also accepts environment overrides for QA or another dataset.
Change paths if needed. `SPLIT = "train"` is the default. Use `validation` to
check findings. Test signal exploration is blocked by the loader; notebook 01
may inspect test metadata/coverage and execute integrity checks.

## What is interactive?

| View | Interaction |
| --- | --- |
| Plotly | Hover, zoom, pan, legend selection, box/lasso tools, image download |
| Healthy/fault explorers | Shared signal, asset, component and operating-context controls |
| HoloViews | Brush a relationship plot and link the same sampled rows in a time plot |
| Correlation matrix | Switch level; cluster related signals using absolute Spearman association |
| Folium | Street/aerial/topographic layers, routes, marker clusters, heat layers and timed density replay |
| Tables | Sort and page through bounded rows |

The fault explorer uses **EDA context groups**, not a finished training-label
policy. Parent-context readings do not mean every signal on that parent changed.
Wheel-slide/locked-axle/flat evidence remains axle-level; it does not identify an
individual wheel. Brake-release comparison uses the scenario's selected bogie.

## Maps and performance

- Esri street, aerial and topographic maps include attribution. Map tiles and
  Folium browser libraries need internet; there is no offline-basemap claim.
- Locations are coarse synthetic interpolations, not surveyed railway track.
- Only wagon reporting positions are mapped; wheel rows are not duplicated.
- Clusters use a deterministic sample of at most 600 markers; lines are thinned.
  Heat calculations use all received wagon reports, rounded to 0.01° cells.
- Density counts reflect reporting exposure and dwell. The fault-share layer
  shows anomalous **received** reports divided by received reports per cell,
  not natural failure probability, mileage-adjusted risk or all expected slots.
- Density replay uses 30-minute bins. It is a presentation view, not an animation
  of continuous wagon physics.
- HoloViews draws at most 12,000 rows, labelled as a selection sample. Plotly
  geographic points are sampled at 2,500; analytical tables/distributions retain
  the chosen population.
- Standard 48-wagon, 10-second data can take time and memory to load. Large
  replicated/1-second cohorts need deliberate asset subsets or a later columnar
  loading layer; this is not an enterprise-scale in-memory engine.

## Session tasks and stopping points

**01 — 45 minutes:** setup/open (10), coverage/identities (10), gaps/maps (15),
record findings (10). Stop knowing the population and reporting exposure.

**02 — 45 minutes:** availability (5), scan all four levels (15), inspect selected
signals and linked plots (15), record decisions (10). Stop knowing healthy
variation and the strong generator relationships. Do not declare causal links
from a pooled correlation matrix.

**03 — 45 minutes:** evidence/localisation (15), raw/minute and outage checks
(15), maps/artefacts (5), modelling decisions (10). Stop with explicit questions
for model-input/label design, not an automatically chosen model.

Use a second session if you want to inspect every fault in depth. The notebooks
are prepared together; there is no requirement to run all three tonight.

## Verification and limitations

All three notebook files pass nbformat validation and their code cells compile.
All code cells and initial visual objects were executed sequentially in-process
on a separately generated **48-wagon, 60-second coverage fixture**, not your
local 10-second portfolio. Six helper tests passed. Level/signal callbacks and
all 13 fault choices were exercised. The runtime blocked normal Jupyter kernel
sockets, so live-kernel execution remains a local check. Esri tile availability
also needs your local internet/browser.

The delivered notebooks have clean outputs to avoid presenting fixture results
as findings about your dataset. Run them locally to save your actual charts and
findings. The notebooks read data; they do not write over datasets or construct
predictive model inputs. Truth is used for EDA/evaluation context only.

```cmd
python -m ruff check .
python -m pytest tests\eda\test_eda_helpers.py -v
python -m pytest -v
```

After your session's checks and review:

```cmd
git add .
git commit -m "Add FleetGuard interactive EDA notebooks"
git push
git status
```

## Reference shelf

- `docs/data_workflow.md`: the six-part generation workflow.
- `docs/signal_catalogue.md`: scope, meanings and units.
- `docs/anomaly_catalogue.md`: fault signatures and limitations.
- `docs/hierarchical_feature_rules.md`: exact aggregation rules.

Tool guidance used: Plotly tile-map layers, Panel Plotly panes/notebook extensions,
HoloViz linked selections and Folium HeatMapWithTime documentation. The notebook
outputs should determine findings; this pack makes no trained-model or commercial
performance claims.

Official tool references:

- [Plotly tile-map layers](https://plotly.com/python/tile-map-layers/)
- [Panel Plotly panes](https://panel.holoviz.org/reference/panes/Plotly.html)
- [Panel notebook output](https://panel.holoviz.org/how_to/notebook/notebook.html)
- [HoloViz linked selections](https://holoviz.org/tutorial/exercises/Linking_Plots.html)
- [Folium heat replay](https://python-visualization.github.io/folium/latest/user_guide/plugins/heatmap_with_time.html)
