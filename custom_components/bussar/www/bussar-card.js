// Bussar-kortet: en rad per bevakad linje med en stapel som töms mot springgränsen.
// Design från prototypen (issue #5): variant A2, med aktuell avgång under destinationen
// och nästa buss under minuterna. All räknelogik finns i card-model.js.
// Två kompakta lägen (layout i YAML): compact har allt på en rad med stapeln mellan
// destination och minuter, dense är normal-layoutens uppbyggnad hopdragen till en textrad.

// Samma version som kortet laddades med, så att en HACS-uppdatering inte blandar
// nytt kort med en gammal cachad card-model.js.
const version = new URL(import.meta.url).search;
const { rowModel } = await import(`./card-model.js${version}`);
const { LAYOUTS, cardConfig, cardSize } = await import(`./card-config.js${version}`);
const { rowKey } = await import(`./map-model.js${version}`);
const { BusMap, MAP_STYLE } = await import(`./bussar-map.js${version}`);

const ZONE_LABEL = {
  plenty: "Gott om tid",
  go: "Nu passar det att gå",
  run: "Spring",
};

const STYLE = `
  :host { --bussar-plenty: var(--success-color, #43a047); --bussar-go: #f4c20d; --bussar-run: var(--warning-color, #ffa600); }
  .title { padding: 14px 16px 4px; font-size: 18px; }
  .row { padding: 12px 16px; border-top: 1px solid var(--divider-color); display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto; gap: 4px 12px; align-items: center; }
  .rows > .row:first-child { border-top: 0; }
  .badge { display: inline-flex; align-items: center; justify-content: center; min-width: 34px; height: 28px;
    padding: 0 8px; border-radius: 8px; font-weight: 700; font-size: 15px;
    color: var(--text-primary-color, #fff); background: var(--primary-color); }
  .left, .right { line-height: 1.15; min-width: 0; }
  .right { text-align: right; }
  .dest { display: block; font-size: 15px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .min { display: block; font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .sub { display: block; font-size: 13px; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .late { color: var(--error-color, #db4437); font-weight: 600; }
  .early { color: var(--success-color, #43a047); font-weight: 600; }
  .live { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: 3px;
    background: var(--success-color, #43a047); animation: pulse 2s infinite; }
  .live[hidden] { display: none; }
  @keyframes pulse { 50% { opacity: .35; } }
  @media (prefers-reduced-motion: reduce) { .live { animation: none; } }
  .bars { grid-column: 1 / -1; display: grid; gap: 4px; }
  .bar { height: 10px; border-radius: 5px; overflow: hidden;
    background: color-mix(in srgb, var(--primary-text-color) 8%, transparent); }
  .fill { height: 100%; width: 0; border-radius: 5px; background: var(--zone-color, transparent);
    transition: width .9s linear, background .4s; }
  .bar.following { height: 5px; border-radius: 3px; }
  .bar.following .fill { border-radius: 3px; opacity: .55; }
  .bar[hidden] { display: none; }
  .plenty { --zone-color: var(--bussar-plenty); }
  .go { --zone-color: var(--bussar-go); }
  .run { --zone-color: var(--bussar-run); }
  .hint { padding: 16px; color: var(--secondary-text-color); }
  .foll, .min-delay { display: none; }
${MAP_STYLE}
  /* Båda kompakta lägena: mindre titel och kartknapp, och smal kolumn känns igen på radernas bredd. */
  .compact .title, .dense .title { padding: 10px 16px 2px; font-size: 16px; }
  .compact .toggle, .dense .toggle { padding: 6px; font-size: 13px; }
  .compact .rows, .dense .rows { container-type: inline-size; }
  .compact .live, .dense .live { width: 6px; height: 6px; margin-right: 4px; vertical-align: 2px; }

  /* compact: bricka, destination, staplar och minuter på en rad; inget klockslag. */
  .compact .row { padding: 6px 16px; grid-template-columns: auto minmax(0, 1fr) minmax(64px, 1.6fr) auto;
    gap: 0 10px; min-height: 22px; }
  .compact .badge { min-width: 28px; height: 22px; padding: 0 6px; font-size: 12px; border-radius: 6px; }
  .compact .dest { font-size: 14px; }
  .compact .now { display: none; }
  .compact .bars { grid-column: 3; grid-row: 1; gap: 3px; }
  .compact .bar { height: 5px; border-radius: 3px; }
  .compact .bar.following { height: 3px; }
  .compact .right { grid-column: 4; grid-row: 1; min-width: 88px; }
  .compact .min { font-size: 15px; }
  .compact .min-delay { display: inline; font-size: 11px; }
  .compact .min-delay:empty { display: none; }
  .compact .next { font-size: 11px; }
  @container (max-width: 300px) {
    .compact .row { grid-template-columns: auto minmax(0, 1fr) auto; gap: 3px 10px; }
    .compact .right { grid-column: 3; min-width: 0; }
    .compact .bars { grid-column: 1 / -1; grid-row: 2; }
  }

  /* dense: destination och klockslag på en rad, "nästa" efter minuterna, tunna staplar.
     Med två streck får nästa buss en egen liten rad mellan staplarna. */
  .dense .row { padding: 7px 16px; gap: 3px 10px; }
  .dense .badge { min-width: 30px; height: 24px; font-size: 13px; border-radius: 7px; }
  .dense .left { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .dense .dest { display: inline; font-size: 14px; }
  .dense .now { display: inline; font-size: 12px; margin-left: 6px; }
  .dense .min { display: inline; font-size: 16px; }
  .dense .next { display: inline; font-size: 12px; margin-left: 6px; }
  .dense .next:empty { display: none; }
  .dense .bars { display: contents; }
  .dense .bar { grid-column: 1 / -1; height: 4px; border-radius: 2px; }
  .dense .bar.following { height: 3px; }
  .dense .foll { grid-column: 1 / -1; display: flex; justify-content: space-between; font-size: 12px;
    color: var(--secondary-text-color); font-variant-numeric: tabular-nums; margin-top: 1px; }
  .dense .foll[hidden] { display: none; }
  @container (max-width: 300px) { .dense .next { display: none; } }`;

function delayNode(delay) {
  const minutes = Number(delay);
  if (!minutes) return null;
  const span = document.createElement("span");
  span.className = minutes > 0 ? "late" : "early";
  span.textContent = minutes > 0 ? `+${minutes}` : `${minutes}`;
  return span;
}

// Zonklassen sitter på stapeln, så att varje stapel får färgen för sin egen buss.
function showBar(bar, model, prefix, emptyLabel) {
  bar.classList.remove("plenty", "go", "run");
  if (model?.zone) bar.classList.add(model.zone);
  const zone = model?.zone ? ZONE_LABEL[model.zone] : null;
  bar.setAttribute("aria-label", zone ? (prefix ? `${prefix}: ${zone.toLowerCase()}` : zone) : emptyLabel);
  bar.firstElementChild.style.width = `${((model?.fill ?? 0) * 100).toFixed(1)}%`;
}

// En rad byggs en gång. Varje sekund uppdateras bara text, klasser och stapelns bredd,
// så att stapeln glider och realtidspunkten pulserar utan att startas om.
class Row {
  constructor(entityId, followingBar, layout) {
    this.entityId = entityId;
    this.followingBar = followingBar;
    this.layout = layout;
    this.el = document.createElement("div");
    this.el.className = "row";
    this.el.innerHTML = `
      <span class="badge"></span>
      <span class="left"><span class="dest"></span><span class="sub now"></span></span>
      <span class="right"><span class="min"><span class="live" title="Realtid" hidden></span><span class="minutes"></span><span class="min-delay"></span></span><span class="sub next"></span></span>
      <div class="bars">
        <div class="bar current" role="img"><div class="fill"></div></div>
        <div class="foll" hidden><span class="foll-clock"></span><span class="foll-min"></span></div>
        <div class="bar following" role="img" hidden><div class="fill"></div></div>
      </div>`;
    const q = (sel) => this.el.querySelector(sel);
    this.badge = q(".badge");
    this.dest = q(".dest");
    this.now = q(".now");
    this.live = q(".live");
    this.minutes = q(".minutes");
    this.minDelay = q(".min-delay");
    this.next = q(".next");
    this.foll = q(".foll");
    this.follClock = q(".foll-clock");
    this.follMin = q(".foll-min");
    this.bar = q(".bar.current");
    this.followingBarEl = q(".bar.following");
    this.followingBarEl.hidden = !followingBar;
    // Nästa buss egen lilla rad finns bara i dense med två streck.
    this.foll.hidden = !(followingBar && layout === "dense");
  }

  update(stateObj, nowMs, timeZone, selected) {
    this.key = stateObj ? rowKey(stateObj) : null;
    this.el.classList.toggle("selected", this.key !== null && this.key === selected);
    if (!stateObj) {
      this._show({ line: "?", destination: `${this.entityId} saknas` });
      return;
    }
    const row = rowModel(stateObj, nowMs, timeZone);
    this._show(row);
  }

  _show(row) {
    this.badge.textContent = row.line ?? "?";
    // Utan vald linjefärg gäller temats färger från stilen.
    this.badge.style.background = row.color ?? "";
    this.badge.style.color = row.textColor ?? "";
    this.dest.textContent = row.destination ?? "";
    this.live.hidden = !row.live;
    this.minutes.textContent = row.minutes === null || row.minutes === undefined ? "–" : `${row.minutes} min`;
    this.now.replaceChildren(...(row.clock ? [row.clock, ...this._delay(row.delay)] : []));
    // compact har inget klockslag, så förseningen hänger på minuterna där.
    this.minDelay.replaceChildren(...(this.layout === "compact" ? this._delay(row.delay) : []));
    if (this.followingBar) {
      // Med två streck visar raden nästa buss som minuter, i linje med dess stapel.
      const next = row.following ? `nästa ${row.following.minutes} min` : "";
      if (this.layout === "dense") {
        // dense: nästa buss står på egen rad ovanför sin stapel, med klockslaget till vänster.
        this.next.textContent = "";
        this.follClock.textContent = row.following ? (row.followingClock ?? "") : "";
        this.follMin.textContent = next;
      } else {
        this.next.textContent = next;
      }
      showBar(this.followingBarEl, row.following, "Nästa buss", "Ingen nästa buss");
    } else {
      // compact visar inga klockslag, inte heller för nästa buss.
      this.next.textContent = row.followingClock && this.layout !== "compact" ? `nästa ${row.followingClock}` : "";
    }
    showBar(this.bar, row, "", "Ingen buss att hinna");
  }

  _delay(delay) {
    const node = delayNode(delay);
    return node ? [" ", node] : [];
  }
}

class BussarCard extends HTMLElement {
  setConfig(config) {
    this._config = cardConfig(config);
    this._rows = null;
    this._render();
  }

  set hass(hass) {
    const previous = this._hass;
    this._hass = hass;
    // HA skickar hass vid varje tillståndsändring i hela systemet. Rita bara om när
    // någon av kortets sensorer har ändrats; nedräkningen sköts av timern.
    const changed =
      !previous || !this._config || this._config.entities.some((id) => previous.states[id] !== hass.states[id]);
    if (changed) this._render();
  }

  connectedCallback() {
    this._timer = setInterval(() => this._render(), 1000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    // Kortet syns inte längre: fäll ihop kartan så att positionshämtningen slutar.
    this._map?.disconnect();
  }

  getCardSize() {
    return this._config ? cardSize(this._config) : 2;
  }

  static getStubConfig(hass) {
    // Bussar-sensorer känns igen på plattformen i entitetsregistret, även när de är otillgängliga.
    const entities = Object.keys(hass.states).filter(
      (id) => id.startsWith("sensor.") && hass.entities?.[id]?.platform === "bussar",
    );
    return { title: "Bussar", entities };
  }

  _build() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card><div class="title" hidden></div><div class="rows"></div>
      <button class="toggle" type="button"><span class="label">Visa karta</span><span class="chev">▾</span></button>
      <div class="map" hidden><div class="status" hidden></div></div></ha-card>`;
    this._map = new BusMap(this.shadowRoot.querySelector("ha-card"));
    // Tryck på en rad medan kartan är utfälld för att markera radens bussar.
    this.shadowRoot.querySelector(".rows").addEventListener("click", (ev) => {
      const row = this._rows?.find((r) => r.el.contains(ev.target));
      if (row?.key) {
        this._map.select(row.key);
        this._render();
      }
    });
    this.shadowRoot.querySelector("ha-card").addEventListener("bussar-map-closed", () => this._render());
  }

  _render() {
    if (!this._config || !this._hass) return;
    if (!this.shadowRoot) this._build();
    // Läget sitter som klass på kortet; stilen för compact och dense hänger på den.
    const card = this.shadowRoot.querySelector("ha-card");
    for (const layout of LAYOUTS) card.classList.toggle(layout, this._config.layout === layout);
    const title = this.shadowRoot.querySelector(".title");
    title.textContent = this._config.title ?? "";
    title.hidden = !this._config.title;
    const rows = this.shadowRoot.querySelector(".rows");
    if (this._rows === null) {
      this._rows = this._config.entities.map((id) => new Row(id, this._config.following_bar, this._config.layout));
      rows.replaceChildren(...this._rows.map((r) => r.el));
      if (this._rows.length === 0) {
        rows.innerHTML = `<div class="hint">Lägg till Bussar-sensorer under entities.</div>`;
      }
    }
    this._map.hass = this._hass;
    this._map.sensors = this._config.entities;
    const now = Date.now();
    const timeZone = this._hass.config?.time_zone;
    const selected = this._map.selected;
    for (const row of this._rows) row.update(this._hass.states[row.entityId], now, timeZone, selected);
  }
}

if (!customElements.get("bussar-card")) {
  customElements.define("bussar-card", BussarCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "bussar-card",
    name: "Bussar",
    description: "När är det dags att gå till bussen?",
  });
}
