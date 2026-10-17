"""Config flow för Bussar."""

from __future__ import annotations

from collections.abc import Mapping
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
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import TrafiklabAuthError, TrafiklabError, client_for
from .const import (
    CONF_LINE,
    CONF_PLATFORM,
    CONF_RUN_MINUTES,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    CONF_WALK_MINUTES,
    CONF_WINDOW_MINUTES,
    DOMAIN,
    SUBENTRY_LINE,
)
from .departures import WatchedLine, line_choices, parse_departures
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


def _minutes() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=0, max=60, step=0.5, unit_of_measurement="min", mode=NumberSelectorMode.BOX
        )
    )


def _timing_schema(current: Mapping[str, Any]) -> Any:
    defaults = {
        CONF_WALK_MINUTES: DEFAULT_TIMING.walk.total_seconds() / 60,
        CONF_RUN_MINUTES: DEFAULT_TIMING.run.total_seconds() / 60,
        CONF_WINDOW_MINUTES: DEFAULT_TIMING.window.total_seconds() / 60,
    }
    return vol.Schema(
        {
            vol.Required(key, default=current.get(key, default)): _minutes()
            for key, default in defaults.items()
        }
    )


class LineSubentryFlow(ConfigSubentryFlow):
    """Lägg till en bevakad linje: hållplats, linje och läge."""

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Ändra gångtid, springtid och fönster för en bevakad linje."""
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_RUN_MINUTES] > user_input[CONF_WALK_MINUTES]:
                errors["base"] = "run_longer_than_walk"
            else:
                return self.async_update_and_abort(
                    self._get_entry(), subentry, data_updates=user_input
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_timing_schema(user_input or subentry.data),
            errors=errors,
        )

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
