# ha-bussar

Home Assistant-integration som visar när det är dags att gå till bussen. Se `SPEC.md`.

## Integritet

Checka aldrig in riktiga hållplatsnamn eller hållplats-ID:n. Användarens egna värden finns i `.local/` (gitignored). Testdata ska anonymiseras.

## Agent skills

### Issue tracker

Issues ligger i GitHub Issues i andersmoldin/ha-bussar och hanteras med `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

Standardetiketterna: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` och `docs/adr/` i roten. See `docs/agents/domain.md`.
