"""Hämtar avgångar för en hållplats, delat av alla bevakade linjer där."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import TrafiklabAuthError, TrafiklabClient, TrafiklabError
from .const import DOMAIN
from .departures import TRAFIKLAB_TZ, Departure, parse_departures

_LOGGER = logging.getLogger(__name__)

# Avgångs-API:t cachar i 60 s, så tätare anrop ger inget.
UPDATE_INTERVAL = timedelta(seconds=60)
# Inga anrop nattetid, för att hålla nere kvoten.
QUIET_START = time(23, 0)
QUIET_END = time(5, 0)


def is_quiet(now: datetime) -> bool:
    local = now.astimezone(TRAFIKLAB_TZ).time()
    return local >= QUIET_START or local < QUIET_END


class StopCoordinator(DataUpdateCoordinator[list[Departure] | None]):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: TrafiklabClient,
        stop_id: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {stop_id}",
            update_interval=UPDATE_INTERVAL,
            config_entry=entry,
        )
        self._client = client
        self.stop_id = stop_id

    async def _async_update_data(self) -> list[Departure] | None:
        if is_quiet(dt_util.now()):
            # Räkna vidare på senaste datan i stället för att hämta.
            return self.data
        try:
            return parse_departures(await self._client.departures(self.stop_id))
        except TrafiklabAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except TrafiklabError as err:
            raise UpdateFailed(str(err)) from err
