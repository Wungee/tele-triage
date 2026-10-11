"""Generate a SYNTHETIC dataset in the exact PhysioNet 2015 format, for testing the pipeline only.

    python scripts/make_synthetic.py --out data/synthetic --n 150

Never present results on this data as model performance. It exists so CI / a fresh laptop can
exercise download-free training, the API and the UI end to end. The real dataset is fetched by
scripts/download_data.py.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

FS = 250
DUR = 300.0
TYPES = {  # prefix, share of records, share that are TRUE alarms (roughly like the real set)
    "Asystole": ("a", 0.16, 0.2),
    "Bradycardia": ("b", 0.12, 0.5),
    "Tachycardia": ("t", 0.19, 0.9),
    "Ventricular_Tachycardia": ("v", 0.45, 0.27),
    "Ventricular_Flutter_Fib": ("f", 0.08, 0.15),
}


def _g(t, mu, a, w):
    return a * np.exp(-0.5 * ((t - mu) / w) ** 2)


def ecg_from_beats(t, beats, wide=None, amp=1.0):
    x = np.zeros_like(t)
    wide = wide if wide is not None else np.zeros(len(beats), bool)
    for b, w in zip(beats, wide):
        lo, hi = np.searchsorted(t, [b - 0.35, b + 0.5])
        tt = t[lo:hi] - b
        if w:  # ventricular beat: wide, tall, no P wave
            x[lo:hi] += _g(tt, 0, 1.4 * amp, 0.045) + _g(tt, 0.12, -0.6 * amp, 0.06) + _g(tt, 0.32, -0.3 * amp, 0.07)
        else:
            x[lo:hi] += (_g(tt, -0.2, 0.12, 0.025) + _g(tt, -0.03, -0.12, 0.01) + _g(tt, 0, amp, 0.012)
                         + _g(tt, 0.03, -0.25, 0.01) + _g(tt, 0.25, 0.3, 0.05))
    return x


def pulse_from_beats(t, beats, delay=0.3, amps=None):
    x = np.zeros_like(t)
    amps = amps if amps is not None else np.ones(len(beats))
    for b, a in zip(beats, amps):
        lo, hi = np.searchsorted(t, [b, b + 1.0])
        tt = t[lo:hi] - b
        x[lo:hi] += a * (_g(tt, delay, 1.0, 0.08) + _g(tt, delay + 0.3, 0.3, 0.06))
    return x


def beat_train(rng, start, end, hr, jitter=0.03):
    out, t = [], start + rng.uniform(0, 60 / hr)
    while t < end:
        out.append(t)
        t += 60 / hr * (1 + rng.normal(0, jitter))
    return np.array(out)


def motion(rng, t, t0, t1, amp):
    x = np.zeros_like(t)
    m = (t >= t0) & (t < t1)
    n = int(m.sum())
    if n:
        noise = np.convolve(rng.normal(0, 1, n + 50), np.ones(25) / 5, mode="same")[:n]
        noise += amp * np.sin(2 * np.pi * rng.uniform(3, 6) * t[m])
        x[m] = amp * noise / (np.std(noise) + 1e-9)
    return x


def make_record(rng, alarm_type, is_true):
    t = np.arange(int(DUR * FS)) / FS
    hr0 = rng.uniform(60, 100)
    ev = rng.uniform(288, 297)  # event onset, within 10 s of the alarm
    beats = beat_train(rng, 0, DUR, hr0)
    ecg_beats, pulse_beats = beats.copy(), beats.copy()
    wide = np.zeros(len(beats), bool)
    pulse_amps = np.ones(len(beats))
    art = {"II": np.zeros_like(t), "V": np.zeros_like(t)}
    flat = {"II": None, "V": None}
    pulse_flat_from = None

    if alarm_type == "Asystole":
        if is_true:
            ecg_beats = beats[beats < ev]
            pulse_beats = ecg_beats
            pulse_flat_from = ev
        else:
            flat["II"] = ev
            if rng.random() < 0.5:
                flat["V"] = ev
    elif alarm_type == "Bradycardia":
        if is_true:
            b2 = beat_train(rng, ev - 8, DUR, rng.uniform(28, 38))
            ecg_beats = np.concatenate([beats[beats < ev - 8], b2])
            pulse_beats = ecg_beats
        else:  # every other QRS tiny on lead II (monitor undercounts); pulse fine
            pass
    elif alarm_type == "Tachycardia":
        if is_true:
            b2 = beat_train(rng, ev - 12, DUR, rng.uniform(150, 185))
            ecg_beats = np.concatenate([beats[beats < ev - 12], b2])
            pulse_beats = ecg_beats
        else:
            for k in ("II", "V"):
                art[k] += motion(rng, t, ev - 10, DUR, rng.uniform(0.4, 0.9))
    elif alarm_type == "Ventricular_Tachycardia":
        if is_true:
            b2 = beat_train(rng, ev, DUR, rng.uniform(150, 210), jitter=0.02)
            ecg_beats = np.concatenate([beats[beats < ev], b2])
            wide = np.concatenate([np.zeros((beats < ev).sum(), bool), np.ones(len(b2), bool)])
            pulse_beats = ecg_beats
            pulse_amps = np.where(wide, rng.uniform(0.05, 0.3), 1.0)
        else:
            lead = "II" if rng.random() < 0.6 else "V"
            art[lead] += motion(rng, t, ev, DUR, rng.uniform(0.8, 1.6))
            if rng.random() < 0.4:
                art["V" if lead == "II" else "II"] += motion(rng, t, ev, DUR, rng.uniform(0.3, 0.8))
    elif alarm_type == "Ventricular_Flutter_Fib":
        if is_true:
            ecg_beats = beats[beats < ev]
            pulse_beats = ecg_beats
            pulse_flat_from = ev
            for k in ("II", "V"):
                m = t >= ev
                f = rng.uniform(4, 6)
                env = 0.5 + 0.4 * np.sin(2 * np.pi * 0.3 * t[m])
                art[k][m] += env * np.sin(2 * np.pi * f * t[m] + rng.uniform(0, 6)) * rng.uniform(0.6, 1.2)
        else:
            for k in ("II", "V"):
                art[k] += motion(rng, t, ev, DUR, rng.uniform(0.8, 1.5))

    if len(wide) != len(ecg_beats):
        wide = np.zeros(len(ecg_beats), bool)
    if len(pulse_amps) != len(pulse_beats):
        pulse_amps = np.ones(len(pulse_beats))

    sigs, names, units = [], [], []
    for lead, amp in (("II", 1.0), ("V", rng.uniform(0.5, 0.9))):
        x = ecg_from_beats(t, ecg_beats, wide, amp)
        if alarm_type == "Bradycardia" and not is_true and lead == "II":
            small = np.arange(len(ecg_beats)) % 2 == 1
            small &= ecg_beats > ev - 10
            x = ecg_from_beats(t, ecg_beats[~small], None, amp) + ecg_from_beats(t, ecg_beats[small], None, 0.03)
        x += art[lead] + 0.15 * np.sin(2 * np.pi * 0.25 * t) + rng.normal(0, 0.02, len(t))
        if flat[lead] is not None:
            x[t >= flat[lead]] = rng.normal(0, 0.003, int((t >= flat[lead]).sum()))
        sigs.append(x); names.append(lead); units.append("mV")

    p = pulse_from_beats(t, pulse_beats, amps=pulse_amps) + rng.normal(0, 0.01, len(t))
    if pulse_flat_from is not None:
        m = t >= pulse_flat_from + 1.0
        p[m] = rng.normal(0, 0.01, int(m.sum()))
    if rng.random() < 0.6:
        sigs.append(0.5 + 0.4 * p); names.append("PLETH"); units.append("NU")
    else:
        sigs.append(75 + 45 * p); names.append("ABP"); units.append("mmHg")
    return np.vstack(sigs).T, names, units


def main() -> None:
    import wfdb

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/synthetic")
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    records, k = [], 100
    for alarm_type, (prefix, share, true_share) in TYPES.items():
        n = max(4, int(round(args.n * share)))
        n_true = max(2, int(round(n * true_share)))
        n_true = min(n_true, n - 2)
        for i in range(n):
            is_true = i < n_true
            sig, names, units = make_record(rng, alarm_type, is_true)
            name = f"{prefix}{k}s"
            k += 1
            wfdb.wrsamp(name, fs=FS, units=units, sig_name=names, p_signal=sig, fmt=["16"] * len(names),
                        comments=[alarm_type, "True alarm" if is_true else "False alarm"], write_dir=str(out))
            records.append(name)
    (out / "RECORDS").write_text("\n".join(records) + "\n")
    print(f"Wrote {len(records)} SYNTHETIC records to {out}")


if __name__ == "__main__":
    main()
