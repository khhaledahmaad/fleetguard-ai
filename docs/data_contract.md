# FleetGuard AI — Data Contract 3.2

## Event grain

One `TelemetryEvent` represents one wagon at one configured sampling instant
within one journey.
It contains wagon-level readings plus nested telemetry for exactly two bogies,
two axles/wheelsets per bogie and one monitoring controller.

## Physical metadata

| Scope | Fields | Character |
|---|---|---|
| Wagon | identity, fleet, age, nominal load, healthy baselines | persistent |
| Wagon battery | expected standby endurance in days | persistent |
| Bogie | identity 1/2 and handbrake-equipped flag | persistent |
| Axle/wheelset | inner/outer position within its bogie | persistent |
| Wheel | left/right side and diameter in millimetres | slowly changing |

Healthy left/right wheel diameter difference is at most 2 mm. The two wheels
share one rigid axle and therefore one measured wheelset RPM.

## Telemetry ownership

| Scope | Signals |
|---|---|
| Journey | journey ID, route ID, phase, progress |
| Wagon | GPS, speed, ambient temperature, three-axis acceleration |
| Pneumatics | brake pipe, auxiliary reservoir, secondary reservoir |
| Wagon power | `battery_voltage_v`, `power_source`, `available_axle_generators` |
| Bogie | brake-cylinder pressure |
| Wheelset | RPM, wheel speed, axle load, two bearing temperatures, vibration RMS |
| Controller | temperature, separate regulated `supply_voltage_v`, health, uptime, reset and communication counters |

All numerical units are encoded in field names. Contract ranges are synthetic
validation boundaries rather than certified railway limits.

`battery_voltage_v` is a synthetic single-cell-equivalent battery measurement
(3.0–4.2 V); it is not a measured whole-pack voltage. The controller's regulated
~25 V supply is a separate electrical rail. Each wagon has one shared battery
and four axle-end generators, one at each axle. The journey generator treats
speeds of at least 5 km/h as sufficient for generator power and charging; this
is a simulation threshold, not a manufacturer specification. While generator
power is unavailable the battery discharges at a configured rate corresponding
to a full-to-cut-off standby period of 5–7 days. Charging and discharging use
simple linear voltage approximations, not a physical state-of-charge model.

Schema 3.2 adds nullable failed speed/pressure readings with `signal_quality`,
`brake_demand`, `available_axle_generators`, missing-report truth and outage truth.
Do not mix historical 3.0/3.1 files with 3.2 without migration.
A healthy expected timestamp emits one event. A controller power outage emits
no event; it is represented on a separate expected-report truth timeline.
Multi-day parking duty planning is still outside the current journey generator.

## Quality and lineage

An omitted `signal_quality` entry means valid. A null speed or pressure requires
`missing` or `invalid` quality. Invalid raw device codes are retained only in
quality metadata, never as engineering-unit measurements. BPP/AR/SR quality
belongs to the wagon; BCP quality belongs to its bogie; speed/RPM quality belongs
to its axle. The normalised tables preserve this information.

`brake_demand` is simulated apply/release command context. `operating_state` and
route trajectory retain the planned operating context after injection; they are
not a re-simulation of vehicle dynamics under a brake fault.

One observed event joins exactly one `anomaly_truth` row using event ID and asset
ID. Missing-report truth is disjoint from observed events. For every run:
`expected_reports = telemetry_events + missing_reports`.
Each observed event still creates exactly 2 bogie, 4 axle and 8 wheel rows.
Outage intervals use `[start_time, end_time_exclusive)`. Unrecovered intervals
end at the dataset horizon. See `anomaly_catalogue.md` for timing and label rules.

## Raw versus derived values

Schema 3.2 stores simulated sensor readings and physical metadata. Feature
engineering will later derive diameter difference, wheel/ground-speed residual,
slip ratio, bogie pressure imbalance, pressure decay/recovery rates, bearing
temperature residuals and vibration-window statistics. Ground truth must never
enter model features.

## Route limitations

The London–Swansea fixture follows real UK corridor locations but is deliberately
coarse. It is deterministic, offline and suitable for synthetic analytics—not
navigation, infrastructure inspection, train control or claims about actual
Tarmac operations. Commercial terminals and schedules are fictional.

Random journey planning chooses reproducibly among London–Avonmouth,
Avonmouth–Cardiff, Cardiff–Swansea and full London–Swansea duties, including
reverse movements. Journey duration is derived rather than fixed.

## Sampling and feature windows

- 60 seconds: development and fast testing.
- 10 seconds: standard portfolio dataset and default operational journey.
- 1 second: high-resolution braking and motion experiments.
- 60 seconds: standard downstream feature-window duration.

The controller publishes one wagon-level estimated adhesion coefficient derived
from wheel, motion and braking information. Internal physical truth retains the
true adhesion coefficient and does not expose it to model inputs.

Each raw event normalises into two bogie, four axle and eight wheel observations.
