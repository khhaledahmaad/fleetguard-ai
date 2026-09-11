# FleetGuard AI

FleetGuard AI is a production-shaped MLOps platform for anomaly detection on
synthetic freight-wagon telemetry. It is a portfolio and learning system, not a
safety-critical railway product.

The schema models two bogies and four wheelsets per wagon, shared pneumatic
signals, controller diagnostics and journey-aware motion along a synthetic UK
freight corridor. Development batches can use a fixed period count; production-
shaped generation uses route-derived journey durations with terminal and
intermediate dwell.

`create_random_journey_plan(seed)` reproducibly selects one of several London,
Avonmouth, Cardiff and Swansea terminal-to-terminal duties and may reverse its
direction. `create_journey_plan(...)` builds a specific duty.

## Local verification (Windows CMD)

```cmd
python -m pip install -e ".[dev]"
python -m ruff check .
python -m pytest -v
```

See `docs/product_contract.md`, `docs/domain_specification.md` and
`docs/data_contract.md` for scope and modelling decisions.
