"""Synthetic fault signatures, not a coupled train-dynamics simulator.

One scenario per asset per batch keeps the existing single-label truth unambiguous.
Outages remove observations; their truth belongs to the expected-report timeline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from fleetguard.contracts import (
    AnomalySeverity,
    AnomalyTruth,
    AnomalyType,
    ControllerHealthStatus,
    MissingReportTruth,
    OutageTruth,
    PowerSource,
    SignalQuality,
    TelemetryEvent,
)

if TYPE_CHECKING:
    from fleetguard.generator.anomalies import AnomalyScenario, InjectedBatch

AXLE_TYPES = {
    AnomalyType.AXLE_SPEED_GENERATOR_FAILURE,
    AnomalyType.WHEEL_SLIDE,
    AnomalyType.LOCKED_AXLE,
    AnomalyType.SUSPECTED_WHEEL_FLAT,
}
PRESSURES = {
    "brake_pipe_pressure_bar",
    "auxiliary_reservoir_pressure_bar",
    "secondary_reservoir_pressure_bar",
    "brake_cylinder_pressure_bar",
}


def validate_scenario(s: AnomalyScenario) -> None:
    if s.anomaly_type == AnomalyType.NONE or s.peak_severity == AnomalySeverity.NONE:
        raise ValueError("scenario requires an anomaly type and non-none severity")
    if not s.scenario_id.strip():
        raise ValueError("scenario_id must not be empty")
    wagon_types = {
        AnomalyType.PREMATURE_BATTERY_DEPLETION,
        AnomalyType.CONTROLLER_SUPPLY_FAILURE,
        AnomalyType.UNDEMANDED_BRAKE_APPLICATION,
    }
    if s.anomaly_type in wagon_types and any(
        (s.target.bogie_id, s.target.axle_position, s.target.wheel_side)
    ):
        raise ValueError("this scenario requires wagon scope")
    if s.anomaly_type == AnomalyType.BRAKE_RELEASE_FAILURE and any(
        (s.target.axle_position, s.target.wheel_side)
    ):
        raise ValueError(
            "brake release failure supports a bogie effect, not axle or wheel targeting"
        )
    if s.target.bogie_id not in (None, 1, 2):
        raise ValueError("bogie_id must be 1 or 2")
    if s.target.axle_position not in (None, "inner", "outer"):
        raise ValueError("invalid axle_position")
    if s.target.wheel_side not in (None, "left", "right"):
        raise ValueError("invalid wheel_side")
    if s.anomaly_type in AXLE_TYPES:
        if s.target.bogie_id is None or s.target.axle_position is None:
            raise ValueError("axle scenario requires bogie and axle targeting")
        if s.target.wheel_side is not None:
            raise ValueError("axle signatures do not identify an individual wheel")
    if s.anomaly_type == AnomalyType.PRESSURE_TRANSDUCER_FAILURE:
        if s.target.signal_name not in PRESSURES:
            raise ValueError("pressure transducer requires a pressure signal")
        bcp = s.target.signal_name == "brake_cylinder_pressure_bar"
        if bcp != (s.target.bogie_id is not None):
            raise ValueError("BCP needs a bogie; shared pressures use wagon scope")
        if s.target.axle_position is not None or s.target.wheel_side is not None:
            raise ValueError("pressure target cannot be an axle or wheel")
    if s.failure_encoding not in ("missing", "invalid"):
        raise ValueError("failure_encoding must be missing or invalid")
    if s.outage_mode not in ("persistent", "bounded"):
        raise ValueError("outage_mode must be persistent or bounded")
    if s.outage_mode == "bounded":
        if s.anomaly_type != AnomalyType.CONTROLLER_SUPPLY_FAILURE:
            raise ValueError("bounded outage mode applies only to controller supply failure")
        if s.recovery_time is None or s.recovery_time.utcoffset() is None:
            raise ValueError("bounded outage requires timezone-aware recovery_time")
        if s.recovery_time <= s.end_time:
            raise ValueError("recovery_time must follow end_time")
    elif s.recovery_time is not None:
        raise ValueError("persistent outage cannot specify recovery_time")
    if not math.isfinite(s.battery_extra_drain_v_per_hour) or s.battery_extra_drain_v_per_hour <= 0:
        raise ValueError("battery extra drain must be finite and positive")


def _copy(model, **changes):
    """Unlike model_copy(update=...), validate every modified nested contract."""
    return type(model).model_validate({**model.model_dump(), **changes})


def _label(truth, s, event_time, component, signal, progress=None):
    return _copy(
        truth,
        is_anomaly=True,
        anomaly_type=s.anomaly_type,
        anomaly_severity=s.peak_severity,
        affected_component=component,
        affected_signal=signal,
        anomaly_start_time=s.start_time,
        anomaly_progress=round(s.progress_at(event_time) if progress is None else progress, 6),
    )


def _quality(s):
    return SignalQuality(
        status=s.failure_encoding, raw_value=255 if s.failure_encoding == "invalid" else None
    )


def _axle_fault(event, truth, s):
    kind = s.anomaly_type
    if kind == AnomalyType.WHEEL_SLIDE and (
        event.event_time >= s.end_time or event.brake_demand != "apply" or event.speed_kph <= 5
    ):
        return event, truth
    if kind in (AnomalyType.LOCKED_AXLE, AnomalyType.SUSPECTED_WHEEL_FLAT) and event.speed_kph <= 5:
        return event, truth
    strength = {
        AnomalySeverity.LOW: 0.25,
        AnomalySeverity.MEDIUM: 0.55,
        AnomalySeverity.HIGH: 0.85,
    }[s.peak_severity]
    bogies = []
    for bogie in event.bogies:
        axles = []
        for axle in bogie.axles:
            if bogie.bogie_id != s.target.bogie_id or axle.axle_position != s.target.axle_position:
                axles.append(axle)
                continue
            if kind == AnomalyType.AXLE_SPEED_GENERATOR_FAILURE:
                axle = _copy(
                    axle,
                    wheel_speed_kph=None,
                    rotational_speed_rpm=None,
                    signal_quality={
                        "wheel_speed_kph": _quality(s),
                        "rotational_speed_rpm": _quality(s),
                    },
                )
            elif kind in (AnomalyType.WHEEL_SLIDE, AnomalyType.LOCKED_AXLE):
                ratio = 0 if kind == AnomalyType.LOCKED_AXLE else 1 - strength
                axle = _copy(
                    axle,
                    wheel_speed_kph=round(axle.wheel_speed_kph * ratio, 3),
                    rotational_speed_rpm=round(axle.rotational_speed_rpm * ratio, 3),
                )
            else:
                # RMS uplift is an interval summary, not a sampled wheel-impact waveform.
                uplift = strength * min(event.speed_kph / 40, 2)
                axle = _copy(axle, vibration_rms_g=round(min(10, axle.vibration_rms_g + uplift), 4))
            axles.append(axle)
        bogies.append(_copy(bogie, axles=tuple(axles)))
    updates = {"bogies": tuple(bogies)}
    if kind == AnomalyType.AXLE_SPEED_GENERATOR_FAILURE:
        updates["available_axle_generators"] = 3
        # Simplified linear charging contribution; the remaining three keep the rail alive.
    event = _copy(event, **updates)
    component = f"bogie:{s.target.bogie_id}/axle:{s.target.axle_position}"
    signal = "vibration_rms_g" if kind == AnomalyType.SUSPECTED_WHEEL_FLAT else "wheel_speed_kph"
    return event, _label(truth, s, event.event_time, component, signal, 1.0)


def _pressure_fault(event, truth, s):
    signal = s.target.signal_name
    if s.target.bogie_id is None:
        event = _copy(event, **{signal: None}, signal_quality={signal: _quality(s)})
        component = f"wagon:sensor:{signal}"
    else:
        event = _copy(
            event,
            bogies=tuple(
                _copy(b, **{signal: None}, signal_quality={signal: _quality(s)})
                if b.bogie_id == s.target.bogie_id
                else b
                for b in event.bogies
            ),
        )
        component = f"bogie:{s.target.bogie_id}/sensor:{signal}"
    return event, _label(truth, s, event.event_time, component, signal, 1.0)


@dataclass
class _State:
    previous_time: datetime | None = None
    previous_demand: str = "release"
    release_failed: bool = False
    voltage: float | None = None
    last_baseline_voltage: float | None = None
    offline: bool = False
    restart_time: datetime | None = None
    resets: int = 0


def _brake_fault(event, truth, s, state):
    if event.brake_demand != "release":
        return event, truth
    if s.anomaly_type == AnomalyType.BRAKE_RELEASE_FAILURE:
        state.release_failed |= state.previous_demand == "apply"
        if not state.release_failed:
            return event, truth
    pressure = {AnomalySeverity.LOW: 0.8, AnomalySeverity.MEDIUM: 1.6, AnomalySeverity.HIGH: 2.8}[
        s.peak_severity
    ]
    # Physical effect can be local, but diagnostic/truth scope is the wagon brake system.
    affected = s.target.bogie_id or 1
    bogies = tuple(
        _copy(b, brake_cylinder_pressure_bar=pressure) if b.bogie_id == affected else b
        for b in event.bogies
    )
    updates = {"bogies": bogies}
    if s.anomaly_type == AnomalyType.UNDEMANDED_BRAKE_APPLICATION:
        updates["brake_pipe_pressure_bar"] = round(max(0, event.brake_pipe_pressure_bar - 1.5), 3)
        updates["bogies"] = tuple(
            _copy(b, brake_cylinder_pressure_bar=pressure) for b in event.bogies
        )
    event = _copy(event, **updates)
    return event, _label(
        truth, s, event.event_time, "wagon:brake_system", "brake_cylinder_pressure_bar", 1.0
    )


def _power_fault(event, truth, s, state, elapsed):
    offline = False
    if s.anomaly_type == AnomalyType.CONTROLLER_SUPPLY_FAILURE:
        if s.outage_mode == "bounded":
            offline = s.start_time <= event.event_time < s.recovery_time
        else:
            offline = event.event_time >= s.end_time
            if not offline:
                rail = event.controller.supply_voltage_v * (
                    1 - 0.7 * s.progress_at(event.event_time)
                )
                event = _copy(
                    event,
                    controller=_copy(
                        event.controller,
                        supply_voltage_v=round(rail, 3),
                        health_status=ControllerHealthStatus.DEGRADED,
                    ),
                )
        if not offline and (s.outage_mode == "persistent" or event.event_time < s.recovery_time):
            truth = _label(
                truth, s, event.event_time, "wagon:controller", "controller_supply_voltage_v"
            )
    else:
        if state.voltage is None:
            state.voltage = event.battery_voltage_v
        if event.power_source == PowerSource.BATTERY:
            healthy_loss = (
                0
                if state.last_baseline_voltage is None
                else max(0, state.last_baseline_voltage - event.battery_voltage_v)
            )
            state.voltage = max(
                3.0,
                state.voltage - healthy_loss - elapsed * s.battery_extra_drain_v_per_hour / 3600,
            )
        else:
            state.voltage = min(4.2, state.voltage + elapsed * 0.18 / 3600)
        state.last_baseline_voltage = event.battery_voltage_v
        offline = state.voltage <= (3.1 if state.offline else 3.0)
        original_voltage = event.battery_voltage_v
        event = _copy(event, battery_voltage_v=round(state.voltage, 4))
        truth = (
            _label(
                truth,
                s,
                event.event_time,
                "wagon:battery",
                "battery_voltage_v",
                min(1, max(0, (4.2 - state.voltage) / 1.2)),
            )
            if event.battery_voltage_v < original_voltage
            else truth
        )
    if offline:
        state.offline = True
        return None, truth
    if state.offline:
        state.offline = False
        state.restart_time = event.event_time
        state.resets += 1
    if state.restart_time is not None:
        event = _copy(
            event,
            controller=_copy(
                event.controller,
                uptime_seconds=int((event.event_time - state.restart_time).total_seconds()),
                reset_count=event.controller.reset_count + state.resets,
            ),
        )
    return event, truth


def inject_batch(events, truth, scenarios) -> InjectedBatch:
    from fleetguard.generator.anomalies import (
        InjectedBatch,
        inject_bearing_degradation,
        inject_bearing_temperature_sensor_drift,
        inject_brake_pressure_leak,
    )

    if len({s.scenario_id for s in scenarios}) != len(scenarios):
        raise ValueError("scenario IDs must be unique")
    if len({s.target.asset_id for s in scenarios}) != len(scenarios):
        raise ValueError("one scenario per asset per batch; multi-label overlap is not supported")
    by_asset = {s.target.asset_id: s for s in scenarios}
    if not set(by_asset) <= {e.asset_id for e in events}:
        raise ValueError("scenario target asset is absent")
    if any(t.is_anomaly for t in truth):
        raise ValueError("injection requires healthy baseline truth")
    if len({e.event_id for e in events}) != len(events):
        raise ValueError("event IDs must be unique")
    states = {asset: _State() for asset in by_asset}
    output, labels, missing = [], [], []
    legacy = {
        AnomalyType.BEARING_DEGRADATION: inject_bearing_degradation,
        AnomalyType.BRAKE_PRESSURE_LEAK: inject_brake_pressure_leak,
        AnomalyType.SENSOR_FAULT: inject_bearing_temperature_sensor_drift,
    }
    last_time = {}
    for event, label in zip(events, truth, strict=True):
        if event.event_id != label.event_id or event.asset_id != label.asset_id:
            raise ValueError("event and truth identities must match")
        if event.asset_id in last_time and event.event_time <= last_time[event.asset_id]:
            raise ValueError("events must be chronological within each asset")
        last_time[event.asset_id] = event.event_time
        s = by_asset.get(event.asset_id)
        original = event
        if s:
            state = states[event.asset_id]
            elapsed = (
                0
                if state.previous_time is None
                else max(
                    0, (event.event_time - max(state.previous_time, s.start_time)).total_seconds()
                )
            )
            if event.event_time >= s.start_time:
                if s.anomaly_type in legacy:
                    event, label = legacy[s.anomaly_type](event, label, s)
                elif s.anomaly_type in AXLE_TYPES:
                    event, label = _axle_fault(event, label, s)
                    if s.anomaly_type == AnomalyType.AXLE_SPEED_GENERATOR_FAILURE:
                        if state.voltage is None:
                            state.voltage = original.battery_voltage_v
                        elif event.power_source == PowerSource.AXLE_GENERATORS:
                            state.voltage = min(4.2, state.voltage + elapsed * 0.18 * 0.75 / 3600)
                        else:
                            # Preserve the healthy stationary-discharge increments.
                            state.voltage = max(
                                3,
                                state.voltage
                                + original.battery_voltage_v
                                - state.last_baseline_voltage,
                            )
                        event = _copy(event, battery_voltage_v=round(state.voltage, 4))
                        state.last_baseline_voltage = original.battery_voltage_v
                elif s.anomaly_type == AnomalyType.PRESSURE_TRANSDUCER_FAILURE:
                    event, label = _pressure_fault(event, label, s)
                elif s.anomaly_type in (
                    AnomalyType.BRAKE_RELEASE_FAILURE,
                    AnomalyType.UNDEMANDED_BRAKE_APPLICATION,
                ):
                    event, label = _brake_fault(event, label, s, state)
                elif s.anomaly_type in (
                    AnomalyType.PREMATURE_BATTERY_DEPLETION,
                    AnomalyType.CONTROLLER_SUPPLY_FAILURE,
                ):
                    event, label = _power_fault(event, label, s, state, elapsed)
                else:
                    raise ValueError(f"unsupported anomaly type: {s.anomaly_type}")
            state.previous_time = original.event_time
            state.previous_demand = original.brake_demand
        if event is None:
            missing.append(
                MissingReportTruth(
                    event_id=original.event_id,
                    asset_id=original.asset_id,
                    expected_at=original.event_time,
                    scenario_id=s.scenario_id,
                    anomaly_type=s.anomaly_type,
                    anomaly_severity=s.peak_severity,
                )
            )
        else:
            # Validate legacy copies too, so null/quality rules cannot be bypassed.
            output.append(TelemetryEvent.model_validate(event.model_dump()))
            labels.append(AnomalyTruth.model_validate(label.model_dump()))
    outages = _outage_intervals(events, output, missing)
    return InjectedBatch(tuple(output), tuple(labels), tuple(missing), tuple(outages))


def _outage_intervals(expected, observed, missing):
    missing_by_id = {m.event_id: m for m in missing}
    observed_ids = {e.event_id for e in observed}
    groups = {}
    for event in expected:
        groups.setdefault(event.asset_id, []).append(event)
    result = []
    for asset, records in groups.items():
        active = []
        for event in records:
            if event.event_id in missing_by_id:
                active.append(missing_by_id[event.event_id])
            elif active and event.event_id in observed_ids:
                result.append(
                    OutageTruth(
                        asset_id=asset,
                        scenario_id=active[0].scenario_id,
                        anomaly_type=active[0].anomaly_type,
                        start_time=active[0].expected_at,
                        end_time_exclusive=event.event_time,
                        recovered=True,
                        missing_reports=len(active),
                    )
                )
                active = []
        if active:
            result.append(
                OutageTruth(
                    asset_id=asset,
                    scenario_id=active[0].scenario_id,
                    anomaly_type=active[0].anomaly_type,
                    start_time=active[0].expected_at,
                    end_time_exclusive=records[-1].event_time
                    + timedelta(seconds=records[-1].sampling_interval_seconds),
                    recovered=False,
                    missing_reports=len(active),
                )
            )
    return result
