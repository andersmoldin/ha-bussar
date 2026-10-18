"""En sensor per bevakad linje: minuter till nästa buss som går att hinna, med zon."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import BussarConfigEntry
from .const import (
    CONF_LINE,
    CONF_PLATFORM,
    CONF_STOP_ID,
    DOMAIN,
    SUBENTRY_LINE,
    USAGE_DEPARTURES,
    USAGE_POSITIONS,
)
from .coordinator import StopCoordinator
from .departures import WatchedLine
from .zones import Timing, assess, next_change


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BussarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for subentry in entry.get_subentries_of_type(SUBENTRY_LINE):
        coordinator = entry.runtime_data.coordinators[subentry.data[CONF_STOP_ID]]
        async_add_entities(
            [NextDepartureSensor(coordinator, subentry)],
            config_subentry_id=subentry.subentry_id,
        )
    async_add_entities(UsageSensor(entry, api) for api in (USAGE_DEPARTURES, USAGE_POSITIONS))


class UsageSensor(SensorEntity):
    """Antal API-anrop denna månad, för att enkelt kunna kontrollera kvoten."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "anrop"
    _attr_icon = "mdi:counter"
    _attr_should_poll = False

    def __init__(self, entry: BussarConfigEntry, api: str) -> None:
        self._usage = entry.runtime_data.usage
        self._api = api
        self._attr_unique_id = f"{entry.entry_id}_usage_{api}"
        self._attr_translation_key = f"usage_{api}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Trafiklab",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> int:
        return self._usage.count(self._api, dt_util.now())

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._usage.async_add_listener(self.async_write_ha_state))


class NextDepartureSensor(CoordinatorEntity[StopCoordinator], SensorEntity):
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:bus-clock"
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: StopCoordinator, subentry: ConfigSubentry) -> None:
        super().__init__(coordinator)
        self._watched = WatchedLine(subentry.data[CONF_LINE], subentry.data[CONF_PLATFORM])
        self._timing = Timing.from_minutes(subentry.data)
        self._unsub_timer: CALLBACK_TYPE | None = None
        self._attr_unique_id = subentry.subentry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            entry_type=DeviceEntryType.SERVICE,
        )
        self._recompute()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._cancel_timer)
        self._schedule_next_change()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._recompute()
        self._schedule_next_change()
        self.async_write_ha_state()

    @callback
    def _handle_boundary(self, _now: datetime) -> None:
        self._unsub_timer = None
        self._handle_coordinator_update()

    def _cancel_timer(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None

    def _schedule_next_change(self) -> None:
        """Skriv om sensorn vid nästa minutbyte eller zongräns, utan att vänta på ny data."""
        self._cancel_timer()
        if self.hass is None or self._assessment is None:
            return
        when = next_change(self._assessment, now=self._computed_at, timing=self._timing)
        self._unsub_timer = async_track_point_in_utc_time(self.hass, self._handle_boundary, when)

    def _recompute(self) -> None:
        """Räkna värde och attribut från en och samma tidpunkt."""
        now = dt_util.now()
        self._computed_at = now
        result = (
            assess(self.coordinator.data, self._watched, now=now, timing=self._timing)
            if self.coordinator.data
            else None
        )
        self._assessment = result
        attrs: dict[str, Any] = {
            "line": self._watched.line,
            "platform": self._watched.platform,
            "walk_seconds": int(self._timing.walk.total_seconds()),
            "run_seconds": int(self._timing.run.total_seconds()),
            "window_seconds": int(self._timing.window.total_seconds()),
            "zone": None,
            "departure_time": None,
            "expected": None,
            "scheduled": None,
            "delay_minutes": None,
            "is_realtime": None,
            "destination": None,
            "canceled": [],
            "following_departure_time": None,
            "following_expected": None,
        }
        if result is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = attrs
            return
        departure = result.departure
        self._attr_native_value = int((departure.expected - now).total_seconds() // 60)
        attrs |= {
            "zone": result.zone.value,
            "departure_time": _clock(departure.expected),
            "expected": departure.expected.isoformat(),
            "scheduled": departure.scheduled.isoformat(),
            "delay_minutes": departure.delay_minutes,
            "is_realtime": departure.is_realtime,
            "destination": departure.destination,
            "canceled": [_clock(d.scheduled) for d in result.canceled],
        }
        if result.following is not None:
            attrs["following_departure_time"] = _clock(result.following.expected)
            attrs["following_expected"] = result.following.expected.isoformat()
        self._attr_extra_state_attributes = attrs


def _clock(moment: datetime) -> str:
    return dt_util.as_local(moment).strftime("%H:%M")
