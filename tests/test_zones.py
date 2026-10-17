from datetime import datetime

import pytest

from custom_components.bussar.departures import TRAFIKLAB_TZ, WatchedLine, parse_departures
from custom_components.bussar.zones import DEFAULT_TIMING, Zone, assess, next_change

LINE_10_A = WatchedLine("10", "A")
DEFAULT = DEFAULT_TIMING


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


def _cancel(payload: dict, *scheduled_times: str) -> None:
    for dep in payload["departures"]:
        if dep["route"]["designation"] == "10" and dep["scheduled"][-8:] in scheduled_times:
            dep["canceled"] = True


def test_canceled_departure_is_reported_and_skipped(stop_a_payload):
    _cancel(stop_a_payload, "19:59:29")

    result = assess(parse_departures(stop_a_payload), LINE_10_A, now=at(19, 50, 0), timing=DEFAULT)

    assert result.departure.expected == at(20, 14, 47)
    assert [d.expected for d in result.canceled] == [at(19, 59, 29)]


def test_canceled_departure_after_the_shown_bus_is_also_reported(stop_a_payload):
    _cancel(stop_a_payload, "20:14:47")

    result = assess(parse_departures(stop_a_payload), LINE_10_A, now=at(19, 50, 0), timing=DEFAULT)

    assert result.departure.expected == at(19, 59, 29)
    assert result.following.expected == at(20, 29, 19)
    assert [d.expected for d in result.canceled] == [at(20, 14, 47)]


def test_delay_in_whole_minutes(stop_a_payload):
    # Linje 10 läge D: planerad 19:47:22, förväntad 19:48:02 (+40 s), avrundas till 1 min.
    result = assess(
        parse_departures(stop_a_payload), WatchedLine("10", "D"), now=at(19, 43, 36), timing=DEFAULT
    )

    assert result.departure.expected == at(19, 48, 2)
    assert result.departure.delay_minutes == 1


def test_nothing_left_gives_no_assessment(stop_a_payload):
    assert (
        assess(parse_departures(stop_a_payload), LINE_10_A, now=at(21, 0, 0), timing=DEFAULT)
        is None
    )


@pytest.mark.parametrize(
    ("delay_seconds", "minutes"),
    [(0, 0), (29, 0), (30, 1), (90, 2), (150, 3), (-29, 0), (-31, -1)],
)
def test_delay_rounds_to_nearest_minute_with_halves_up(delay_seconds, minutes):
    from datetime import timedelta

    from custom_components.bussar.departures import Departure

    scheduled = at(19, 0, 0)
    departure = Departure(
        line="10",
        platform="A",
        destination="Ort C",
        scheduled=scheduled,
        expected=scheduled + timedelta(seconds=delay_seconds),
        is_realtime=True,
        canceled=False,
    )

    assert departure.delay_minutes == minutes


@pytest.mark.parametrize(
    ("now", "change"),
    [
        # Visad buss 19:59:29. Nästa ändring sker 1 s efter den närmaste gränsen:
        # minutbyte (minuter är golvade) eller zongräns.
        (at(19, 43, 36), at(19, 44, 30)),  # 953 s kvar: 15 → 14 min när 900 s passerats
        (at(19, 49, 30), at(19, 50, 0)),  # gott om tid → gå nu vid 570 s
        (at(19, 54, 40), at(19, 55, 0)),  # gå nu → spring när 270 s passerats
        (at(19, 57, 10), at(19, 57, 30)),  # springtiden 120 s passeras → nästa buss
        (at(19, 57, 29), at(19, 57, 30)),  # exakt på springtiden
    ],
)
def test_next_change_is_one_second_after_the_next_boundary(stop_a_payload, now, change):
    result = assess(parse_departures(stop_a_payload), LINE_10_A, now=now, timing=DEFAULT)

    assert next_change(result, now=now, timing=DEFAULT) == change
