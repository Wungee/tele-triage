import { ALARM_TEXT, VERDICT, fmtClock } from "../waveform.js";

// Active alarms, ordered by the co-pilot: likely-real first, likely-artifact last.
// Nothing is removed. The order is the only thing the AI changes.
export default function Queue({ beds, now, onOpen, selectedId }) {
  const active = beds
    .filter((b) => b.fired && !b.review && b.data)
    .sort(
      (a, b) =>
        VERDICT[a.data.verdict].rank - VERDICT[b.data.verdict].rank || a.firedAtWall - b.firedAtWall
    );
  return (
    <aside className="queue" aria-label="Alarm queue">
      <h2 className="queue__h">
        Alarm queue <span>{active.length}</span>
      </h2>
      <p className="queue__sub">Sorted by the co-pilot. Likely-real alarms rise to the top.</p>
      {!active.length && <p className="queue__empty">No open alarms. Beds are replaying the minute before each alarm.</p>}
      <ol className="queue__list">
        {active.map((b) => (
          <li key={b.key}>
            <button
              className={`qrow qrow--${b.data.verdict} ${selectedId === b.key ? "qrow--sel" : ""}`}
              onClick={() => onOpen(b)}
            >
              <span className="qrow__bed">{b.label}</span>
              <span className="qrow__alarm">{ALARM_TEXT[b.data.alarm_type]}</span>
              <span className="qrow__age">{fmtClock((now - b.firedAtWall) / 1000)}</span>
              <span className={`qrow__ai ai-text--${b.data.verdict}`}>{VERDICT[b.data.verdict].label}</span>
            </button>
          </li>
        ))}
      </ol>
    </aside>
  );
}
