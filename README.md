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
| `delay_minutes`, `is_realtime` | Försening i hela minuter (halva uppåt, negativ om bussen är tidig), och om tiden är realtid eller tidtabell |
| `canceled` | Kommande inställda turer på linjen (planerad tid) |
| `following_departure_time`, `following_expected` | Bussen efter |
| `walk_seconds`, `run_seconds`, `window_seconds` | Zongränserna, så att ett kort kan räkna ner själv |

Sensorn skrivs om vid varje minutbyte och zongräns, även mellan hämtningarna. Gångtid (4,5 min), springtid (2 min) och fönster (5 min) ändras per linje via **⋮ → Ändra gångtider** på den bevakade linjen.

## Kvoter

En hållplats hämtas en gång per minut, delat mellan alla linjer där, och inga anrop görs 23–05 när det redan finns data; efter omstart eller omladdning nattetid hämtas varje hållplats en gång. Två hållplatser blir ungefär 67 000 anrop per månad, vilket ryms i Bronze-nivåns 100 000.

## Utveckling

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
```

Se `SPEC.md` och `docs/data-findings.md`.
