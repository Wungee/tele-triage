"""Model loading + live triage of one alarm record."""

from __future__ import annotations

import json
import math
import re
import warnings
from pathlib import Path

import joblib
import numpy as np

from triage.features import Analysis, analyze, feature_vector
from triage.io import ALARM_LABELS, ALARM_TIME_S, AlarmRecord, load_npz

from .explain import build_reasons

SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _clean(v):
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, (np.floating,)):
        return _clean(float(v))
    return v


class TriageService:
    def __init__(self, artifact_dir: Path):
        self.artifact_dir = artifact_dir
        bundle = joblib.load(artifact_dir / "model.joblib")
        import sklearn

        if bundle.get("sklearn_version") != sklearn.__version__:
            warnings.warn(f"model trained with scikit-learn {bundle.get('sklearn_version')}, "
                          f"running {sklearn.__version__}; retrain if predictions look off")
        self.model = bundle["model"]
        self.names: list[str] = bundle["feature_names"]
        self.t_low: float = bundle["t_low"]
        self.t_high: float = bundle["t_high"]
        self.dataset: str = bundle.get("dataset", "")
        self.synthetic: bool = bool(bundle.get("synthetic"))
        rp = artifact_dir / "report.json"
        self.report = json.loads(rp.read_text()) if rp.exists() else {}
        self.report.pop("test_predictions", None)
        ip = artifact_dir / "demo" / "index.json"
        self.demo_index = json.loads(ip.read_text())["alarms"] if ip.exists() else []
        self._demo_ids = {a["id"] for a in self.demo_index}
        self._cache: dict[str, tuple[AlarmRecord, Analysis, dict]] = {}

    # --------------------------------------------------------------- records
    def demo_record(self, alarm_id: str) -> AlarmRecord:
        if not SAFE_ID.match(alarm_id) or alarm_id not in self._demo_ids:
            raise KeyError(alarm_id)
        return load_npz(self.artifact_dir / "demo" / f"{alarm_id}.npz")

    # ---------------------------------------------------------------- triage
    def verdict(self, p_true: float) -> str:
        if p_true < self.t_low:
            return "likely_artifact"
        if p_true >= self.t_high:
            return "likely_real"
        return "needs_review"

    def triage(self, rec: AlarmRecord) -> tuple[Analysis, dict]:
        A = analyze(rec)
        p = float(self.model.predict_proba(feature_vector(A, self.names))[0, 1])
        v = self.verdict(p)
        F = A.features
        ecg = [c for c in A.channels if c.kind == "ecg"]
        pulses = [c for c in A.channels if c.kind in ("pleth", "abp")]
        vitals = {
            "ecg": [{"lead": c.name, "hr": _clean(c.stats.get("hr")), "quality": round(c.quality, 2),
                     "max_gap_s": _clean(c.stats.get("max_gap"))} for c in ecg],
            "pulse": [{"source": c.name, "hr": _clean(c.stats.get("hr")),
                       "max_gap_s": _clean(c.stats.get("max_gap")),
                       "amplitude_vs_baseline": _clean(c.stats.get("late_amp_ratio")),
                       "present": bool(c.stats.get("present", 0))} for c in pulses],
            "abp_mean": _clean(F.get("abp_mean_pressure")),
        }
        result = {
            "id": rec.record_id, "alarm_type": rec.alarm_type,
            "alarm_label": ALARM_LABELS.get(rec.alarm_type, rec.alarm_type),
            "alarm_time_s": ALARM_TIME_S, "window_s": [ALARM_TIME_S - 16.0, ALARM_TIME_S],
            "p_true": round(p, 4), "verdict": v,
            "thresholds": {"likely_artifact_below": self.t_low, "likely_real_at_or_above": self.t_high},
            "reasons": build_reasons(rec.alarm_type, A), "vitals": vitals,
            "model": {"dataset": self.dataset, "synthetic": self.synthetic},
        }
        return A, result

    def triage_demo(self, alarm_id: str) -> tuple[AlarmRecord, Analysis, dict]:
        if alarm_id not in self._cache:
            rec = self.demo_record(alarm_id)
            A, res = self.triage(rec)
            self._cache[alarm_id] = (rec, A, res)
        return self._cache[alarm_id]

    # -------------------------------------------------------------- waveform
    @staticmethod
    def waveform(rec: AlarmRecord, A: Analysis, target_fs: float = 125.0) -> dict:
        step = max(1, int(round(rec.fs / target_fs)))
        n = len(rec.signals) // step * step
        beats = {c.name: c.beats_s for c in A.channels}
        quality = {c.name: round(c.quality, 2) for c in A.channels}
        chans = []
        from triage.io import channel_kind

        for i, name in enumerate(rec.names):
            kind = channel_kind(name)
            if kind not in ("ecg", "pleth", "abp", "resp"):
                continue
            x = rec.signals[:n, i].reshape(-1, step).mean(axis=1)
            vals = [None if not np.isfinite(v) else round(float(v), 3) for v in x]
            chans.append({"name": name, "kind": kind, "units": rec.units[i], "values": vals,
                          "beats_s": [round(b, 3) for b in beats.get(name, [])],
                          "quality": quality.get(name)})
        order = {"ecg": 0, "pleth": 1, "abp": 2, "resp": 3}
        chans.sort(key=lambda c: order[c["kind"]])
        return {"t0": rec.t0, "fs": rec.fs / step, "channels": chans}
