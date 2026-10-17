"""Hur bråttom är det? Zon för nästa buss som går att hinna med."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from .departures import Departure, WatchedLine, upcoming


class Zone(StrEnum):
    PLENTY = "plenty"  # Gott om tid
    GO = "go"  # Nu passar det att gå
    RUN = "run"  # Du hinner om du springer


@dataclass(frozen=True)
class Timing:
    walk: timedelta
    run: timedelta
    window: timedelta


DEFAULT_TIMING = Timing(
    walk=timedelta(minutes=4.5), run=timedelta(minutes=2), window=timedelta(minutes=5)
)


@dataclass(frozen=True)
class Assessment:
    departure: Departure
    zone: Zone
    following: Departure | None
    canceled: list[Departure]

    @property
    def delay_minutes(self) -> int:
        return round((self.departure.expected - self.departure.scheduled).total_seconds() / 60)


def zone_for(time_left: timedelta, timing: Timing) -> Zone | None:
    """Zon för en buss som går om time_left, eller None om den inte går att hinna."""
    if time_left > timing.walk + timing.window:
        return Zone.PLENTY
    if time_left >= timing.walk:
        return Zone.GO
    if time_left >= timing.run:
        return Zone.RUN
    return None


def assess(
    departures: list[Departure], watched: WatchedLine, *, now: datetime, timing: Timing
) -> Assessment | None:
    """Första bussen som går att hinna med (minst springtid kvar), och bussen efter den."""
    candidates = upcoming(departures, watched, now=now)
    for index, departure in enumerate(candidates):
        zone = zone_for(departure.expected - now, timing)
        if zone is None:
            continue
        canceled = [
            d
            for d in departures
            if d.canceled
            and d.line == watched.line
            and d.platform == watched.platform
            and now <= d.expected <= departure.expected
        ]
        following = candidates[index + 1] if index + 1 < len(candidates) else None
        return Assessment(departure, zone, following, sorted(canceled, key=lambda d: d.expected))
    return None
