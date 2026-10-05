"""Build offline atlas data from the implemented generator and feature contracts."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleetguard.features.hierarchical_aggregation import (  # noqa: E402
    CATEGORICAL,
    NUMERIC,
    aggregate_components,
    flatten_event,
)
from fleetguard.generator import (  # noqa: E402
    create_random_journey_plan,
    generate_fleet_assets,
    generate_healthy_journey_fleet,
    inject_fleet_anomaly_scenarios,
)
from fleetguard.generator.cli import (  # noqa: E402
    _build_bearing_demo_scenario,
    _build_brake_leak_demo_scenario,
    _build_sensor_drift_demo_scenario,
)
from fleetguard.generator.profiles import build_demo_scenario  # noqa: E402
from fleetguard.portfolio.planning import (  # noqa: E402
    PortfolioConfig,
    plan_assignments,
    plan_journey,
    serialise_scenario,
)

START = datetime(2026, 1, 1, 6, tzinfo=UTC)
SPECS = [
    (
        "Bearing degradation",
        "Mechanical",
        "bearing-demo",
        "bearing",
        "bearing_temp_c",
        "vibration_rms_g",
        "°C",
        "g",
        "A developing bearing signature",
        (
            "One bearing warms above its healthy baseline; vibration also rises"
            " at the parent axle. The other bearings retain their healthy value"
            "s."
        ),
        (
            "The ramp reaches its configured peak, then persists. Temperature a"
            "nd vibration are statistical evidence, not proof of physical failu"
            "re."
        ),
    ),
    (
        "Brake pressure leak",
        "Pneumatic",
        "brake-leak-demo",
        "brakes",
        "brake_pipe_pressure_bar",
        "auxiliary_reservoir_pressure_bar",
        "bar",
        "bar",
        "Shared pressure loss",
        (
            "Wagon BPP and auxiliary-reservoir pressure decline. Secondary-rese"
            "rvoir and bogie BCP values remain on their healthy trajectories."
        ),
        (
            "This injection is a controlled signal signature. It does not recal"
            "culate train braking forces or stopping distance."
        ),
    ),
    (
        "Bearing sensor drift",
        "Sensor",
        "sensor-drift-demo",
        "bearing",
        "bearing_temp_c",
        "vibration_rms_g",
        "°C",
        "g",
        "A reading drifts; the mechanics do not",
        (
            "The selected wheel's temperature measurement develops a bias. Pare"
            "nt axle vibration remains healthy, providing useful comparative ev"
            "idence."
        ),
        (
            "Temperature drift and genuine degradation can overlap. Multiple si"
            "gnals are needed; this is not a certified diagnostic rule."
        ),
    ),
    (
        "Axle speed generator failure",
        "Sensor / power",
        "axle-generator-demo",
        "axle",
        "wheel_speed_kph",
        "available_axle_generators",
        "km/h",
        "count",
        "Unknown rotation is different from zero",
        (
            "The target axle's speed and RPM become unavailable with explicit q"
            "uality. Available generators fall from four to three; simplified c"
            "harging runs at 75% of healthy."
        ),
        (
            "Null is not a locked axle. Three generators are assumed sufficient"
            " for controller power in this simulation."
        ),
    ),
    (
        "Wheel slide",
        "Mechanical",
        "wheel-slide-demo",
        "axle",
        "wheel_speed_kph",
        "speed_kph",
        "km/h",
        "km/h",
        "The wheelset rotates too slowly",
        (
            "During eligible moving brake application, the target axle retains "
            "positive rotation but its reported speed is below wagon speed. Bot"
            "h wheels share the axle's rotation."
        ),
        (
            "The bounded injection returns to baseline after its interval. It d"
            "oes not simulate contact forces or the resulting stopping distance"
            "."
        ),
    ),
    (
        "Locked axle",
        "Mechanical",
        "locked-axle-demo",
        "axle",
        "wheel_speed_kph",
        "speed_kph",
        "km/h",
        "km/h",
        "Valid zero rotation while moving",
        (
            "The target axle reports valid zero wheel speed and RPM while wagon"
            " speed exceeds the synthetic 5 km/h evidence threshold."
        ),
        (
            "The shared wheelset is affected. The signature persists after onse"
            "t but its evidence is conditional on wagon motion."
        ),
    ),
    (
        "Suspected wheel flat",
        "Mechanical",
        "wheel-flat-demo",
        "axle",
        "vibration_rms_g",
        "speed_kph",
        "g",
        "km/h",
        "An axle-level vibration signature",
        (
            "The selected axle has a speed-dependent vibration RMS uplift while"
            " moving. Its speed remains on the healthy baseline."
        ),
        (
            "RMS telemetry does not identify the left or right wheel or resolve"
            " high-frequency impacts. This scenario is suspected flat, not conf"
            "irmed damage."
        ),
    ),
    (
        "Pressure transducer failure",
        "Sensor",
        "pressure-transducer-demo",
        "brakes",
        "brake_cylinder_pressure_bar",
        "brake_pipe_pressure_bar",
        "bar",
        "bar",
        "A pressure measurement becomes unavailable",
        (
            "This example fails bogie 2 BCP. The scenario API also supports sha"
            "red BPP, AR and SR, and either bogie's BCP."
        ),
        (
            "An invalid code such as 255 is retained as quality metadata, never"
            " treated as 255 bar. The code is illustrative, not a universal dev"
            "ice standard."
        ),
    ),
    (
        "Brake release failure",
        "Pneumatic",
        "brake-release-demo",
        "brakes",
        "brake_cylinder_pressure_bar",
        "brake_pipe_pressure_bar",
        "bar",
        "bar",
        "Release demanded; pressure remains",
        (
            "After an apply-to-release transition, BPP follows its recovered ba"
            "seline but one bogie's BCP remains elevated. Truth belongs to the "
            "wagon brake system."
        ),
        (
            "Detection must consider command context and shared BPP as well as "
            "bogie BCP. The fault is not labelled as a separate bogie failure."
        ),
    ),
    (
        "Undemanded brake application",
        "Pneumatic",
        "undemanded-brake-demo",
        "brakes",
        "brake_cylinder_pressure_bar",
        "brake_pipe_pressure_bar",
        "bar",
        "bar",
        "Braking evidence without an apply demand",
        (
            "During release demand, shared BPP falls unexpectedly and both bogi"
            "e BCP readings rise. The label belongs to the overall brake system"
            "."
        ),
        (
            "These are synthetic pressure signatures; the planned journey speed"
            " is preserved rather than re-simulated under the braking fault."
        ),
    ),
    (
        "Premature battery depletion",
        "Power",
        "battery-depletion-demo",
        "battery",
        "battery_voltage_v",
        "controller_supply_voltage_v",
        "V",
        "V",
        "Depletion, silence and possible recharge",
        (
            "Additional discharge applies in battery mode. At the simulated 3.0"
            " V cutoff, reports stop; generator charging above 3.1 V can permit"
            " restart."
        ),
        (
            "This demo deliberately accelerates extra discharge to 18 V/hour. T"
            "he 3.0–4.2 V scale is cell-equivalent, distinct from the controlle"
            "r rail; this is not a 5–7-day endurance result."
        ),
    ),
    (
        "Controller supply failure",
        "Power / reporting",
        "controller-persistent-demo",
        "controller",
        "controller_supply_voltage_v",
        "battery_voltage_v",
        "V",
        "V",
        "Healthy upstream power; an unavailable controller",
        (
            "Persistent mode sags then stops reporting. Bounded mode stops abru"
            "ptly and later returns with reset and uptime evidence. Both are on"
            "e anomaly type."
        ),
        (
            "The simulator knows the cause. In practice, the back office sees l"
            "ast observations and missed reports; silence alone does not identi"
            "fy a controller or communications failure."
        ),
    ),
]


def signal(event, scenario, name):
    if event is None:
        return None
    if name.startswith("controller_"):
        return getattr(event.controller, name.removeprefix("controller_"))
    if hasattr(event, name):
        return getattr(event, name)
    bogie_id = scenario.target.bogie_id or 1
    bogie = next(b for b in event.bogies if b.bogie_id == bogie_id)
    if hasattr(bogie, name):
        return getattr(bogie, name)
    axle = next(
        a
        for a in bogie.axles
        if a.axle_position == (scenario.target.axle_position or "outer")
    )
    if hasattr(axle, name):
        return getattr(axle, name)
    wheel = next(
        w for w in axle.wheels if w.wheel_side == (scenario.target.wheel_side or "left")
    )
    return getattr(wheel, name)


def main():
    assets = generate_fleet_assets(1, 42)
    asset = assets[0]
    journey = create_random_journey_plan(42, service_date=START.date())
    healthy = generate_healthy_journey_fleet(assets, START, journey, 10)
    cases = []
    feature_examples = []
    for number, spec in enumerate(SPECS, 1):
        (
            title,
            category,
            profile,
            component,
            primary,
            secondary,
            unit1,
            unit2,
            headline,
            explanation,
            limit,
        ) = spec
        if number <= 3:
            factory = (
                _build_bearing_demo_scenario,
                _build_brake_leak_demo_scenario,
                _build_sensor_drift_demo_scenario,
            )[number - 1]
            scenario = factory(asset.asset_id, START, journey.duration_seconds)
        else:
            scenario = build_demo_scenario(profile, healthy.events)
        variants = [scenario]
        if number == 12:
            variants.append(
                build_demo_scenario("controller-bounded-demo", healthy.events)
            )
        modes = []
        for current in variants:
            injected = inject_fleet_anomaly_scenarios(healthy, (current,))
            observed = {e.event_time: e for e in injected.events}
            left = max(START, current.start_time - timedelta(minutes=3))
            horizon = (
                current.recovery_time
                if current.outage_mode == "bounded"
                else current.end_time
            )
            right = min(
                START + timedelta(seconds=journey.duration_seconds),
                horizon + timedelta(minutes=6),
            )
            if number == 11:
                recovered = [
                    o.end_time_exclusive for o in injected.outages if o.recovered
                ]
                if recovered:
                    right = min(
                        START + timedelta(seconds=journey.duration_seconds),
                        max(recovered) + timedelta(minutes=5),
                    )
            baseline = [e for e in healthy.events if left <= e.event_time <= right]
            trace = []
            for e in baseline:
                after = observed.get(e.event_time)
                trace.append(
                    {
                        "seconds": int((e.event_time - START).total_seconds()),
                        "baseline": [
                            signal(e, current, primary),
                            signal(e, current, secondary),
                        ],
                        "observed": [
                            signal(after, current, primary),
                            signal(after, current, secondary),
                        ],
                        "speed": e.speed_kph,
                        "demand": e.brake_demand,
                        "state": e.operating_state,
                        "reported": after is not None,
                    }
                )
            mode = "bounded" if current.outage_mode == "bounded" else "persistent"
            modes.append(
                {
                    "mode": mode,
                    "scenario": serialise_scenario(current),
                    "trace": trace,
                    "missing_reports": len(injected.missing_reports),
                    "outages": [o.model_dump(mode="json") for o in injected.outages],
                }
            )
            if number in (1, 4, 8, 12) and mode != "bounded":
                moment = current.end_time + timedelta(minutes=2)
                moment = moment.replace(second=0, microsecond=0)
                records = tuple(
                    e
                    for e in injected.events
                    if moment <= e.event_time < moment + timedelta(minutes=1)
                )
                rows = aggregate_components(
                    records,
                    asset=asset,
                    journey_id=journey.journey_id,
                    route_id=journey.route.route_id,
                    split="train",
                    window_start=moment,
                    sampling_interval_seconds=10,
                )
                raw = [
                    {
                        "time": e.event_time.isoformat(),
                        "components": [
                            {"identity": list(k), "values": v}
                            for k, v in flatten_event(e, asset).items()
                        ],
                    }
                    for e in records
                ]
                feature_examples.append(
                    {
                        "title": title,
                        "rows": [r.model_dump(mode="json") for r in rows],
                        "raw": raw,
                    }
                )
        cases.append(
            {
                "number": number,
                "title": title,
                "category": category,
                "profile": profile,
                "component": component,
                "signals": [primary, secondary],
                "units": [unit1, unit2],
                "headline": headline,
                "explanation": explanation,
                "limit": limit,
                "modes": modes,
            }
        )
    healthy_records = []
    for e in healthy.events:
        healthy_records.append(
            {
                "seconds": int((e.event_time - START).total_seconds()),
                "latitude": e.latitude,
                "longitude": e.longitude,
                "speed": e.speed_kph,
                "bpp": e.brake_pipe_pressure_bar,
                "bcp": e.bogies[0].brake_cylinder_pressure_bar,
                "battery": e.battery_voltage_v,
                "controller": e.controller.supply_voltage_v,
                "temp": e.bogies[0].axles[0].wheels[0].bearing_temp_c,
                "vibration": e.bogies[0].axles[0].vibration_rms_g,
                "state": e.operating_state,
                "phase": e.journey_phase,
                "demand": e.brake_demand,
                "source": e.power_source,
            }
        )
    first_minute = tuple(
        e
        for e in healthy.events
        if START <= e.event_time < START + timedelta(minutes=1)
    )
    rows = aggregate_components(
        first_minute,
        asset=asset,
        journey_id=journey.journey_id,
        route_id=journey.route.route_id,
        split="train",
        window_start=START,
        sampling_interval_seconds=10,
    )
    feature_examples.insert(
        0,
        {
            "title": "Healthy minute",
            "rows": [r.model_dump(mode="json") for r in rows],
            "raw": [
                {
                    "time": e.event_time.isoformat(),
                    "components": [
                        {"identity": list(k), "values": v}
                        for k, v in flatten_event(e, asset).items()
                    ],
                }
                for e in first_minute
            ],
        },
    )
    cohorts = {}
    for seed in (42, 43):
        config = PortfolioConfig(
            seed=seed, start_time=START, sampling_interval_seconds=10
        )
        cohorts[str(seed)] = [
            {
                "asset_id": a.asset.asset_id,
                "split": a.split,
                "variant": a.variant,
                "route": plan_journey(a, config).route.route_id,
                "journey_seed": a.journey_seed,
            }
            for a in plan_assignments(config)
        ]
    docs = []
    for file in sorted((ROOT / "docs").glob("*.md")):
        docs.append(
            {
                "path": f"docs/{file.name}",
                "title": file.stem.replace("_", " ").title(),
                "text": file.read_text(encoding="utf-8"),
            }
        )
    docs.insert(
        0,
        {
            "path": "README.md",
            "title": "Repository overview",
            "text": (ROOT / "README.md").read_text(encoding="utf-8"),
        },
    )
    code = [
        {"path": str(p.relative_to(ROOT)), "text": p.read_text()}
        for p in sorted((ROOT / "src/fleetguard").rglob("*.py"))
    ]
    data = {
        "schema": "3.2",
        "feature_schema": "2.0",
        "seed": 42,
        "start": START.isoformat(),
        "journey": {
            "origin": journey.origin,
            "destination": journey.destination,
            "duration_minutes": journey.duration_minutes,
            "route_id": journey.route.route_id,
            "points": [
                {"name": p.name, "latitude": p.latitude, "longitude": p.longitude}
                for p in journey.route.points
            ],
        },
        "asset": asset.model_dump(mode="json"),
        "healthy": healthy_records,
        "cases": cases,
        "features": feature_examples,
        "numeric": NUMERIC,
        "categorical": CATEGORICAL,
        "cohorts": cohorts,
        "documents": docs,
        "code": code,
    }
    folder = ROOT / "atlas"
    (folder / "assets/data.js").write_text(
        "window.FG_DATA="
        + json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
        + ";\n",
        encoding="utf-8",
    )
    # Atlas animations are native SVG/HTML; independent root assets stay separate.
    for file in (folder / "assets").glob("*.gif"):
        file.unlink()
    for file in (folder / "_site/assets").glob("*.gif"):
        file.unlink()
    shutil.copy2(
        ROOT / "assets/fleetguard-logo.svg", folder / "assets/fleetguard-logo.svg"
    )
    body = (folder / "_body.html").read_text()
    document = (
        (
            '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta n'
            'ame="viewport" content="width=device-width,initial-scale=1"><title'
            '>FleetGuard AI · Engineering Atlas</title><link rel="stylesheet" h'
            'ref="assets/atlas.css"></head><body>'
        )
        + body
        + (
            '<script src="assets/data.js"></script><script src="assets/atlas.js'
            '"></script></body></html>'
        )
    )
    (folder / "index.html").write_text(document)
    (folder / "index.qmd").write_text(
        (
            '---\ntitle: "FleetGuard AI — Engineering Atlas"\nformat:\n  html:\n   '
            " theme: none\n    css: assets/atlas.css\n    toc: false\n    include-"
            "after-body: _scripts.html\npage-layout: custom\ntitle-block-style: n"
            "one\n---\n\n```{=html}\n"
        )
        + body
        + "\n```\n"
    )
    (folder / "_scripts.html").write_text(
        '<script src="assets/data.js"></script><script src="assets/atlas.js"></script>\n'
    )
    (folder / "_quarto.yml").write_text(
        "project:\n  type: website\n  render: [index.qmd]\n"
        "  output-dir: _site\n  resources:\n    - as"
        'sets/\nwebsite:\n  title: "FleetGuard AI Engineering Atlas"\n'
    )
    site = folder / "_site"
    site.mkdir(exist_ok=True)
    shutil.copy2(folder / "index.html", site / "index.html")
    shutil.copytree(folder / "assets", site / "assets", dirs_exist_ok=True)
    print(
        f"Atlas built: {len(cases)} scenarios, {len(docs)} documents, "
        f"{len(code)} source files. Open atlas/_site/index.html"
    )


if __name__ == "__main__":
    main()
