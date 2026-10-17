"""En sensor per bevakad linje: minuter till nästa avgång."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import BussarConfigEntry
from .const import CONF_LINE, CONF_PLATFORM, CONF_STOP_ID, SUBENTRY_LINE
from .coordinator import StopCoordinator
from .departures import Departure, upcoming


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BussarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for subentry in entry.get_subentries_of_type(SUBENTRY_LINE):
        coordinator = entry.runtime_data[subentry.data[CONF_STOP_ID]]
        async_add_entities(
            [NextDepartureSensor(coordinator, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


class NextDepartureSensor(CoordinatorEntity[StopCoordinator], SensorEntity):
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:bus-clock"

    def __init__(self, coordinator: StopCoordinator, subentry: ConfigSubentry) -> None:
        super().__init__(coordinator)
        self._line = subentry.data[CONF_LINE]
        self._platform = subentry.data[CONF_PLATFORM]
        self._attr_unique_id = subentry.subentry_id
        self._attr_name = subentry.title

    def _next(self) -> Departure | None:
        if not self.coordinator.data:
            return None
        found = upcoming(
            self.coordinator.data,
            line=self._line,
            platform=self._platform,
            now=dt_util.now(),
        )
        return found[0] if found else None

    @property
    def native_value(self) -> int | None:
        departure = self._next()
        if departure is None:
            return None
        return int((departure.expected - dt_util.now()).total_seconds() // 60)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        departure = self._next()
        if departure is None:
            return {}
        return {
            "departure_time": dt_util.as_local(departure.expected).strftime("%H:%M"),
            "expected": departure.expected.isoformat(),
            "destination": departure.destination,
            "line": self._line,
            "platform": self._platform,
        }
