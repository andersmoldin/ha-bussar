// Kartan i Bussar-kortet (issue #7): HA:s egen ha-map, utfälld under raderna.
// Kartan zoomar en gång när den fälls ut och flyttar sig sedan aldrig själv.
// Räknelogik och prenumeration finns i map-model.js.

const version = new URL(import.meta.url).search;
const { VehicleFeed, mapPoints, vehicleMarkers } = await import(`./map-model.js${version}`);

const HEIGHT = 250;
const MARKER_SIZE = 24;
const STOP_SIZE = 14;
const FIT = { maxZoom: 16, pad: 0.15, animate: false };

const ZONE_COLOR = {
  plenty: "var(--bussar-plenty)",
  go: "var(--bussar-go)",
  run: "var(--bussar-run)",
};
// Samma färger som ovan, för spåren i reservläget där ha-map vill ha en färgsträng.
const ZONE_HEX = { plenty: "#43a047", go: "#f4c20d", run: "#ffa600" };
const NO_ZONE = "#9e9e9e";

const STATUS_TEXT = {
  waiting: "Bussar startar …",
  unavailable: "Bussar är inte igång.",
  invalid_key: "Nyckeln för fordonspositioner avvisades.",
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
    background: ZONE_COLOR[marker.zone] ?? NO_ZONE,
    color: "#fff",
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

// HA laddar ha-map först när ett kartkort behövs. Ett osynligt kartkort hämtar den.
async function loadHaMap() {
  if (customElements.get("ha-map")) return;
  const helpers = await window.loadCardHelpers?.();
  helpers?.createCardElement({ type: "map", entities: [] });
  await customElements.whenDefined("ha-map");
}

export class BusMap {
  constructor(root) {
    this._root = root;
    this.toggle = root.querySelector(".toggle");
    this._box = root.querySelector(".map");
    this._status = root.querySelector(".status");
    this._rows = root.querySelector(".rows");
    this._open = false;
    this.noKey = false;
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
    await loadHaMap();
    if (!this._open) return;
    this._createMap();
    this._feed = new VehicleFeed(this._hass.connection, (state) => this._update(state));
    this._feed.start();
  }

  _createMap() {
    const map = document.createElement("ha-map");
    map.clickable = false;
    map.zoom = 14;
    // ha-map signalerar att kartmotorn är klar, även efter ett byte till Leaflet-reserven.
    map.addEventListener("editing-available-changed", () => {
      this._handles = [];
      this._draw();
    });
    this._box.append(map);
    this._map = map;
  }

  _removeMap() {
    this._handles.forEach((h) => h.remove());
    this._handles = [];
    this._map?.remove();
    this._map = null;
  }

  _update({ status, vehicles }) {
    if (status === "no_vehicle_key") {
      // Ingen nyckel för fordonspositioner: ingen karta alls.
      this.noKey = true;
      this.toggle.hidden = true;
      this._setOpen(false);
      return;
    }
    this._vehicles = vehicles;
    this._answered = true;
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
    const markers = vehicleMarkers(this._vehicles, sensors, Date.now());
    // Bussarna är inga entiteter, så de läggs ut via ha-map:s kartmotor. Finns den inte
    // (HA har ändrat den) blir bussarna prickar via det publika spår-gränssnittet.
    const engine = this._map._engine;
    if (engine?.addMarker) {
      this._map.paths = [];
      this._drawWithEngine(engine, sensors, markers);
    } else {
      this._map.paths = markers.map((m) => ({
        name: `Linje ${m.line}`,
        color: ZONE_HEX[m.zone] ?? NO_ZONE,
        points: [m, m].map((p) => ({ point: [p.lat, p.lon], timestamp: new Date() })),
      }));
    }
  }

  _drawWithEngine(engine, sensors, markers) {
    this._handles.forEach((h) => h.remove());
    this._handles = [];
    const stops = mapPoints(sensors, [], null);
    for (const [lat, lon] of stops) {
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
    // En gång per utfällning, när Bussar har svarat första gången: hem, hållplatser och bussar.
    if (!this._fitted && this._answered) {
      this._fitted = true;
      const home = this._hass.config?.latitude !== undefined ? [this._hass.config.latitude, this._hass.config.longitude] : null;
      engine.fitBounds(mapPoints(sensors, this._vehicles, home), FIT);
    }
  }
}
