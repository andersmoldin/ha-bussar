from datetime import datetime
from zoneinfo import ZoneInfo

from custom_components.bussar.departures import parse_departures, upcoming

STOCKHOLM = ZoneInfo("Europe/Stockholm")
RECORDED_AT = datetime(2026, 10, 17, 19, 43, 36, tzinfo=STOCKHOLM)


def at(hour: int, minute: int, second: int) -> datetime:
    return datetime(2026, 10, 17, hour, minute, second, tzinfo=STOCKHOLM)


def test_upcoming_departures_for_line_and_platform_in_expected_order(stop_a_payload):
    departures = parse_departures(stop_a_payload)

    result = upcoming(departures, line="10", platform="A", now=RECORDED_AT)

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

    result = upcoming(
        parse_departures(stop_a_payload), line="10", platform="A", now=RECORDED_AT
    )

    assert result[0].expected == at(19, 59, 29)


def test_departure_already_gone_is_skipped(stop_a_payload):
    result = upcoming(
        parse_departures(stop_a_payload), line="10", platform="A", now=at(19, 45, 0)
    )

    assert result[0].expected == at(19, 59, 29)


def test_no_departures_gives_empty_list():
    assert upcoming(parse_departures({"departures": []}), line="10", platform="A", now=RECORDED_AT) == []
