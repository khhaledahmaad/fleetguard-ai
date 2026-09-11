# FleetGuard AI — Data Contract 2.0

## Event grain

One `TelemetryEvent` represents one wagon at one UTC minute within one journey.
It contains wagon-level readings plus nested telemetry for exactly two bogies,
two wheelsets per bogie and one monitoring controller.

## Physical metadata

| Scope | Fields | Character |
|---|---|---|
| Wagon | identity, fleet, age, nominal load, healthy baselines | persistent |
| Bogie | identity, A/B position, handbrake-equipped flag | persistent |
| Wheelset | identity, leading/trailing position | persistent |
| Wheel | left/right side, diameter in millimetres | slowly changing |

Healthy left/right wheel diameter difference is at most 2 mm. The two wheels
share one rigid axle and therefore one measured wheelset RPM.

## Telemetry ownership

| Scope | Signals |
|---|---|
| Journey | journey ID, route ID, phase, progress |
| Wagon | GPS, speed, ambient temperature, three-axis acceleration |
| Pneumatics | brake pipe, auxiliary reservoir, secondary reservoir |
| Bogie | brake-cylinder pressure |
| Wheelset | RPM, wheel speed, axle load, two bearing temperatures, vibration RMS |
| Controller | temperature, voltage, health, uptime, reset and communication counters |

All numerical units are encoded in field names. Contract ranges are synthetic
validation boundaries rather than certified railway limits.

## Raw versus derived values

Schema 2.0 stores simulated sensor readings and physical metadata. Feature
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
