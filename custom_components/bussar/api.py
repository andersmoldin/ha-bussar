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
        except (aiohttp.ClientError, TimeoutError) as err:
            raise TrafiklabError(str(err)) from err
