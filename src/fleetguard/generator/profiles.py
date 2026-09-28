"""Reproducible demonstration scenarios selected from the healthy operating plan."""

from datetime import timedelta

from fleetguard.contracts import AnomalySeverity, AnomalyType
from fleetguard.generator.anomalies import AnomalyScenario, ComponentTarget
from fleetguard.generator.extended_anomalies import AXLE_TYPES

NEW_PROFILES = {
    "axle-generator-demo": AnomalyType.AXLE_SPEED_GENERATOR_FAILURE,
    "wheel-slide-demo": AnomalyType.WHEEL_SLIDE,
    "locked-axle-demo": AnomalyType.LOCKED_AXLE,
    "wheel-flat-demo": AnomalyType.SUSPECTED_WHEEL_FLAT,
    "pressure-transducer-demo": AnomalyType.PRESSURE_TRANSDUCER_FAILURE,
    "brake-release-demo": AnomalyType.BRAKE_RELEASE_FAILURE,
    "undemanded-brake-demo": AnomalyType.UNDEMANDED_BRAKE_APPLICATION,
    "battery-depletion-demo": AnomalyType.PREMATURE_BATTERY_DEPLETION,
    "controller-persistent-demo": AnomalyType.CONTROLLER_SUPPLY_FAILURE,
    "controller-bounded-demo": AnomalyType.CONTROLLER_SUPPLY_FAILURE,
}


def build_demo_scenario(profile, events) -> AnomalyScenario:
    """Use asset one; leave all other assets as matched healthy controls."""
    kind = NEW_PROFILES[profile]
    asset_id = events[0].asset_id
    records = [e for e in events if e.asset_id == asset_id]
    moving = next(e for e in records if e.speed_kph > 10 and e.brake_demand == "release")
    start = moving.event_time
    end = start + timedelta(minutes=5)
    target = ComponentTarget(asset_id)
    kwargs = {}
    if kind in AXLE_TYPES:
        target = ComponentTarget(asset_id, bogie_id=1, axle_position="outer")
    if kind == AnomalyType.WHEEL_SLIDE:
        braking = next(e for e in records if e.brake_demand == "apply" and e.speed_kph > 5)
        start = braking.event_time
        end = start + timedelta(minutes=2)
    elif kind == AnomalyType.BRAKE_RELEASE_FAILURE:
        release = next(
            b
            for a, b in zip(records, records[1:], strict=False)
            if a.brake_demand == "apply" and b.brake_demand == "release"
        )
        start = release.event_time
        end = start + timedelta(minutes=5)
        target = ComponentTarget(asset_id, bogie_id=1)
    elif kind == AnomalyType.PRESSURE_TRANSDUCER_FAILURE:
        target = ComponentTarget(asset_id, bogie_id=2, signal_name="brake_cylinder_pressure_bar")
        kwargs["failure_encoding"] = "invalid"
    elif kind == AnomalyType.PREMATURE_BATTERY_DEPLETION:
        # Accelerated depletion makes a short smoke test observable, not realistic battery life.
        stationary = next(e for e in records if e.speed_kph == 0)
        start = stationary.event_time
        end = start + timedelta(minutes=5)
        kwargs["battery_extra_drain_v_per_hour"] = 18.0
    elif profile == "controller-bounded-demo":
        kwargs["outage_mode"] = "bounded"
        kwargs["recovery_time"] = end + timedelta(minutes=5)
    return AnomalyScenario(
        scenario_id=f"FG-ANO-{profile.upper()}",
        anomaly_type=kind,
        target=target,
        start_time=start,
        end_time=end,
        peak_severity=AnomalySeverity.HIGH,
        **kwargs,
    )
