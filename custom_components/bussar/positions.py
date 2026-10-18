"""Bussarnas positioner, hämtade bara medan någon prenumererar (kartan i kortet visas)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import TrafiklabError, VehiclePositionsClient
from .const import DOMAIN, POSITIONS_MONTHLY_LIMIT, USAGE_POSITIONS
from .coordinator import StopCoordinator
from .departures import WatchedLine
from .schema import vol
from .usage import UsageCounter
from .vehicles import WatchedVehicle, parse_vehicle_positions, watched_vehicles

_LOGGER = logging.getLogger(__name__)

POLL_INTERVAL = timedelta(seconds=10)
QUOTA_ISSUE = "positions_quota_reached"

type Subscriber = Callable[[list[WatchedVehicle]], None]


class VehicleTracker:
    """Hämtar positioner var 10:e sekund så länge minst en prenumerant finns."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: VehiclePositionsClient,
        coordinators: dict[str, StopCoordinator],
        watched: set[tuple[str, WatchedLine]],
        usage: UsageCounter,
    ) -> None:
        self._hass = hass
        self._client = client
        self._coordinators = coordinators
        self._watched = watched
        self._usage = usage
        self._subscribers: list[Subscriber] = []
        self._unsub_interval: CALLBACK_TYPE | None = None

    @callback
    def async_subscribe(self, subscriber: Subscriber) -> CALLBACK_TYPE:
        self._subscribers.append(subscriber)
        if self._unsub_interval is None:
            self._unsub_interval = async_track_time_interval(
                self._hass, self._async_poll, POLL_INTERVAL
            )
            self._hass.async_create_task(self._async_poll(dt_util.now()))

        @callback
        def unsubscribe() -> None:
            self._subscribers.remove(subscriber)
            if not self._subscribers:
                self.async_stop()

        return unsubscribe

    @callback
    def async_stop(self) -> None:
        if self._unsub_interval is not None:
            self._unsub_interval()
            self._unsub_interval = None

    async def _async_poll(self, now: datetime) -> None:
        if not self._subscribers:
            return
        if not self._usage.within_limit(USAGE_POSITIONS, now, limit=POSITIONS_MONTHLY_LIMIT):
            self._raise_quota_issue()
            return
        ir.async_delete_issue(self._hass, DOMAIN, QUOTA_ISSUE)
        self._usage.record(USAGE_POSITIONS, now)
        try:
            payload = await self._client.fetch()
        except TrafiklabError as err:
            _LOGGER.debug("Kunde inte hämta fordonspositioner: %s", err)
            return
        departures = {
            stop_id: coordinator.data or [] for stop_id, coordinator in self._coordinators.items()
        }
        buses = watched_vehicles(
            parse_vehicle_positions(payload), departures, self._watched, now=dt_util.now()
        )
        for subscriber in list(self._subscribers):
            subscriber(buses)

    def _raise_quota_issue(self) -> None:
        ir.async_create_issue(
            self._hass,
            DOMAIN,
            QUOTA_ISSUE,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=QUOTA_ISSUE,
            translation_placeholders={"limit": f"{POSITIONS_MONTHLY_LIMIT:,}".replace(",", " ")},
        )


def _as_json(bus: WatchedVehicle) -> dict[str, Any]:
    return {
        "vehicle_id": bus.vehicle_id,
        "line": bus.line,
        "platform": bus.platform,
        "stop_id": bus.stop_id,
        "expected": bus.expected.isoformat(),
        "latitude": bus.latitude,
        "longitude": bus.longitude,
        "bearing": bus.bearing,
    }


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_subscribe_vehicles)


@websocket_api.websocket_command({vol.Required("type"): "bussar/vehicles/subscribe"})
@callback
def ws_subscribe_vehicles(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    entries = [
        e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED
    ]
    tracker = entries[0].runtime_data.tracker if entries else None
    if tracker is None:
        connection.send_error(
            msg["id"], "no_vehicle_key", "Ange en nyckel för GTFS Regional Realtime"
        )
        return

    @callback
    def forward(buses: list[WatchedVehicle]) -> None:
        connection.send_message(
            websocket_api.event_message(msg["id"], {"vehicles": [_as_json(b) for b in buses]})
        )

    # Bekräfta först, så att första positionerna inte når klienten före svaret.
    connection.send_result(msg["id"])
    connection.subscriptions[msg["id"]] = tracker.async_subscribe(forward)
