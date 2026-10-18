# ha-bussar – spec

Home Assistant-integration som visar när det är dags att gå till bussen: så att man hinner, men slipper stå i regn och kyla i onödan.

Första trafikbolaget är UL (Uppsala län) via Trafiklab. Designen ska gå att utöka till fler bolag som har data hos Trafiklab.

## Konfiguration (per bevakad linje)

All konfiguration görs i HA:s UI (config flow). Den finns inte i repot.

- Hållplats (sök via Trafiklab Stop Lookup; använd `stop_groups[].id`)
- Linje
- Riktning, angiven som hållplatsläge (t.ex. "A"). Varje riktning har ett eget läge, medan destinationen kan variera mellan turer i samma riktning (se `docs/data-findings.md`). Config flow visar kommande avgångar med läge och destination så att rätt läge är lätt att välja.
- Gångtid och springtid till hållplatsen

Användarens egna hållplatser, linjer och riktningar finns i `.local/`, som inte checkas in.

## Mätare (en per bevakad linje)

Zon beräknas från tid kvar till förväntad avgång. Exempel med 4,5 min gångtid och 2 min springtid:

| Zon | Villkor (tid till avgång) |
|---|---|
| 🟢 Gott om tid | > gångtid + 5 min |
| 🟡 Nu passar det att gå | gångtid till gångtid + 5 min |
| 🟠 Du hinner om du springer | springtid till gångtid |
| ⚫ Kört | < springtid → mätaren byter till nästa buss |

Gångtid, springtid och bredden på det gula fönstret ska vara inställbara.

Varje mätare visar:

- zon
- "om X min" och klockslag
- realtid eller tidtabell
- försening (t.ex. "+3")
- nästa buss efter

Mätaren räknar ner lokalt varje sekund och rättar sig när ny data kommer.

## Karta

- Fälls ut under mätarna i samma kort (Visa karta/Dölj karta), 250 px hög. HA:s egen `<ha-map>`.
- Bussar i bevakad riktning på bevakade linjer, som en cirkel med linjenumret i linjens färg (temats färg om ingen är vald)
- Bevakade hållplatser
- Zoomar en gång vid utfällning så att hem (HA:s hemposition), hållplatser och kortets bussar syns, och flyttar sig sedan aldrig själv
- Tryck på en rad markerar radens bussar
- Inga linjesträckningar i v1 (kräver statisk GTFS)

## Data och kvoter (Trafiklab Bronze)

| Flöde | Källa | Takt | Kvot/månad |
|---|---|---|---|
| Avgångar | Trafiklab Realtime APIs, `GET /v1/departures/{areaId}` | var 60:e s per hållplats, 05–23 | ~32 000 per hållplats av 100 000 totalt |
| Fordonspositioner | GTFS Regional Realtime, `gtfs-rt/{operator}/VehiclePositions.pb` | var 10:e s, endast när kartan är utfälld | hård spärr vid 28 000 av 30 000 |

- Två separata API-nycklar, en per API.
- Avgångs-API:t cachar 60 s, så tätare anrop är meningslösa.
- Ett anrop per hållplats täcker alla linjer där.
- Inga anrop 23–05 när data redan finns; saknas data (omstart, omladdning) hämtas varje hållplats en gång.
- Silver nekas för privata avgångstavlor, så vi kör på Bronze.
- ResRobot används inte. Det saknar realtid för UL och är deprecated.

## Arkitektur

- Egen custom integration i Python, domän `bussar`, med config flow för API-nycklar och bevakade linjer.
- **All logik i sensorer:** zon, nästa buss, försening. Kortet ritar bara upp dem, så att en e-ink-skärm senare kan läsa samma sensorer.
- Lovelace-kortet (mätare och karta) levereras och registreras av integrationen. Ett repo, en installation.
- Kartan prenumererar hos integrationen medan den är utfälld och kortet syns, och bara då hämtas positioner.
- Installeras via HACS som custom repository.

## Tester

- Tester för zonlogik, filtrering på linje och riktning samt nedräkning.
- Testdata är inspelade API-svar som anonymiserats. Inga riktiga hållplatsnamn eller ID:n checkas in.
- Live-anrop testas för hand.

## Senare

- E-ink-skärm
- Eventuellt en "gå nu"-notis
- Fler trafikbolag

## Byggordning

1. Skapa två API-nycklar på trafiklab.se: Trafiklab Realtime APIs och GTFS Regional Realtime.
2. Skript som hämtar och sparar avgångssvar för de bevakade hållplatserna, för att verifiera riktningstexter och realtid.
3. Integration med sensorer och tester.
4. Kort med mätare.
5. Karta med positioner endast när den visas.
