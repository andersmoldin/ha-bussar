"""Config flow för Bussar."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import TrafiklabAuthError, TrafiklabClient, TrafiklabError
from .const import (
    CONF_LINE,
    CONF_PLATFORM,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    DOMAIN,
    SUBENTRY_LINE,
)
from .departures import parse_departures
from .schema import vol

# Godtycklig sökning som bara används för att pröva nyckeln.
KEY_PROBE_QUERY = "Stockholm"
CONF_QUERY = "query"
CONF_LINE_PLATFORM = "line_platform"


class BussarConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_LINE: LineSubentryFlow}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = TrafiklabClient(async_get_clientsession(self.hass), user_input[CONF_API_KEY])
            try:
                await client.search_stops(KEY_PROBE_QUERY)
            except TrafiklabAuthError:
                errors["base"] = "invalid_auth"
            except TrafiklabError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title="Trafiklab", data={CONF_API_KEY: user_input[CONF_API_KEY]}
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )


class LineSubentryFlow(ConfigSubentryFlow):
    """Lägg till en bevakad linje: hållplats, linje och läge."""

    def __init__(self) -> None:
        self._stops: dict[str, str] = {}
        self._stop_id: str | None = None

    def _client(self) -> TrafiklabClient:
        entry = self._get_entry()
        return TrafiklabClient(async_get_clientsession(self.hass), entry.data[CONF_API_KEY])

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                stops = await self._client().search_stops(user_input[CONF_QUERY])
            except TrafiklabError:
                errors["base"] = "cannot_connect"
            else:
                if stops:
                    self._stops = {s.id: s.name for s in stops}
                    return await self.async_step_stop()
                errors["base"] = "no_stops"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_QUERY): str}),
            errors=errors,
        )

    async def async_step_stop(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._stop_id = user_input[CONF_STOP_ID]
            return await self.async_step_line()
        options = [SelectOptionDict(value=i, label=n) for i, n in self._stops.items()]
        return self.async_show_form(
            step_id="stop",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STOP_ID): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
                    )
                }
            ),
        )

    async def async_step_line(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        assert self._stop_id is not None
        stop_name = self._stops[self._stop_id]
        if user_input is not None:
            line, platform = user_input[CONF_LINE_PLATFORM].split("|", 1)
            return self.async_create_entry(
                title=f"{line} läge {platform}, {stop_name}",
                data={
                    CONF_STOP_ID: self._stop_id,
                    CONF_STOP_NAME: stop_name,
                    CONF_LINE: line,
                    CONF_PLATFORM: platform,
                },
            )
        try:
            departures = parse_departures(await self._client().departures(self._stop_id))
        except TrafiklabError:
            return self.async_abort(reason="cannot_connect")
        # En rad per linje och läge, med destinationerna som syns i kommande avgångar.
        combos: dict[str, list[str]] = {}
        for d in departures:
            if d.platform is None:
                continue
            dests = combos.setdefault(f"{d.line}|{d.platform}", [])
            if d.destination not in dests:
                dests.append(d.destination)
        if not combos:
            return self.async_abort(reason="no_departures")
        options = [
            SelectOptionDict(
                value=key,
                label=f"{key.split('|')[0]} läge {key.split('|')[1]} → {', '.join(dests)}",
            )
            for key, dests in sorted(combos.items(), key=lambda kv: _sort_key(kv[0]))
        ]
        return self.async_show_form(
            step_id="line",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LINE_PLATFORM): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
                    )
                }
            ),
        )


def _sort_key(key: str) -> tuple[int, str, str]:
    line, platform = key.split("|", 1)
    return (int(line) if line.isdigit() else 10**6, line, platform)
