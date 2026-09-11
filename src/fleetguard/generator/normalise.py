from __future__ import annotations

from dataclasses import dataclass

from fleetguard.contracts import (
    AssetMetadata,
    AxleObservation,
    BogieObservation,
    TelemetryEvent,
    WheelObservation,
)


@dataclass(frozen=True)
class NormalisedObservations:
    bogies: tuple[BogieObservation, ...]
    axles: tuple[AxleObservation, ...]
    wheels: tuple[WheelObservation, ...]


def normalise_event(event: TelemetryEvent, asset: AssetMetadata) -> NormalisedObservations:
    if event.asset_id != asset.asset_id:
        raise ValueError("event and asset IDs must match")

    common = {
        "event_id": event.event_id,
        "event_time": event.event_time,
        "asset_id": event.asset_id,
        "journey_id": event.journey_id,
        "route_id": event.route_id,
    }
    bogie_rows: list[BogieObservation] = []
    axle_rows: list[AxleObservation] = []
    wheel_rows: list[WheelObservation] = []

    metadata_by_bogie = {bogie.bogie_id: bogie for bogie in asset.bogies}
    for bogie in event.bogies:
        bogie_rows.append(
            BogieObservation(
                **common,
                bogie_id=bogie.bogie_id,
                handbrake_equipped=bogie.handbrake_equipped,
                speed_kph=event.speed_kph,
                rail_condition=event.rail_condition,
                estimated_adhesion_coefficient=event.estimated_adhesion_coefficient,
                brake_pipe_pressure_bar=event.brake_pipe_pressure_bar,
                auxiliary_reservoir_pressure_bar=event.auxiliary_reservoir_pressure_bar,
                secondary_reservoir_pressure_bar=event.secondary_reservoir_pressure_bar,
                brake_cylinder_pressure_bar=bogie.brake_cylinder_pressure_bar,
            )
        )
        axle_metadata = {
            axle.axle_position: axle for axle in metadata_by_bogie[bogie.bogie_id].axles
        }
        for axle in bogie.axles:
            axle_rows.append(
                AxleObservation(
                    **common,
                    bogie_id=bogie.bogie_id,
                    axle_position=axle.axle_position,
                    rotational_speed_rpm=axle.rotational_speed_rpm,
                    wheel_speed_kph=axle.wheel_speed_kph,
                    axle_load_tonnes=axle.axle_load_tonnes,
                    vibration_rms_g=axle.vibration_rms_g,
                )
            )
            diameters = {
                wheel.wheel_side: wheel.diameter_mm
                for wheel in axle_metadata[axle.axle_position].wheels
            }
            for wheel in axle.wheels:
                wheel_rows.append(
                    WheelObservation(
                        **common,
                        bogie_id=bogie.bogie_id,
                        axle_position=axle.axle_position,
                        wheel_side=wheel.wheel_side,
                        diameter_mm=diameters[wheel.wheel_side],
                        bearing_temp_c=wheel.bearing_temp_c,
                    )
                )

    return NormalisedObservations(
        bogies=tuple(bogie_rows),
        axles=tuple(axle_rows),
        wheels=tuple(wheel_rows),
    )
