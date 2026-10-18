// Räknar fram kartans innehåll ur bussarna från bussar/vehicles/subscribe och kortets sensorer.

// Samma version som kortet laddades med, se bussar-card.js.
const { zoneFor } = await import(`./card-model.js${new URL(import.meta.url).search}`);

const key = (line, platform, stopId) => `${stopId}|${line}|${platform}`;

// Nyckeln som kopplar en rad i kortet till bussarna på samma hållplats, linje och läge.
export const rowKey = ({ attributes: a }) => key(a.line, a.platform, a.stop_id);

// En markör per buss, i samma zonfärg som stapeln för bussens avgång vid hållplatsen.
export function vehicleMarkers(vehicles, sensors, nowMs) {
  const timingByRow = new Map(
    sensors.map((sensor) => [
      rowKey(sensor),
      { walk: sensor.attributes.walk_seconds, run: sensor.attributes.run_seconds, window: sensor.attributes.window_seconds },
    ]),
  );
  return vehicles.map((v) => {
    const row = key(v.line, v.platform, v.stop_id);
    const timing = timingByRow.get(row);
    const secondsLeft = (Date.parse(v.expected) - nowMs) / 1000;
    return { id: v.vehicle_id, line: v.line, row, zone: zoneFor(secondsLeft, timing), lat: v.latitude, lon: v.longitude };
  });
}

// Punkterna kartan zoomar till när den fälls ut: hemmet, varje hållplats en gång och bussarna.
export function mapPoints(sensors, vehicles, home) {
  const points = home ? [home] : [];
  const seen = new Set();
  for (const { attributes: a } of sensors) {
    if (typeof a.latitude !== "number" || typeof a.longitude !== "number") continue;
    const key = `${a.latitude},${a.longitude}`;
    if (seen.has(key)) continue;
    seen.add(key);
    points.push([a.latitude, a.longitude]);
  }
  for (const v of vehicles) points.push([v.latitude, v.longitude]);
  return points;
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
  }

  start() {
    this.stop();
    this._subscribe();
  }

  stop() {
    // Ett svar som kommer efter stop() hör till en gammal prenumeration och avslutas direkt.
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
      }, SUBSCRIBE);
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
