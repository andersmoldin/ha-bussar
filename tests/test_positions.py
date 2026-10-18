from datetime import datetime, timedelta

import pytest
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.bussar.const import (
    CONF_LINE,
    CONF_PLATFORM,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    CONF_VEHICLE_API_KEY,
    DOMAIN,
)
from custom_components.bussar.departures import TRAFIKLAB_TZ

from .conftest import (
    DEPARTURES_URL,
    STOP_A_ID,
    STOP_B_ID,
    VEHICLE_POSITIONS_URL,
    load_fixture,
    vehicle_positions_bytes,
)

RECORDED_AT = datetime(2026, 10, 17, 19, 43, 36, tzinfo=TRAFIKLAB_TZ)


@pytest.fixture(autouse=True)
def frozen_at_recording(freezer):
    # Före hass och websocket-token, så att token inte är utfärdad "i framtiden".
    freezer.move_to(RECORDED_AT)


def _line(stop_id: str, line: str, platform: str) -> ConfigSubentryData:
    return ConfigSubentryData(
        subentry_type="line",
        title=f"{line} läge {platform}",
        unique_id=f"{stop_id}_{line}_{platform}",
        data={
            CONF_STOP_ID: stop_id,
            CONF_STOP_NAME: "Hållplats",
            CONF_LINE: line,
            CONF_PLATFORM: platform,
        },
    )


@pytest.fixture
async def entry(hass: HomeAssistant, aioclient_mock, freezer) -> MockConfigEntry:
    await hass.config.async_set_time_zone("Europe/Stockholm")
    aioclient_mock.get(f"{DEPARTURES_URL}{STOP_A_ID}", json=load_fixture("departures-stop-a.json"))
    aioclient_mock.get(f"{DEPARTURES_URL}{STOP_B_ID}", json=load_fixture("departures-stop-b.json"))
    aioclient_mock.get(VEHICLE_POSITIONS_URL, content=vehicle_positions_bytes())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={CONF_API_KEY: "secret", CONF_VEHICLE_API_KEY: "vehicles"},
        subentries_data=[
            _line(STOP_A_ID, "10", "A"),
            _line(STOP_A_ID, "20", "A"),
            _line(STOP_B_ID, "40", "A"),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _position_calls(aioclient_mock) -> int:
    return sum(
        1 for call in aioclient_mock.mock_calls if str(call[1]).startswith(VEHICLE_POSITIONS_URL)
    )


async def _tick(hass: HomeAssistant, freezer, seconds: int) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_no_position_requests_without_a_subscriber(hass, entry, aioclient_mock, freezer):
    await _tick(hass, freezer, 120)

    assert _position_calls(aioclient_mock) == 0


async def test_subscriber_gets_watched_buses_every_ten_seconds_until_unsubscribed(
    hass, entry, aioclient_mock, freezer, hass_ws_client
):
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "bussar/vehicles/subscribe"})
    result = await client.receive_json()
    assert result["success"], result
    event = await client.receive_json()
    buses = event["event"]["vehicles"]
    assert sorted((b["line"], b["platform"]) for b in buses) == [("10", "A"), ("20", "A")]
    assert {"latitude", "longitude", "bearing", "expected", "vehicle_id"} <= set(buses[0])
    assert _position_calls(aioclient_mock) == 1

    await _tick(hass, freezer, 10)
    await client.receive_json()
    assert _position_calls(aioclient_mock) == 2

    await client.send_json_auto_id({"type": "unsubscribe_events", "subscription": result["id"]})
    assert (await client.receive_json())["success"]
    await _tick(hass, freezer, 60)
    assert _position_calls(aioclient_mock) == 2


async def test_quota_cap_stops_requests_and_raises_a_repair_issue(
    hass, aioclient_mock, freezer, hass_ws_client, hass_storage
):
    hass_storage["bussar.usage"] = {
        "version": 1,
        "key": "bussar.usage",
        "data": {"2026-10": {"positions": 27_999}},
    }
    await hass.config.async_set_time_zone("Europe/Stockholm")
    aioclient_mock.get(f"{DEPARTURES_URL}{STOP_A_ID}", json=load_fixture("departures-stop-a.json"))
    aioclient_mock.get(VEHICLE_POSITIONS_URL, content=vehicle_positions_bytes())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={CONF_API_KEY: "secret", CONF_VEHICLE_API_KEY: "vehicles"},
        subentries_data=[_line(STOP_A_ID, "10", "A")],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "bussar/vehicles/subscribe"})
    await client.receive_json()
    await client.receive_json()
    await _tick(hass, freezer, 30)

    assert _position_calls(aioclient_mock) == 1
    assert ir.async_get(hass).async_get_issue(DOMAIN, "positions_quota_reached") is not None


async def test_subscribing_without_a_vehicle_key_is_an_error(
    hass, aioclient_mock, freezer, hass_ws_client
):
    await hass.config.async_set_time_zone("Europe/Stockholm")
    aioclient_mock.get(f"{DEPARTURES_URL}{STOP_A_ID}", json=load_fixture("departures-stop-a.json"))
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={CONF_API_KEY: "secret"},
        subentries_data=[_line(STOP_A_ID, "10", "A")],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "bussar/vehicles/subscribe"})
    result = await client.receive_json()

    assert not result["success"]
    assert result["error"]["code"] == "no_vehicle_key"


async def test_diagnostic_sensors_count_requests_this_month(
    hass, entry, aioclient_mock, freezer, hass_ws_client
):
    registry = er.async_get(hass)
    departures_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_usage_departures"
    )
    positions_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_usage_positions"
    )
    assert hass.states.get(departures_id).state == "2"
    assert hass.states.get(positions_id).state == "0"
    assert registry.async_get(positions_id).entity_category == "diagnostic"

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "bussar/vehicles/subscribe"})
    await client.receive_json()
    await client.receive_json()
    await hass.async_block_till_done()

    assert hass.states.get(positions_id).state == "1"
