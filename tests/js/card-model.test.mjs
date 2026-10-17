import { test } from "node:test";
import assert from "node:assert/strict";

import { rowModel } from "../../custom_components/bussar/www/card-model.js";

const TZ = "Europe/Stockholm";
const at = (hms) => Date.parse(`2026-10-17T${hms}+02:00`);

// Samma form som sensorattributen från #4: linje 10 läge A, bussen 19:59:29, sedan 20:14:47.
const sensor = (overrides = {}) => ({
  state: "15",
  attributes: {
    line: "10",
    destination: "Ort C",
    expected: "2026-10-17T19:59:29+02:00",
    scheduled: "2026-10-17T19:57:29+02:00",
    delay_minutes: 2,
    is_realtime: true,
    following_expected: "2026-10-17T20:14:47+02:00",
    walk_seconds: 270,
    run_seconds: 120,
    window_seconds: 300,
    ...overrides,
  },
});

test("gott om tid: minuter, zon, full stapel, klockslag och nästa buss", () => {
  const row = rowModel(sensor(), at("19:43:36"), TZ);

  assert.equal(row.minutes, 15);
  assert.equal(row.zone, "plenty");
  assert.equal(row.fill, 1);
  assert.equal(row.clock, "19:59");
  assert.equal(row.delay, 2);
  assert.equal(row.live, true);
  assert.equal(row.followingClock, "20:14");
});

test("exakt gångtid + fönster är gå nu, och stapeln töms mot springgränsen", () => {
  // 570 s kvar. Stapeln är full vid gångtid + fönster + 5 min (870 s) och tom vid springtiden (120 s).
  const row = rowModel(sensor(), at("19:49:59"), TZ);

  assert.equal(row.zone, "go");
  assert.equal(row.fill, 0.6);
});

test("mellan springtid och gångtid är spring", () => {
  assert.equal(rowModel(sensor(), at("19:56:09"), TZ).zone, "run"); // 200 s kvar
});

test("under springtiden byter raden till nästa buss", () => {
  const row = rowModel(sensor(), at("19:57:30"), TZ); // 119 s kvar

  assert.equal(row.clock, "20:14");
  assert.equal(row.minutes, 17);
  assert.equal(row.zone, "plenty");
  assert.equal(row.delay, null);
  assert.equal(row.live, null);
  assert.equal(row.followingClock, null);
});

test("ingen buss att hinna ger tom rad", () => {
  const row = rowModel(sensor({ expected: null, following_expected: null }), at("19:43:36"), TZ);

  assert.equal(row.minutes, null);
  assert.equal(row.zone, null);
  assert.equal(row.fill, 0);
  assert.equal(row.line, "10");
});
