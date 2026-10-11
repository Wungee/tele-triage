import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api.js";
import AlarmDetail from "./components/AlarmDetail.jsx";
import BedTile, { BedSkeleton } from "./components/BedTile.jsx";
import ModelCard from "./components/ModelCard.jsx";
import Queue from "./components/Queue.jsx";

const N_BEDS = 12;
const REPLAY_START = 240; // each bed replays from 4:00 into the record; the alarm fires at 5:00

// Deterministic shuffle, so a demo run is rehearsable: same ?seed= -> same alarm order.
function shuffled(arr, seed) {
  const a = [...arr];
  let s = seed >>> 0 || 1;
  for (let i = a.length - 1; i > 0; i--) {
    s = (s * 1664525 + 1013904223) >>> 0;
    const j = s % (i + 1);
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export default function App() {
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);
  const [beds, setBeds] = useState([]);
  const [openKey, setOpenKey] = useState(null);
  const [paused, setPaused] = useState(false);
  const [stats, setStats] = useState(null);
  const [card, setCard] = useState(null);
  const [showCard, setShowCard] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [expected, setExpected] = useState(N_BEDS);

  const sim = useRef(0); // simulated seconds since the wall started
  const pausedRef = useRef(false);
  const pool = useRef([]);
  const keySeq = useRef(0);

  // ---- simulation clock -----------------------------------------------------
  useEffect(() => {
    let last = performance.now();
    let raf;
    const tick = (t) => {
      const dt = Math.min(0.25, (t - last) / 1000);
      last = t;
      if (!pausedRef.current) sim.current += dt;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);
  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  const getRecordTime = useCallback(
    (bed) => Math.min(300, bed.startRt + (sim.current - bed.simStart)),
    []
  );

  const makeBed = useCallback(async (label, fireIn) => {
    const id = pool.current.shift();
    if (!id) return null;
    pool.current.push(id); // loop forever in long demos
    const data = await api.alarm(id);
    const startRt = Math.max(REPLAY_START, 300 - fireIn);
    return {
      key: `${label}-${keySeq.current++}`, label, alarmId: id, data,
      startRt, simStart: sim.current, fired: false, firedAtWall: null, review: null,
    };
  }, []);

  // ---- boot -------------------------------------------------------------------
  const booted = useRef(false);
  useEffect(() => {
    if (booted.current) return; // React StrictMode runs effects twice in dev
    booted.current = true;
    (async () => {
      try {
        const h = await api.health();
        setHealth(h);
        if (!h.model_loaded) {
          setError("No trained model on the server. Run python scripts/train.py, then reload.");
          return;
        }
        const [{ alarms }, mc, st] = await Promise.all([api.alarms(), api.model(), api.stats()]);
        setCard(mc);
        setStats(st);
        let ids = shuffled(alarms.map((a) => a.id), Number(params.get("seed") || 7));
        const first = params.get("first");
        if (first && ids.includes(first)) ids = [first, ...ids.filter((x) => x !== first)];
        pool.current = ids;
        const n = Math.min(N_BEDS, ids.length);
        // stagger: first alarm after ~6 s, then one every ~5 s, like a busy night
        setExpected(n);
        for (let i = 0; i < n; i++) {
          const bed = await makeBed(String(i + 1).padStart(2, "0"), 6 + i * 5);
          if (bed) setBeds((bs) => [...bs, bed]); // fill the wall bed by bed; skeletons hold the rest
        }
      } catch (e) {
        setError(`Cannot reach the API (${e.message}). Is the backend running on port 8000?`);
      }
    })();
  }, [makeBed, params]);

  // ---- fire alarms when a replay reaches 5:00 ----------------------------------
  useEffect(() => {
    const iv = setInterval(() => {
      setNow(Date.now());
      setBeds((bs) => {
        let changed = false;
        const next = bs.map((b) => {
          if (!b.fired && getRecordTime(b) >= 300) {
            changed = true;
            return { ...b, fired: true, firedAtWall: Date.now() };
          }
          return b;
        });
        return changed ? next : bs;
      });
    }, 250);
    return () => clearInterval(iv);
  }, [getRecordTime]);

  const openBed = beds.find((b) => b.key === openKey) || null;

  const onReviewed = useCallback((bed, review) => {
    setBeds((bs) => bs.map((b) => (b.key === bed.key ? { ...b, review } : b)));
    api.stats().then(setStats).catch(() => {});
  }, []);

  const closeDetail = useCallback(() => {
    const b = beds.find((x) => x.key === openKey);
    setOpenKey(null);
    if (b?.review) {
      // bed gets a new patient-minute; its next alarm comes 20-40 s later
      setTimeout(async () => {
        const nb = await makeBed(b.label, 20 + Math.random() * 20);
        if (nb) setBeds((bs) => bs.map((x) => (x.key === b.key ? nb : x)));
      }, 1500);
    }
  }, [beds, openKey, makeBed]);

  const agree = stats?.ai_agreement_with_experts;
  return (
    <div className="app">
      {health?.synthetic && (
        <p className="banner">Synthetic demo data. Train on the PhysioNet dataset before presenting.</p>
      )}
      <header className="top">
        <div className="brand">
          <svg viewBox="0 0 32 32" aria-hidden="true">
            <path d="M2 18h7l3-9 4 15 3-9h11" />
          </svg>
          <div>
            <h1>Alarm Triage Co-Pilot</h1>
            <p>Central monitoring, replaying real ICU alarms the model never trained on</p>
          </div>
        </div>
        <dl className="kpis">
          <div>
            <dt>Reviewed</dt>
            <dd>{stats?.reviews ?? 0}</dd>
          </div>
          <div>
            <dt>Co-pilot matched experts</dt>
            <dd>{agree === null || agree === undefined ? "--" : `${Math.round(agree * 100)}%`}</dd>
          </div>
          <div>
            <dt>Avg time to decide</dt>
            <dd>{stats?.avg_seconds_to_decision ? `${stats.avg_seconds_to_decision.toFixed(1)} s` : "--"}</dd>
          </div>
        </dl>
        <div className="top__actions">
          <button className="btn" onClick={() => setPaused((p) => !p)} aria-pressed={paused}>
            {paused ? "Resume replay" : "Pause replay"}
          </button>
          <button className="btn" onClick={() => setShowCard(true)} disabled={!card}>
            Model accuracy
          </button>
        </div>
      </header>

      {error && <p className="error">{error}</p>}

      <main className="main">
        {openBed ? (
          <AlarmDetail key={openBed.key} bed={openBed} onClose={closeDetail} onReviewed={onReviewed} />
        ) : (
          <section className="wall" aria-label="Bed wall">
            {beds.map((b) => (
              <BedTile key={b.key} bed={b} getRecordTime={getRecordTime} selected={false} onOpen={(x) => setOpenKey(x.key)} />
            ))}
            {!error &&
              Array.from({ length: Math.max(0, expected - beds.length) }, (_, i) => (
                <BedSkeleton key={`sk-${i}`} label={String(beds.length + i + 1).padStart(2, "0")} />
              ))}
          </section>
        )}
        <Queue beds={beds} now={now} onOpen={(b) => setOpenKey(b.key)} selectedId={openKey} />
      </main>

      <footer className="foot">
        <span>Research prototype. Not for clinical use.</span>
        <a href="/terms">Terms</a>
        <a href="/privacy">Privacy</a>
        <span className="foot__credit">
          Data: PhysioNet/CinC Challenge 2015 (ODC-By). Type: Ronzino and Coconat by Collletttivo (OFL).
        </span>
      </footer>

      {showCard && <ModelCard card={card} onClose={() => setShowCard(false)} />}
    </div>
  );
}
