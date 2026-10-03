from datetime import datetime, timedelta
from statistics import mean
from typing import Literal

from fleetguard.contracts.models import TelemetryEvent
from fleetguard.features.models import WindowFeatures


def aggregate_window(
    events: tuple[TelemetryEvent, ...],
    *,
    asset_id: str,
    journey_id: str,
    split: Literal["train", "validation", "test"],
    window_start: datetime,
    sampling_interval_seconds: Literal[1, 10, 60],
) -> WindowFeatures:
    """Summarise reports inside one half-open, one-minute window."""

    window_end = window_start + timedelta(seconds=60)

    # Validate the window configuration even when no reports arrived.
    empty_window = WindowFeatures(
        asset_id=asset_id,
        journey_id=journey_id,
        split=split,
        window_start=window_start,
        window_end=window_end,
        sampling_interval_seconds=sampling_interval_seconds,
        expected_reports=60 // sampling_interval_seconds,
        received_reports=0,
        report_completeness=0.0,
    )

    timestamps: set[datetime] = set()
    event_ids = set()

    for event in events:
        if event.asset_id != asset_id or event.journey_id != journey_id:
            raise ValueError("reports must belong to the requested wagon and journey")

        if event.sampling_interval_seconds != sampling_interval_seconds:
            raise ValueError("report sampling interval does not match the window")

        if not window_start <= event.event_time < window_end:
            raise ValueError("report timestamp falls outside the window")

        elapsed = (event.event_time - window_start).total_seconds()

        if elapsed % sampling_interval_seconds != 0:
            raise ValueError("report timestamp is off the sampling grid")

        if event.event_time in timestamps or event.event_id in event_ids:
            raise ValueError("duplicate report")

        timestamps.add(event.event_time)
        event_ids.add(event.event_id)

    if not events:
        return empty_window

    bearing_differences: list[float] = []
    vibration_values: list[float] = []
    speed_differences: list[float] = []

    bpp_values: list[float] = []
    bcp_values: list[float] = []
    ar_values: list[float] = []
    sr_values: list[float] = []

    unavailable_axle_speeds = 0
    unavailable_pressures = 0

    for event in events:
        shared_pressures = (
            (event.brake_pipe_pressure_bar, bpp_values),
            (event.auxiliary_reservoir_pressure_bar, ar_values),
            (event.secondary_reservoir_pressure_bar, sr_values),
        )

        for value, destination in shared_pressures:
            if value is None:
                unavailable_pressures += 1
            else:
                destination.append(value)

        for bogie in event.bogies:
            if bogie.brake_cylinder_pressure_bar is None:
                unavailable_pressures += 1
            else:
                bcp_values.append(bogie.brake_cylinder_pressure_bar)

            for axle in bogie.axles:
                vibration_values.append(axle.vibration_rms_g)

                if axle.wheel_speed_kph is None:
                    unavailable_axle_speeds += 1
                else:
                    speed_differences.append(
                        abs(event.speed_kph - axle.wheel_speed_kph)
                    )

                for wheel in axle.wheels:
                    bearing_differences.append(
                        wheel.bearing_temp_c - event.ambient_temp_c
                    )

    received = len(events)

    return WindowFeatures(
        asset_id=asset_id,
        journey_id=journey_id,
        split=split,
        window_start=window_start,
        window_end=window_end,
        sampling_interval_seconds=sampling_interval_seconds,
        expected_reports=empty_window.expected_reports,
        received_reports=received,
        report_completeness=received / empty_window.expected_reports,
        speed_mean_kph=mean(event.speed_kph for event in events),
        bearing_temp_above_ambient_max_c=max(bearing_differences),
        vibration_max_g=max(vibration_values),
        axle_speed_difference_max_kph=(
            max(speed_differences) if speed_differences else None
        ),
        brake_pipe_pressure_min_bar=min(bpp_values) if bpp_values else None,
        brake_cylinder_pressure_max_bar=max(bcp_values) if bcp_values else None,
        auxiliary_reservoir_pressure_min_bar=(min(ar_values) if ar_values else None),
        secondary_reservoir_pressure_min_bar=(min(sr_values) if sr_values else None),
        battery_voltage_min_v=min(event.battery_voltage_v for event in events),
        controller_supply_voltage_min_v=min(
            event.controller.supply_voltage_v for event in events
        ),
        unavailable_axle_speed_fraction=unavailable_axle_speeds / (received * 4),
        unavailable_pressure_fraction=unavailable_pressures / (received * 5),
    )
