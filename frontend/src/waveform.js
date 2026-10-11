// Shared waveform helpers: colours follow bedside-monitor convention so a tech reads them instantly.
export const TRACE = {
  ecg: "#5fcf78",
  pleth: "#4dbfd6",
  abp: "#e0575f",
  resp: "#d9c25a",
};

export const INK = "#ede6d6"; // the co-pilot's colour: warm paper white, never a monitor colour
export const ALARM_RED = "#e0303c";

export const VERDICT = {
  likely_artifact: { label: "Likely artifact", rank: 2 },
  needs_review: { label: "Needs a look", rank: 1 },
  likely_real: { label: "Likely real", rank: 0 },
};

export const ALARM_TEXT = {
  Asystole: "ASYSTOLE",
  Bradycardia: "EXTREME BRADY",
  Tachycardia: "EXTREME TACHY",
  Ventricular_Tachycardia: "V-TACH",
  Ventricular_Flutter_Fib: "V-FIB/V-FLUT",
};

export function scaleFor(values) {
  const v = values.filter((x) => x !== null);
  if (!v.length) return [0, 1];
  const s = [...v].sort((a, b) => a - b);
  const lo = s[Math.floor(s.length * 0.01)];
  const hi = s[Math.floor(s.length * 0.99)];
  const pad = (hi - lo) * 0.12 || 0.5;
  return [lo - pad, hi + pad];
}

export function sampleAt(ch, wf, t) {
  const i = Math.round((t - wf.t0) * wf.fs);
  if (i < 0 || i >= ch.values.length) return null;
  return ch.values[i];
}

// Heart rate from the last few detected beats before time t (what the monitor numeric shows)
export function rateAt(beats, t, lookback = 6) {
  const b = beats.filter((x) => x <= t && x > t - lookback);
  if (b.length < 3) return null;
  const rr = [];
  for (let i = 1; i < b.length; i++) rr.push(b[i] - b[i - 1]);
  rr.sort((a, c) => a - c);
  const med = rr[Math.floor(rr.length / 2)];
  return Math.round(60 / med);
}

export function primary(wf, kind) {
  const chans = wf.channels.filter((c) => c.kind === kind);
  if (!chans.length) return null;
  return chans.reduce((a, b) => ((b.quality ?? 0) > (a.quality ?? 0) ? b : a));
}

export function pulseChannel(wf) {
  return primary(wf, "abp") || primary(wf, "pleth");
}

export function setupCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const { width, height } = canvas.getBoundingClientRect();
  if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, width, height };
}

export const fmtClock = (s) => {
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${String(r).padStart(2, "0")}`;
};
