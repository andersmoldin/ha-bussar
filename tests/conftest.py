import json
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def stop_a_payload() -> dict:
    return load_fixture("departures-stop-a.json")


STOP_LOOKUP_URL = "https://realtime-api.trafiklab.se/v1/stops/name/"
DEPARTURES_URL = "https://realtime-api.trafiklab.se/v1/departures/"

STOP_A_ID = "740000001"
STOP_B_ID = "740000002"


def stop_lookup_payload() -> dict:
    """Svar från Stop Lookup, i samma form som Trafiklabs men med påhittade värden."""
    return {
        "timestamp": "2026-10-17T19:40:00",
        "query": "Hållplats",
        "stop_groups": [
            {
                "id": STOP_A_ID,
                "name": "Hållplats A (Ort)",
                "area_type": "RIKSHALLPLATS",
                "average_daily_stop_times": 200.0,
                "transport_modes": ["BUS"],
                "stops": [{"id": "1000", "name": "Hållplats A", "lat": 58.3, "lon": 19.1}],
            }
        ],
    }


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def shifted(payload: dict, delta) -> dict:
    """Samma svar, men med alla avgångstider flyttade delta framåt."""
    from datetime import datetime

    out = json.loads(json.dumps(payload))
    for dep in out["departures"]:
        for key in ("scheduled", "realtime"):
            if dep.get(key):
                dep[key] = (datetime.fromisoformat(dep[key]) + delta).isoformat()
    return out


VEHICLE_POSITIONS_URL = "https://opendata.samtrafiken.se/gtfs-rt/ul/VehiclePositions.pb"


def vehicle_positions_bytes() -> bytes:
    return (FIXTURES / "vehicle-positions.pb").read_bytes()
