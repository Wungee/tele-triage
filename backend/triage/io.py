"""Loading alarm records (PhysioNet/CinC 2015 WFDB format, or our compact .npz demo clips).

Dataset facts this code relies on (PhysioNet/CinC Challenge 2015):
  * 250 Hz, every record has 2 ECG leads + at least one pulsatile channel (PLETH and/or ABP),
    sometimes RESP.
  * The alarm fires at exactly 5:00 (t = 300 s). The triggering event starts somewhere in the
    10 s before that. "Short" records end at 300 s; "long" records keep 30 s after the alarm.
  * Header comments hold the alarm type and the expert label, e.g. ["Asystole", "False alarm"].

We only ever read data from BEFORE the alarm fires (<= 300 s), so the model is something a
central station could actually run in real time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ALARM_TIME_S = 300.0
CONTEXT_START_S = 240.0  # we keep one minute of pre-alarm signal

ALARM_TYPES = [
    "Asystole",
    "Bradycardia",
    "Tachycardia",
    "Ventricular_Tachycardia",
    "Ventricular_Flutter_Fib",
]

ALARM_LABELS = {
    "Asystole": "Asystole",
    "Bradycardia": "Extreme brady",
    "Tachycardia": "Extreme tachy",
    "Ventricular_Tachycardia": "V-tach",
    "Ventricular_Flutter_Fib": "V-fib / flutter",
}

ECG_NAMES = {"I", "II", "III", "V", "AVR", "AVL", "AVF", "MCL", "MCL1", "V1", "V2", "V3", "V4", "V5", "V6"}
PLETH_NAMES = {"PLETH", "SPO2"}
ABP_NAMES = {"ABP", "ART", "AOBP"}


def channel_kind(name: str) -> str:
    n = name.strip().upper()
    if n in ECG_NAMES:
        return "ecg"
    if n in PLETH_NAMES:
        return "pleth"
    if n in ABP_NAMES:
        return "abp"
    if n.startswith("RESP"):
        return "resp"
    return "other"


@dataclass
class AlarmRecord:
    record_id: str
    alarm_type: str
    is_true_alarm: bool | None  # None when unknown (e.g. a live record)
    fs: float
    t0: float  # time in seconds (record clock) of the first sample we hold
    names: list[str]
    units: list[str]
    signals: np.ndarray  # shape (n_samples, n_channels), physical units, NaN = invalid sample
    meta: dict = field(default_factory=dict)

    # ---- convenience views -------------------------------------------------
    def channels(self, kind: str) -> list[tuple[str, np.ndarray]]:
        return [(n, self.signals[:, i]) for i, n in enumerate(self.names) if channel_kind(n) == kind]

    def segment(self, start_s: float, end_s: float) -> "AlarmRecord":
        i0 = max(0, int(round((start_s - self.t0) * self.fs)))
        i1 = min(len(self.signals), int(round((end_s - self.t0) * self.fs)))
        return AlarmRecord(
            self.record_id, self.alarm_type, self.is_true_alarm, self.fs,
            self.t0 + i0 / self.fs, list(self.names), list(self.units),
            self.signals[i0:i1].copy(), dict(self.meta),
        )


def parse_comments(comments: list[str]) -> tuple[str, bool | None]:
    alarm_type, label = "", None
    for c in comments:
        c = c.strip().lstrip("#").strip()
        if c in ALARM_TYPES:
            alarm_type = c
        elif c.lower().startswith("true"):
            label = True
        elif c.lower().startswith("false"):
            label = False
    return alarm_type, label


def alarm_type_from_name(record_id: str) -> str:
    return {
        "a": "Asystole", "b": "Bradycardia", "t": "Tachycardia",
        "v": "Ventricular_Tachycardia", "f": "Ventricular_Flutter_Fib",
    }.get(record_id[:1].lower(), "")


def load_wfdb(path: str | Path, start_s: float = CONTEXT_START_S, end_s: float = ALARM_TIME_S,
              alarm_type: str | None = None) -> AlarmRecord:
    """Read one WFDB record (path without extension), keeping [start_s, end_s)."""
    import wfdb  # imported lazily: the API can run on .npz clips without wfdb installed

    path = Path(path)
    header = wfdb.rdheader(str(path))
    fs = float(header.fs)
    sampto = min(int(end_s * fs), header.sig_len)
    sampfrom = max(0, min(int(start_s * fs), sampto - 1))
    rec = wfdb.rdrecord(str(path), sampfrom=sampfrom, sampto=sampto)
    a_type, label = parse_comments(rec.comments or [])
    a_type = alarm_type or a_type or alarm_type_from_name(path.name)
    if a_type not in ALARM_TYPES:
        raise ValueError(f"{path.name}: unknown alarm type {a_type!r}")
    sig = np.asarray(rec.p_signal, dtype=np.float64)
    return AlarmRecord(
        record_id=path.name, alarm_type=a_type, is_true_alarm=label, fs=fs,
        t0=sampfrom / fs, names=list(rec.sig_name), units=list(rec.units), signals=sig,
    )


def save_npz(rec: AlarmRecord, out_path: str | Path) -> None:
    np.savez_compressed(
        out_path,
        signals=rec.signals.astype(np.float32),
        names=np.array(rec.names), units=np.array(rec.units),
        fs=rec.fs, t0=rec.t0, alarm_type=rec.alarm_type,
        is_true_alarm=-1 if rec.is_true_alarm is None else int(rec.is_true_alarm),
        record_id=rec.record_id,
    )


def load_npz(path: str | Path) -> AlarmRecord:
    with np.load(path, allow_pickle=False) as z:
        lab = int(z["is_true_alarm"])
        return AlarmRecord(
            record_id=str(z["record_id"]), alarm_type=str(z["alarm_type"]),
            is_true_alarm=None if lab < 0 else bool(lab), fs=float(z["fs"]), t0=float(z["t0"]),
            names=[str(n) for n in z["names"]], units=[str(u) for u in z["units"]],
            signals=z["signals"].astype(np.float64),
        )
