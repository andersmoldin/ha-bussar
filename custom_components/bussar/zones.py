"""Hur bråttom är det? Zon för nästa buss som går att hinna med."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from .const import CONF_RUN_MINUTES, CONF_WALK_MINUTES, CONF_WINDOW_MINUTES
from .departures import Departure, WatchedLine, upcoming

# Gränser och minuter ändras strikt efter en tidpunkt, så omräkningen sker strax efter.
_AFTER_BOUNDARY = timedelta(seconds=1)
_MINUTE = timedelta(minutes=1)


class Zone(StrEnum):
    PLENTY = "plenty"  # Gott om tid
    GO = "go"  # Nu passar det att gå
    RUN = "run"  # Du hinner om du springer


@dataclass(frozen=True)
class Timing:
    walk: timedelta
    run: timedelta
    window: timedelta

    @classmethod
    def from_minutes(cls, data: Mapping[str, Any]) -> Timing:
        """Tider sparade i en bevakad linje, med standardvärden för det som saknas."""
        defaults = DEFAULT_TIMING.as_minutes()
        return cls(
            walk=timedelta(minutes=data.get(CONF_WALK_MINUTES, defaults[CONF_WALK_MINUTES])),
            run=timedelta(minutes=data.get(CONF_RUN_MINUTES, defaults[CONF_RUN_MINUTES])),
            window=timedelta(minutes=data.get(CONF_WINDOW_MINUTES, defaults[CONF_WINDOW_MINUTES])),
        )

    def as_minutes(self) -> dict[str, float]:
        return {
            CONF_WALK_MINUTES: self.walk / _MINUTE,
            CONF_RUN_MINUTES: self.run / _MINUTE,
            CONF_WINDOW_MINUTES: self.window / _MINUTE,
        }


DEFAULT_TIMING = Timing(
    walk=timedelta(minutes=4.5), run=timedelta(minutes=2), window=timedelta(minutes=5)
)


@dataclass(frozen=True)
class Assessment:
    departure: Departure
    zone: Zone
    following: Departure | None
    canceled: list[Departure]


def zone_for(time_left: timedelta, timing: Timing) -> Zone | None:
    """Zon för en buss som går om time_left, eller None om den inte går att hinna.

    Exakt på gångtiden räknas som "gå nu", exakt på springtiden som "spring".
    """
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
    canceled = sorted(
        (d for d in departures if d.canceled and watched.matches(d) and d.expected >= now),
        key=lambda d: d.expected,
    )
    for index, departure in enumerate(candidates):
        zone = zone_for(departure.expected - now, timing)
        if zone is None:
            continue
        following = candidates[index + 1] if index + 1 < len(candidates) else None
        return Assessment(departure, zone, following, canceled)
    return None


def next_change(result: Assessment, *, now: datetime, timing: Timing) -> datetime:
    """När visade minuter eller zon ändras nästa gång, 1 s efter gränsen."""
    expected = result.departure.expected
    time_left = expected - now
    # Minuterna är golvade och ändras när time_left passerar närmaste hela minut nedåt.
    whole_minute = _MINUTE * (time_left // _MINUTE)
    thresholds = [timing.walk + timing.window, timing.walk, timing.run, whole_minute]
    return min(
        expected - x + _AFTER_BOUNDARY for x in thresholds if expected - x + _AFTER_BOUNDARY > now
    )
