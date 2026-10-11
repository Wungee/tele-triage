import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { ALARM_TEXT, VERDICT } from "../waveform.js";
import Strip from "./Strip.jsx";

const STRIP_S = 20; // seconds shown before the alarm

export default function AlarmDetail({ bed, onClose, onReviewed }) {
  const data = bed.data;
  const wf = data.waveform;
  const [hl, setHl] = useState(data.reasons[0]?.channel ?? null);
  const [summary, setSummary] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const openedAt = useRef(performance.now());
  const closeRef = useRef(null);
  const review = bed.review;

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const decide = async (decision) => {
    setBusy(true);
    setErr(null);
    try {
      const secs = (performance.now() - openedAt.current) / 1000;
      const r = await api.review(data.id, decision, Math.round(secs * 10) / 10);
      onReviewed(bed, { ...r, decision, secs });
    } catch (e) {
      setErr(`Could not save the review: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const explain = async () => {
    setSummary("loading");
    try {
      setSummary(await api.summary(data.id));
    } catch (e) {
      setSummary({ text: `Summary unavailable: ${e.message}`, source: "" });
    }
  };

  // never display certainty: a model that says "100%" invites people to stop looking
  const pReal = Math.min(99, Math.max(1, Math.round(data.p_true * 100)));
  const from = data.alarm_time_s - STRIP_S;
  return (
    <section className="detail" role="dialog" aria-modal="true" aria-label={`Bed ${bed.label} alarm review`}>
      <header className="detail__head">
        <div>
          <span className="detail__bed">Bed {bed.label}</span>
          <span className="detail__alarm">*** {ALARM_TEXT[data.alarm_type]}</span>
        </div>
        <button ref={closeRef} className="btn" onClick={onClose}>
          Back to wall
        </button>
      </header>

      <div className="detail__grid">
        <div className="detail__strips">
          <div className="detail__stack">
          {wf.channels
            .filter((c) => c.kind !== "resp")
            .map((ch) => (
              <Strip
                key={ch.name}
                ch={ch}
                wf={wf}
                from={from}
                to={data.alarm_time_s + 0.4}
                alarmT={data.alarm_time_s}
                windowS={data.window_s}
                highlighted={hl === ch.name}
              />
            ))}
          </div>
          <p className="detail__legend">
            <span className="tick" /> beats the co-pilot found
            <span className="shade" /> the 16 s it analysed
            <span className="mark" /> alarm fired
          </p>
        </div>

        <aside className="detail__side">
          <div className={`verdict verdict--${data.verdict}`}>
            <span className="verdict__who">Co-pilot</span>
            <span className="verdict__label">{VERDICT[data.verdict].label}</span>
            <div className="meter" aria-label={`${pReal}% chance this alarm is real`}>
              <div className="meter__fill" style={{ width: `${Math.max(2, pReal)}%` }} />
            </div>
            <span className="verdict__p">{pReal}% chance this alarm is real</span>
          </div>

          <h3 className="side__h">Why</h3>
          <ul className="reasons">
            {data.reasons.map((r, i) => (
              <li
                key={i}
                className={`reason reason--${r.toward}`}
                onMouseEnter={() => r.channel && setHl(r.channel)}
                onFocus={() => r.channel && setHl(r.channel)}
                tabIndex={0}
              >
                <span className="reason__tag">
                  {r.toward === "artifact" ? "Points to artifact" : r.toward === "real" ? "Points to a real alarm" : "Note"}
                </span>
                <span className="reason__text">{r.text}</span>
              </li>
            ))}
            {!data.reasons.length && (
              <li className="reason">
                <span className="reason__text">No single signal stands out. Read the strip.</span>
              </li>
            )}
          </ul>

          <div className="summary">
            {summary === "loading" ? (
              <div aria-label="Writing summary" role="status">
                <span className="skel" />
                <span className="skel" />
                <span className="skel skel--short" />
              </div>
            ) : summary ? (
              <p className="summary__text">
                {summary.text}
                {summary.source && (
                  <small>Written by {summary.source.startsWith("gemini") ? "Gemini" : "a rule template"}</small>
                )}
              </p>
            ) : (
              <button className="btn" onClick={explain}>
                Summarize in plain English
              </button>
            )}
          </div>

          {!review ? (
            <div className="decide">
              <p className="decide__q">Your call</p>
              <button className="btn btn--real" disabled={busy} onClick={() => decide("real")}>
                Real alarm, call the RN
              </button>
              <button className="btn btn--artifact" disabled={busy} onClick={() => decide("artifact")}>
                Artifact, ask RN to check leads
              </button>
              {err && <p className="err">{err}</p>}
            </div>
          ) : (
            <div className="reveal">
              <p>
                Expert annotation: <strong>{review.expert_label === "real" ? "true alarm" : "false alarm"}</strong>
              </p>
              <p>
                You said {review.decision}{" "}
                {review.tech_agrees_expert ? "and matched the experts." : "and the experts disagreed."}
              </p>
              <p>
                {review.ai_agrees_expert === null
                  ? "The co-pilot did not commit on this one."
                  : review.ai_agrees_expert
                  ? "The co-pilot matched the experts."
                  : "The co-pilot got this one wrong."}
              </p>
              <button className="btn" onClick={onClose}>
                Back to wall
              </button>
            </div>
          )}
          <p className="fineprint">
            Decision support only. The co-pilot never silences, delays or hides an alarm. It reorders the queue and
            shows its evidence.
          </p>
        </aside>
      </div>
    </section>
  );
}
