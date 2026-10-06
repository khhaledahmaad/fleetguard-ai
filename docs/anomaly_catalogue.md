# FleetGuard AI — Twelve anomaly scenarios

This catalogue describes synthetic test signatures, not manufacturer-validated
failure physics or operational diagnostic rules. All injections start from a
reproducible healthy baseline. They preserve the planned journey trajectory.
Brake and wheel faults do not re-simulate train forces, stopping distances,
route timing or subsequent wear.

| # | Scenario | Truth scope | Injected evidence | CLI profile |
|---|---|---|---|---|
| 1 | Bearing degradation | Target wheel bearing and parent axle | Temperature ramp plus axle vibration uplift | `bearing-demo` |
| 2 | Brake pressure leak | Wagon pneumatic system | BPP and AR loss; SR and BCP retain baseline | `brake-leak-demo` |
| 3 | Bearing-temperature sensor drift | Target wheel sensor | Temperature bias; vibration and mechanics unchanged | `sensor-drift-demo` |
| 4 | Axle speed generator failure | Target axle | Null speed/RPM with quality; three generators remain available | `axle-generator-demo` |
| 5 | Wheel slide | Target axle/wheelset | Reduced, positive speed/RPM during moving brake application | `wheel-slide-demo` |
| 6 | Locked axle | Target axle/wheelset | Valid zero speed/RPM while wagon speed exceeds 5 km/h | `locked-axle-demo` |
| 7 | Suspected wheel flat | Target axle/wheelset | Speed-dependent vibration RMS uplift, no left/right claim | `wheel-flat-demo` |
| 8 | Pressure transducer failure | Target wagon or bogie sensor | Null pressure with missing/invalid quality | `pressure-transducer-demo` |
| 9 | Brake release failure | Wagon brake system | After application, release demand and recovered BPP but one BCP remains high | `brake-release-demo` |
| 10 | Undemanded brake application | Wagon brake system | Release demand, unexpected BPP loss and both BCP readings high | `undemanded-brake-demo` |
| 11 | Premature battery depletion | Wagon battery | Extra discharge, cutoff silence, possible recharge/reboot in motion | `battery-depletion-demo` |
| 12 | Controller supply failure | Wagon controller | Persistent sag/outage or abrupt bounded outage/reboot | `controller-persistent-demo`, `controller-bounded-demo` |

`none` produces the healthy control. There are twelve anomaly types; two CLI
profiles demonstrate the two controller modes. No new hub, GPS-failure scenario,
or additional mechanical subsystem has been introduced.

## Targeting and scenario timing

The public entry point remains `inject_fleet_anomaly_scenarios(batch, scenarios)`.
`AnomalyScenario` describes type, component, start, end and configured severity.
One scenario per asset per batch is enforced, even for non-overlapping times,
because event truth currently carries one label. Different assets can have
different scenarios in the same batch. Always inject together into a fresh
healthy baseline; repeated injection is rejected.

- The three progressive scenarios use `end_time` as the time to reach the peak;
  the peak persists for the rest of the dataset.
- Wheel slide uses `[start_time, end_time)` and only changes eligible moving,
  brake-applied samples. It recovers to baseline after that interval.
- Generator failure, pressure failure, locked axle and suspected flat persist
  after onset. Mechanical evidence for locked axle and flat is emitted only
  while speed exceeds the synthetic 5 km/h evidence threshold.
- Brake-release failure waits for an apply-to-release transition. Its elevated
  BCP signature persists during subsequent release demand. Undemanded braking
  also only appears during release demand. Both labels belong to the wagon
  brake system. `brake_demand` is independent simulated command context, not a
  command inferred from the faulty pressures.
- Battery depletion is stateful and persists after onset. `end_time` is retained
  for the common scenario contract, but does not control discharge or repair.
- Persistent controller failure sags from start to `end_time`, then stops
  reporting. Bounded controller failure is abrupt at start and resumes at
  `recovery_time`; `end_time` is not its cutoff. The common contract requires
  `start_time < end_time < recovery_time` for a bounded scenario.

`anomaly_severity` records the configured scenario severity. It does not change
as progression changes. Instantaneous signatures use progress 1; progressive
signatures use elapsed ramp progress. Battery progress is a simple
`(4.2 - voltage) / 1.2` depletion proxy, not physical state of charge.
`outage_mode` is independent of severity.

## Invalid readings are not physical values

The pressure demo fails bogie 2 BCP. The Python scenario API also supports wagon
BPP, AR, SR, and either bogie BCP. The engineering value becomes `null`.

```json
{
  "brake_cylinder_pressure_bar": null,
  "signal_quality": {
    "brake_cylinder_pressure_bar": {"status": "invalid", "raw_value": 255}
  }
}
```

255 is an illustrative device error code only, not an industry-wide standard.
`failure_encoding="missing"` emits null with missing quality and no raw value.
An omitted quality entry means valid. Null without a non-valid quality flag is
rejected. Normalised records carry the same quality context.

An axle speed-generator failure makes both speed and RPM unavailable; it does
not physically stop the axle. Three remaining generators are assumed sufficient
to power the controller. A simplified charging rate of 75% of healthy is used
for that wagon. `available_axle_generators` reports 3 rather than 4.

A locked axle has valid zero measurements. This distinction is central to later
feature engineering; do not impute missing speed to zero.

## Battery and controller outages

Battery voltage uses the existing synthetic 3.0–4.2 V cell-equivalent scale.
Extra battery discharge applies only in battery power mode, in addition to the
healthy baseline discharge. In generator mode it charges at 0.18 V/hour.
At 3.0 V it stops reporting. Generator charging above 3.1 V permits restart;
this small hysteresis avoids rapid switching around cutoff. These are simulation
settings, not hardware specifications. 3.2 V is an explanatory low-battery
reference, not an implemented alert service.

The battery CLI demo sets extra discharge to **18 V/hour**, deliberately
accelerated so a normal journey contains failure and recovery. Do not use this
smoke profile as a 5–7-day endurance study. The default scenario API extra drain
is 0.1 V/hour. Long parked-duty generation and endurance calibration remain
separate dataset-design work. Battery event labels indicate an observed deficit
relative to baseline; latent fault configuration stays in scenario metadata.

Controller supply failure leaves upstream battery/generator values unchanged in
the synthetic baseline. Persistent mode uses a voltage sag followed by complete
silence. Bounded mode interrupts abruptly and resumes with `uptime_seconds=0`
and one extra `reset_count`. Battery-caused restarts use the same counter logic.

During silence there is no telemetry row, no event truth row, and no derived
bogie/axle/wheel row. Instead:

- `missing_report_truth.jsonl` records each scheduled-but-unemitted report;
- `outage_truth.jsonl` groups those missing slots into half-open time intervals;
- `recovered=false` means no recovery **within the generated horizon**, not a
  claim that the equipment can never be repaired.

The back office sees last observations and absent expected reports. Only
synthetic truth knows the injected cause. Missingness alone does not distinguish
controller power failure from communications failure. Missing-report detection
will be a separate expected-report monitor, not a model scoring nonexistent rows.

## Sampling and evaluation limits

Use 10-second sampling for the standard portfolio source. Additional 60-second
summaries exist at each component level; granular modelling remains available.
A 60-second smoke test may contain only two slide samples. A one-minute feature
window at that frequency contains one sample, which is insufficient for useful
within-window variance. One-second experiments still do not resolve raw
high-frequency wheel impacts. The suspected-flat signature is an RMS uplift;
it does not synthesize impact waveforms or prove an individual wheel is flat.

Keep all three truth outputs and scenario configuration out of model inputs.
Split evaluation by held-out assets; report mechanical detection, sensor-quality
detection and outage detection separately. Seeded dataset splits and hierarchical minute summaries are implemented.
Model feature selection, evaluation labels, trained models and runtime monitoring
remain subsequent milestones.

## Connected references

See the [documentation guide](README.md), [signal catalogue](signal_catalogue.md),
[data contract](data_contract.md) and [dataset generation guide](dataset_generation_guide.md).
