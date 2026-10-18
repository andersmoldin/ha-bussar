# Bussar för Home Assistant

Visar när nästa buss går från dina hållplatser, med realtid från [Trafiklab](https://www.trafiklab.se). Data: Trafiklab, CC BY 4.0.

## Installera

1. HACS → ⋮ → **Custom repositories** → lägg till `https://github.com/andersmoldin/ha-bussar`, typ **Integration**.
2. Installera **Bussar** och starta om Home Assistant.
3. Inställningar → Enheter och tjänster → **Lägg till integration** → **Bussar**, och ange din nyckel för Trafiklab Realtime APIs.
4. På integrationen: **Lägg till bevakad linje** → sök hållplats → välj linje och läge. Syns inte linjen bland kommande avgångar (nattetid eller gles linje), välj **Annan linje…** och ange linje och läge själv.

Varje bevakad linje blir en sensor med minuter till nästa buss **som går att hinna med**. Har bussen mindre än springtiden kvar går sensorn vidare till nästa.

| Attribut | Betydelse |
|---|---|
| `zone` | `plenty` (gott om tid), `go` (nu passar det att gå) eller `run` (du hinner om du springer). Exakt på gångtiden räknas som `go`. `null` när ingen buss går att hinna. |
| `departure_time`, `expected`, `scheduled` | Klockslag samt förväntad och planerad tid (ISO) |
| `line`, `platform`, `destination` | Linje, hållplatsläge och bussens destination |
| `stop_id`, `stop_latitude`, `stop_longitude` | Hållplatsens ID och position, för kartan. Positionen saknas tills första svaret har hämtats. Namnen är valda så att HA:s egen kartvy inte ritar sensorerna. |
| `delay_minutes`, `is_realtime` | Försening i hela minuter (halva uppåt, negativ om bussen är tidig), och om tiden är realtid eller tidtabell |
| `canceled` | Kommande inställda turer på linjen (planerad tid) |
| `following_departure_time`, `following_expected` | Bussen efter |
| `walk_seconds`, `run_seconds`, `window_seconds` | Zongränserna, så att ett kort kan räkna ner själv |

Sensorn skrivs om vid varje minutbyte och zongräns, även mellan hämtningarna. Gångtid (4,5 min), springtid (2 min) och fönster (5 min) ändras per linje via **⋮ → Ändra gångtider** på den bevakade linjen.

## Kortet

Integrationen laddar kortet själv, så ingen resurs behöver läggas till. Redigera en dashboard → **Lägg till kort** → **Bussar**, eller använd YAML:

```yaml
type: custom:bussar-card
title: Bussar
entities:
  - sensor.10_lage_a_hallplats_a
  - sensor.40_lage_a_hallplats_b
```

Varje rad visar linje och destination med aktuell avgång under (`23:40 +2`), och till höger minuter kvar med nästa buss under (`sedan 23:55`). Stapeln töms mot springgränsen och är grön (gott om tid), gul (nu passar det att gå) eller orange (spring). En pulserande grön punkt betyder realtid. Kortet räknar ner varje sekund och byter till nästa buss vid springgränsen.

Med **Visa karta** fälls en karta ut under raderna (kräver nyckeln för positioner, se nedan). Varje buss är en cirkel i samma färg som radens stapel, med linjenumret inuti, och hållplatserna är ringar. Kartan zoomar en gång när den fälls ut, till hemmet, hållplatserna och kortets bussar, och flyttar sig sedan inte själv. Tryck på en rad för att markera radens bussar. Utan positionsnyckel försvinner knappen vid första försöket. Kartan är HA:s egen, och därför kräver Bussar Home Assistant 2026.10 eller senare.

Förhandsvisa kortet utan HA: `python3 -m http.server 8765` och öppna `http://localhost:8765/tests/js/preview.html?theme=dark`.

## Bussarnas positioner (för kartan)

Kartan behöver en extra, valfri nyckel för **GTFS Regional Realtime** från samma Trafiklab-projekt. Ange den via Inställningar → Enheter och tjänster → Bussar → ⋮ → **Konfigurera om**. Lämna fältet tomt där för att ta bort nyckeln. Slutar nyckeln fungera stoppas hämtningen och en notis visas under Inställningar → Reparationer tills du konfigurerar om.

Positionerna hämtas **bara medan kartan är utfälld och kortet syns**: kortet öppnar en prenumeration (websocket-kommandot `bussar/vehicles/subscribe`), och integrationen hämtar var 10:e sekund så länge någon prenumererar. Bara bussar på väg mot dina bevakade hållplatser i bevakad riktning skickas. De kopplas via kommande avgångar, så kartan är tom på natten (23–05) när avgångar inte hämtas. Laddas integrationen om medan kartan är utfälld ber den kortet att prenumerera igen.

## Kvoter

Enheten **Trafiklab** under integrationen har två diagnostiksensorer, *Anrop avgångar denna månad* och *Anrop positioner denna månad*, så att du kan följa förbrukningen.

Positioner stoppas vid 28 000 anrop per kalendermånad (Bronze-gränsen är 30 000). Då visas en notis under Inställningar → Reparationer, och hämtningen fortsätter den 1:a nästa månad.

En hållplats hämtas en gång per minut, delat mellan alla linjer där, och inga anrop görs 23–05 när det redan finns data; efter omstart eller omladdning nattetid hämtas varje hållplats en gång. Två hållplatser blir ungefär 67 000 anrop per månad, vilket ryms i Bronze-nivåns 100 000.

## Utveckling

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
scripts/check test   # pytest och node --test tests/js/*.test.mjs
```

Se `SPEC.md` och `docs/data-findings.md`.
