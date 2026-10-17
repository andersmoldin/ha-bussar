// Bussar-kortet: en rad per bevakad linje med en stapel som töms mot springgränsen.
// Design: variant A2 + N2 från prototypen (se issue #5). All logik finns i card-model.js.

import { rowModel } from "./card-model.js";

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
  .title + .row, .row:first-child { border-top: 0; }
  .badge { display: inline-flex; align-items: center; justify-content: center; min-width: 34px; height: 28px;
    padding: 0 8px; border-radius: 8px; font-weight: 700; font-size: 15px;
    color: var(--text-primary-color, #fff); background: var(--primary-color); }
  .dest { font-size: 15px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .right { text-align: right; line-height: 1.1; }
  .min { display: block; font-size: 22px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .time { font-size: 12px; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .late { color: var(--error-color, #db4437); font-weight: 600; }
  .early { color: var(--success-color, #43a047); font-weight: 600; }
  .live { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: 2px;
    background: var(--success-color, #43a047); animation: pulse 2s infinite; }
  @keyframes pulse { 50% { opacity: .35; } }
  @media (prefers-reduced-motion: reduce) { .live { animation: none; } }
  .bar { grid-column: 1 / -1; height: 10px; border-radius: 5px; overflow: hidden;
    background: color-mix(in srgb, var(--primary-text-color) 8%, transparent); }
  .fill { height: 100%; border-radius: 5px; background: var(--zone-color, transparent); transition: width .9s linear, background .4s; }
  .plenty { --zone-color: var(--bussar-plenty); }
  .go { --zone-color: var(--bussar-go); }
  .run { --zone-color: var(--bussar-run); }
  .empty { color: var(--secondary-text-color); }
`;

const escape = (text) =>
  String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function delayHtml(delay) {
  if (!delay) return "";
  return delay > 0 ? ` <span class="late">+${delay}</span>` : ` <span class="early">${delay}</span>`;
}

function rowHtml(entityId, stateObj, now, timeZone) {
  if (!stateObj) {
    return `<div class="row"><span class="badge">?</span><span class="dest empty">${escape(entityId)} saknas</span><span></span></div>`;
  }
  const row = rowModel(stateObj, now, timeZone);
  const zone = row.zone ?? "none";
  const label = row.zone ? ZONE_LABEL[row.zone] : "Ingen buss att hinna";
  const minutes = row.minutes === null ? "–" : `${row.minutes} min`;
  const time =
    row.clock === null
      ? ""
      : `${row.clock}${delayHtml(row.delay)}${row.followingClock ? ` · ${row.followingClock}` : ""}`;
  return `<div class="row ${zone}">
    <span class="badge">${escape(row.line)}</span>
    <span class="dest">${escape(row.destination ?? "")}</span>
    <span class="right"><span class="min">${row.live ? '<span class="live" title="Realtid"></span>' : ""}${minutes}</span><span class="time">${time}</span></span>
    <div class="bar" role="img" aria-label="${escape(label)}"><div class="fill" style="width:${(row.fill * 100).toFixed(1)}%"></div></div>
  </div>`;
}

class BussarCard extends HTMLElement {
  setConfig(config) {
    if (!Array.isArray(config.entities) || config.entities.length === 0) {
      throw new Error("Ange minst en sensor under entities");
    }
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  connectedCallback() {
    // Lokal nedräkning varje sekund mellan sensorns uppdateringar.
    this._timer = setInterval(() => this._render(), 1000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  getCardSize() {
    return 1 + (this._config?.entities.length ?? 1);
  }

  static getStubConfig(hass) {
    const entities = Object.keys(hass.states).filter(
      (id) => id.startsWith("sensor.") && hass.states[id].attributes.walk_seconds !== undefined,
    );
    return { title: "Bussar", entities };
  }

  _render() {
    if (!this._config || !this._hass) return;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card></ha-card>`;
    }
    const now = Date.now();
    const timeZone = this._hass.config?.time_zone;
    const title = this._config.title ? `<div class="title">${escape(this._config.title)}</div>` : "";
    this.shadowRoot.querySelector("ha-card").innerHTML =
      title + this._config.entities.map((id) => rowHtml(id, this._hass.states[id], now, timeZone)).join("");
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
