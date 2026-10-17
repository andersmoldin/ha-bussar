"""Avgångar från Trafiklab Realtime APIs, utan beroenden till Home Assistant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

# Trafiklab anger tider som lokal svensk tid utan tidszon.
TRAFIKLAB_TZ = ZoneInfo("Europe/Stockholm")


@dataclass(frozen=True, order=False)
class WatchedLine:
    """En linje i en riktning, där riktningen anges av hållplatsläget."""

    line: str
    platform: str

    @property
    def key(self) -> str:
        return f"{self.line}|{self.platform}"

    @classmethod
    def parse(cls, key: str) -> WatchedLine:
        line, platform = key.split("|", 1)
        return cls(line, platform)

    def sort_key(self) -> tuple[bool, int, str, str]:
        # Numeriska linjer först, i nummerordning.
        numeric = self.line.isdigit()
        return (not numeric, int(self.line) if numeric else 0, self.line, self.platform)


@dataclass(frozen=True)
class Departure:
    line: str
    platform: str | None
    destination: str
    scheduled: datetime
    expected: datetime
    is_realtime: bool
    canceled: bool


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=TRAFIKLAB_TZ)
    return parsed


def parse_departures(payload: dict) -> list[Departure]:
    departures = []
    for item in payload.get("departures", []):
        platform = item.get("realtime_platform") or item.get("scheduled_platform") or {}
        departures.append(
            Departure(
                line=item["route"]["designation"],
                platform=platform.get("designation"),
                destination=item["route"]["destination"]["name"],
                scheduled=_parse_time(item["scheduled"]),
                expected=_parse_time(item.get("realtime") or item["scheduled"]),
                is_realtime=bool(item.get("is_realtime")),
                canceled=bool(item.get("canceled")),
            )
        )
    return departures


def upcoming(
    departures: list[Departure], watched: WatchedLine, *, now: datetime
) -> list[Departure]:
    return sorted(
        (
            d
            for d in departures
            if d.line == watched.line
            and d.platform == watched.platform
            and not d.canceled
            and d.expected >= now
        ),
        key=lambda d: d.expected,
    )


def line_choices(departures: list[Departure]) -> dict[WatchedLine, list[str]]:
    """Varje linje och läge i avgångarna, med destinationerna som syns där."""
    destinations_by_line: dict[WatchedLine, list[str]] = {}
    for d in departures:
        if d.platform is None:
            continue
        destinations = destinations_by_line.setdefault(WatchedLine(d.line, d.platform), [])
        if d.destination not in destinations:
            destinations.append(d.destination)
    return dict(sorted(destinations_by_line.items(), key=lambda kv: kv[0].sort_key()))
