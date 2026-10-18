// Räknar fram kartans innehåll ur bussarna från bussar/vehicles/subscribe och kortets sensorer.

// Samma version som kortet laddades med, se bussar-card.js.
const { lineColors } = await import(`./card-model.js${new URL(import.meta.url).search}`);

const key = (line, platform, stopId) => `${stopId}|${line}|${platform}`;

// Nyckeln som kopplar en rad i kortet till bussarna på samma hållplats, linje och läge.
export const rowKey = ({ attributes: a }) => key(a.line, a.platform, a.stop_id);

// En markör per buss, i linjens färg.
export function vehicleMarkers(vehicles, sensors) {
  const colorsByRow = new Map(sensors.map((sensor) => [rowKey(sensor), lineColors(sensor.attributes.line_color)]));
  // Bussar skickar bussarna för alla bevakade linjer. Kortet visar bara sina egna.
  return vehicles.flatMap((v) => {
    const row = key(v.line, v.platform, v.stop_id);
    const colors = colorsByRow.get(row);
    if (!colors) return [];
    return [{ id: v.vehicle_id, line: v.line, row, ...colors, lat: v.latitude, lon: v.longitude }];
  });
}

// Varje hållplats en gång. Alla lägen vid en hållplats delar position.
export function stopPoints(sensors) {
  const points = new Map();
  for (const { attributes: a } of sensors) {
    if (typeof a.stop_latitude !== "number" || typeof a.stop_longitude !== "number") continue;
    points.set(`${a.stop_latitude},${a.stop_longitude}`, [a.stop_latitude, a.stop_longitude]);
  }
  return [...points.values()];
}

// Punkterna kartan zoomar till när den fälls ut: hemmet, hållplatserna och bussarna.
export function mapPoints(sensors, vehicles, home) {
  return [...(home ? [home] : []), ...stopPoints(sensors), ...vehicles.map((v) => [v.latitude, v.longitude])];
}

const SUBSCRIBE = { type: "bussar/vehicles/subscribe" };
// Bussar laddas eller väntar på att försöka igen (not_ready). Prenumerera igen om en stund.
const RETRY_MS = 5000;

// Prenumerationen på bussarnas positioner medan kartan är utfälld.
// onChange får { status, vehicles } vid varje ändring.
export class VehicleFeed {
  constructor(connection, onChange, timers = globalThis) {
    this._connection = connection;
    this._onChange = onChange;
    this._timers = timers;
    // Efter en återanslutning finns den gamla prenumerationen inte längre. Prenumerera igen
    // själv, så att not_ready ger ett nytt försök även då.
    this._reconnected = () => {
      this._unsubscribe = null;
      this._cancel();
      this._subscribe();
    };
  }

  start() {
    this.stop();
    this._connection.addEventListener("ready", this._reconnected);
    this._subscribe();
  }

  stop() {
    this._connection.removeEventListener("ready", this._reconnected);
    this._cancel();
  }

  _cancel() {
    // Ett svar som kommer efter _cancel() hör till en gammal prenumeration och avslutas direkt.
    this._generation = (this._generation ?? 0) + 1;
    this._timers.clearTimeout(this._retry);
    this._retry = null;
    this._unsubscribe?.().catch(() => {});
    this._unsubscribe = null;
  }

  async _subscribe() {
    const generation = this._generation;
    let unsubscribe;
    try {
      unsubscribe = await this._connection.subscribeMessage((event) => {
        if (generation === this._generation) this._event(event);
      }, SUBSCRIBE, { resubscribe: false });
    } catch (err) {
      if (generation === this._generation) this._failed(err?.code);
      return;
    }
    if (generation !== this._generation) {
      unsubscribe().catch(() => {});
      return;
    }
    this._unsubscribe = unsubscribe;
  }

  _failed(code) {
    if (code === "not_ready") {
      this._onChange({ status: "waiting", vehicles: [] });
      this._retry = this._timers.setTimeout(() => this._subscribe(), RETRY_MS);
      return;
    }
    this._onChange({ status: code ?? "unavailable", vehicles: [] });
  }

  _event(event) {
    if (event.resubscribe) {
      // Bussar laddades om och har redan släppt prenumerationen. Bussarna ligger kvar tills nya kommer.
      this.start();
      return;
    }
    if (event.error) {
      this._onChange({ status: event.error, vehicles: [] });
      return;
    }
    this._onChange({ status: "live", vehicles: event.vehicles });
  }
}
