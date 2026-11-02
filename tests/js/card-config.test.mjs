import { test } from "node:test";
import assert from "node:assert/strict";

import { cardConfig, cardSize } from "../../custom_components/bussar/www/card-config.js";

test("utan nycklar: normal-layouten, ett streck, inga sensorer", () => {
  const config = cardConfig({ type: "custom:bussar-card" });

  assert.equal(config.layout, "normal");
  assert.equal(config.following_bar, false);
  assert.deepEqual(config.entities, []);
});

test("layout compact och dense godtas", () => {
  assert.equal(cardConfig({ layout: "compact" }).layout, "compact");
  assert.equal(cardConfig({ layout: "dense", following_bar: true }).layout, "dense");
});

test("okänd layout ger ett fel som namnger de giltiga värdena", () => {
  assert.throws(() => cardConfig({ layout: "tight" }), /layout ska vara normal, compact, dense \(fick "tight"\)/);
  assert.throws(() => cardConfig({ layout: true }), /layout ska vara/);
});

test("fel typ för entities och following_bar ger fel", () => {
  assert.throws(() => cardConfig({ entities: "sensor.a" }), /entities ska vara en lista/);
  assert.throws(() => cardConfig({ following_bar: "ja" }), /following_bar ska vara true eller false/);
});

const sensors = (n) => Array.from({ length: n }, (_, i) => `sensor.linje_${i}`);

test("kortets höjd: normal-layouten en enhet per rad plus titel", () => {
  assert.equal(cardSize(cardConfig({ entities: sensors(3) })), 4);
  assert.equal(cardSize(cardConfig({ entities: sensors(3), following_bar: true })), 4);
  assert.equal(cardSize(cardConfig({})), 2);
});

test("kortets höjd: kompakta lägen är lägre", () => {
  assert.equal(cardSize(cardConfig({ entities: sensors(8), layout: "compact" })), 5);
  assert.equal(cardSize(cardConfig({ entities: sensors(8), layout: "compact", following_bar: true })), 5);
  assert.equal(cardSize(cardConfig({ entities: sensors(3), layout: "dense" })), 3);
  assert.equal(cardSize(cardConfig({ entities: sensors(3), layout: "dense", following_bar: true })), 4);
  assert.equal(cardSize(cardConfig({ layout: "compact" })), 2);
});
