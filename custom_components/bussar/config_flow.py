"""Config flow för Bussar."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.selector import (
    BooleanSelector,
    ColorRGBSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util import dt as dt_util

from .api import TrafiklabAuthError, TrafiklabError, client_for, vehicle_client_for
from .const import (
    CONF_LINE,
    CONF_LINE_COLOR,
    CONF_PLATFORM,
    CONF_RUN_MINUTES,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    CONF_THEME_COLOR,
    CONF_VEHICLE_API_KEY,
    CONF_WALK_MINUTES,
    CONF_WINDOW_MINUTES,
    DOMAIN,
    POSITIONS_KEY_ISSUE,
    SUBENTRY_LINE,
    USAGE_POSITIONS,
)
from .departures import WatchedLine, line_choices, parse_departures
from .line_colors import as_rgb, line_color, with_line_color, without_line_color
from .schema import vol
from .zones import DEFAULT_TIMING

# Godtycklig sökning som bara används för att pröva nyckeln.
KEY_PROBE_QUERY = "Stockholm"
CONF_QUERY = "query"
CONF_LINE_PLATFORM = "line_platform"
# Valet för en linje som inte syns bland de kommande avgångarna.
OTHER_LINE = "other"

API_KEY_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): str})


def _pick_one(field: str, options: list[SelectOptionDict]) -> Any:
    return vol.Schema(
        {
            vol.Required(field): SelectSelector(
                SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
            )
        }
    )


class BussarConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_LINE: LineSubentryFlow}

    async def _validate_key(self, api_key: str) -> dict[str, str]:
        try:
            await client_for(self.hass, api_key).search_stops(KEY_PROBE_QUERY)
        except TrafiklabAuthError:
            return {"base": "invalid_auth"}
        except TrafiklabError:
            return {"base": "cannot_connect"}
        return {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        # En instans räcker: alla bevakade linjer delar nyckel och kvot.
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured(error="single_instance_allowed")
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._validate_key(user_input[CONF_API_KEY])
            if not errors:
                return self.async_create_entry(
                    title="Trafiklab", data={CONF_API_KEY: user_input[CONF_API_KEY]}
                )
        return self.async_show_form(step_id="user", data_schema=API_KEY_SCHEMA, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Lägg till, byt eller ta bort den valfria nyckeln för fordonspositioner.

        Huvudnyckeln byts via reauth.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            vehicle_key = (user_input.get(CONF_VEHICLE_API_KEY) or "").strip()
            if vehicle_key:
                if entry.state is ConfigEntryState.LOADED:
                    entry.runtime_data.usage.record(USAGE_POSITIONS, dt_util.now())
                try:
                    await vehicle_client_for(self.hass, vehicle_key).fetch()
                except TrafiklabAuthError:
                    errors[CONF_VEHICLE_API_KEY] = "invalid_auth"
                except TrafiklabError:
                    errors[CONF_VEHICLE_API_KEY] = "cannot_connect"
            if not errors:
                data = {k: v for k, v in entry.data.items() if k != CONF_VEHICLE_API_KEY}
                if vehicle_key:
                    data[CONF_VEHICLE_API_KEY] = vehicle_key
                ir.async_delete_issue(self.hass, DOMAIN, POSITIONS_KEY_ISSUE)
                return self.async_update_reload_and_abort(entry, data=data)
        current = user_input or entry.data
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_VEHICLE_API_KEY,
                        description={"suggested_value": current.get(CONF_VEHICLE_API_KEY)},
                    ): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._validate_key(user_input[CONF_API_KEY])
            if not errors:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates={CONF_API_KEY: user_input[CONF_API_KEY]}
                )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=API_KEY_SCHEMA, errors=errors
        )


def _minutes_selector(minimum: float) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum, max=60, step=0.5, unit_of_measurement="min", mode=NumberSelectorMode.BOX
        )
    )


def _timing_schema(current: Mapping[str, Any]) -> Any:
    shown = DEFAULT_TIMING.as_minutes() | {
        k: current[k]
        for k in (CONF_WALK_MINUTES, CONF_RUN_MINUTES, CONF_WINDOW_MINUTES)
        if k in current
    }
    return vol.Schema(
        {
            vol.Required(CONF_WALK_MINUTES, default=shown[CONF_WALK_MINUTES]): _minutes_selector(
                0.5
            ),
            vol.Required(CONF_RUN_MINUTES, default=shown[CONF_RUN_MINUTES]): _minutes_selector(0.5),
            vol.Required(
                CONF_WINDOW_MINUTES, default=shown[CONF_WINDOW_MINUTES]
            ): _minutes_selector(0),
        }
    )


class LineSubentryFlow(ConfigSubentryFlow):
    """Lägg till en bevakad linje: hållplats, linje och läge."""

    def __init__(self) -> None:
        self._stops: dict[str, str] = {}
        self._stop_id: str | None = None

    def _client(self):
        return client_for(self.hass, self._get_entry().data[CONF_API_KEY])

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
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

    async def async_step_stop(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if user_input is not None:
            self._stop_id = user_input[CONF_STOP_ID]
            return await self.async_step_line()
        options = [SelectOptionDict(value=i, label=n) for i, n in self._stops.items()]
        return self.async_show_form(step_id="stop", data_schema=_pick_one(CONF_STOP_ID, options))

    async def async_step_line(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        assert self._stop_id is not None
        if user_input is not None:
            if user_input[CONF_LINE_PLATFORM] == OTHER_LINE:
                return await self.async_step_manual()
            return self._create(WatchedLine.parse(user_input[CONF_LINE_PLATFORM]))
        try:
            choices = line_choices(parse_departures(await self._client().departures(self._stop_id)))
        except TrafiklabError:
            return self.async_abort(reason="cannot_connect")
        if not choices:
            # T.ex. nattetid eller gles linje: ange linje och läge själv.
            return await self.async_step_manual()
        options = [
            SelectOptionDict(
                value=watched.key,
                label=f"{watched.line} läge {watched.platform} → {', '.join(destinations)}",
            )
            for watched, destinations in choices.items()
        ]
        options.append(SelectOptionDict(value=OTHER_LINE, label="Annan linje…"))
        return self.async_show_form(
            step_id="line", data_schema=_pick_one(CONF_LINE_PLATFORM, options)
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            watched = WatchedLine(
                user_input[CONF_LINE].strip(), user_input[CONF_PLATFORM].strip().upper()
            )
            if watched.line and watched.platform:
                return self._create(watched)
            errors["base"] = "missing_line_or_platform"
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {vol.Required(CONF_LINE): str, vol.Required(CONF_PLATFORM): str}
            ),
            errors=errors,
        )

    def _create(self, watched: WatchedLine) -> SubentryFlowResult:
        assert self._stop_id is not None
        unique_id = f"{self._stop_id}_{watched.line}_{watched.platform}"
        if any(sub.unique_id == unique_id for sub in self._get_entry().subentries.values()):
            return self.async_abort(reason="already_configured")
        stop_name = self._stops[self._stop_id]
        return self.async_create_entry(
            title=f"{watched.line} läge {watched.platform}, {stop_name}",
            unique_id=unique_id,
            data={
                CONF_STOP_ID: self._stop_id,
                CONF_STOP_NAME: stop_name,
                CONF_LINE: watched.line,
                CONF_PLATFORM: watched.platform,
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Ändra gångtid, springtid och fönster för en bevakad linje, och linjens färg."""
        subentry = self._get_reconfigure_subentry()
        entry = self._get_entry()
        line = subentry.data[CONF_LINE]
        errors: dict[str, str] = {}
        if user_input is not None:
            timing = {
                k: v for k, v in user_input.items() if k not in (CONF_LINE_COLOR, CONF_THEME_COLOR)
            }
            if timing[CONF_RUN_MINUTES] > timing[CONF_WALK_MINUTES]:
                errors["base"] = "run_longer_than_walk"
            else:
                # Färgen gäller linjenumret, alltså alla bevakade linjer med samma nummer.
                options = dict(entry.options)
                if user_input.get(CONF_THEME_COLOR):
                    options = without_line_color(options, line)
                elif CONF_LINE_COLOR in user_input:
                    options = with_line_color(options, line, user_input[CONF_LINE_COLOR])
                self.hass.config_entries.async_update_entry(entry, options=options)
                # Varje ändring laddar om posten. Ändrades bara färgen räcker den omladdningen.
                if all(subentry.data.get(k) == v for k, v in timing.items()):
                    return self.async_abort(reason="reconfigure_successful")
                return self.async_update_and_abort(entry, subentry, data_updates=timing)
        color = line_color(entry, line)
        shown = (user_input or {}).get(CONF_LINE_COLOR) or (as_rgb(color) if color else None)
        schema = _timing_schema(user_input or subentry.data).extend(
            {
                vol.Optional(CONF_LINE_COLOR, description={"suggested_value": shown}): (
                    ColorRGBSelector()
                ),
                vol.Optional(CONF_THEME_COLOR, default=False): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
            description_placeholders={"line": line},
        )
