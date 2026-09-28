# FleetGuard AI — Domain Specification

## 1. Domain Boundary

FleetGuard models a fictional fleet of instrumented freight rail assets.

Each asset produces synthetic telemetry describing its operating conditions,
axle-bearing behaviour and pneumatic braking behaviour.

All asset identities, measurements, operating patterns and failures are
synthetically generated. They do not represent any real operator, vehicle,
fleet or employer-owned system.

Each wagon models two bogies, two axles/wheelsets per bogie, two wheels per axle,
shared wagon-level pneumatic equipment and one digital monitoring controller.
The model is production-shaped but intentionally vendor-neutral.

## 2. Initial Fleet

The CLI defaults to 3 assets. A larger portfolio cohort will be configured
during dataset design.

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
| `bogies` | Two bogies, four axles and eight wheels | nested metadata |
| `generator_seed` | Seed used for reproducibility | `1042` |

Assets must not behave identically. Persistent differences in age, load and
sensor baselines will create controlled fleet heterogeneity.

## 3. Time and Sampling

The standard portfolio sampling design uses:

- an explicitly configured asset cohort and journey set;
- one telemetry event per active asset every 10 seconds;
- timestamps stored in UTC;
- complete route-derived journeys rather than continuous fabricated movement.

The final event count depends on the randomly assigned journeys and dwell
periods. Development and high-resolution profiles use 60-second and 1-second
sampling respectively. All profiles feed one-minute feature windows.

A smaller development profile may generate a requested number of periods. Main
dataset generation uses complete journeys whose duration is calculated from
route distance, nominal freight speed, terminal dwell and intermediate stops.

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

Journey phases provide operational context: `origin_dwell`, `running`,
`intermediate_dwell` and `destination_dwell`.

## 5. Telemetry Signals

Schema 3.2 contains wagon, bogie, axle, wheel and controller signals.

| Signal | Unit | Healthy range | Purpose |
|---|---:|---:|---|
| `speed_kph` | km/h | 0–120 | Represents vehicle movement |
| `ambient_temp_c` | °C | -10–35 | Provides environmental context |
| `latitude`, `longitude` | degrees | UK corridor | Route position context |
| three-axis acceleration | m/s² | contract bounded | Braking, curves and track response |
| `brake_pipe_pressure_bar` | bar | 3.2–5.2 | Indicates pneumatic brake-pipe state |
| AR/SR pressure | bar | 0–6 | Shared reservoir behaviour |
| bogie brake-cylinder pressure | bar | 0–5 | Bogie-level braking response |
| wheelset RPM and speed | rpm, km/h | contract bounded | Rotation and ground-speed consistency |
| axle load | tonnes | 0–30 | Per-wheelset load context |
| left/right bearing temperature | °C | ambient to 85 | Bearing-health signals |
| wheelset vibration RMS | g | 0.02–0.70 | Mechanical-health signal |
| `battery_voltage_v` | V | 3.0–4.2, per-cell equivalent | Shared wagon battery |
| `power_source` | category | battery/generators | Current wagon power source |
| controller temperature and supply voltage | °C, V | contract bounded | Regulated device-health context |
| controller health and counters | categorical/count | healthy baseline | Device diagnostics |
| `rail_condition` | category | dry/wet/leaf/icy | Route-surface context |
| `estimated_adhesion_coefficient` | coefficient | 0–0.6 | Wagon controller estimate |

These ranges are synthetic modelling constraints, not operational railway
limits.

Four axle-end generators are assumed to provide wagon power and charge one
shared battery during movement above the synthetic 5 km/h generation threshold.
At a standstill, the battery supplies the controller. The configured healthy
full-to-cut-off standby duration varies from five to seven days per wagon.
The current journey dataset covers hours. Injected battery and controller faults
can create message gaps, but multi-day parked-duty planning is not yet implemented.

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

### Controller behaviour

Controller voltage changes slowly, temperature responds mildly to ambient and
activity, and health/counter values remain stable in healthy generation.

## 6.1 Physical hierarchy and signal ownership

- Wagon: journey, route, GPS, ground speed, acceleration, BP, AR and SR.
- Bogie: handbrake configuration and brake-cylinder pressure.
- Wheelset: one axle RPM, axle load, vibration and two bearing temperatures.
- Wheel: left/right identity and slowly changing diameter metadata.
- Controller: temperature, supply voltage, health, uptime and error counters.

Rail condition belongs to the wagon's current route position. The controller
combines wagon, bogie and axle information into one wagon-level estimated
adhesion coefficient. A separate true adhesion value remains internal ground
truth and must not be provided to the model.

Both wheels on a conventional axle/wheelset share RPM. Their diameters may
differ slightly within the healthy synthetic tolerance; speed/RPM/diameter
disagreement is reserved for later fault injection or derived features.

## 6.2 Synthetic UK route

The initial route follows the geographic order of the Great Western and South
Wales corridor: London, Reading, Swindon, Bath, Bristol, Avonmouth, Newport,
Cardiff, Port Talbot and Swansea. Terminal names and all commercial movements
are fictional. The committed points form a compact corridor-level polyline,
not navigation-grade track geometry and not an operational railway timetable.

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

## 11. Anomaly injection and evaluation

The authoritative twelve-scenario catalogue is `anomaly_catalogue.md`.
The earlier bearing/leak/sensor sections describe the three original signatures;
the catalogue defines all current types, targets, quality and outage semantics.

- One scenario per asset per batch; multiple assets can have distinct scenarios.
- Injection requires a healthy baseline and preserves it for comparisons.
- Progressive peak effects can persist; healthy post-fault periods are not
  guaranteed. Bounded controller outages explicitly recover.
- Keep control assets and held-out assets for evaluation.
- Truth never enters feature inputs.
- The manifest records observed anomaly counts, missing counts and scenario assets.
- Fault signatures preserve planned movement; they are not coupled rail dynamics.

## 12. Dataset profiles

Development uses 60-second sampling; the portfolio standard uses 10 seconds;
1-second experiments provide more detailed low-frequency motion observations.
Feature windows are one minute. The CLI generates one route-derived journey
per invocation for the configured fleet. Multi-day cohorts, parked duty cycles,
train/validation/test splits and calibrated anomaly prevalence are subsequent
work, not outputs already delivered by the CLI.

## 13. Current assumptions

There are two bogies, four axles, eight wheel/bearing observations, two BCP
transducers (one per bogie), shared BPP/AR/SR, one battery and one controller.
Wheels share rigid wheelset rotation. Vibration is axle RMS evidence. Power
voltage and charging are simple synthetic approximations. Coordinates follow a
coarse UK corridor fixture. All outputs support learning and human investigation,
not operational safety or automatic maintenance decisions.
