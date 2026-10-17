# Bussar för Home Assistant

Visar när nästa buss går från dina hållplatser, med realtid från [Trafiklab](https://www.trafiklab.se). Data: Trafiklab, CC BY 4.0.

## Installera

1. HACS → ⋮ → **Custom repositories** → lägg till `https://github.com/andersmoldin/ha-bussar`, typ **Integration**.
2. Installera **Bussar** och starta om Home Assistant.
3. Inställningar → Enheter och tjänster → **Lägg till integration** → **Bussar**, och ange din nyckel för Trafiklab Realtime APIs.
4. På integrationen: **Lägg till bevakad linje** → sök hållplats → välj linje och läge. Syns inte linjen bland kommande avgångar (nattetid eller gles linje), välj **Annan linje…** och ange linje och läge själv.

Varje bevakad linje blir en sensor med minuter till nästa avgång. Klockslag, destination och förväntad tid finns som attribut.

## Kvoter

En hållplats hämtas en gång per minut, delat mellan alla linjer där, och inga anrop görs 23–05. Två hållplatser blir ungefär 67 000 anrop per månad, vilket ryms i Bronze-nivåns 100 000.

## Utveckling

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
```

Se `SPEC.md` och `docs/data-findings.md`.
