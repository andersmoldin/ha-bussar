"""Fordonspositioner från GTFS Regional Realtime, kopplade till bevakade linjer."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from google.transit import gtfs_realtime_pb2

from .departures import Departure, WatchedLine


@dataclass(frozen=True)
class Vehicle:
    vehicle_id: str
    trip_id: str | None
    latitude: float
    longitude: float
    bearing: float | None


@dataclass(frozen=True)
class WatchedVehicle:
    """En buss på väg mot en bevakad hållplats, i bevakad riktning."""

    vehicle_id: str
    line: str
    platform: str
    stop_id: str
    expected: datetime
    latitude: float
    longitude: float
    bearing: float | None


def parse_vehicle_positions(payload: bytes) -> list[Vehicle]:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(payload)
    vehicles = []
    for entity in feed.entity:
        if not entity.HasField("vehicle") or not entity.vehicle.HasField("position"):
            continue
        v = entity.vehicle
        vehicles.append(
            Vehicle(
                vehicle_id=v.vehicle.id or entity.id,
                trip_id=v.trip.trip_id or None,
                latitude=v.position.latitude,
                longitude=v.position.longitude,
                bearing=v.position.bearing if v.position.HasField("bearing") else None,
            )
        )
    return vehicles


def watched_vehicles(
    vehicles: Iterable[Vehicle],
    departures_by_stop: Mapping[str, list[Departure]],
    watched: Iterable[tuple[str, WatchedLine]],
    *,
    now: datetime,
) -> list[WatchedVehicle]:
    """Bussar vars tur ännu inte har passerat en bevakad hållplats i bevakad riktning.

    VehiclePositions saknar linje och riktning, men trip_id är samma som i
    avgångs-API:t (se docs/data-findings.md). Kommande avgångar ger därför kopplingen.
    """
    by_trip: dict[str, tuple[str, WatchedLine, Departure]] = {}
    for stop_id, line in watched:
        for d in departures_by_stop.get(stop_id, []):
            if d.trip_id and line.matches(d) and not d.canceled and d.expected >= now:
                by_trip[d.trip_id] = (stop_id, line, d)
    result = []
    for v in vehicles:
        if v.trip_id is None or v.trip_id not in by_trip:
            continue
        stop_id, line, departure = by_trip[v.trip_id]
        result.append(
            WatchedVehicle(
                vehicle_id=v.vehicle_id,
                line=line.line,
                platform=line.platform,
                stop_id=stop_id,
                expected=departure.expected,
                latitude=v.latitude,
                longitude=v.longitude,
                bearing=v.bearing,
            )
        )
    return sorted(result, key=lambda w: w.expected)
