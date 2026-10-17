"""Spela in riktiga Trafiklab-svar och skriv anonymiserade fixtures.

Råsvar hamnar i .local/raw/ (gitignored). Anonymiserade kopior hamnar i
tests/fixtures/ och får checkas in: hållplatser, linjer, destinationer,
trip-ID:n och koordinater ersätts deterministiskt.

    .venv/bin/python scripts/record_fixtures.py

Läser nycklar från .local/keys.env och hållplats-ID:n från .local/watch.json.
"""

import gzip
import hashlib
import json
import pathlib
import urllib.parse
import urllib.request

from google.transit import gtfs_realtime_pb2

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOCAL = ROOT / ".local"
RAW = LOCAL / "raw"
FIXTURES = ROOT / "tests" / "fixtures"

# Förskjutning av alla koordinater, så att fixtures inte pekar ut riktiga platser.
LAT_OFFSET = -1.5
LON_OFFSET = 1.5


def load_keys() -> dict[str, str]:
    keys = {}
    for line in (LOCAL / "keys.env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            name, value = line.split("=", 1)
            keys[name.strip()] = value.strip()
    return keys


def fetch(url: str, params: dict[str, str]) -> bytes:
    # Samtrafikens GTFS-RT svarar 406 utan Accept-Encoding: gzip.
    request = urllib.request.Request(
        f"{url}?{urllib.parse.urlencode(params)}", headers={"Accept-Encoding": "gzip"}
    )
    with urllib.request.urlopen(request, timeout=30) as resp:
        body = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        return body


class Anonymizer:
    """Ersätter identifierande värden konsekvent över alla fixtures."""

    def __init__(self) -> None:
        self._maps: dict[str, dict[str, str]] = {}

    def _label(self, kind: str, value: str, fmt: str) -> str:
        mapping = self._maps.setdefault(kind, {})
        if value not in mapping:
            mapping[value] = fmt.format(n=len(mapping) + 1, letter=chr(ord("A") + len(mapping)))
        return mapping[value]

    def stop_group(self, value: str) -> str:
        return self._label("stop_group", value, "74000000{n}")

    def stop(self, value: str) -> str:
        return self._label("stop", value, "{n}000")

    def stop_name(self, value: str) -> str:
        return self._label("stop_name", value, "Hållplats {letter}")

    def platform(self, value: str) -> str:
        return self._label("platform", value, "90220500000{n:02d}")

    def line(self, value: str) -> str:
        return self._label("line", value, "{n}0")

    def place(self, value: str) -> str:
        return self._label("place", value, "Ort {letter}")

    def trip(self, value: str) -> str:
        return "3301" + hashlib.sha256(value.encode()).hexdigest()[:13]

    def vehicle(self, value: str) -> str:
        return "9031" + hashlib.sha256(value.encode()).hexdigest()[:12]


def anonymize_departures(data: dict, anon: Anonymizer) -> dict:
    data["query"]["query"] = anon.stop_group(data["query"]["query"])
    for stop in data["stops"]:
        stop["id"] = anon.stop(stop["id"])
        stop["name"] = anon.stop_name(stop["name"])
        stop["lat"] = round(stop["lat"] + LAT_OFFSET, 6)
        stop["lon"] = round(stop["lon"] + LON_OFFSET, 6)
    for dep in data["departures"]:
        route = dep["route"]
        route["designation"] = anon.line(route["designation"])
        route["direction"] = anon.place(route["direction"])
        for end in ("origin", "destination"):
            route[end]["id"] = anon.stop(route[end]["id"])
            route[end]["name"] = anon.place(route[end]["name"])
        dep["trip"]["trip_id"] = anon.trip(dep["trip"]["trip_id"])
        stop = dep["stop"]
        stop["id"] = anon.stop(stop["id"])
        stop["name"] = anon.stop_name(stop["name"])
        stop["lat"] = round(stop["lat"] + LAT_OFFSET, 6)
        stop["lon"] = round(stop["lon"] + LON_OFFSET, 6)
        for key in ("scheduled_platform", "realtime_platform"):
            if dep.get(key):
                dep[key]["id"] = anon.platform(dep[key]["id"])
        for alert in dep.get("alerts", []):
            alert.clear()
    return data


def anonymize_vehicle_positions(raw: bytes, anon: Anonymizer) -> bytes:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(raw)
    for entity in feed.entity:
        vehicle = entity.vehicle
        if vehicle.trip.trip_id:
            vehicle.trip.trip_id = anon.trip(vehicle.trip.trip_id)
        if vehicle.vehicle.id:
            vehicle.vehicle.id = anon.vehicle(vehicle.vehicle.id)
        vehicle.position.latitude += LAT_OFFSET
        vehicle.position.longitude += LON_OFFSET
    return feed.SerializeToString()


def main() -> None:
    keys = load_keys()
    stop_ids = json.loads((LOCAL / "watch.json").read_text())["stop_ids"]
    RAW.mkdir(parents=True, exist_ok=True)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    anon = Anonymizer()

    for n, stop_id in enumerate(stop_ids, start=1):
        raw = fetch(
            f"https://realtime-api.trafiklab.se/v1/departures/{stop_id}",
            {"key": keys["TRAFIKLAB_REALTIME_KEY"]},
        )
        (RAW / f"departures-{stop_id}.json").write_bytes(raw)
        data = anonymize_departures(json.loads(raw), anon)
        out = FIXTURES / f"departures-stop-{chr(ord('a') + n - 1)}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        print(f"{out.relative_to(ROOT)}: {len(data['departures'])} avgångar")

    raw = fetch(
        "https://opendata.samtrafiken.se/gtfs-rt/ul/VehiclePositions.pb",
        {"key": keys["GTFS_REGIONAL_REALTIME_KEY"]},
    )
    (RAW / "VehiclePositions.pb").write_bytes(raw)
    out = FIXTURES / "vehicle-positions.pb"
    out.write_bytes(anonymize_vehicle_positions(raw, anon))
    print(f"{out.relative_to(ROOT)}: {len(raw)} B")


if __name__ == "__main__":
    main()
