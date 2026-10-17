from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bussar.const import (
    CONF_LINE,
    CONF_PLATFORM,
    CONF_STOP_ID,
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
