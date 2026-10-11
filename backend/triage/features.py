"""Feature extraction: turns one alarm (the minute before it fired) into ~90 numbers.

The features encode the same cross-checks a monitor tech does by eye:
  1. Is each ECG lead even readable? (signal quality: detector agreement, flat line, noise)
  2. Do the two ECG leads tell the same story?
  3. Does the pulse waveform (pleth / arterial line) agree with the ECG?
     A heart in true asystole or V-fib does not produce a regular pulse.
  4. Alarm-specific rhythm math (longest pause, slowest 5 beats, fastest 17 beats).

Everything is computed from data BEFORE the alarm (t <= 300 s).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.signal import welch
from scipy.stats import kurtosis

from .beats import (
    bandpass, detect_pulse, detect_qrs, detect_qrs_gqrs, fill_nan, match_fraction,
    pulse_amplitude, rhythm_stats,
)
from .io import ALARM_TIME_S, ALARM_TYPES, AlarmRecord, CONTEXT_START_S

WINDOW_S = 16.0  # analysis window right before the alarm
LATE_S = 6.0  # "most recent seconds" window: the triggering event starts in the last 10 s
WIN_START = ALARM_TIME_S - WINDOW_S
LATE_START = ALARM_TIME_S - LATE_S


@dataclass
class ChannelAnalysis:
    name: str
    kind: str  # ecg | pleth | abp
    beats_s: list[float]  # beat times (record clock, seconds) over the whole minute
    quality: float  # 0..1, for ordering leads and for the UI
    stats: dict[str, float] = field(default_factory=dict)


@dataclass
class Analysis:
    features: dict[str, float]
    channels: list[ChannelAnalysis]


# ------------------------------------------------------------------ helpers
def _band_power_frac(f: np.ndarray, p: np.ndarray, lo: float, hi: float, tlo: float, thi: float) -> float:
    tot = p[(f >= tlo) & (f <= thi)].sum()
    if tot <= 0:
        return np.nan
    return float(p[(f >= lo) & (f <= hi)].sum() / tot)


def _flat_fraction(x: np.ndarray, fs: float, thresh: float) -> float:
    n = int(0.5 * fs)
    if len(x) < n:
        return 1.0
    segs = x[: len(x) // n * n].reshape(-1, n)
    return float(np.mean(np.nanstd(segs, axis=1) < thresh))


def _template_corr(f: np.ndarray, beats_idx: np.ndarray, fs: float) -> float:
    half = int(0.1 * fs)
    snippets = [f[k - half:k + half] for k in beats_idx if k - half >= 0 and k + half <= len(f)]
    if len(snippets) < 3:
        return np.nan
    m = np.vstack(snippets)
    tmpl = np.median(m, axis=0)
    if np.std(tmpl) == 0:
        return np.nan
    cs = [np.corrcoef(s, tmpl)[0, 1] for s in m if np.std(s) > 0]
    return float(np.mean(cs)) if cs else np.nan


def _in(times: np.ndarray, a: float, b: float) -> np.ndarray:
    return times[(times >= a) & (times < b)]


def _win(rec: AlarmRecord, x: np.ndarray, a: float, b: float) -> np.ndarray:
    i0 = max(0, int(round((a - rec.t0) * rec.fs)))
    i1 = min(len(x), int(round((b - rec.t0) * rec.fs)))
    return x[i0:i1]


# ------------------------------------------------------------------ per channel
def _ecg_lead(rec: AlarmRecord, name: str, x: np.ndarray) -> ChannelAnalysis:
    fs = rec.fs
    beats_full = detect_qrs(x, fs)
    t_beats = rec.t0 + beats_full / fs
    w = _win(rec, x, WIN_START, ALARM_TIME_S)
    wf, nan_frac = fill_nan(w)
    tb = _in(t_beats, WIN_START, ALARM_TIME_S)

    s: dict[str, float] = {"nan_frac": nan_frac}
    s["flat_frac"] = _flat_fraction(w, fs, 0.01)
    bp = bandpass(wf, fs, 0.5, 40.0) if len(wf) > fs else wf
    s["amp"] = float(np.percentile(bp, 99.5) - np.percentile(bp, 0.5)) if len(bp) else 0.0
    s["kurt"] = float(kurtosis(bp)) if np.std(bp) > 0 else 0.0
    if len(wf) >= 2 * fs:
        f, p = welch(wf - np.mean(wf), fs=fs, nperseg=int(4 * fs))
        s["psqi"] = _band_power_frac(f, p, 5, 15, 5, 40)
        s["bas"] = _band_power_frac(f, p, 0, 1, 0, 40)
        s["vf_frac"] = _band_power_frac(f, p, 2.5, 7.5, 1, 40)
        band = (f >= 1) & (f <= 10)
        s["dom_freq"] = float(f[band][np.argmax(p[band])]) if band.any() and p[band].max() > 0 else np.nan
    else:
        s.update(psqi=np.nan, bas=np.nan, vf_frac=np.nan, dom_freq=np.nan)
    late = _win(rec, x, LATE_START, ALARM_TIME_S)
    late_f, _ = fill_nan(late)
    if len(late_f) >= 2 * fs:
        f, p = welch(late_f - np.mean(late_f), fs=fs, nperseg=int(2 * fs))
        s["vf_frac_late"] = _band_power_frac(f, p, 2.5, 7.5, 1, 40)
    else:
        s["vf_frac_late"] = np.nan

    # second, independent detector on the analysis window only -> bSQI
    g = detect_qrs_gqrs(w, fs)
    tb_idx = np.round((tb - WIN_START) * fs).astype(int)
    s["bsqi"] = match_fraction(tb_idx, g, fs)
    s["n_gqrs"] = float(len(g))
    f15 = bandpass(wf, fs, 5.0, 15.0) if len(wf) > fs else wf
    s["tsqi"] = _template_corr(f15, tb_idx, fs)

    s.update(rhythm_stats(tb, WIN_START, ALARM_TIME_S))
    late_b = _in(t_beats, LATE_START, ALARM_TIME_S)
    s["hr_late"] = float(60.0 / np.median(np.diff(late_b))) if len(late_b) >= 3 else np.nan
    s["n_late"] = float(len(late_b))

    q = s["bsqi"] * (1 - s["flat_frac"]) * (1 - nan_frac)
    if not np.isnan(s["tsqi"]):
        q *= 0.5 + 0.5 * max(0.0, s["tsqi"])
    return ChannelAnalysis(name, "ecg", [float(t) for t in t_beats], float(q), s)


def _pulse(rec: AlarmRecord, name: str, kind: str, x: np.ndarray) -> ChannelAnalysis:
    fs = rec.fs
    ctx = _win(rec, x, CONTEXT_START_S, WIN_START)
    ref = pulse_amplitude(ctx, fs)
    min_abs = 3.0 if kind == "abp" else 0.0  # mmHg: a few mmHg of "pulse" is noise on an art line
    peaks_full, prom_full = detect_pulse(x, fs, ref_amp=ref or None, min_abs_amp=0.0)
    t_beats = rec.t0 + peaks_full / fs
    w = _win(rec, x, WIN_START, ALARM_TIME_S)
    _, nan_frac = fill_nan(w)
    amp_w = pulse_amplitude(w, fs)
    late_amp = pulse_amplitude(_win(rec, x, LATE_START, ALARM_TIME_S), fs)
    in_w = (t_beats >= WIN_START) & (t_beats < ALARM_TIME_S)
    tb = t_beats[in_w]
    if amp_w < min_abs:  # flat arterial line: no beats regardless of peak finder
        tb = tb[:0]
    s: dict[str, float] = {"present": 1.0 if nan_frac < 0.9 else 0.0, "nan_frac": nan_frac}
    s["amp_ratio"] = float(amp_w / ref) if ref > 0 else np.nan
    s["late_amp_ratio"] = float(late_amp / ref) if ref > 0 else np.nan
    proms = prom_full[in_w] if len(prom_full) else np.array([])
    s["beat_amp_cv"] = float(np.std(proms) / np.mean(proms)) if len(proms) >= 3 and np.mean(proms) > 0 else np.nan
    s.update(rhythm_stats(tb, WIN_START, ALARM_TIME_S))
    late_b = _in(tb, LATE_START, ALARM_TIME_S)
    s["hr_late"] = float(60.0 / np.median(np.diff(late_b))) if len(late_b) >= 3 else np.nan
    if kind == "abp":
        wf, _ = fill_nan(w)
        s["mean_pressure"] = float(np.median(wf)) if len(wf) else np.nan
        s["pulse_pressure"] = float(np.median(proms)) if len(proms) else 0.0
    q = s["present"] * (1 - nan_frac) * (1.0 if np.isnan(s["rr_cv"]) else max(0.0, 1 - s["rr_cv"]))
    return ChannelAnalysis(name, kind, [float(t) for t in t_beats], float(q), s)


# ------------------------------------------------------------------ main entry
ECG_KEYS = ["nan_frac", "flat_frac", "amp", "kurt", "psqi", "bas", "vf_frac", "vf_frac_late", "dom_freq",
            "bsqi", "n_gqrs", "tsqi", "n_beats", "max_gap", "hr", "min_hr5", "max_hr17", "rr_cv",
            "hr_late", "n_late"]
PULSE_KEYS = ["present", "nan_frac", "amp_ratio", "late_amp_ratio", "beat_amp_cv", "n_beats", "max_gap",
              "hr", "min_hr5", "max_hr17", "rr_cv", "hr_late"]
ABP_EXTRA = ["mean_pressure", "pulse_pressure"]


def feature_names() -> list[str]:
    names = [f"type_{t}" for t in ALARM_TYPES]
    names += [f"ecg_a_{k}" for k in ECG_KEYS] + [f"ecg_b_{k}" for k in ECG_KEYS]
    names += [f"pleth_{k}" for k in PULSE_KEYS] + [f"abp_{k}" for k in PULSE_KEYS + ABP_EXTRA]
    names += [f"pulse_{k}" for k in ["hr", "max_gap", "min_hr5", "max_hr17", "hr_late", "late_amp_ratio"]]
    names += ["ecg_leads_match", "ecg_leads_hr_diff", "ecg_min_max_gap", "ecg_max_min_hr5", "ecg_min_max_hr17",
              "ecg_min_vf_frac_late", "hr_diff_a_pulse", "hr_diff_b_pulse", "hr_diff_best_pulse",
              "pulse_to_ecg_beats", "n_ecg_leads", "n_pulse_channels"]
    return names


def _nanmin(*v: float) -> float:
    v = [x for x in v if x is not None and not np.isnan(x)]
    return float(min(v)) if v else np.nan


def _nanmax(*v: float) -> float:
    v = [x for x in v if x is not None and not np.isnan(x)]
    return float(max(v)) if v else np.nan


def analyze(rec: AlarmRecord) -> Analysis:
    leads = [_ecg_lead(rec, n, x) for n, x in rec.channels("ecg")]
    leads.sort(key=lambda c: c.quality, reverse=True)
    pulses = [_pulse(rec, n, "pleth", x) for n, x in rec.channels("pleth")[:1]]
    pulses += [_pulse(rec, n, "abp", x) for n, x in rec.channels("abp")[:1]]

    F: dict[str, float] = {k: np.nan for k in feature_names()}
    for t in ALARM_TYPES:
        F[f"type_{t}"] = 1.0 if rec.alarm_type == t else 0.0
    for prefix, lead in zip(["ecg_a_", "ecg_b_"], leads[:2]):
        for k in ECG_KEYS:
            F[prefix + k] = lead.stats.get(k, np.nan)
    by_kind = {c.kind: c for c in pulses}
    for kind in ("pleth", "abp"):
        if kind in by_kind:
            keys = PULSE_KEYS + (ABP_EXTRA if kind == "abp" else [])
            for k in keys:
                F[f"{kind}_{k}"] = by_kind[kind].stats.get(k, np.nan)
        else:
            F[f"{kind}_present"] = 0.0

    # best pulse source: the more regular of the available ones (ABP wins ties)
    usable = [c for c in pulses if c.stats.get("present", 0) > 0]
    if usable:
        best = max(usable, key=lambda c: (c.quality, c.kind == "abp"))
        for k in ["hr", "max_gap", "min_hr5", "max_hr17", "hr_late", "late_amp_ratio"]:
            F[f"pulse_{k}"] = best.stats.get(k, np.nan)

    a = leads[0].stats if leads else {}
    b = leads[1].stats if len(leads) > 1 else {}
    if len(leads) > 1:
        ta = np.round(np.array(_in(np.array(leads[0].beats_s), WIN_START, ALARM_TIME_S)) * rec.fs).astype(int)
        tb = np.round(np.array(_in(np.array(leads[1].beats_s), WIN_START, ALARM_TIME_S)) * rec.fs).astype(int)
        F["ecg_leads_match"] = match_fraction(ta, tb, rec.fs)
        F["ecg_leads_hr_diff"] = abs(a.get("hr", np.nan) - b.get("hr", np.nan))
    F["ecg_min_max_gap"] = _nanmin(a.get("max_gap"), b.get("max_gap"))
    F["ecg_max_min_hr5"] = _nanmax(a.get("min_hr5"), b.get("min_hr5"))
    F["ecg_min_max_hr17"] = _nanmin(a.get("max_hr17"), b.get("max_hr17"))
    F["ecg_min_vf_frac_late"] = _nanmin(a.get("vf_frac_late"), b.get("vf_frac_late"))
    ph = F["pulse_hr"]
    F["hr_diff_a_pulse"] = abs(a.get("hr", np.nan) - ph) if leads else np.nan
    F["hr_diff_b_pulse"] = abs(b.get("hr", np.nan) - ph) if len(leads) > 1 else np.nan
    F["hr_diff_best_pulse"] = _nanmin(F["hr_diff_a_pulse"], F["hr_diff_b_pulse"])
    if leads and a.get("n_beats", 0) > 0 and usable:
        F["pulse_to_ecg_beats"] = best.stats.get("n_beats", 0) / a["n_beats"]
    F["n_ecg_leads"] = float(len(leads))
    F["n_pulse_channels"] = float(len(usable))
    F = {k: (float(v) if v is not None else np.nan) for k, v in F.items()}
    return Analysis(features=F, channels=leads + pulses)


def feature_vector(analysis: Analysis, names: list[str]) -> np.ndarray:
    return np.array([[analysis.features.get(n, np.nan) for n in names]], dtype=np.float64)
