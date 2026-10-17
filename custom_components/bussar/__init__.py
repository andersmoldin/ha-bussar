"""Bussar: när är det dags att gå till bussen?"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant

from .api import client_for
from .const import CONF_STOP_ID, SUBENTRY_LINE
from .coordinator import StopCoordinator
from .frontend import async_register_card

PLATFORMS = [Platform.SENSOR]

type BussarConfigEntry = ConfigEntry[dict[str, StopCoordinator]]


async def async_setup_entry(hass: HomeAssistant, entry: BussarConfigEntry) -> bool:
    await async_register_card(hass)
    client = client_for(hass, entry.data[CONF_API_KEY])
    stop_ids = {sub.data[CONF_STOP_ID] for sub in entry.get_subentries_of_type(SUBENTRY_LINE)}
    coordinators = {stop_id: StopCoordinator(hass, entry, client, stop_id) for stop_id in stop_ids}
    for coordinator in coordinators.values():
        await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinators
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BussarConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: BussarConfigEntry) -> None:
    # Ny eller borttagen bevakad linje.
    await hass.config_entries.async_reload(entry.entry_id)
