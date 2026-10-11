import { useEffect, useMemo, useRef } from "react";
import { ALARM_TEXT, TRACE, VERDICT, primary, pulseChannel, rateAt, sampleAt, scaleFor, setupCanvas } from "../waveform.js";

const SWEEP_S = 6; // seconds of trace per screen width, like a central station tile

// One bed on the central station. Replays the minute before a real alarm with a monitor-style
// sweep; when the replay reaches t = 300 s the alarm fires and the co-pilot's verdict appears.
export default function BedTile({ bed, getRecordTime, selected, onOpen }) {
  const canvasRef = useRef(null);
  const hrRef = useRef(null);
  const prRef = useRef(null);
  const data = bed.data;
  const wf = data?.waveform;
  const ecg = useMemo(() => (wf ? primary(wf, "ecg") : null), [wf]);
  const pulse = useMemo(() => (wf ? pulseChannel(wf) : null), [wf]);
  const scales = useMemo(
    () => ({ ecg: ecg ? scaleFor(ecg.values) : null, pulse: pulse ? scaleFor(pulse.values) : null }),
    [ecg, pulse]
  );
  const fired = bed.fired;

  useEffect(() => {
    if (!wf) return;
    let raf;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const draw = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const { ctx, width, height } = setupCanvas(canvas);
      const rt = getRecordTime(bed);
      ctx.clearRect(0, 0, width, height);
      const rows = [
        [ecg, scales.ecg, 0, height * 0.62],
        [pulse, scales.pulse, height * 0.64, height * 0.36],
      ];
      for (const [ch, sc, y0, h] of rows) {
        if (!ch) continue;
        ctx.strokeStyle = TRACE[ch.kind];
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        let pen = false;
        const sweepStart = Math.floor(rt / SWEEP_S) * SWEEP_S;
        for (let x = 0; x <= width; x += 1) {
          // left of the sweep head: this pass; just ahead of it: the erase bar; beyond: last pass
          const tc = sweepStart + (x / width) * SWEEP_S;
          const t = tc <= rt ? tc : tc - rt < 0.3 ? null : tc - SWEEP_S;
          const v = t === null ? null : sampleAt(ch, wf, t);
          if (v === null) {
            pen = false;
            continue;
          }
          const y = y0 + h - ((v - sc[0]) / (sc[1] - sc[0])) * h;
          if (!pen) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
          pen = true;
        }
        ctx.stroke();
      }
      if (hrRef.current && ecg) hrRef.current.textContent = rateAt(ecg.beats_s, rt) ?? "--";
      if (prRef.current && pulse) prRef.current.textContent = rateAt(pulse.beats_s, rt) ?? "--";
      if (!reduce) raf = requestAnimationFrame(draw);
    };
    draw();
    const slow = reduce ? setInterval(draw, 1000) : null;
    return () => {
      cancelAnimationFrame(raf);
      if (slow) clearInterval(slow);
    };
  }, [wf, ecg, pulse, scales, bed, getRecordTime]);

  const verdict = data?.verdict;
  const reviewed = bed.review;
  return (
    <button
      className={`bed ${fired && !reviewed ? "bed--alarm" : ""} ${selected ? "bed--selected" : ""}`}
      onClick={() => fired && onOpen(bed)}
      aria-label={`Bed ${bed.label}${fired ? `, ${data.alarm_label} alarm` : ""}`}
      disabled={!fired}
    >
      <div className="bed__head">
        <span className="bed__no">{bed.label}</span>
        {fired && !reviewed && <span className="bed__alarm">*** {ALARM_TEXT[data.alarm_type]}</span>}
        {reviewed && <span className="bed__done">Reviewed</span>}
      </div>
      <div className="bed__body">
        <canvas ref={canvasRef} className="bed__trace" />
        <div className="bed__nums">
          <div className="num num--ecg">
            <small>HR</small>
            <span ref={hrRef}>--</span>
          </div>
          {pulse && (
            <div className={`num num--${pulse.kind}`}>
              <small>{pulse.kind === "abp" ? "ABP PR" : "Pleth PR"}</small>
              <span ref={prRef}>--</span>
            </div>
          )}
        </div>
      </div>
      {fired && !reviewed && verdict && (
        <div className={`ai-chip ai-chip--${verdict}`}>
          <span className="ai-chip__who">Co-pilot</span> {VERDICT[verdict].label}
        </div>
      )}
    </button>
  );
}
