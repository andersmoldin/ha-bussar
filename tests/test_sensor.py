from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_API_KEY, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.bussar.const import (
    CONF_LINE,
    CONF_PLATFORM,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    DOMAIN,
)

from .conftest import DEPARTURES_URL, STOP_A_ID, STOP_B_ID, load_fixture

STOCKHOLM = ZoneInfo("Europe/Stockholm")
RECORDED_AT = datetime(2026, 10, 17, 19, 43, 36, tzinfo=STOCKHOLM)


def _line(stop_id: str, stop_name: str, line: str, platform: str) -> ConfigSubentryData:
    return ConfigSubentryData(
        subentry_type="line",
        title=f"{line} läge {platform}, {stop_name}",
        unique_id=f"{stop_id}_{line}_{platform}",
        data={
            CONF_STOP_ID: stop_id,
            CONF_STOP_NAME: stop_name,
            CONF_LINE: line,
            CONF_PLATFORM: platform,
        },
    )


@pytest.fixture
async def entry(hass: HomeAssistant, aioclient_mock) -> MockConfigEntry:
    await hass.config.async_set_time_zone("Europe/Stockholm")
    aioclient_mock.get(f"{DEPARTURES_URL}{STOP_A_ID}", json=load_fixture("departures-stop-a.json"))
    aioclient_mock.get(f"{DEPARTURES_URL}{STOP_B_ID}", json=load_fixture("departures-stop-b.json"))
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_KEY: "secret"},
        subentries_data=[
            _line(STOP_A_ID, "Hållplats A", "10", "A"),
            _line(STOP_A_ID, "Hållplats A", "20", "B"),
            _line(STOP_B_ID, "Hållplats B", "40", "A"),
        ],
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _state(hass: HomeAssistant, entry: MockConfigEntry, line: str, platform: str):
    registry = er.async_get(hass)
    subentry_id = next(
        sid
        for sid, sub in entry.subentries.items()
        if sub.data[CONF_LINE] == line and sub.data[CONF_PLATFORM] == platform
    )
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, subentry_id)
    assert entity_id is not None
    return hass.states.get(entity_id)


async def test_sensor_shows_minutes_and_time_of_next_departure(
    hass: HomeAssistant, entry, freezer
):
    freezer.move_to(RECORDED_AT)

    await _setup(hass, entry)

    line_10 = _state(hass, entry, "10", "A")
    assert line_10.state == "1"
    assert line_10.attributes["unit_of_measurement"] == "min"
    assert line_10.attributes["departure_time"] == "19:44"
    assert _state(hass, entry, "20", "B").state == "12"
    assert _state(hass, entry, "40", "A").state == "16"


async def test_one_request_per_stop_per_minute(
    hass: HomeAssistant, entry, aioclient_mock, freezer
):
    freezer.move_to(RECORDED_AT)
    await _setup(hass, entry)
    assert aioclient_mock.call_count == 2

    freezer.tick(timedelta(minutes=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert aioclient_mock.call_count == 4
    assert _state(hass, entry, "10", "A").state == "13"


async def test_no_requests_during_night(
    hass: HomeAssistant, entry, aioclient_mock, freezer
):
    freezer.move_to(datetime(2026, 10, 17, 23, 30, tzinfo=STOCKHOLM))

    await _setup(hass, entry)
    freezer.tick(timedelta(minutes=5))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert aioclient_mock.call_count == 0
    assert _state(hass, entry, "10", "A").state == STATE_UNKNOWN
