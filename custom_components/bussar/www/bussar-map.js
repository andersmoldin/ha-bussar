// Kartan i Bussar-kortet (issue #7): HA:s egen ha-map, utfälld under raderna.
// Kartan zoomar en gång när den fälls ut och flyttar sig sedan aldrig själv.
// Räknelogik och prenumeration finns i map-model.js.

const version = new URL(import.meta.url).search;
const { VehicleFeed, mapPoints, stopPoints, vehicleMarkers } = await import(`./map-model.js${version}`);

const HEIGHT = 250;
const MARKER_SIZE = 24;
const STOP_SIZE = 14;
const FIT = { maxZoom: 16, pad: 0.15, animate: false };
// Så länge får ha-map på sig att ladda och starta sin kartmotor.
const LOAD_TIMEOUT_MS = 10000;

// HA:s standardfärg för --primary-color. Reservläget vill ha en färgsträng och förstår
// inte CSS-variabler, så där används den direkt.
const FALLBACK_COLOR = "#03a9f4";

const STATUS_TEXT = {
  waiting: "Bussar startar …",
  unavailable: "Bussar är inte igång.",
  invalid_key: "Nyckeln för fordonspositioner avvisades.",
  no_map: "Kartan kunde inte laddas.",
};

export const MAP_STYLE = `
  .toggle { display: flex; align-items: center; justify-content: center; gap: 6px; width: 100%; padding: 10px;
    border: 0; border-top: 1px solid var(--divider-color); background: none; color: var(--primary-color);
    font: inherit; font-size: 14px; font-weight: 500; cursor: pointer; }
  .toggle[hidden] { display: none; }
  .chev { transition: transform .25s; }
  .open .chev { transform: rotate(180deg); }
  .map { position: relative; height: ${HEIGHT}px; }
  .map[hidden] { display: none; }
  .map ha-map { height: ${HEIGHT}px; }
  .status { position: absolute; top: 8px; right: 8px; z-index: 1; padding: 2px 8px; border-radius: 6px; font-size: 12px;
    background: var(--card-background-color); color: var(--secondary-text-color); box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.3)); }
  .status[hidden] { display: none; }
  .row.selected { background: color-mix(in srgb, var(--primary-color) 12%, transparent); }
  .rows.selectable .row { cursor: pointer; }
`;

// Markörerna ligger i ha-map:s skuggträd, så deras stil sätts direkt på elementen.
function busElement(marker, selected) {
  const el = document.createElement("div");
  el.textContent = marker.line;
  Object.assign(el.style, {
    width: `${MARKER_SIZE}px`,
    height: `${MARKER_SIZE}px`,
    boxSizing: "border-box",
    borderRadius: "50%",
    border: "2px solid #fff",
    // Linjens färg, eller temats färger när ingen linjefärg är vald.
    background: marker.color ?? `var(--primary-color, ${FALLBACK_COLOR})`,
    color: marker.textColor ?? "var(--text-primary-color, #fff)",
    font: "700 11px/20px var(--ha-font-family-body, sans-serif)",
    textAlign: "center",
    boxShadow: "0 1px 3px rgba(0,0,0,.4)",
    transform: selected ? "scale(1.5)" : "",
    transition: "transform .2s",
  });
  return el;
}

function stopElement() {
  const el = document.createElement("div");
  Object.assign(el.style, {
    width: `${STOP_SIZE}px`,
    height: `${STOP_SIZE}px`,
    boxSizing: "border-box",
    borderRadius: "50%",
    border: "3px solid var(--primary-text-color, #212121)",
    background: "var(--card-background-color, #fff)",
  });
  return el;
}

const timeout = (ms) => new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), ms));

// HA laddar ha-map först när ett kartkort behövs. Ett osynligt kartkort hämtar den.
async function loadHaMap() {
  if (customElements.get("ha-map")) return;
  const load = async () => {
    const helpers = await window.loadCardHelpers();
    helpers.createCardElement({ type: "map", entities: [] });
    await customElements.whenDefined("ha-map");
  };
  await Promise.race([load(), timeout(LOAD_TIMEOUT_MS)]);
}

export class BusMap {
  constructor(root) {
    this._root = root;
    this.toggle = root.querySelector(".toggle");
    this._box = root.querySelector(".map");
    this._status = root.querySelector(".status");
    this._rows = root.querySelector(".rows");
    this._open = false;
    this._noKey = false;
    this._generation = 0;
    this._vehicles = [];
    this._handles = [];
    this._selected = null;
    this.toggle.addEventListener("click", () => this._setOpen(!this._open));
  }

  set hass(hass) {
    this._hass = hass;
  }

  set sensors(ids) {
    this._sensorIds = ids;
    this.toggle.hidden = this._noKey || ids.length === 0;
  }

  // Raden som visas på kartan, eller null. Nyckeln är samma som i map-model.js.
  select(key) {
    if (!this._open) return;
    this._selected = this._selected === key ? null : key;
    this._draw();
  }

  get selected() {
    return this._open ? this._selected : null;
  }

  disconnect() {
    this._setOpen(false);
  }

  _sensorStates() {
    return (this._sensorIds ?? []).map((id) => this._hass?.states[id]).filter(Boolean);
  }

  async _setOpen(open) {
    if (open === this._open) return;
    this._open = open;
    // En utfällning som avbryts medan ha-map laddas ska inte skapa någon karta.
    const generation = ++this._generation;
    this._root.classList.toggle("open", open);
    this.toggle.querySelector(".label").textContent = open ? "Dölj karta" : "Visa karta";
    this._box.hidden = !open;
    this._rows.classList.toggle("selectable", open);
    if (!open) {
      this._feed?.stop();
      this._feed = null;
      this._selected = null;
      this._vehicles = [];
      this._removeMap();
      this._root.dispatchEvent(new CustomEvent("bussar-map-closed"));
      return;
    }
    this._fitted = false;
    this._answered = false;
    this._showStatus("");
    try {
      await loadHaMap();
    } catch {
      if (generation === this._generation) this._showStatus(STATUS_TEXT.no_map);
      return;
    }
    if (generation !== this._generation) return;
    this._createMap();
    this._feed = new VehicleFeed(this._hass.connection, (state) => this._update(state));
    this._feed.start();
  }

  _createMap() {
    const map = document.createElement("ha-map");
    map.clickable = false;
    map.zoom = 14;
    // ha-map signalerar när kartmotorn är klar, även efter ett byte till Leaflet-reserven.
    // Kommer signalen aldrig ritas bussarna som prickar via det publika spår-gränssnittet.
    map.addEventListener("editing-available-changed", () => {
      clearTimeout(this._fallbackTimer);
      this._draw();
    });
    this._fallbackTimer = setTimeout(() => {
      this._fallback = true;
      this._draw();
    }, LOAD_TIMEOUT_MS);
    this._fallback = false;
    this._box.append(map);
    this._map = map;
  }

  _removeMap() {
    clearTimeout(this._fallbackTimer);
    this._clearMarkers();
    this._map?.remove();
    this._map = null;
  }

  _clearMarkers() {
    // Markörerna på en kartmotor som ha-map har bytt ut är redan borta med den.
    if (this._map?._engine === this._handlesEngine) this._handles.forEach((h) => h.remove());
    this._handles = [];
    this._handlesEngine = null;
  }

  _update({ status, vehicles }) {
    if (status === "no_vehicle_key") {
      // Ingen nyckel för fordonspositioner: ingen karta alls.
      this._noKey = true;
      this.toggle.hidden = true;
      this._setOpen(false);
      return;
    }
    this._vehicles = vehicles;
    // Medan Bussar startar finns inga bussar att zooma till ännu.
    if (status !== "waiting") this._answered = true;
    this._showStatus(STATUS_TEXT[status] ?? "");
    this._draw();
  }

  _showStatus(text) {
    this._status.textContent = text;
    this._status.hidden = !text;
  }

  _draw() {
    if (!this._map) return;
    const sensors = this._sensorStates();
    const markers = vehicleMarkers(this._vehicles, sensors);
    // Bussarna är inga entiteter, så de läggs ut via ha-map:s kartmotor (privat API).
    const engine = this._map._engine;
    if (engine?.addMarker) {
      this._drawWithEngine(engine, sensors, markers);
    } else if (this._fallback) {
      this._drawAsPaths(markers);
    }
  }

  // Reservläge om HA har ändrat sin kartmotor: varje buss blir ett spår med två likadana
  // punkter, vilket ha-map ritar som en prick. Ingen hållplats, markering eller zoom här.
  _drawAsPaths(markers) {
    this._map.paths = markers.map((m) => ({
      name: `Linje ${m.line}`,
      color: m.color ?? FALLBACK_COLOR,
      points: [m, m].map((p) => ({ point: [p.lat, p.lon], timestamp: new Date() })),
    }));
  }

  _drawWithEngine(engine, sensors, markers) {
    this._clearMarkers();
    this._handlesEngine = engine;
    for (const [lat, lon] of stopPoints(sensors)) {
      this._handles.push(
        engine.addMarker(stopElement(), [lat, lon], { size: [STOP_SIZE, STOP_SIZE], interactive: false, title: "Hållplats" }),
      );
    }
    for (const m of markers) {
      const selected = this._selected !== null && this._selected === m.row;
      this._handles.push(
        engine.addMarker(busElement(m, selected), [m.lat, m.lon], {
          size: [MARKER_SIZE, MARKER_SIZE],
          raised: selected,
          interactive: false,
          title: `Linje ${m.line}`,
        }),
      );
    }
    // En gång per utfällning, när Bussar har svarat: hem, hållplatser och kortets bussar.
    if (!this._fitted && this._answered) {
      this._fitted = true;
      const { latitude, longitude } = this._hass.config ?? {};
      const home = typeof latitude === "number" ? [latitude, longitude] : null;
      const shown = markers.map((m) => ({ latitude: m.lat, longitude: m.lon }));
      engine.fitBounds(mapPoints(sensors, shown, home), FIT);
    }
  }
}
