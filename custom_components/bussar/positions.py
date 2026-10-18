"""Bussarnas positioner, hämtade bara medan någon prenumererar (kartan i kortet visas)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import TrafiklabAuthError, TrafiklabError, VehiclePositionsClient
from .const import DOMAIN, POSITIONS_KEY_ISSUE, POSITIONS_MONTHLY_LIMIT, USAGE_POSITIONS
from .coordinator import StopCoordinator
from .departures import WatchedLine
from .schema import vol
from .usage import UsageCounter
from .vehicles import WatchedVehicle, parse_vehicle_positions, watched_vehicles

_LOGGER = logging.getLogger(__name__)

POLL_INTERVAL = timedelta(seconds=10)
QUOTA_ISSUE = "positions_quota_reached"

type Subscriber = Callable[[list[WatchedVehicle]], None]
type OnClosed = Callable[[dict[str, Any]], None]


class VehicleTracker:
    """Hämtar positioner var 10:e sekund så länge minst en prenumerant finns."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: VehiclePositionsClient,
        coordinators: dict[str, StopCoordinator],
        watched: set[tuple[str, WatchedLine]],
        usage: UsageCounter,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._client = client
        self._coordinators = coordinators
        self._watched = watched
        self._usage = usage
        self._subscribers: dict[int, tuple[Subscriber, OnClosed]] = {}
        self._next_id = 0
        self._unsub_interval: CALLBACK_TYPE | None = None
        self._polling = False

    @callback
    def async_subscribe(self, subscriber: Subscriber, on_closed: OnClosed) -> CALLBACK_TYPE:
        self._next_id += 1
        key = self._next_id
        self._subscribers[key] = (subscriber, on_closed)
        if self._unsub_interval is None:
            self._unsub_interval = async_track_time_interval(
                self._hass, self._async_poll, POLL_INTERVAL
            )
            self._entry.async_create_background_task(
                self._hass, self._async_poll(dt_util.now()), "bussar first vehicle poll"
            )

        @callback
        def unsubscribe() -> None:
            self._subscribers.pop(key, None)
            if not self._subscribers:
                self._stop_polling()

        return unsubscribe

    @callback
    def async_stop(self) -> None:
        """Stoppa hämtningen och be öppna prenumerationer att prenumerera igen.

        Anropas när posten laddas om eller ur, t.ex. efter ny nyckel eller ny linje.
        """
        self._close({"vehicles": [], "resubscribe": True})

    def _close(self, event: dict[str, Any]) -> None:
        self._stop_polling()
        subscribers, self._subscribers = self._subscribers, {}
        for _, on_closed in subscribers.values():
            on_closed(event)

    def _stop_polling(self) -> None:
        if self._unsub_interval is not None:
            self._unsub_interval()
            self._unsub_interval = None

    async def _async_poll(self, now: datetime) -> None:
        # Hoppa över om förra hämtningen inte är klar, så att anrop inte överlappar.
        if not self._subscribers or self._polling:
            return
        self._polling = True
        try:
            await self._async_poll_once(now)
        finally:
            self._polling = False

    async def _async_poll_once(self, now: datetime) -> None:
        if not self._usage.within_limit(USAGE_POSITIONS, now, limit=POSITIONS_MONTHLY_LIMIT):
            self._raise_quota_issue()
            return
        ir.async_delete_issue(self._hass, DOMAIN, QUOTA_ISSUE)
        self._usage.record(USAGE_POSITIONS, now)
        try:
            payload = await self._client.fetch()
        except TrafiklabAuthError as err:
            _LOGGER.warning(
                "Nyckeln för bussarnas positioner godkändes inte (%s); slutar hämta dem", err
            )
            ir.async_create_issue(
                self._hass,
                DOMAIN,
                POSITIONS_KEY_ISSUE,
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=POSITIONS_KEY_ISSUE,
            )
            self._close({"vehicles": [], "error": "invalid_key"})
            return
        except TrafiklabError as err:
            _LOGGER.debug("Kunde inte hämta fordonspositioner: %s", err)
            return
        departures = {
            stop_id: coordinator.data or [] for stop_id, coordinator in self._coordinators.items()
        }
        buses = watched_vehicles(
            parse_vehicle_positions(payload), departures, self._watched, now=dt_util.now()
        )
        for subscriber, _ in list(self._subscribers.values()):
            subscriber(buses)

    def _raise_quota_issue(self) -> None:
        async_raise_quota_issue(self._hass)


@callback
def async_raise_quota_issue(hass: HomeAssistant) -> None:
    ir.async_create_issue(
        hass,
        DOMAIN,
        QUOTA_ISSUE,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=QUOTA_ISSUE,
        translation_placeholders={"limit": f"{POSITIONS_MONTHLY_LIMIT:,}".replace(",", " ")},
    )


@callback
def async_refresh_quota_issue(hass: HomeAssistant, usage: UsageCounter, now: datetime) -> None:
    """Ta bort notisen när en ny månad har börjat (eller visa den om gränsen är nådd)."""
    if usage.within_limit(USAGE_POSITIONS, now, limit=POSITIONS_MONTHLY_LIMIT):
        ir.async_delete_issue(hass, DOMAIN, QUOTA_ISSUE)
    else:
        async_raise_quota_issue(hass)


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


# Posten laddas (om) eller väntar på att försöka igen: kortet kan prenumerera om en stund.
_COMING_UP = {
    ConfigEntryState.UNLOAD_IN_PROGRESS,
    ConfigEntryState.NOT_LOADED,
    ConfigEntryState.SETUP_IN_PROGRESS,
    ConfigEntryState.SETUP_RETRY,
}


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_subscribe_vehicles)


@websocket_api.websocket_command({vol.Required("type"): "bussar/vehicles/subscribe"})
@callback
def ws_subscribe_vehicles(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    entries = hass.config_entries.async_entries(
        DOMAIN, include_ignore=False, include_disabled=False
    )
    loaded = [e for e in entries if e.state is ConfigEntryState.LOADED]
    if not loaded and any(e.state in _COMING_UP for e in entries):
        connection.send_error(msg["id"], "not_ready", "Bussar is still being set up")
        return
    tracker = loaded[0].runtime_data.tracker if loaded else None
    if tracker is None:
        connection.send_error(
            msg["id"], "no_vehicle_key", "No GTFS Regional Realtime key is configured"
        )
        return

    @callback
    def forward(buses: list[WatchedVehicle]) -> None:
        connection.send_message(
            websocket_api.event_message(msg["id"], {"vehicles": [_as_json(b) for b in buses]})
        )

    @callback
    def closed(event: dict[str, Any]) -> None:
        # Posten laddas om (kortet ska prenumerera igen) eller nyckeln slutade gälla.
        connection.subscriptions.pop(msg["id"], None)
        connection.send_message(websocket_api.event_message(msg["id"], event))

    # Bekräfta först, så att första positionerna inte når klienten före svaret.
    connection.send_result(msg["id"])
    connection.subscriptions[msg["id"]] = tracker.async_subscribe(forward, closed)
