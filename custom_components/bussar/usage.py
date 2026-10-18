"""Antal API-anrop per kalendermånad, sparat i HA:s lagring så att det överlever omstart."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .departures import TRAFIKLAB_TZ

STORAGE_VERSION = 1
# Spara inte vid varje anrop; HA skriver samlat efter en stund och vid avstängning.
SAVE_DELAY_SECONDS = 60


def _month(moment: datetime) -> str:
    return moment.astimezone(TRAFIKLAB_TZ).strftime("%Y-%m")


class UsageCounter:
    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, dict[str, int]]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.usage"
        )
        # månad → API → antal
        self._months: dict[str, dict[str, int]] = {}
        self._listeners: list[Callable[[], None]] = []

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    async def async_load(self) -> None:
        self._months = await self._store.async_load() or {}

    async def async_save(self) -> None:
        await self._store.async_save(self._months)

    def record(self, api: str, now: datetime) -> None:
        month = _month(now)
        # Bara innevarande månad behöver sparas.
        self._months = {month: self._months.get(month, {})}
        self._months[month][api] = self._months[month].get(api, 0) + 1
        self._store.async_delay_save(lambda: self._months, SAVE_DELAY_SECONDS)
        for listener in list(self._listeners):
            listener()

    @callback
    def async_notify(self) -> None:
        """Låt lyssnare räkna om, t.ex. vid månadsskifte när antalet blir 0."""
        for listener in list(self._listeners):
            listener()

    def count(self, api: str, now: datetime) -> int:
        return self._months.get(_month(now), {}).get(api, 0)

    def within_limit(self, api: str, now: datetime, *, limit: int) -> bool:
        return self.count(api, now) < limit
