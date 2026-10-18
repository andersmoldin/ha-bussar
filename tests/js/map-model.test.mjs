import { test } from "node:test";
import assert from "node:assert/strict";

import { mapPoints, rowKey, vehicleMarkers } from "../../custom_components/bussar/www/map-model.js";

const at = (hms) => Date.parse(`2026-10-17T${hms}+02:00`);

// Samma form som sensorattributen: linje, läge, hållplats och gränserna för gå och spring.
const sensor = (line, platform, stopId = "1000") => ({
  state: "15",
  attributes: { line, platform, stop_id: stopId, walk_seconds: 270, run_seconds: 120, window_seconds: 300 },
});

// Samma form som ett fordon i bussar/vehicles/subscribe.
const vehicle = (overrides = {}) => ({
  vehicle_id: "v1",
  line: "10",
  platform: "A",
  stop_id: "1000",
  expected: "2026-10-17T19:59:29+02:00",
  latitude: 58.31,
  longitude: 19.12,
  bearing: 90,
  ...overrides,
});

test("bussen får linjens färg och kopplas till sin rad", () => {
  const blue = { ...sensor("10", "A"), attributes: { ...sensor("10", "A").attributes, line_color: "#1e88e5" } };

  const markers = vehicleMarkers([vehicle()], [blue], at("19:43:36"));

  assert.deepEqual(markers, [
    { id: "v1", line: "10", row: rowKey(blue), color: "#1e88e5", textColor: "#fff", lat: 58.31, lon: 19.12 },
  ]);
});

test("samma linje och läge vid två hållplatser: bussen hör till sin egen hållplats", () => {
  const markers = vehicleMarkers([vehicle({ stop_id: "2000" })], [sensor("10", "A", "1000"), sensor("10", "A", "2000")], at("19:43:36"));

  assert.equal(markers[0].row, rowKey(sensor("10", "A", "2000")));
});

test("linje utan vald färg: markören får temats färg", () => {
  const markers = vehicleMarkers([vehicle()], [sensor("10", "A")], at("19:43:36"));

  assert.equal(markers[0].color, null);
});

test("kartan zoomar till hem, varje hållplats en gång och bussarna", () => {
  const withPlace = (s, lat, lon) => ({ ...s, attributes: { ...s.attributes, stop_latitude: lat, stop_longitude: lon } });
  const sensors = [withPlace(sensor("10", "A"), 58.3, 19.1), withPlace(sensor("20", "B"), 58.3, 19.1), sensor("40", "A", "2000")];

  const points = mapPoints(sensors, [vehicle()], [58.2, 19.0]);

  assert.deepEqual(points, [[58.2, 19.0], [58.3, 19.1], [58.31, 19.12]]);
});

test("raden och bussen får samma nyckel, så att en rad kan markera sin buss", () => {
  assert.equal(rowKey(sensor("10", "A", "1000")), "1000|10|A");
  assert.notEqual(rowKey(sensor("10", "A", "1000")), rowKey(sensor("10", "A", "2000")));
});

test("bussar på linjer som kortet inte visar ritas inte", () => {
  const markers = vehicleMarkers([vehicle({ line: "30" })], [sensor("10", "A")], at("19:43:36"));

  assert.deepEqual(markers, []);
});
