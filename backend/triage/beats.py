"""Beat detection and signal-quality primitives.

Two independent QRS detectors run on every ECG lead:
  * a Pan-Tompkins-style energy detector (ours, below), and
  * GQRS from the wfdb library (a different algorithm entirely).
When a lead is clean the two agree almost beat-for-beat; when it's noise, motion or a loose
electrode they disagree. Their agreement (bSQI) is one of the strongest false-alarm signals
in the literature (Li & Clifford, Physiol Meas 2008; Behar et al. 2013).

Pulse waveforms (PLETH / ABP) get a peak detector whose sensitivity is anchored to the pulse
amplitude in the minute BEFORE the alarm, so a pulse that genuinely collapses is not "found"
in the noise floor.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, find_peaks, sosfiltfilt


def fill_nan(x: np.ndarray) -> tuple[np.ndarray, float]:
    x = np.asarray(x, dtype=np.float64).copy()
    bad = ~np.isfinite(x)
    frac = float(bad.mean()) if len(x) else 1.0
    if bad.all():
        return np.zeros_like(x), 1.0
    if bad.any():
        idx = np.arange(len(x))
        x[bad] = np.interp(idx[bad], idx[~bad], x[~bad])
    return x, frac


def bandpass(x: np.ndarray, fs: float, lo: float, hi: float, order: int = 2) -> np.ndarray:
    hi = min(hi, 0.45 * fs)
    sos = butter(order, [lo, hi], btype="band", fs=fs, output="sos")
    if len(x) <= 3 * (2 * order + 1) * 2:
        return x - np.mean(x)
    return sosfiltfilt(sos, x)


# ---------------------------------------------------------------------------- ECG
QRS_MIN_AMP_MV = 0.05  # band-passed peak-to-peak below this = no usable QRS on this lead


def detect_qrs(x: np.ndarray, fs: float) -> np.ndarray:
    """Energy-based QRS detector. Returns sample indices of R peaks."""
    x, _ = fill_nan(x)
    if len(x) < fs:
        return np.array([], dtype=int)
    f = bandpass(x, fs, 5.0, 15.0)
    if np.percentile(f, 99.5) - np.percentile(f, 0.5) < QRS_MIN_AMP_MV:
        return np.array([], dtype=int)
    d = np.diff(f, prepend=f[0])
    w = max(1, int(0.15 * fs))
    integ = np.convolve(d * d, np.ones(w) / w, mode="same")
    cand, _ = find_peaks(integ, distance=int(0.2 * fs))
    if len(cand) == 0:
        return np.array([], dtype=int)
    h = integ[cand]
    global_ref = np.percentile(h, 90)
    # Local adaptive threshold (+/- 2.5 s): a burst of large artifact elsewhere in the strip
    # must not hide the real, smaller QRS complexes around it.
    half_win = int(2.5 * fs)
    keep_mask = np.zeros(len(cand), dtype=bool)
    for i, k in enumerate(cand):
        near = h[(cand >= k - half_win) & (cand <= k + half_win)]
        local_ref = np.percentile(near, 75)
        keep_mask[i] = h[i] >= 0.3 * local_ref and h[i] >= 0.02 * global_ref
    cand = cand[keep_mask]
    # snap each candidate to the largest deflection of the band-passed ECG nearby,
    # and drop anything too small to be a QRS on any real lead (flat line + noise)
    half = int(0.1 * fs)
    r = []
    for k in cand:
        lo, hi = max(0, k - half), min(len(f), k + half)
        seg = f[lo:hi]
        if np.ptp(seg) < QRS_MIN_AMP_MV:
            continue
        r.append(lo + int(np.argmax(np.abs(seg))))
    r = np.unique(np.asarray(r, dtype=int))
    # enforce a 200 ms refractory period, keeping the larger beat
    keep: list[int] = []
    for k in r:
        if keep and k - keep[-1] < 0.2 * fs:
            if abs(f[k]) > abs(f[keep[-1]]):
                keep[-1] = k
        else:
            keep.append(int(k))
    return np.asarray(keep, dtype=int)


def detect_qrs_gqrs(x: np.ndarray, fs: float) -> np.ndarray:
    """Second, independent detector (GQRS via wfdb). Empty array if it can't run."""
    try:
        from wfdb import processing
    except Exception:  # pragma: no cover - wfdb is a hard dependency in practice
        return np.array([], dtype=int)
    x, _ = fill_nan(x)
    if len(x) < 2 * fs or np.ptp(x) < 1e-6:
        return np.array([], dtype=int)
    try:
        idx = processing.gqrs_detect(sig=x, fs=fs, adc_gain=200.0, adc_zero=0)
        return np.asarray(idx, dtype=int)
    except Exception:
        return np.array([], dtype=int)


def match_fraction(a: np.ndarray, b: np.ndarray, fs: float, tol_s: float = 0.15) -> float:
    """bSQI-style agreement: matched / (|a| + |b| - matched). 1.0 = identical beat lists.

    Both empty counts as agreement (both detectors see a flat line)."""
    if len(a) == 0 and len(b) == 0:
        return 1.0
    if len(a) == 0 or len(b) == 0:
        return 0.0
    tol = tol_s * fs
    j = matched = 0
    for k in a:
        while j < len(b) and b[j] < k - tol:
            j += 1
        if j < len(b) and abs(b[j] - k) <= tol:
            matched += 1
            j += 1
    return matched / (len(a) + len(b) - matched)


# --------------------------------------------------------------------------- pulse
def pulse_amplitude(x: np.ndarray, fs: float) -> float:
    """Robust peak-to-peak amplitude of the band-passed pulse waveform."""
    x, frac = fill_nan(x)
    if frac > 0.9 or len(x) < fs:
        return 0.0
    f = bandpass(x, fs, 0.5, 8.0)
    return float(np.percentile(f, 95) - np.percentile(f, 5))


def detect_pulse(x: np.ndarray, fs: float, ref_amp: float | None = None,
                 min_abs_amp: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Peak detector for PLETH / ABP. Returns (peak indices, peak prominences).

    ref_amp: typical pulse amplitude from the pre-alarm minute; anchors the threshold so a
    collapsed pulse yields no beats instead of noise "beats".
    """
    x, frac = fill_nan(x)
    if frac > 0.9 or len(x) < fs:
        return np.array([], dtype=int), np.array([])
    f = bandpass(x, fs, 0.5, 8.0)
    amp = float(np.percentile(f, 95) - np.percentile(f, 5))
    ref = ref_amp if ref_amp and ref_amp > 0 else amp
    if ref <= 0 or amp < min_abs_amp:
        return np.array([], dtype=int), np.array([])
    peaks, props = find_peaks(f, distance=int(0.27 * fs), prominence=0.3 * ref)
    return peaks.astype(int), props["prominences"]


# ------------------------------------------------------------------ rhythm stats
def rhythm_stats(beat_times: np.ndarray, win_start: float, win_end: float) -> dict[str, float]:
    """Heart-rate statistics that mirror how monitors define each alarm.

    * max_gap   : longest stretch without a beat (asystole = no QRS for >= 4 s)
    * min_hr5   : slowest rate over any 5 consecutive beats (extreme brady = < 40 bpm)
    * max_hr17  : fastest rate over any 17 consecutive beats (extreme tachy = > 140 bpm)
    """
    t = np.sort(np.asarray(beat_times, dtype=float))
    n = len(t)
    edges = np.concatenate([[win_start], t, [win_end]])
    out = {
        "n_beats": float(n),
        "max_gap": float(np.max(np.diff(edges))) if len(edges) > 1 else float(win_end - win_start),
        "hr": np.nan, "min_hr5": np.nan, "max_hr17": np.nan, "rr_cv": np.nan,
    }
    if n >= 2:
        rr = np.diff(t)
        out["hr"] = float(60.0 / np.median(rr))
        out["rr_cv"] = float(np.std(rr) / np.mean(rr))
        k = min(4, len(rr))
        out["min_hr5"] = float(60.0 / np.max(np.convolve(rr, np.ones(k) / k, mode="valid")))
        k = min(16, len(rr))
        out["max_hr17"] = float(60.0 / np.min(np.convolve(rr, np.ones(k) / k, mode="valid")))
    return out
