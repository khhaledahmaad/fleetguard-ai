from __future__ import annotations

import hashlib
import json
import math
import random
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, datetime
from functools import cached_property
from importlib.resources import files

from fleetguard.contracts import (
    STANDARD_SAMPLING_INTERVAL_SECONDS,
    JourneyMetadata,
    JourneyPhase,
    LoadState,
    OperatingState,
    TravelDirection,
)


@dataclass(frozen=True)
class RoutePoint:
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class RailRoute:
    route_id: str
    name: str
    points: tuple[RoutePoint, ...]
    intermediate_stop_indices: tuple[int, ...] = ()

    @cached_property
    def cumulative_km(self) -> tuple[float, ...]:
        distances = [0.0]
        for first, second in zip(self.points, self.points[1:], strict=False):
            distances.append(distances[-1] + _haversine_km(first, second))
        return tuple(distances)

    @property
    def distance_km(self) -> float:
        return self.cumulative_km[-1]


@dataclass(frozen=True)
class JourneySegment:
    phase: JourneyPhase
    state: OperatingState
    duration_seconds: int
    start_progress: float
    end_progress: float
    start_speed_kph: float = 0.0
    end_speed_kph: float = 0.0


@dataclass(frozen=True)
class JourneyPlan:
    journey_id: str
    route: RailRoute
    segments: tuple[JourneySegment, ...]
    reverse: bool
    nominal_speed_kph: float
    load_state: LoadState
    cargo_type: str

    @property
    def duration_seconds(self) -> int:
        return sum(segment.duration_seconds for segment in self.segments)

    @property
    def duration_minutes(self) -> int:
        return math.ceil(self.duration_seconds / 60)

    @property
    def travel_direction(self) -> TravelDirection:
        return TravelDirection.REVERSE if self.reverse else TravelDirection.FORWARD

    @property
    def origin(self) -> str:
        return self.route.points[-1 if self.reverse else 0].name

    @property
    def destination(self) -> str:
        return self.route.points[0 if self.reverse else -1].name


# Bundled Network Rail track-level geometry; no network calls during generation.
GEOMETRY_VERSION = "2.0"


def _load_routes() -> tuple[RailRoute, ...]:
    source = files("fleetguard.generator").joinpath("data/uk_rail_routes.geojson")
    payload = json.loads(source.read_text(encoding="utf-8"))
    result = []
    for feature in payload["features"]:
        props = feature["properties"]
        names = props["named_points"]
        points = tuple(
            RoutePoint(names.get(str(i), f"Track vertex {i}"), lat, lon)
            for i, (lon, lat) in enumerate(feature["geometry"]["coordinates"])
        )
        result.append(
            RailRoute(
                props["route_id"],
                props["origin"] + "–" + props["destination"],
                points,
                tuple(props["intermediate_stop_indices"]),
            )
        )
    return tuple(result)


(
    LONDON_AVONMOUTH_FREIGHT_ROUTE,
    AVONMOUTH_CARDIFF_FREIGHT_ROUTE,
    CARDIFF_SWANSEA_FREIGHT_ROUTE,
    LONDON_SWANSEA_FREIGHT_ROUTE,
) = DEFAULT_ROUTES = _load_routes()


def _haversine_km(first: RoutePoint, second: RoutePoint) -> float:
    radius_km = 6371.0088
    lat1, lat2 = math.radians(first.latitude), math.radians(second.latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(second.longitude - first.longitude)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(value))


def interpolate_route(
    route: RailRoute, progress: float, reverse: bool = False
) -> tuple[float, float]:
    progress = max(0.0, min(progress, 1.0))
    if reverse:
        progress = 1 - progress

    target = progress * route.distance_km
    index = min(max(0, bisect_right(route.cumulative_km, target) - 1), len(route.points) - 2)
    first, second = route.points[index : index + 2]
    length = route.cumulative_km[index + 1] - route.cumulative_km[index]
    local = (target - route.cumulative_km[index]) / length if length else 0.0
    return (
        first.latitude + local * (second.latitude - first.latitude),
        first.longitude + local * (second.longitude - first.longitude),
    )


def create_journey_plan(
    seed: int,
    route: RailRoute = LONDON_SWANSEA_FREIGHT_ROUTE,
    allow_reverse: bool = True,
    service_date: date = date(2026, 1, 1),
    journey_number: int | None = None,
) -> JourneyPlan:
    rng = random.Random(seed)
    reverse = allow_reverse and bool(rng.randrange(2))
    nominal_speed = rng.uniform(48, 62)
    stop_progresses = [
        route.cumulative_km[index] / route.distance_km for index in route.intermediate_stop_indices
    ]
    if reverse:
        stop_progresses = sorted(1 - progress for progress in stop_progresses)
    segments = [
        JourneySegment(
            JourneyPhase.ORIGIN_DWELL, OperatingState.STATIONARY, rng.randint(20, 45) * 60, 0.0, 0.0
        )
    ]
    boundaries = [0.0, *stop_progresses, 1.0]
    ramp_seconds = 120
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:], strict=False)):
        distance = (end - start) * route.distance_km
        # A trapezoid with two 120-second ramps. Round total running time upward
        # to whole minutes, then solve the cruise speed for the exact distance.
        duration = max(
            2 * ramp_seconds, math.ceil((distance * 3600 / nominal_speed + ramp_seconds) / 60) * 60
        )
        speed = distance * 3600 / (duration - ramp_seconds)
        ramp_progress = 0.5 * speed * ramp_seconds / 3600 / route.distance_km
        segments.append(
            JourneySegment(
                JourneyPhase.RUNNING,
                OperatingState.MOVING,
                ramp_seconds,
                start,
                start + ramp_progress,
                0,
                speed,
            )
        )
        if duration > 2 * ramp_seconds:
            segments.append(
                JourneySegment(
                    JourneyPhase.RUNNING,
                    OperatingState.MOVING,
                    duration - 2 * ramp_seconds,
                    start + ramp_progress,
                    end - ramp_progress,
                    speed,
                    speed,
                )
            )
        segments.append(
            JourneySegment(
                JourneyPhase.RUNNING,
                OperatingState.BRAKING,
                ramp_seconds,
                end - ramp_progress,
                end,
                speed,
                0,
            )
        )
        if index < len(stop_progresses):
            segments.append(
                JourneySegment(
                    JourneyPhase.INTERMEDIATE_DWELL,
                    OperatingState.STATIONARY,
                    rng.randint(4, 14) * 60,
                    end,
                    end,
                )
            )
    segments.append(
        JourneySegment(
            JourneyPhase.DESTINATION_DWELL,
            OperatingState.STATIONARY,
            rng.randint(25, 60) * 60,
            1.0,
            1.0,
        )
    )
    sequence = seed % 10000 if journey_number is None else journey_number
    if not 0 <= sequence <= 9999:
        raise ValueError("journey_number must be between 0 and 9999")
    load_state = rng.choice((LoadState.LOADED, LoadState.EMPTY))
    return JourneyPlan(
        journey_id=f"FG-JNY-{service_date:%Y%m%d}-{sequence:04d}",
        route=route,
        segments=tuple(segments),
        reverse=reverse,
        nominal_speed_kph=nominal_speed,
        load_state=load_state,
        cargo_type="aggregates" if load_state == LoadState.LOADED else "none",
    )


def create_random_journey_plan(
    seed: int,
    service_date: date = date(2026, 1, 1),
) -> JourneyPlan:
    rng = random.Random(seed)
    route = rng.choice(DEFAULT_ROUTES)
    return create_journey_plan(
        seed=seed,
        route=route,
        allow_reverse=True,
        service_date=service_date,
    )


def build_journey_metadata(
    plan: JourneyPlan,
    scheduled_start_time: datetime,
    sampling_interval_seconds: int = STANDARD_SAMPLING_INTERVAL_SECONDS,
) -> JourneyMetadata:
    return JourneyMetadata(
        journey_id=plan.journey_id,
        route_id=plan.route.route_id,
        origin_terminal=plan.origin,
        destination_terminal=plan.destination,
        travel_direction=plan.travel_direction,
        scheduled_start_time=scheduled_start_time,
        estimated_duration_seconds=plan.duration_seconds,
        sampling_interval_seconds=sampling_interval_seconds,
        load_state=plan.load_state,
        cargo_type=plan.cargo_type,
    )


def journey_state_at(
    plan: JourneyPlan, elapsed_seconds: int
) -> tuple[JourneyPhase, OperatingState, float, float]:
    if not 0 <= elapsed_seconds < plan.duration_seconds:
        raise ValueError("elapsed_seconds is outside the journey")
    elapsed = 0
    for segment in plan.segments:
        if elapsed_seconds < elapsed + segment.duration_seconds:
            local = (elapsed_seconds - elapsed) / segment.duration_seconds
            if segment.state == OperatingState.STATIONARY:
                fraction = 0.0
            else:
                v0, v1 = segment.start_speed_kph, segment.end_speed_kph
                fraction = (v0 * local + 0.5 * (v1 - v0) * local**2) / (0.5 * (v0 + v1))
            progress = segment.start_progress + fraction * (
                segment.end_progress - segment.start_progress
            )
            return segment.phase, segment.state, progress, local
        elapsed += segment.duration_seconds
    raise RuntimeError("journey timeline is incomplete")


def journey_speed_at(plan: JourneyPlan, elapsed_seconds: int) -> float:
    """Instantaneous speed from the same integral used for along-track position."""
    if not 0 <= elapsed_seconds < plan.duration_seconds:
        raise ValueError("elapsed_seconds is outside the journey")
    start = 0
    for segment in plan.segments:
        if elapsed_seconds < start + segment.duration_seconds:
            fraction = (elapsed_seconds - start) / segment.duration_seconds
            return segment.start_speed_kph + fraction * (
                segment.end_speed_kph - segment.start_speed_kph
            )
        start += segment.duration_seconds
    raise RuntimeError("journey timeline is incomplete")


def route_provenance() -> dict[str, str]:
    payload = files("fleetguard.generator").joinpath("data/uk_rail_routes.geojson").read_bytes()
    return {
        "route_geometry_version": GEOMETRY_VERSION,
        "route_geometry_sha256": hashlib.sha256(payload).hexdigest(),
        "motion_model_version": "2.0",
    }
