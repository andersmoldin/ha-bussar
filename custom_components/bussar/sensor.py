"""En sensor per bevakad linje: minuter till nästa avgång."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import BussarConfigEntry
from .const import CONF_LINE, CONF_PLATFORM, CONF_STOP_ID, DOMAIN, SUBENTRY_LINE
from .coordinator import StopCoordinator
from .departures import Departure, WatchedLine, upcoming


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
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: StopCoordinator, subentry: ConfigSubentry) -> None:
        super().__init__(coordinator)
        self._watched = WatchedLine(subentry.data[CONF_LINE], subentry.data[CONF_PLATFORM])
        self._attr_unique_id = subentry.subentry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    def _next(self) -> Departure | None:
        if not self.coordinator.data:
            return None
        found = upcoming(self.coordinator.data, self._watched, now=dt_util.now())
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
            "line": self._watched.line,
            "platform": self._watched.platform,
        }
