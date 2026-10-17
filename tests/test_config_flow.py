from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bussar.const import (
    CONF_LINE,
    CONF_PLATFORM,
    CONF_RUN_MINUTES,
    CONF_STOP_ID,
    CONF_WALK_MINUTES,
    CONF_WINDOW_MINUTES,
    DOMAIN,
)

from .conftest import (
    DEPARTURES_URL,
    STOP_A_ID,
    STOP_LOOKUP_URL,
    load_fixture,
    stop_lookup_payload,
)


async def test_user_enters_valid_api_key(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{STOP_LOOKUP_URL}Stockholm", json=stop_lookup_payload())

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "secret"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_API_KEY: "secret"}


async def test_invalid_api_key_shows_error(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{STOP_LOOKUP_URL}Stockholm", status=401)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "wrong"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_add_watched_line_by_searching_stop_and_picking_line_and_platform(
    hass: HomeAssistant, aioclient_mock
):
    aioclient_mock.get(f"{STOP_LOOKUP_URL}H%C3%A5llplats", json=stop_lookup_payload())
    aioclient_mock.get(f"{DEPARTURES_URL}{STOP_A_ID}", json=load_fixture("departures-stop-a.json"))
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_KEY: "secret"})
    entry.add_to_hass(hass)

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "line"), context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"query": "Hållplats"}
    )
    assert result["step_id"] == "stop"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_STOP_ID: STOP_A_ID}
    )
    assert result["step_id"] == "line"
    offered = [o["value"] for o in _select_options(result, "line_platform")]
    assert "10|A" in offered and "10|D" in offered and "20|B" in offered

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"line_platform": "10|A"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    subentry = next(iter(entry.subentries.values()))
    assert subentry.data == {
        CONF_STOP_ID: STOP_A_ID,
        "stop_name": "Hållplats A (Ort)",
        CONF_LINE: "10",
        CONF_PLATFORM: "A",
    }
    assert subentry.title == "10 läge A, Hållplats A (Ort)"


def _select_options(result, field: str) -> list[dict]:
    for key, validator in result["data_schema"].schema.items():
        if str(key) == field:
            return [
                o if isinstance(o, dict) else {"value": o, "label": o}
                for o in validator.config["options"]
            ]
    raise AssertionError(f"{field} saknas i formuläret")


async def _start_line_flow(hass, entry, aioclient_mock, departures_payload):
    aioclient_mock.get(f"{STOP_LOOKUP_URL}H%C3%A5llplats", json=stop_lookup_payload())
    aioclient_mock.get(f"{DEPARTURES_URL}{STOP_A_ID}", json=departures_payload)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "line"), context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"query": "Hållplats"}
    )
    return await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_STOP_ID: STOP_A_ID}
    )


async def test_same_line_and_platform_cannot_be_watched_twice(hass: HomeAssistant, aioclient_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_KEY: "secret"})
    entry.add_to_hass(hass)
    for _ in range(2):
        result = await _start_line_flow(
            hass, entry, aioclient_mock, load_fixture("departures-stop-a.json")
        )
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"], {"line_platform": "10|A"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(entry.subentries) == 1


async def test_line_can_be_entered_manually_when_no_departures_are_shown(
    hass: HomeAssistant, aioclient_mock
):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_KEY: "secret"})
    entry.add_to_hass(hass)

    result = await _start_line_flow(hass, entry, aioclient_mock, {"departures": []})
    assert result["step_id"] == "manual"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_LINE: "107", CONF_PLATFORM: "B"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    subentry = next(iter(entry.subentries.values()))
    assert (subentry.data[CONF_LINE], subentry.data[CONF_PLATFORM]) == ("107", "B")


async def test_integration_can_only_be_added_once(hass: HomeAssistant, aioclient_mock):
    MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={CONF_API_KEY: "a"}).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_reauth_replaces_api_key(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{STOP_LOOKUP_URL}Stockholm", json=stop_lookup_payload())
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={CONF_API_KEY: "old"})
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "new"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == "new"


async def test_unreadable_response_shows_cannot_connect(hass: HomeAssistant, aioclient_mock):
    aioclient_mock.get(f"{STOP_LOOKUP_URL}Stockholm", text="<html>Underhåll</html>")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "secret"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_line_not_among_upcoming_departures_can_be_entered_manually(
    hass: HomeAssistant, aioclient_mock
):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_KEY: "secret"})
    entry.add_to_hass(hass)

    result = await _start_line_flow(
        hass, entry, aioclient_mock, load_fixture("departures-stop-a.json")
    )
    other = _select_options(result, "line_platform")[-1]
    assert other["label"] == "Annan linje…"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"line_platform": other["value"]}
    )
    assert result["step_id"] == "manual"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_LINE: " 107 ", CONF_PLATFORM: " b "}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    subentry = next(iter(entry.subentries.values()))
    assert (subentry.data[CONF_LINE], subentry.data[CONF_PLATFORM]) == ("107", "B")
    assert subentry.title == "107 läge B, Hållplats A (Ort)"


async def test_manual_entry_of_watched_line_in_other_case_is_a_duplicate(
    hass: HomeAssistant, aioclient_mock
):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_KEY: "secret"})
    entry.add_to_hass(hass)
    payload = load_fixture("departures-stop-a.json")
    result = await _start_line_flow(hass, entry, aioclient_mock, payload)
    await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"line_platform": "10|A"}
    )

    result = await _start_line_flow(hass, entry, aioclient_mock, payload)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"line_platform": _select_options(result, "line_platform")[-1]["value"]}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_LINE: "10", CONF_PLATFORM: "a"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(entry.subentries) == 1


async def test_manual_entry_requires_both_line_and_platform(hass: HomeAssistant, aioclient_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_KEY: "secret"})
    entry.add_to_hass(hass)

    result = await _start_line_flow(hass, entry, aioclient_mock, {"departures": []})
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_LINE: "107", CONF_PLATFORM: "  "}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {"base": "missing_line_or_platform"}
    assert not entry.subentries


def _entry_with_line_10_a() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_KEY: "secret"},
        subentries_data=[
            {
                "subentry_type": "line",
                "title": "10 läge A, Hållplats A",
                "unique_id": f"{STOP_A_ID}_10_A",
                "data": {
                    CONF_STOP_ID: STOP_A_ID,
                    "stop_name": "Hållplats A",
                    CONF_LINE: "10",
                    CONF_PLATFORM: "A",
                },
            }
        ],
    )


async def _start_reconfigure(hass: HomeAssistant, entry: MockConfigEntry):
    subentry_id = next(iter(entry.subentries))
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "line"),
        context={"source": config_entries.SOURCE_RECONFIGURE, "subentry_id": subentry_id},
    )
    return subentry_id, result


async def test_walk_run_and_window_can_be_changed_per_watched_line(hass: HomeAssistant):
    entry = _entry_with_line_10_a()
    entry.add_to_hass(hass)

    subentry_id, result = await _start_reconfigure(hass, entry)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_WALK_MINUTES: 6, CONF_RUN_MINUTES: 2.5, CONF_WINDOW_MINUTES: 4}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    data = entry.subentries[subentry_id].data
    timing = (data[CONF_WALK_MINUTES], data[CONF_RUN_MINUTES], data[CONF_WINDOW_MINUTES])
    assert timing == (6, 2.5, 4)


async def test_run_time_longer_than_walk_time_is_rejected(hass: HomeAssistant):
    entry = _entry_with_line_10_a()
    entry.add_to_hass(hass)
    _, result = await _start_reconfigure(hass, entry)

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_WALK_MINUTES: 2, CONF_RUN_MINUTES: 3, CONF_WINDOW_MINUTES: 5}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "run_longer_than_walk"}
