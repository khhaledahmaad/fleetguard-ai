# FleetGuard minute aggregation rules — feature schema 2.0

The original schema-3.2 telemetry remains the granular source. These minute
summaries are an additional representation, not a mandated modelling resolution.
The standard source sampling remains 10 seconds. Rapid faults may require finer
experiments; a minute summary is not proof that a transient has been captured.

## Grouping

Every row has split, journey ID, route ID, asset ID and minute start/end. Bogie
rows additionally have bogie ID; axle rows add axle position; wheel rows add
wheel side. Each wagon minute produces 1 wagon + 2 bogie + 4 axle + 8 wheel rows.
Controller and battery summaries are at wagon level, reflecting one shared
controller and battery. Shared context in normalised bogie observations is
retained in the bogie summaries, even when also present at wagon level.

## Field policies

Numerical fields keep their source name inside `numeric`. Each has `mean`,
`minimum`, `maximum`, `first` and `last` calculated from valid readings only.
`first` and `last` mean first/last valid reading in timestamp order. Quality
counts are per received component report. Unavailable numerical values are never
replaced with zero, and invalid raw codes are counted separately.

Categorical fields keep their source name inside `categorical`: last observed
value, counts, fractions of received reports, and transitions between observed
reports within the minute. These are sample fractions, not continuous-time
occupancy estimates when reports are missing. Transitions across gaps are
observed differences, not exact transition times or complete event counts.

Controller field names are prefixed `controller_` when flattened to wagon level.

| Level | Field | Policy |
| --- | --- | --- |
| wagon | `route_progress` | Mean/minimum/maximum/first/last; quality counts |
| wagon | `speed_kph` | Mean/minimum/maximum/first/last; quality counts |
| wagon | `ambient_temp_c` | Mean/minimum/maximum/first/last; quality counts |
| wagon | `longitudinal_acceleration_mps2` | Mean/minimum/maximum/first/last; quality counts |
| wagon | `lateral_acceleration_mps2` | Mean/minimum/maximum/first/last; quality counts |
| wagon | `vertical_acceleration_mps2` | Mean/minimum/maximum/first/last; quality counts |
| wagon | `estimated_adhesion_coefficient` | Mean/minimum/maximum/first/last; quality counts |
| wagon | `brake_pipe_pressure_bar` | Mean/minimum/maximum/first/last; quality counts |
| wagon | `auxiliary_reservoir_pressure_bar` | Mean/minimum/maximum/first/last; quality counts |
| wagon | `secondary_reservoir_pressure_bar` | Mean/minimum/maximum/first/last; quality counts |
| wagon | `battery_voltage_v` | Mean/minimum/maximum/first/last; quality counts |
| wagon | `available_axle_generators` | Mean/minimum/maximum/first/last; quality counts |
| wagon | `controller_temperature_c` | Mean/minimum/maximum/first/last; quality counts |
| wagon | `controller_supply_voltage_v` | Mean/minimum/maximum/first/last; quality counts |
| wagon | `controller_uptime_seconds` | Mean/minimum/maximum/first/last; quality counts; observed positive changes and decreases within the minute |
| wagon | `controller_reset_count` | Mean/minimum/maximum/first/last; quality counts; observed positive changes and decreases within the minute |
| wagon | `controller_sensor_communication_error_count` | Mean/minimum/maximum/first/last; quality counts; observed positive changes and decreases within the minute |
| bogie | `speed_kph` | Mean/minimum/maximum/first/last; quality counts |
| bogie | `estimated_adhesion_coefficient` | Mean/minimum/maximum/first/last; quality counts |
| bogie | `brake_pipe_pressure_bar` | Mean/minimum/maximum/first/last; quality counts |
| bogie | `auxiliary_reservoir_pressure_bar` | Mean/minimum/maximum/first/last; quality counts |
| bogie | `secondary_reservoir_pressure_bar` | Mean/minimum/maximum/first/last; quality counts |
| bogie | `brake_cylinder_pressure_bar` | Mean/minimum/maximum/first/last; quality counts |
| axle | `rotational_speed_rpm` | Mean/minimum/maximum/first/last; quality counts |
| axle | `wheel_speed_kph` | Mean/minimum/maximum/first/last; quality counts |
| axle | `axle_load_tonnes` | Mean/minimum/maximum/first/last; quality counts |
| axle | `vibration_rms_g` | Mean/minimum/maximum/first/last; quality counts |
| wheel | `bearing_temp_c` | Mean/minimum/maximum/first/last; quality counts |
| wagon | `travel_direction` | Last, category counts/fractions, observed transitions |
| wagon | `operating_state` | Last, category counts/fractions, observed transitions |
| wagon | `journey_phase` | Last, category counts/fractions, observed transitions |
| wagon | `rail_condition` | Last, category counts/fractions, observed transitions |
| wagon | `power_source` | Last, category counts/fractions, observed transitions |
| wagon | `brake_demand` | Last, category counts/fractions, observed transitions |
| wagon | `controller_health_status` | Last, category counts/fractions, observed transitions |
| bogie | `rail_condition` | Last, category counts/fractions, observed transitions |
| bogie | `handbrake_equipped` | Known asset metadata; require observed values to agree |
| wheel | `diameter_mm` | Known asset metadata; require observed values to agree |
| Wagon | `latitude`, `longitude` | Paired coordinates from the last report, with its timestamp |
| All | `event_id` | Ordered `source_event_ids` for lineage; never averaged |
| All | `event_time` | First and last observed timestamps |
| Wagon source, retained in all rows | `generated_at` | First and last reports' generation timestamps |
| All | Schema version | Explicit source schema version |
| All | Sampling interval | Explicit interval and expected reports |
| All | Signal quality | Valid/missing/invalid counts and invalid raw-code counts per numerical signal |
| All | Component identities | Grouping keys, not model measurements |
| Wagon | Nested bogies/controller | Bogies split into their own levels; controller fields flattened into wagon summaries |
| Bogie | Nested axles | Separate axle summaries |
| Axle | Nested wheels | Separate wheel summaries |

Static asset metadata (fleet, age, baselines and configuration) and journey
metadata (terminals, declared duration/load/cargo) remain in the raw source.
They are not time-varying sensor variables and are not all repeated as minute
features. The wheel diameter and handbrake attributes already present in
normalised observations are retained explicitly. No original source file is
modified or discarded.

## Missingness and counters

Expected minus received reports describes whole-report gaps. Sensor missing/
invalid counts describe unavailable values in reports that actually arrived.
A silent minute has zero received reports and zero sensor observation counts,
with null statistics and empty category counts. Known metadata is still known;
it is not an invented sensor reading.

`observed_positive_change` sums positive differences between consecutive valid
counter observations within the same minute. `decrease_count` counts decreases;
these may indicate a reset, wrap or discontinuity, and are not automatically
classified as reboots. Cross-minute differences are not included. One valid
sample has zero observed within-minute change. These fields cannot reconstruct
unobserved changes during gaps.

## Boundaries and evaluation

Minute windows are `[start,end)` and require minute-aligned journey starts.
The final incomplete minute is excluded; excluded duration/report counts are
recorded per journey. Source IDs, split, route, timestamps and quality raw-code
values are provenance/diagnostic data, not a ready-made numerical model matrix.
Choose explicit model features later. Separate event/window truth labels are
not read into aggregation features.

A field-coverage test checks every TelemetryEvent, ControllerTelemetry,
BogieTelemetry, AxleTelemetry, WheelTelemetry and normalised observation field.
Adding an unhandled contract field fails that test. Asset/journey metadata is
retained upstream rather than being subject to that telemetry-field test.

Saved-file validation checks checksums, schemas, component catalogues, split
isolation, counts, consecutive per-component windows and common source-event
lineage across levels. It does not recalculate all statistics from original
telemetry. Checksums are accidental-corruption checks, not signatures.

## Connected references

See the [documentation guide](README.md), [signal catalogue](signal_catalogue.md),
[data contract](data_contract.md) and [dataset generation guide](dataset_generation_guide.md).
