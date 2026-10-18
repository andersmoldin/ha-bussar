"""Bussar: när är det dags att gå till bussen?"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType

from .api import client_for, vehicle_client_for
from .const import (
    CONF_LINE,
    CONF_PLATFORM,
    CONF_STOP_ID,
    CONF_VEHICLE_API_KEY,
    DOMAIN,
    SUBENTRY_LINE,
)
from .coordinator import StopCoordinator
from .departures import WatchedLine
from .frontend import async_register_card
from .positions import VehicleTracker, async_refresh_quota_issue, async_register_websocket
from .usage import UsageCounter

PLATFORMS = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class BussarData:
    coordinators: dict[str, StopCoordinator]
    usage: UsageCounter
    # None när ingen nyckel för fordonspositioner är angiven.
    tracker: VehicleTracker | None


type BussarConfigEntry = ConfigEntry[BussarData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_register_websocket(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BussarConfigEntry) -> bool:
    await async_register_card(hass)
    usage = UsageCounter(hass)
    await usage.async_load()
    client = client_for(hass, entry.data[CONF_API_KEY])
    lines = entry.get_subentries_of_type(SUBENTRY_LINE)
    stop_ids = {sub.data[CONF_STOP_ID] for sub in lines}
    coordinators = {
        stop_id: StopCoordinator(hass, entry, client, stop_id, usage) for stop_id in stop_ids
    }
    for coordinator in coordinators.values():
        await coordinator.async_config_entry_first_refresh()
    tracker = None
    if vehicle_key := entry.data.get(CONF_VEHICLE_API_KEY):
        watched = {
            (sub.data[CONF_STOP_ID], WatchedLine(sub.data[CONF_LINE], sub.data[CONF_PLATFORM]))
            for sub in lines
        }
        tracker = VehicleTracker(
            hass, entry, vehicle_client_for(hass, vehicle_key), coordinators, watched, usage
        )
        entry.async_on_unload(tracker.async_stop)
    entry.runtime_data = BussarData(coordinators, usage, tracker)

    @callback
    def at_midnight(now: datetime) -> None:
        # Nollställ diagnostiksensorerna och kvotnotisen när en ny månad börjar.
        usage.async_notify()
        async_refresh_quota_issue(hass, usage, now)

    entry.async_on_unload(async_track_time_change(hass, at_midnight, hour=0, minute=0, second=0))
    entry.async_on_unload(usage.async_save)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BussarConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: BussarConfigEntry) -> None:
    # Ny eller borttagen bevakad linje, eller ny nyckel.
    await hass.config_entries.async_reload(entry.entry_id)
