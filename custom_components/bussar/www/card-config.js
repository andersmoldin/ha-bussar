// Kortets YAML-inställningar: validering, standardvärden och kortets höjd.

// normal är grundlayouten. compact: allt på en rad, utan klockslag.
// dense: grundlayoutens uppbyggnad hopdragen till en textrad.
export const LAYOUTS = ["normal", "compact", "dense"];

// Kastar ett fel som HA visar i kortet när en nyckel har fel värde.
export function cardConfig(config) {
  if (config.entities !== undefined && !Array.isArray(config.entities)) {
    throw new Error("entities ska vara en lista med sensorer");
  }
  if (config.following_bar !== undefined && typeof config.following_bar !== "boolean") {
    throw new Error("following_bar ska vara true eller false");
  }
  if (config.layout !== undefined && !LAYOUTS.includes(config.layout)) {
    throw new Error(`layout ska vara ${LAYOUTS.join(", ")} (fick ${JSON.stringify(config.layout)})`);
  }
  return {
    ...config,
    entities: config.entities ?? [],
    following_bar: config.following_bar ?? false,
    layout: config.layout ?? "normal",
  };
}

// Radens höjd i förhållande till en rad i normal-layouten (82 px), uppmätt i tests/js/preview.html:
// compact 35 px (43 med två streck), dense 49 px (70 med två streck).
function rowUnits({ layout, following_bar }) {
  if (layout === "compact") return 0.5;
  if (layout === "dense") return following_bar ? 0.85 : 0.6;
  return 1;
}

// Höjd för HA:s masonry-vy: en enhet för titel och kartknapp, sedan raderna (minst en).
export function cardSize(config) {
  return 1 + Math.max(1, Math.ceil(config.entities.length * rowUnits(config)));
}
