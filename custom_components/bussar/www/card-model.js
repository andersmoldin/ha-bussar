// Räknar fram en rad i Bussar-kortet ur en sensor och en tidpunkt.
// Sensorn (se zones.py) äger zonlogiken. Kortet räknar bara ner lokalt varje sekund
// med samma gränser, så att stapeln rör sig mellan sensorns uppdateringar.

// Stapeln är full när det är så här mycket mer än gångtid + fönster kvar.
const FULL_EXTRA_SECONDS = 300;

function zoneFor(secondsLeft, { walk, run, window }) {
  if (secondsLeft > walk + window) return "plenty";
  if (secondsLeft >= walk) return "go";
  if (secondsLeft >= run) return "run";
  return null;
}

function clockIn(ms, timeZone) {
  return new Intl.DateTimeFormat("sv-SE", { hour: "2-digit", minute: "2-digit", timeZone }).format(ms);
}

export function rowModel(stateObj, nowMs, timeZone) {
  const a = stateObj.attributes;
  const timing = { walk: a.walk_seconds, run: a.run_seconds, window: a.window_seconds };
  let expected = a.expected ? Date.parse(a.expected) : null;
  let following = a.following_expected ? Date.parse(a.following_expected) : null;
  let delay = a.delay_minutes ?? null;
  let live = a.is_realtime ?? null;

  // Sensorn byter buss först vid nästa omskrivning. Kortet byter direkt vid springgränsen,
  // och för nästa buss vet vi varken försening eller om tiden är realtid.
  if (expected !== null && (expected - nowMs) / 1000 < timing.run) {
    expected = following;
    following = null;
    delay = null;
    live = null;
  }

  const base = { line: a.line, destination: a.destination ?? null };
  if (expected === null) {
    return { ...base, minutes: null, zone: null, fill: 0, clock: null, delay: null, live: null, followingClock: null };
  }

  const secondsLeft = (expected - nowMs) / 1000;
  const full = timing.walk + timing.window + FULL_EXTRA_SECONDS;
  const fill = Math.max(0, Math.min(1, (secondsLeft - timing.run) / (full - timing.run)));
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
