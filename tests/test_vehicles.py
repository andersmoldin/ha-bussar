from datetime import datetime

from custom_components.bussar.departures import (
    TRAFIKLAB_TZ,
    Departure,
    WatchedLine,
    parse_departures,
)
from custom_components.bussar.vehicles import Vehicle, parse_vehicle_positions, watched_vehicles

from .conftest import FIXTURES, STOP_A_ID, STOP_B_ID, load_fixture

RECORDED_AT = datetime(2026, 10, 17, 19, 43, 36, tzinfo=TRAFIKLAB_TZ)


def _departures_by_stop():
    return {
        STOP_A_ID: parse_departures(load_fixture("departures-stop-a.json")),
        STOP_B_ID: parse_departures(load_fixture("departures-stop-b.json")),
    }


def test_parse_reads_every_vehicle_with_a_position():
    vehicles = parse_vehicle_positions((FIXTURES / "vehicle-positions.pb").read_bytes())

    assert len(vehicles) == 284
    assert sum(1 for v in vehicles if v.trip_id) == 100


def test_only_vehicles_on_watched_lines_in_watched_direction_are_kept():
    vehicles = parse_vehicle_positions((FIXTURES / "vehicle-positions.pb").read_bytes())
    watched = {
        (STOP_A_ID, WatchedLine("10", "A")),
        (STOP_A_ID, WatchedLine("20", "A")),
        (STOP_B_ID, WatchedLine("40", "A")),
    }

    result = watched_vehicles(vehicles, _departures_by_stop(), watched, now=RECORDED_AT)

    # I inspelningen är en buss på väg på 10 läge A och en på 20 läge A.
    # Linje 40:s bussar i rörelse går åt andra hållet (läge B).
    assert sorted((v.line, v.platform) for v in result) == [("10", "A"), ("20", "A")]
    bus_10 = next(v for v in result if v.line == "10")
    assert bus_10.stop_id == STOP_A_ID
    assert bus_10.expected == datetime(2026, 10, 17, 19, 44, 40, tzinfo=TRAFIKLAB_TZ)
    assert -90 <= bus_10.latitude <= 90 and -180 <= bus_10.longitude <= 180


def test_vehicle_that_already_passed_the_stop_is_dropped():
    vehicles = parse_vehicle_positions((FIXTURES / "vehicle-positions.pb").read_bytes())
    watched = {(STOP_A_ID, WatchedLine("10", "A"))}
    later = datetime(2026, 10, 17, 19, 45, 0, tzinfo=TRAFIKLAB_TZ)

    assert watched_vehicles(vehicles, _departures_by_stop(), watched, now=later) == []


def test_trip_past_two_watched_stops_is_shown_for_the_one_it_reaches_first():
    def departure(minute: int) -> Departure:
        at = datetime(2026, 10, 17, 19, minute, tzinfo=TRAFIKLAB_TZ)
        return Departure("10", "A", "Ändhållplats", at, at, True, False, trip_id="tur-1")

    bus = Vehicle("buss-1", "tur-1", 58.3, 19.1, None)
    departures = {STOP_A_ID: [departure(46)], STOP_B_ID: [departure(50)]}
    line = WatchedLine("10", "A")

    for watched in ([(STOP_A_ID, line), (STOP_B_ID, line)], [(STOP_B_ID, line), (STOP_A_ID, line)]):
        [result] = watched_vehicles([bus], departures, watched, now=RECORDED_AT)
        assert result.stop_id == STOP_A_ID
        assert result.expected == departures[STOP_A_ID][0].expected
