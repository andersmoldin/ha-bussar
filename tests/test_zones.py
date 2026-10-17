from datetime import datetime, timedelta

import pytest

from custom_components.bussar.departures import TRAFIKLAB_TZ, WatchedLine, parse_departures
from custom_components.bussar.zones import Timing, Zone, assess

LINE_10_A = WatchedLine("10", "A")
DEFAULT = Timing(walk=timedelta(minutes=4.5), run=timedelta(minutes=2), window=timedelta(minutes=5))


def at(hour: int, minute: int, second: int) -> datetime:
    return datetime(2026, 10, 17, hour, minute, second, tzinfo=TRAFIKLAB_TZ)


# Linje 10 läge A i fixturen avgår 19:44:40, 19:59:29, 20:14:47 och 20:29:19.
@pytest.mark.parametrize(
    ("now", "zone"),
    [
        (at(19, 49, 58), Zone.PLENTY),  # 571 s kvar: mer än gångtid + fönster
        (at(19, 49, 59), Zone.GO),  # 570 s: exakt gångtid + fönster
        (at(19, 54, 59), Zone.GO),  # 270 s: exakt gångtid
        (at(19, 55, 0), Zone.RUN),  # 269 s
        (at(19, 57, 29), Zone.RUN),  # 120 s: exakt springtid
    ],
)
def test_zone_boundaries(stop_a_payload, now, zone):
    result = assess(parse_departures(stop_a_payload), LINE_10_A, now=now, timing=DEFAULT)

    assert result.departure.expected == at(19, 59, 29)
    assert result.zone is zone


def test_missed_bus_switches_to_the_next_one(stop_a_payload):
    result = assess(parse_departures(stop_a_payload), LINE_10_A, now=at(19, 57, 30), timing=DEFAULT)

    assert result.departure.expected == at(20, 14, 47)
    assert result.zone is Zone.PLENTY
    assert result.following.expected == at(20, 29, 19)


def test_canceled_departure_is_reported_and_skipped(stop_a_payload):
    for dep in stop_a_payload["departures"]:
        if dep["route"]["designation"] == "10" and dep["scheduled"].endswith("19:59:29"):
            dep["canceled"] = True

    result = assess(parse_departures(stop_a_payload), LINE_10_A, now=at(19, 50, 0), timing=DEFAULT)

    assert result.departure.expected == at(20, 14, 47)
    assert [d.expected for d in result.canceled] == [at(19, 59, 29)]


def test_delay_in_whole_minutes(stop_a_payload):
    # Linje 10 läge D: planerad 19:47:22, förväntad 19:48:02 (+40 s), avrundas till 1 min.
    result = assess(
        parse_departures(stop_a_payload), WatchedLine("10", "D"), now=at(19, 43, 36), timing=DEFAULT
    )

    assert result.departure.expected == at(19, 48, 2)
    assert result.delay_minutes == 1


def test_nothing_left_gives_no_assessment(stop_a_payload):
    assert (
        assess(parse_departures(stop_a_payload), LINE_10_A, now=at(21, 0, 0), timing=DEFAULT)
        is None
    )
