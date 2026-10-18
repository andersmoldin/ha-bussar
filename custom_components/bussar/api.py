"""Klient för Trafiklab Realtime APIs."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import aiohttp

BASE_URL = "https://realtime-api.trafiklab.se/v1"


class TrafiklabError(Exception):
    """Anropet misslyckades."""


class TrafiklabAuthError(TrafiklabError):
    """Nyckeln är ogiltig."""


@dataclass(frozen=True)
class Stop:
    id: str
    name: str


class TrafiklabClient:
    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    async def search_stops(self, name: str) -> list[Stop]:
        payload = await self._get(f"/stops/name/{quote(name)}")
        return [Stop(id=g["id"], name=g["name"]) for g in payload.get("stop_groups", [])]

    async def departures(self, stop_id: str) -> dict:
        return await self._get(f"/departures/{quote(stop_id)}")

    async def _get(self, path: str) -> dict:
        try:
            async with self._session.get(
                f"{BASE_URL}{path}",
                params={"key": self._api_key},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status in (401, 403):
                    raise TrafiklabAuthError(f"HTTP {resp.status}")
                if resp.status != 200:
                    raise TrafiklabError(f"HTTP {resp.status}")
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise TrafiklabError(type(err).__name__) from None


def client_for(hass, api_key: str) -> TrafiklabClient:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    return TrafiklabClient(async_get_clientsession(hass), api_key)


VEHICLE_POSITIONS_URL = "https://opendata.samtrafiken.se/gtfs-rt/{operator}/VehiclePositions.pb"


class VehiclePositionsClient:
    """GTFS Regional Realtime, VehiclePositions för ett trafikbolag."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str, operator: str = "ul") -> None:
        self._session = session
        self._api_key = api_key
        self._url = VEHICLE_POSITIONS_URL.format(operator=operator)

    async def fetch(self) -> bytes:
        try:
            async with self._session.get(
                self._url,
                params={"key": self._api_key},
                # Samtrafiken svarar 406 utan gzip (se docs/data-findings.md).
                headers={"Accept-Encoding": "gzip"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status in (401, 403):
                    raise TrafiklabAuthError(f"HTTP {resp.status}")
                if resp.status != 200:
                    raise TrafiklabError(f"HTTP {resp.status}")
                return await resp.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise TrafiklabError(type(err).__name__) from err


def vehicle_client_for(hass, api_key: str) -> VehiclePositionsClient:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    return VehiclePositionsClient(async_get_clientsession(hass), api_key)
