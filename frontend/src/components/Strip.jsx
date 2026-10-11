import { useEffect, useMemo, useRef } from "react";
import { TRACE, scaleFor, setupCanvas } from "../waveform.js";

// A full-width rhythm strip for one channel, with the co-pilot's beat marks drawn above the
// trace and the 16 s it analysed shaded. Beat marks are the point: a tech can see at a glance
// whether the ECG beats and the pulse beats line up.
export default function Strip({ ch, wf, from, to, alarmT, windowS, highlighted }) {
  const ref = useRef(null);
  const scale = useMemo(() => {
    const i0 = Math.max(0, Math.round((from - wf.t0) * wf.fs));
    const i1 = Math.round((to - wf.t0) * wf.fs);
    return scaleFor(ch.values.slice(i0, i1));
  }, [ch, wf, from, to]);

  useEffect(() => {
    const draw = () => {
      const canvas = ref.current;
      if (!canvas) return;
      const { ctx, width, height } = setupCanvas(canvas);
      const X = (t) => ((t - from) / (to - from)) * width;
      const top = 14;
      const h = height - top - 4;
      ctx.clearRect(0, 0, width, height);

      // 1-second grid, the way strips are read
      ctx.strokeStyle = "rgba(120,140,160,0.13)";
      ctx.lineWidth = 1;
      for (let t = Math.ceil(from); t <= to; t++) {
        ctx.beginPath();
        ctx.moveTo(X(t) + 0.5, top);
        ctx.lineTo(X(t) + 0.5, height);
        ctx.stroke();
      }
      // analysed window
      ctx.fillStyle = "rgba(185,167,255,0.07)";
      ctx.fillRect(X(windowS[0]), 0, X(windowS[1]) - X(windowS[0]), height);

      // trace
      ctx.strokeStyle = TRACE[ch.kind];
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      let pen = false;
      const i0 = Math.max(0, Math.floor((from - wf.t0) * wf.fs));
      const i1 = Math.min(ch.values.length, Math.ceil((to - wf.t0) * wf.fs));
      for (let i = i0; i < i1; i++) {
        const v = ch.values[i];
        if (v === null) {
          pen = false;
          continue;
        }
        const x = X(wf.t0 + i / wf.fs);
        const y = top + h - ((v - scale[0]) / (scale[1] - scale[0])) * h;
        if (!pen) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
        pen = true;
      }
      ctx.stroke();

      // co-pilot beat marks
      ctx.strokeStyle = "#b9a7ff";
      ctx.lineWidth = 2;
      for (const b of ch.beats_s) {
        if (b < from || b > to) continue;
        ctx.beginPath();
        ctx.moveTo(X(b), 2);
        ctx.lineTo(X(b), 10);
        ctx.stroke();
      }
      // alarm marker
      ctx.strokeStyle = "#ff2d3d";
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(X(alarmT) - 1, 0);
      ctx.lineTo(X(alarmT) - 1, height);
      ctx.stroke();
      ctx.setLineDash([]);
    };
    draw();
    window.addEventListener("resize", draw);
    return () => window.removeEventListener("resize", draw);
  }, [ch, wf, from, to, alarmT, windowS, scale]);

  return (
    <div className={`strip ${highlighted ? "strip--hl" : ""}`}>
      <div className="strip__label" style={{ color: TRACE[ch.kind] }}>
        <strong>{ch.name}</strong>
        <span>{ch.units}</span>
        {ch.quality !== null && ch.quality !== undefined && (
          <span className="strip__q">signal quality {Math.round(ch.quality * 100)}%</span>
        )}
      </div>
      <canvas ref={ref} className="strip__canvas" aria-label={`${ch.name} waveform, last ${to - from} seconds`} />
    </div>
  );
}
