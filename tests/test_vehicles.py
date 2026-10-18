from datetime import datetime

from custom_components.bussar.departures import TRAFIKLAB_TZ, WatchedLine, parse_departures
from custom_components.bussar.vehicles import parse_vehicle_positions, watched_vehicles

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
