// Räknar fram en rad i Bussar-kortet ur en sensor och en tidpunkt.
// Sensorn (se zones.py) äger zonlogiken. Kortet räknar bara ner lokalt varje sekund
// med samma gränser, så att stapeln rör sig mellan sensorns uppdateringar.

// Stapeln är full när det är så här mycket mer än gångtid + fönster kvar.
const FULL_EXTRA_SECONDS = 300;

function zoneFor(secondsLeft, { walk, run, window }) {
  if ([walk, run, window].some((v) => typeof v !== "number")) return null;
  if (secondsLeft > walk + window) return "plenty";
  if (secondsLeft >= walk) return "go";
  if (secondsLeft >= run) return "run";
  return null;
}

function clockIn(ms, timeZone) {
  return new Intl.DateTimeFormat("sv-SE", { hour: "2-digit", minute: "2-digit", timeZone }).format(ms);
}

// Över denna relativa luminans blir texten svart. Gränsen ligger högt, så att mellanmörka
// linjefärger (blått, grått) får vit text som hos trafikbolagen, och gult får svart.
const DARK_TEXT_ABOVE = 0.5;

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

// Linjens färg (#rrggbb) och en läsbar textfärg. Utan färg gäller temat (null).
export function lineColors(color) {
  if (!color) return { color: null, textColor: null };
  return { color, textColor: luminance(color) > DARK_TEXT_ABOVE ? "#000" : "#fff" };
}

const EMPTY = { minutes: null, zone: null, fill: 0, clock: null, delay: null, live: null, followingClock: null };

// HA skickar inga extra attribut för en otillgänglig entitet, bara friendly_name,
// som är titeln "<linje> läge <läge>, <hållplats>".
function unavailableRow(name) {
  const line = name?.match(/^(.+?) läge /)?.[1] ?? null;
  const destination = name ? `${name} – ej tillgänglig` : "Ej tillgänglig";
  return { line, destination, ...EMPTY };
}

export function rowModel(stateObj, nowMs, timeZone) {
  const a = stateObj.attributes ?? {};
  if (stateObj.state === "unavailable") return unavailableRow(a.friendly_name);
  const timing = { walk: a.walk_seconds, run: a.run_seconds, window: a.window_seconds };
  let expected = a.expected ? Date.parse(a.expected) : null;
  let following = a.following_expected ? Date.parse(a.following_expected) : null;
  let delay = a.delay_minutes ?? null;
  let live = a.is_realtime ?? null;

  // Sensorn byter buss först vid nästa omskrivning. Kortet byter direkt vid springgränsen,
  // och för nästa buss vet vi varken försening eller om tiden är realtid.
  if (expected !== null && typeof timing.run === "number" && (expected - nowMs) / 1000 < timing.run) {
    expected = following;
    following = null;
    delay = null;
    live = null;
  }

  const base = { line: a.line, destination: a.destination ?? null, ...lineColors(a.line_color) };
  if (expected === null) {
    return { ...base, ...EMPTY };
  }

  const secondsLeft = (expected - nowMs) / 1000;
  const full = timing.walk + timing.window + FULL_EXTRA_SECONDS;
  const ratio = (secondsLeft - timing.run) / (full - timing.run);
  const fill = Number.isFinite(ratio) ? Math.max(0, Math.min(1, ratio)) : 0;
  return {
    ...base,
    minutes: Math.floor(secondsLeft / 60),
    zone: zoneFor(secondsLeft, timing),
    fill: Math.round(fill * 1000) / 1000,
    clock: clockIn(expected, timeZone),
    delay,
    live,
    followingClock: following === null ? null : clockIn(following, timeZone),
  };
}
