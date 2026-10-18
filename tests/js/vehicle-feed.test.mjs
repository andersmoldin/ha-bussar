import { test } from "node:test";
import assert from "node:assert/strict";

import { VehicleFeed } from "../../custom_components/bussar/www/map-model.js";

// Falsk HA-anslutning med samma subscribeMessage som home-assistant-js-websocket:
// ett lyckat svar ger en avprenumerationsfunktion, ett felsvar avvisas med { code }.
function fakeConnection() {
  const subs = [];
  return {
    subs,
    subscribeMessage(callback, message) {
      let settle;
      const promise = new Promise((resolve, reject) => (settle = { resolve, reject }));
      const sub = {
        message,
        active: false,
        send: (event) => callback(event),
        accept() {
          sub.active = true;
          settle.resolve(async () => {
            sub.active = false;
          });
        },
        fail: (code) => settle.reject({ code, message: code }),
      };
      subs.push(sub);
      return promise;
    },
    get latest() {
      return subs[subs.length - 1];
    },
  };
}

// Timer som testet själv stegar fram.
function fakeTimers() {
  const pending = [];
  return {
    pending,
    setTimeout: (fn, ms) => pending.push({ fn, ms }) && pending.length,
    clearTimeout: (id) => (pending[id - 1] = null),
    runAll() {
      const due = pending.splice(0).filter(Boolean);
      due.forEach(({ fn }) => fn());
    },
  };
}

const flush = () => new Promise((r) => setImmediate(r));
const bus = { vehicle_id: "v1", line: "10" };

function feedWith(conn, timers = fakeTimers()) {
  const states = [];
  const feed = new VehicleFeed(conn, (state) => states.push(state), timers);
  return { feed, states, last: () => states[states.length - 1] };
}

test("startad karta prenumererar och visar bussarna som kommer", async () => {
  const conn = fakeConnection();
  const { feed, last } = feedWith(conn);

  feed.start();
  assert.deepEqual(conn.latest.message, { type: "bussar/vehicles/subscribe" });
  conn.latest.accept();
  conn.latest.send({ vehicles: [bus] });
  await flush();

  assert.deepEqual(last(), { status: "live", vehicles: [bus] });
});

test("hopfälld karta avslutar prenumerationen", async () => {
  const conn = fakeConnection();
  const { feed } = feedWith(conn);
  feed.start();
  conn.latest.accept();
  await flush();

  feed.stop();
  await flush();

  assert.equal(conn.latest.active, false);
});

test("fälls kartan ihop innan svaret kommit avslutas prenumerationen när svaret kommer", async () => {
  const conn = fakeConnection();
  const { feed, states } = feedWith(conn);
  feed.start();

  feed.stop();
  conn.latest.accept();
  conn.latest.send({ vehicles: [bus] });
  await flush();

  assert.equal(conn.latest.active, false);
  assert.deepEqual(states.filter((s) => s.status === "live"), []);
});

test("not_ready: försöker igen efter en stund", async () => {
  const conn = fakeConnection();
  const timers = fakeTimers();
  const { feed, last } = feedWith(conn, timers);
  feed.start();

  conn.latest.fail("not_ready");
  await flush();
  assert.deepEqual(last(), { status: "waiting", vehicles: [] });

  timers.runAll();
  assert.equal(conn.subs.length, 2);
  conn.latest.accept();
  conn.latest.send({ vehicles: [bus] });
  await flush();
  assert.equal(last().status, "live");
});

test("hopfälld karta under väntan: inget nytt försök", async () => {
  const conn = fakeConnection();
  const timers = fakeTimers();
  const { feed } = feedWith(conn, timers);
  feed.start();
  conn.latest.fail("not_ready");
  await flush();

  feed.stop();
  timers.runAll();

  assert.equal(conn.subs.length, 1);
});

for (const code of ["unavailable", "no_vehicle_key"]) {
  test(`${code}: visar felet och försöker inte igen`, async () => {
    const conn = fakeConnection();
    const timers = fakeTimers();
    const { feed, last } = feedWith(conn, timers);
    feed.start();

    conn.latest.fail(code);
    await flush();
    timers.runAll();

    assert.deepEqual(last(), { status: code, vehicles: [] });
    assert.equal(conn.subs.length, 1);
  });
}

test("resubscribe: prenumererar igen och behåller bussarna under tiden", async () => {
  const conn = fakeConnection();
  const { feed, last } = feedWith(conn);
  feed.start();
  conn.latest.accept();
  conn.latest.send({ vehicles: [bus] });
  await flush();

  conn.latest.send({ vehicles: [], resubscribe: true });
  await flush();

  assert.equal(conn.subs.length, 2);
  assert.deepEqual(last(), { status: "live", vehicles: [bus] });
});

test("invalid_key: visar felet och försöker inte igen", async () => {
  const conn = fakeConnection();
  const timers = fakeTimers();
  const { feed, last } = feedWith(conn, timers);
  feed.start();
  conn.latest.accept();

  conn.latest.send({ vehicles: [], error: "invalid_key" });
  await flush();
  timers.runAll();

  assert.deepEqual(last(), { status: "invalid_key", vehicles: [] });
  assert.equal(conn.subs.length, 1);
});
