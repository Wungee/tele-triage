"""Run from backend/:  pytest -q

Uses two REAL PhysioNet 2015 records bundled with wfdb-python (a103l: false asystole,
v102s: false V-tach) plus synthetic signals for edge cases.
"""

from pathlib import Path

import numpy as np
import pytest

from triage.beats import detect_pulse, detect_qrs, match_fraction, rhythm_stats
from triage.features import analyze, feature_names
from triage.io import AlarmRecord, load_npz, load_wfdb, save_npz

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def a103l():
    return load_wfdb(FIX / "a103l")


def test_load_real_record(a103l):
    assert a103l.alarm_type == "Asystole"
    assert a103l.is_true_alarm is False
    assert a103l.fs == 250
    assert a103l.t0 == 240.0 and len(a103l.signals) == 60 * 250  # only pre-alarm data
    assert [n for n, _ in a103l.channels("ecg")] == ["II", "V"]


def test_false_asystole_shows_a_heartbeat(a103l):
    F = analyze(a103l).features
    assert F["pulse_max_gap"] < 1.5          # pleth keeps beating
    assert F["ecg_min_max_gap"] < 2.0        # QRS keeps coming on the ECG too
    assert abs(F["ecg_a_hr"] - F["pulse_hr"]) < 10


def test_noisy_lead_is_detected_on_false_vtach():
    F = analyze(load_wfdb(FIX / "v102s")).features
    assert F["ecg_leads_hr_diff"] > 30       # lead II counts noise as beats
    assert F["ecg_b_bsqi"] < F["ecg_a_bsqi"]


def test_feature_vector_complete(a103l):
    F = analyze(a103l).features
    assert list(sorted(F)) == sorted(feature_names())


def test_flat_ecg_has_no_beats():
    fs = 250
    x = np.random.default_rng(0).normal(0, 0.003, 16 * fs)
    assert len(detect_qrs(x, fs)) == 0


def test_collapsed_pulse_has_no_beats():
    fs = 250
    t = np.arange(16 * fs) / fs
    x = 0.002 * np.random.default_rng(1).normal(size=len(t))
    peaks, _ = detect_pulse(x, fs, ref_amp=1.0)
    assert len(peaks) == 0


def test_rhythm_stats_brady():
    beats = np.arange(0, 16, 1.6)  # 37.5 bpm
    s = rhythm_stats(beats, 0, 16)
    assert 36 < s["min_hr5"] < 39
    assert s["max_gap"] == pytest.approx(1.6, abs=0.01)


def test_match_fraction():
    a = np.array([100, 350, 600])
    assert match_fraction(a, a, 250) == 1.0
    assert match_fraction(a, np.array([]), 250) == 0.0
    assert match_fraction(np.array([]), np.array([]), 250) == 1.0


def test_npz_roundtrip(tmp_path, a103l):
    save_npz(a103l, tmp_path / "x.npz")
    r = load_npz(tmp_path / "x.npz")
    assert r.alarm_type == a103l.alarm_type and r.is_true_alarm is False
    assert np.allclose(r.signals, a103l.signals, equal_nan=True, atol=1e-4)


def test_handles_nan_channel(a103l):
    rec = AlarmRecord(**{**a103l.__dict__, "signals": a103l.signals.copy()})
    rec.signals[:, 2] = np.nan  # pleth unplugged
    F = analyze(rec).features
    assert F["n_pulse_channels"] == 0
