import asyncio
from datetime import datetime, timedelta

import pytest
from homeassistant.config_entries import ConfigEntryState, ConfigSubentryData
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

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


async def test_reload_tells_open_subscriptions_to_subscribe_again(
    hass, entry, aioclient_mock, freezer, hass_ws_client
):
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "bussar/vehicles/subscribe"})
    await client.receive_json()
    await client.receive_json()

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    event = await asyncio.wait_for(client.receive_json(), timeout=2)
    assert event["event"] == {"vehicles": [], "resubscribe": True}
    calls = _position_calls(aioclient_mock)
    await _tick(hass, freezer, 60)
    assert _position_calls(aioclient_mock) == calls


async def test_new_month_clears_the_repair_issue_and_resets_the_usage_sensor(
    hass, aioclient_mock, freezer, hass_ws_client, hass_storage
):
    hass_storage["bussar.usage"] = {
        "version": 1,
        "key": "bussar.usage",
        "data": {"2026-10": {"positions": 28_000}},
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
    subscribed = await client.receive_json()
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "positions_quota_reached") is not None
    positions_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_usage_positions"
    )
    assert hass.states.get(positions_id).state == "28000"
    await client.send_json_auto_id({"type": "unsubscribe_events", "subscription": subscribed["id"]})
    await client.receive_json()

    freezer.move_to(datetime(2026, 11, 1, 0, 0, 30, tzinfo=TRAFIKLAB_TZ))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert ir.async_get(hass).async_get_issue(DOMAIN, "positions_quota_reached") is None
    assert hass.states.get(positions_id).state == "0"


async def test_subscribing_while_the_entry_reloads_says_not_ready(
    hass, entry, aioclient_mock, freezer, hass_ws_client
):
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "bussar/vehicles/subscribe"})
    await client.receive_json()
    await client.receive_json()
    release = asyncio.Event()

    async def slow_departures(method, url, data):
        await release.wait()
        return AiohttpClientMockResponse(method, url, json=load_fixture("departures-stop-a.json"))

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{DEPARTURES_URL}{STOP_A_ID}", side_effect=slow_departures)
    aioclient_mock.get(f"{DEPARTURES_URL}{STOP_B_ID}", json=load_fixture("departures-stop-b.json"))
    aioclient_mock.get(VEHICLE_POSITIONS_URL, content=vehicle_positions_bytes())
    reload = hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))

    event = await asyncio.wait_for(client.receive_json(), timeout=2)
    assert event["event"] == {"vehicles": [], "resubscribe": True}
    await asyncio.wait_for(_until(lambda: entry.state is ConfigEntryState.SETUP_IN_PROGRESS), 2)
    await client.send_json_auto_id({"type": "bussar/vehicles/subscribe"})
    result = await client.receive_json()
    assert not result["success"]
    assert result["error"]["code"] == "not_ready"

    release.set()
    assert await reload
    await client.send_json_auto_id({"type": "bussar/vehicles/subscribe"})
    assert (await client.receive_json())["success"]
    assert "vehicles" in (await client.receive_json())["event"]


async def _until(condition) -> None:
    while not condition():
        await asyncio.sleep(0)


async def test_rejected_vehicle_key_stops_polling_and_raises_a_repair_issue(
    hass, entry, aioclient_mock, freezer, hass_ws_client, caplog
):
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{DEPARTURES_URL}{STOP_A_ID}", json=load_fixture("departures-stop-a.json"))
    aioclient_mock.get(f"{DEPARTURES_URL}{STOP_B_ID}", json=load_fixture("departures-stop-b.json"))
    aioclient_mock.get(VEHICLE_POSITIONS_URL, status=401)
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "bussar/vehicles/subscribe"})
    assert (await client.receive_json())["success"]
    event = await client.receive_json()
    await _tick(hass, freezer, 60)

    assert event["event"] == {"vehicles": [], "error": "invalid_key"}
    assert _position_calls(aioclient_mock) == 1
    assert ir.async_get(hass).async_get_issue(DOMAIN, "positions_key_invalid") is not None
    warnings = [r for r in caplog.records if r.levelname == "WARNING" and "bussar" in r.name]
    assert warnings and not any("vehicles" in r.getMessage() for r in warnings)
    assert not any("opendata" in r.getMessage() for r in warnings)

    await client.send_json_auto_id({"type": "bussar/vehicles/subscribe"})
    assert (await client.receive_json())["success"]
    assert (await client.receive_json())["event"] == {"vehicles": [], "error": "invalid_key"}
    await _tick(hass, freezer, 60)
    assert _position_calls(aioclient_mock) == 1

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{DEPARTURES_URL}{STOP_A_ID}", json=load_fixture("departures-stop-a.json"))
    aioclient_mock.get(f"{DEPARTURES_URL}{STOP_B_ID}", json=load_fixture("departures-stop-b.json"))
    aioclient_mock.get(VEHICLE_POSITIONS_URL, content=vehicle_positions_bytes())
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VEHICLE_API_KEY: "new-vehicles"}
    )
    await hass.async_block_till_done()

    assert result["reason"] == "reconfigure_successful"
    assert ir.async_get(hass).async_get_issue(DOMAIN, "positions_key_invalid") is None


async def test_validating_a_new_vehicle_key_counts_as_a_position_request(
    hass, entry, aioclient_mock, freezer
):
    positions_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_usage_positions"
    )
    assert hass.states.get(positions_id).state == "0"

    result = await entry.start_reconfigure_flow(hass)
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VEHICLE_API_KEY: "new-vehicles"}
    )
    await hass.async_block_till_done()

    assert _position_calls(aioclient_mock) == 1
    assert hass.states.get(positions_id).state == "1"


async def test_successful_fetch_clears_the_rejected_key_issue(
    hass, entry, aioclient_mock, freezer, hass_ws_client
):
    ir.async_create_issue(
        hass,
        DOMAIN,
        "positions_key_invalid",
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="positions_key_invalid",
    )
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "bussar/vehicles/subscribe"})
    await client.receive_json()
    await client.receive_json()

    assert ir.async_get(hass).async_get_issue(DOMAIN, "positions_key_invalid") is None


async def test_subscribing_without_any_entry_is_unavailable(hass, hass_ws_client):
    assert await async_setup_component(hass, DOMAIN, {})
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "bussar/vehicles/subscribe"})
    result = await client.receive_json()

    assert result["error"]["code"] == "unavailable"


async def test_subscribing_when_setup_failed_is_unavailable(
    hass, aioclient_mock, freezer, hass_ws_client
):
    await hass.config.async_set_time_zone("Europe/Stockholm")
    aioclient_mock.get(f"{DEPARTURES_URL}{STOP_A_ID}", status=401)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={CONF_API_KEY: "wrong", CONF_VEHICLE_API_KEY: "vehicles"},
        subentries_data=[_line(STOP_A_ID, "10", "A")],
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": "bussar/vehicles/subscribe"})
    result = await client.receive_json()

    assert result["error"]["code"] == "unavailable"
