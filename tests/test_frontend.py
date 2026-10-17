from unittest.mock import patch

from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bussar.const import DOMAIN

CARD_URL_PREFIX = "/bussar_static/bussar-card.js"


async def test_card_is_served_and_registered_with_the_frontend(hass: HomeAssistant, hass_client):
    assert await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_API_KEY: "secret"})
    entry.add_to_hass(hass)

    with patch("custom_components.bussar.frontend.add_extra_js_url") as add_js:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    (registered_url,) = [call.args[1] for call in add_js.call_args_list]
    assert registered_url.startswith(CARD_URL_PREFIX + "?v=")
    client = await hass_client()
    for path in (CARD_URL_PREFIX, "/bussar_static/card-model.js"):
        resp = await client.get(path)
        assert resp.status == 200, path
        assert "javascript" in resp.headers["Content-Type"]
