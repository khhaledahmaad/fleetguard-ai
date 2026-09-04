# FleetGuard AI — Domain Specification

## 1. Domain Boundary

FleetGuard models a fictional fleet of instrumented freight rail assets.

Each asset produces synthetic telemetry describing its operating conditions,
axle-bearing behaviour and pneumatic braking behaviour.

All asset identities, measurements, operating patterns and failures are
synthetically generated. They do not represent any real operator, vehicle,
fleet or employer-owned system.

The initial platform models one monitored axle-bearing assembly and one braking
system per asset. Additional components are outside the first release.

## 2. Initial Fleet

The default generated fleet contains 24 assets.

Asset identifiers follow this format:

`FG-WGN-0001` through `FG-WGN-0024`

Each asset has persistent metadata:

| Field | Description | Example |
|---|---|---|
| `asset_id` | Unique fictional asset identifier | `FG-WGN-0001` |
| `asset_type` | Asset category | `freight_wagon` |
| `fleet_id` | Fictional fleet grouping | `FG-DEMO-01` |
| `commissioning_age_years` | Synthetic asset age | `7.4` |
| `nominal_load_tonnes` | Typical operating load | `62.0` |
| `bearing_baseline_temp_c` | Asset-specific healthy baseline | `42.5` |
| `vibration_baseline_g` | Asset-specific healthy vibration | `0.18` |
| `brake_pressure_baseline_bar` | Asset-specific healthy pressure | `5.0` |
| `generator_seed` | Seed used for reproducibility | `1042` |

Assets must not behave identically. Persistent differences in age, load and
sensor baselines will create controlled fleet heterogeneity.

## 3. Time and Sampling

The default full dataset contains:

- 24 assets;
- 14 consecutive days;
- one telemetry event per asset per minute;
- timestamps stored in UTC;
- approximately 483,840 telemetry events before injected duplicates or missing
  observations.

A smaller development profile may generate fewer assets and shorter periods,
but it must use the same schemas and behaviour rules.

Events must distinguish:

- `event_time`: when the synthetic measurement occurred;
- `generated_at`: when FleetGuard created the event.

## 4. Operating States

Each event belongs to one operating state.

| State | Description | Expected behaviour |
|---|---|---|
| `stationary` | Asset is not moving | Speed is zero; bearing temperature gradually approaches ambient |
| `moving` | Asset is travelling normally | Speed, load and ambient temperature influence bearing temperature and vibration |
| `braking` | Brakes are being applied | Speed decreases, brake-pipe pressure falls and brake-cylinder pressure rises |

Operating states must occur in realistic sequences.

Examples:

- `stationary → moving`
- `moving → braking → stationary`
- `moving → braking → moving`

Invalid direct state changes should be avoided unless deliberately generated as
a data-quality test.

## 5. Telemetry Signals

The first release contains eight core numerical signals.

| Signal | Unit | Healthy range | Purpose |
|---|---:|---:|---|
| `speed_kph` | km/h | 0–120 | Represents vehicle movement |
| `ambient_temp_c` | °C | -10–35 | Provides environmental context |
| `axle_load_tonnes` | tonnes | 10–25 | Represents load on the monitored axle |
| `bearing_temp_c` | °C | ambient to 85 | Primary bearing-health signal |
| `vibration_rms_g` | g | 0.02–0.70 | Secondary bearing-health signal |
| `brake_pipe_pressure_bar` | bar | 3.2–5.2 | Indicates pneumatic brake-pipe state |
| `brake_cylinder_pressure_bar` | bar | 0–3.8 | Indicates applied braking force |
| `battery_voltage_v` | V | 22–28 | Represents telemetry-device power health |

These ranges are synthetic modelling constraints, not operational railway
limits.

## 6. Healthy Signal Relationships

Healthy values must not be generated as independent random columns.

### Speed and operating state

- `stationary` requires speed equal or close to zero.
- `moving` normally produces positive speed.
- `braking` produces a decreasing speed trend.

### Bearing temperature

Healthy bearing temperature is influenced by:

- ambient temperature;
- recent speed;
- axle load;
- asset-specific baseline;
- thermal inertia.

Temperature should rise gradually during movement and cool gradually while
stationary. It should not immediately jump between unrelated values.

### Vibration

Healthy vibration is influenced by:

- speed;
- axle load;
- asset-specific baseline;
- small random noise.

Vibration should generally increase with speed and load.

### Pneumatic braking

During normal movement:

- brake-pipe pressure remains near its asset baseline;
- brake-cylinder pressure remains low.

During braking:

- brake-pipe pressure decreases;
- brake-cylinder pressure increases;
- speed subsequently decreases.

During brake release, pressures should gradually return towards their normal
values.

### Battery voltage

Battery voltage should change slowly and remain largely independent of
short-term mechanical behaviour.

## 7. Ground-Truth Anomaly Fields

Every event includes internal ground-truth fields:

| Field | Allowed values |
|---|---|
| `is_anomaly` | `true`, `false` |
| `anomaly_type` | `none`, `bearing_degradation`, `brake_pressure_leak`, `sensor_fault` |
| `anomaly_severity` | `none`, `low`, `medium`, `high` |
| `affected_signal` | Signal name or `none` |
| `anomaly_start_time` | UTC timestamp or null |
| `anomaly_progress` | Number from `0.0` to `1.0` |

Ground truth is used for generator verification and model evaluation. It must
not be supplied directly to the model as an input feature.

## 8. Failure Mode 1 — Gradual Bearing Degradation

### Description

A developing axle-bearing condition causes bearing temperature and vibration
to diverge gradually from healthy behaviour.

### Onset

- Develops over 12–72 hours.
- Begins with a small residual increase.
- Progresses continuously rather than appearing as an immediate threshold
  breach.

### Signal effects

- `bearing_temp_c` increases above the value expected from ambient temperature,
  speed and axle load.
- `vibration_rms_g` develops an increasing level and variability.
- Speed and axle load remain plausible and must not directly reveal the label.

### Severity

| Severity | Synthetic signature |
|---|---|
| `low` | Small temperature residual and slight vibration increase |
| `medium` | Persistent temperature residual and clearly elevated vibration |
| `high` | Strong residual increases in both signals |

### Detection challenge

The model should identify abnormal relationships and trends rather than merely
treating warm weather or high speed as failure.

## 9. Failure Mode 2 — Brake-Pressure Leakage

### Description

A synthetic pneumatic leak causes pressure to recover poorly or decay when the
braking system should be stable.

### Onset

- May begin gradually or abruptly.
- Persists for a defined episode.
- Can worsen over time.

### Signal effects

- `brake_pipe_pressure_bar` decays unexpectedly or recovers too slowly.
- `brake_cylinder_pressure_bar` may respond inconsistently with operating state.
- The effect must be evaluated relative to whether the asset is moving,
  braking or releasing its brakes.

### Severity

| Severity | Synthetic signature |
|---|---|
| `low` | Small abnormal decay or delayed recovery |
| `medium` | Persistent pressure loss across multiple observations |
| `high` | Rapid loss or major inconsistency between pipe and cylinder pressure |

### Detection challenge

A legitimate pressure decrease during braking must not automatically be
classified as leakage.

## 10. Failure Mode 3 — Sensor Fault

### Description

A telemetry sensor develops a measurement fault while the underlying synthetic
asset remains mechanically healthy.

### Supported behaviours

- gradual measurement drift;
- stuck or flatlined value;
- isolated spikes;
- intermittent missing values.

### Signal effects

The injector affects one selected numerical signal without changing the hidden
healthy physical state of the asset.

### Severity

| Severity | Synthetic signature |
|---|---|
| `low` | Small bias or occasional spike |
| `medium` | Sustained drift or repeated missing observations |
| `high` | Flatline, extreme bias or frequent implausible values |

### Detection challenge

FleetGuard must preserve the distinction between:

- an equipment anomaly;
- a sensor or data-quality problem.

The investigation layer must not describe a sensor fault as confirmed
mechanical failure.

## 11. Anomaly Injection Rules

- An anomaly episode belongs to one asset.
- Every episode has a start time, optional end time and progression curve.
- Multiple failure modes must not overlap on the same asset in the first
  release.
- Failure injection must be reproducible from the generator seed.
- Healthy periods must remain available before and after anomaly episodes.
- Some assets must remain completely healthy for held-out evaluation.
- Failure labels must be generated separately from model input features.
- The generator manifest must record anomaly counts and affected assets.

## 12. Initial Data Profiles

### Development profile

Used for rapid local tests:

- 3 assets;
- 6 hours;
- one event per minute;
- at least one deterministic anomaly episode.

### Standard profile

Used for model development:

- 24 assets;
- 14 days;
- one event per minute;
- mixture of healthy assets and all three anomaly types.

### Load profile

Used later for performance testing:

- configurable asset count and duration;
- same data contract;
- no change to the physical relationship rules.

## 13. Current Assumptions

The domain model intentionally simplifies real railway systems.

It assumes:

- one monitored bearing assembly per asset;
- one aggregated braking system per asset;
- regular one-minute telemetry;
- predefined operating-state transitions;
- labelled synthetic failures for evaluation;
- no direct safety or maintenance action from model output.

Any material change to these assumptions must be recorded in an architecture or
domain decision document.