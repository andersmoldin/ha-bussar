# Datafynd från Trafiklab (UL)

Verifierat mot riktiga svar 2026-10-17. Anonymiserade exempel ligger i `tests/fixtures/`, och skriptet `scripts/record_fixtures.py` spelar in nya.

## Avgångar (Trafiklab Realtime APIs)

- `GET https://realtime-api.trafiklab.se/v1/departures/{stop_group_id}?key=...` ger alla linjer vid hållplatsen ungefär 60 minuter framåt, ca 5–10 kB.
- Hållplats-ID:n (`stop_groups[].id`, RIKSHALLPLATS) gäller fortfarande efter ID-bytet 2026-09-15.
- Per avgång finns `scheduled`, `realtime`, `delay` (sekunder, kan vara negativ), `canceled` och `is_realtime`.
- `route` har `designation` (linjenummer), `direction` och `destination.name`. `direction` och `destination` är inte samma text.
- `scheduled_platform`/`realtime_platform` har `designation` (läge, t.ex. "A"). Varje riktning har ett eget läge vid en hållplats.
- `trip.trip_id` finns på varje avgång.
- `is_realtime` är `true` för turer som har startat. Turer längre fram har `false` och `delay: 0`.
- Destinationen för samma linje och riktning kan variera mellan turer, så filtrering på destination är skör.

## Fordonspositioner (GTFS Regional Realtime)

- `GET https://opendata.samtrafiken.se/gtfs-rt/ul/VehiclePositions.pb?key=...` ger hela UL i ett svar: 284 entiteter och ca 6 kB gzip / 20 kB okomprimerat en lördagskväll.
- **Kräver `Accept-Encoding: gzip`.** Annars svarar servern HTTP 406.
- Bara ungefär en tredjedel av fordonen har `trip.trip_id`. `route_id` saknas helt.
- **`trip_id` i VehiclePositions är samma som `trip.trip_id` i avgångs-API:t.** Ett fordon kopplas alltså till linje, riktning och läge genom att matcha mot kommande avgångar vid de bevakade hållplatserna. Statisk GTFS behövs inte.
- Fordon som ännu inte har startat sin tur saknar position kopplad till turen, och dyker upp först när turen startar.
