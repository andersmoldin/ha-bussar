from datetime import datetime

from custom_components.bussar.departures import (
    TRAFIKLAB_TZ,
    WatchedLine,
    line_choices,
    parse_departures,
    upcoming,
)

STOCKHOLM = TRAFIKLAB_TZ
RECORDED_AT = datetime(2026, 10, 17, 19, 43, 36, tzinfo=STOCKHOLM)


def at(hour: int, minute: int, second: int) -> datetime:
    return datetime(2026, 10, 17, hour, minute, second, tzinfo=STOCKHOLM)


def test_upcoming_departures_for_line_and_platform_in_expected_order(stop_a_payload):
    departures = parse_departures(stop_a_payload)

    result = upcoming(departures, WatchedLine("10", "A"), now=RECORDED_AT)

    assert [d.expected for d in result] == [
        at(19, 44, 40),
        at(19, 59, 29),
        at(20, 14, 47),
        at(20, 29, 19),
    ]


def test_canceled_departure_is_skipped(stop_a_payload):
    first_line_10_on_a = next(
        d
        for d in stop_a_payload["departures"]
        if d["route"]["designation"] == "10" and d["scheduled_platform"]["designation"] == "A"
    )
    first_line_10_on_a["canceled"] = True

    result = upcoming(parse_departures(stop_a_payload), WatchedLine("10", "A"), now=RECORDED_AT)

    assert result[0].expected == at(19, 59, 29)


def test_departure_already_gone_is_skipped(stop_a_payload):
    result = upcoming(parse_departures(stop_a_payload), WatchedLine("10", "A"), now=at(19, 45, 0))

    assert result[0].expected == at(19, 59, 29)


def test_no_departures_gives_empty_list():
    assert (
        upcoming(parse_departures({"departures": []}), WatchedLine("10", "A"), now=RECORDED_AT)
        == []
    )


def test_line_choices_list_each_line_and_platform_once_with_destinations(stop_a_payload):
    choices = line_choices(parse_departures(stop_a_payload))

    assert list(choices) == [
        WatchedLine("10", "A"),
        WatchedLine("10", "D"),
        WatchedLine("20", "A"),
        WatchedLine("20", "B"),
        WatchedLine("30", "B"),
    ]
    assert choices[WatchedLine("10", "A")] == ["Ort C"]


def test_watched_line_round_trips_through_its_key():
    assert WatchedLine.parse(WatchedLine("107", "B").key) == WatchedLine("107", "B")


def test_explicit_offset_in_api_time_is_respected():
    payload = {
        "departures": [
            {
                "scheduled": "2026-10-17T17:44:36+00:00",
                "realtime": None,
                "is_realtime": False,
                "canceled": False,
                "route": {"designation": "10", "destination": {"name": "Ort C"}},
                "scheduled_platform": {"designation": "A"},
            }
        ]
    }

    assert parse_departures(payload)[0].expected == at(19, 44, 36)
