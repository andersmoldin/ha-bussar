"""En sensor per bevakad linje: minuter till nästa buss som går att hinna, med zon."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
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
from .const import (
    CONF_LINE,
    CONF_PLATFORM,
    CONF_RUN_MINUTES,
    CONF_STOP_ID,
    CONF_WALK_MINUTES,
    CONF_WINDOW_MINUTES,
    DOMAIN,
    SUBENTRY_LINE,
)
from .coordinator import StopCoordinator
from .departures import WatchedLine
from .zones import DEFAULT_TIMING, Assessment, Timing, assess


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
        self._timing = _timing(subentry.data)
        self._attr_unique_id = subentry.subentry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            entry_type=DeviceEntryType.SERVICE,
        )

    def _assess(self) -> Assessment | None:
        if not self.coordinator.data:
            return None
        return assess(self.coordinator.data, self._watched, now=dt_util.now(), timing=self._timing)

    @property
    def native_value(self) -> int | None:
        result = self._assess()
        if result is None:
            return None
        return int((result.departure.expected - dt_util.now()).total_seconds() // 60)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "line": self._watched.line,
            "platform": self._watched.platform,
            "walk_seconds": int(self._timing.walk.total_seconds()),
            "run_seconds": int(self._timing.run.total_seconds()),
            "window_seconds": int(self._timing.window.total_seconds()),
        }
        result = self._assess()
        if result is None:
            return attrs
        departure = result.departure
        attrs |= {
            "zone": result.zone.value,
            "departure_time": _clock(departure.expected),
            "expected": departure.expected.isoformat(),
            "scheduled": departure.scheduled.isoformat(),
            "delay_minutes": result.delay_minutes,
            "is_realtime": departure.is_realtime,
            "destination": departure.destination,
            "canceled": [_clock(d.scheduled) for d in result.canceled],
            "following_departure_time": None,
            "following_expected": None,
        }
        if result.following is not None:
            attrs["following_departure_time"] = _clock(result.following.expected)
            attrs["following_expected"] = result.following.expected.isoformat()
        return attrs


def _clock(moment: datetime) -> str:
    return dt_util.as_local(moment).strftime("%H:%M")


def _timing(data: Mapping[str, Any]) -> Timing:
    def minutes(key: str, default: timedelta) -> timedelta:
        return timedelta(minutes=data[key]) if key in data else default

    return Timing(
        walk=minutes(CONF_WALK_MINUTES, DEFAULT_TIMING.walk),
        run=minutes(CONF_RUN_MINUTES, DEFAULT_TIMING.run),
        window=minutes(CONF_WINDOW_MINUTES, DEFAULT_TIMING.window),
    )
