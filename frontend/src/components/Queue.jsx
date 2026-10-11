import { ALARM_TEXT, VERDICT, fmtClock } from "../waveform.js";

// Open alarms, numbered in the order the co-pilot suggests reviewing them: likely-real first,
// likely-artifact last. Nothing is removed; the order is the only thing the AI changes.
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
        Open alarms <span>{active.length}</span>
      </h2>
      <p className="queue__sub">In the order the co-pilot suggests. Likely-real alarms come first.</p>
      {!active.length && (
        <p className="queue__empty">No open alarms yet. Each bed is replaying the minute before its alarm.</p>
      )}
      <ol className="queue__list">
        {active.map((b) => (
          <li key={b.key}>
            <button className={`qrow ${selectedId === b.key ? "qrow--sel" : ""}`} onClick={() => onOpen(b)}>
              <span className="qrow__bed">{b.label}</span>
              <span className="qrow__alarm">{ALARM_TEXT[b.data.alarm_type]}</span>
              <span className="qrow__age">{fmtClock((now - b.firedAtWall) / 1000)}</span>
              <span className={`qrow__ai qrow__ai--${b.data.verdict}`}>{VERDICT[b.data.verdict].label}</span>
            </button>
          </li>
        ))}
      </ol>
    </aside>
  );
}
