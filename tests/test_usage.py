from datetime import datetime

from homeassistant.core import HomeAssistant

from custom_components.bussar.departures import TRAFIKLAB_TZ
from custom_components.bussar.usage import UsageCounter

OCT = datetime(2026, 10, 17, 19, 0, tzinfo=TRAFIKLAB_TZ)
NOV = datetime(2026, 11, 1, 0, 0, tzinfo=TRAFIKLAB_TZ)


async def test_counts_survive_a_restart(hass: HomeAssistant):
    counter = UsageCounter(hass)
    await counter.async_load()
    counter.record("positions", OCT)
    counter.record("positions", OCT)
    counter.record("departures", OCT)
    await counter.async_save()

    restarted = UsageCounter(hass)
    await restarted.async_load()

    assert restarted.count("positions", OCT) == 2
    assert restarted.count("departures", OCT) == 1


async def test_counts_start_over_in_a_new_month(hass: HomeAssistant):
    counter = UsageCounter(hass)
    await counter.async_load()
    counter.record("positions", OCT)

    assert counter.count("positions", NOV) == 0


async def test_limit_is_reached_at_the_cap(hass: HomeAssistant):
    counter = UsageCounter(hass)
    await counter.async_load()
    for _ in range(3):
        counter.record("positions", OCT)

    assert counter.within_limit("positions", OCT, limit=4) is True
    counter.record("positions", OCT)
    assert counter.within_limit("positions", OCT, limit=4) is False
    assert counter.within_limit("positions", NOV, limit=4) is True
