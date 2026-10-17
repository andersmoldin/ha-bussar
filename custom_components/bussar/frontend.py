"""Serverar Bussar-kortet och laddar det i HA:s frontend."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STATIC_URL = "/bussar_static"
CARD_FILE = "bussar-card.js"
_CARD_REGISTERED = f"{DOMAIN}_card_registered"


async def async_register_card(hass: HomeAssistant) -> None:
    """Registrera kortet en gång per HA-start, oavsett antal omladdningar."""
    if hass.data.get(_CARD_REGISTERED):
        return
    www = Path(__file__).parent / "www"
    await hass.http.async_register_static_paths([StaticPathConfig(STATIC_URL, str(www), True)])
    # Versionen i URL:en gör att webbläsare och appen hämtar nytt kort efter en uppdatering.
    version = (await async_get_integration(hass, DOMAIN)).version
    try:
        add_extra_js_url(hass, f"{STATIC_URL}/{CARD_FILE}?v={version}")
    except KeyError:
        _LOGGER.warning("HA:s frontend är inte laddad, så Bussar-kortet registreras inte")
    # Först när allt gått bra, så att ett misslyckat försök görs om vid nästa omladdning.
    hass.data[_CARD_REGISTERED] = True
