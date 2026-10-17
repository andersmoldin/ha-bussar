"""Avgångar från Trafiklab Realtime APIs, utan beroenden till Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

# Trafiklab anger tider som lokal svensk tid utan tidszon.
TRAFIKLAB_TZ = ZoneInfo("Europe/Stockholm")


@dataclass(frozen=True)
class Departure:
    line: str
    platform: str | None
    destination: str
    scheduled: datetime
    expected: datetime
    is_realtime: bool
    canceled: bool


def _local(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=TRAFIKLAB_TZ)


def parse_departures(payload: dict) -> list[Departure]:
    departures = []
    for item in payload.get("departures", []):
        platform = item.get("realtime_platform") or item.get("scheduled_platform") or {}
        departures.append(
            Departure(
                line=item["route"]["designation"],
                platform=platform.get("designation"),
                destination=item["route"]["destination"]["name"],
                scheduled=_local(item["scheduled"]),
                expected=_local(item.get("realtime") or item["scheduled"]),
                is_realtime=bool(item.get("is_realtime")),
                canceled=bool(item.get("canceled")),
            )
        )
    return departures


def upcoming(
    departures: list[Departure], *, line: str, platform: str, now: datetime
) -> list[Departure]:
    return sorted(
        (
            d
            for d in departures
            if d.line == line
            and d.platform == platform
            and not d.canceled
            and d.expected >= now
        ),
        key=lambda d: d.expected,
    )
