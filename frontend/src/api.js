async function req(path, opts = {}) {
  const r = await fetch(path, {
    headers: opts.body ? { "Content-Type": "application/json" } : undefined,
    ...opts,
  });
  if (!r.ok) {
    let detail = `${r.status}`;
    try {
      detail = (await r.json()).detail || detail;
    } catch {}
    throw new Error(detail);
  }
  return r.json();
}

export const api = {
  health: () => req("/api/health"),
  model: () => req("/api/model"),
  alarms: () => req("/api/alarms"),
  alarm: (id) => req(`/api/alarms/${id}`),
  summary: (id) => req(`/api/alarms/${id}/summary`, { method: "POST" }),
  review: (id, decision, seconds) =>
    req(`/api/alarms/${id}/review`, {
      method: "POST",
      body: JSON.stringify({ decision, seconds_to_decision: seconds }),
    }),
  stats: () => req("/api/stats"),
};
