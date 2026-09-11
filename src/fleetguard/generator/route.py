from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, datetime

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

    @property
    def distance_km(self) -> float:
        return sum(
            _haversine_km(first, second)
            for first, second in zip(self.points, self.points[1:], strict=False)
        )


@dataclass(frozen=True)
class JourneySegment:
    phase: JourneyPhase
    state: OperatingState
    duration_seconds: int
    start_progress: float
    end_progress: float


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


# A deliberately compact, non-navigation-grade polyline following the public Great
# Western/South Wales rail corridor. Commercial terminals and operations are fictional.
LONDON_SWANSEA_FREIGHT_ROUTE = RailRoute(
    route_id="FG-RTE-LONDON-SWANSEA",
    name="London–Swansea synthetic freight corridor",
    points=(
        RoutePoint("London Aggregate Terminal", 51.5174, -0.2672),
        RoutePoint("Southall", 51.5061, -0.3786),
        RoutePoint("Hayes", 51.5031, -0.4207),
        RoutePoint("Reading", 51.4590, -0.9722),
        RoutePoint("Didcot", 51.6111, -1.2425),
        RoutePoint("Swindon", 51.5656, -1.7859),
        RoutePoint("Chippenham", 51.4625, -2.1154),
        RoutePoint("Bath", 51.3777, -2.3570),
        RoutePoint("Bristol Temple Meads", 51.4491, -2.5813),
        RoutePoint("Avonmouth Freight Terminal", 51.5007, -2.6992),
        RoutePoint("Filton", 51.5080, -2.5760),
        RoutePoint("Patchway", 51.5259, -2.5627),
        RoutePoint("Severn Tunnel Junction", 51.5848, -2.7772),
        RoutePoint("Newport", 51.5888, -2.9990),
        RoutePoint("Cardiff", 51.4760, -3.1791),
        RoutePoint("Bridgend", 51.5069, -3.5750),
        RoutePoint("Port Talbot", 51.5917, -3.7811),
        RoutePoint("Swansea Materials Terminal", 51.6251, -3.9416),
    ),
    intermediate_stop_indices=(5, 9, 13, 14),
)

LONDON_AVONMOUTH_FREIGHT_ROUTE = RailRoute(
    route_id="FG-RTE-LONDON-AVONMOUTH",
    name="London–Avonmouth synthetic aggregates duty",
    points=LONDON_SWANSEA_FREIGHT_ROUTE.points[:10],
    intermediate_stop_indices=(5,),
)

AVONMOUTH_CARDIFF_FREIGHT_ROUTE = RailRoute(
    route_id="FG-RTE-AVONMOUTH-CARDIFF",
    name="Avonmouth–Cardiff synthetic materials duty",
    points=LONDON_SWANSEA_FREIGHT_ROUTE.points[9:15],
    intermediate_stop_indices=(4,),
)

CARDIFF_SWANSEA_FREIGHT_ROUTE = RailRoute(
    route_id="FG-RTE-CARDIFF-SWANSEA",
    name="Cardiff–Swansea synthetic materials duty",
    points=LONDON_SWANSEA_FREIGHT_ROUTE.points[14:],
    intermediate_stop_indices=(2,),
)

DEFAULT_ROUTES = (
    LONDON_AVONMOUTH_FREIGHT_ROUTE,
    AVONMOUTH_CARDIFF_FREIGHT_ROUTE,
    CARDIFF_SWANSEA_FREIGHT_ROUTE,
    LONDON_SWANSEA_FREIGHT_ROUTE,
)


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

    lengths = [
        _haversine_km(first, second)
        for first, second in zip(route.points, route.points[1:], strict=False)
    ]
    target = progress * sum(lengths)
    travelled = 0.0
    for index, length in enumerate(lengths):
        if travelled + length >= target:
            local = 0.0 if length == 0 else (target - travelled) / length
            first, second = route.points[index], route.points[index + 1]
            return (
                first.latitude + local * (second.latitude - first.latitude),
                first.longitude + local * (second.longitude - first.longitude),
            )
        travelled += length
    final = route.points[-1]
    return final.latitude, final.longitude


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
    # Straight-line waypoint distance understates curved rail mileage, so apply a
    # modest geometry/operational factor before converting distance to running time.
    moving_minutes = max(1, round(route.distance_km * 1.12 / nominal_speed * 60))
    stop_progresses = [index / (len(route.points) - 1) for index in route.intermediate_stop_indices]
    if reverse:
        stop_progresses = sorted(1 - progress for progress in stop_progresses)

    segments: list[JourneySegment] = [
        JourneySegment(
            JourneyPhase.ORIGIN_DWELL,
            OperatingState.STATIONARY,
            rng.randint(20, 45) * 60,
            0.0,
            0.0,
        )
    ]
    boundaries = [0.0, *stop_progresses, 1.0]
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:], strict=False)):
        section_minutes = max(6, round(moving_minutes * (end - start)))
        braking_minutes = min(5, max(2, section_minutes // 8))
        segments.append(
            JourneySegment(
                JourneyPhase.RUNNING,
                OperatingState.MOVING,
                (section_minutes - braking_minutes) * 60,
                start,
                end - (end - start) * braking_minutes / section_minutes,
            )
        )
        segments.append(
            JourneySegment(
                JourneyPhase.RUNNING,
                OperatingState.BRAKING,
                braking_minutes * 60,
                segments[-1].end_progress,
                end,
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
            local = (elapsed_seconds - elapsed) / max(segment.duration_seconds - 1, 1)
            progress = segment.start_progress + local * (
                segment.end_progress - segment.start_progress
            )
            return segment.phase, segment.state, progress, local
        elapsed += segment.duration_seconds
    raise RuntimeError("journey timeline is incomplete")
