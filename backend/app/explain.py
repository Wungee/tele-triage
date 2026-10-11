"""Turn features into evidence a monitor tech can check against the strip in two seconds.

Reasons are deterministic rules over the same features the model uses. They are not the
model's internals; they are the cross-checks that the features encode, written the way a tech
would say them. Gemini (optional) only rephrases this evidence; it never makes the call.
"""

from __future__ import annotations

import math

import httpx

from triage.features import Analysis
from triage.io import ALARM_LABELS

from . import config


def _ok(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def _bpm(v) -> str:
    return f"{v:.0f} bpm"


def build_reasons(alarm_type: str, A: Analysis) -> list[dict]:
    F = A.features
    ecg = [c for c in A.channels if c.kind == "ecg"]
    pulses = [c for c in A.channels if c.kind in ("pleth", "abp") and c.stats.get("present", 0) > 0]
    la = ecg[0].name if ecg else "ECG"
    lb = ecg[1].name if len(ecg) > 1 else None
    best_pulse = max(pulses, key=lambda c: (c.quality, c.kind == "abp")) if pulses else None
    src = best_pulse.name if best_pulse else None
    R: list[dict] = []

    def add(text: str, toward: str, weight: float, channel: str | None = None):
        R.append({"text": text, "toward": toward, "weight": round(weight, 2), "channel": channel})

    # ---- ECG signal quality -------------------------------------------------------
    for prefix, name in (("ecg_a_", la), ("ecg_b_", lb)):
        if name is None:
            continue
        bsqi, flat = F.get(prefix + "bsqi"), F.get(prefix + "flat_frac")
        if _ok(flat) and flat >= 0.5:
            add(f"Lead {name} is flat for {flat * 100:.0f}% of the last 16 s. That reads like a lead-off, "
                "not a heart that stopped.", "artifact", 0.6 + 0.3 * flat, name)
        elif _ok(bsqi) and bsqi < 0.5:
            add(f"Lead {name} is noisy: two independent beat detectors agree on only {bsqi * 100:.0f}% of beats.",
                "artifact", 0.7 - bsqi * 0.5, name)
    if lb and _ok(F.get("ecg_a_bsqi")) and _ok(F.get("ecg_b_bsqi")) \
            and F["ecg_a_bsqi"] >= 0.85 and F["ecg_b_bsqi"] >= 0.85:
        add("Both ECG leads are clean (beat detectors agree on 85%+ of beats), so the ECG itself is trustworthy.",
            "real", 0.35)
    if lb and _ok(F.get("ecg_leads_hr_diff")) and F["ecg_leads_hr_diff"] > 30:
        add(f"The two leads disagree: {la} reads {_bpm(F['ecg_a_hr'])}, {lb} reads {_bpm(F['ecg_b_hr'])}.",
            "artifact", 0.55, lb)

    # ---- pulse waveform vs the alarm -------------------------------------------------
    pgap, phr = F.get("pulse_max_gap"), F.get("pulse_hr")
    late_amp = F.get("pulse_late_amp_ratio")
    if best_pulse is None:
        add("No usable pulse waveform (pleth or art line) on this patient, so the co-pilot can only judge "
            "ECG quality.", "neutral", 0.1)
    if alarm_type == "Asystole":
        if src and _ok(pgap) and pgap < 2.5 and _ok(phr):
            add(f"{src} kept pulsing at {_bpm(phr)} through the alarm (longest gap {pgap:.1f} s).",
                "artifact", 0.95, src)
        elif src and _ok(pgap) and pgap >= 4:
            add(f"No pulse on {src} for {pgap:.1f} s.", "real", 0.95, src)
        g = F.get("ecg_min_max_gap")
        if _ok(g) and g < 3:
            add(f"QRS complexes continue on at least one lead (longest pause {g:.1f} s; asystole needs 4 s+).",
                "artifact", 0.8, la)
        elif _ok(g) and g >= 4:
            add(f"Both leads pause for {g:.1f} s or longer.", "real", 0.8, la)
    elif alarm_type == "Bradycardia":
        e5, p5 = F.get("ecg_max_min_hr5"), F.get("pulse_min_hr5")
        if src and _ok(p5) and p5 >= 45:
            add(f"{src} never drops below {_bpm(p5)} over any 5 beats (alarm threshold is 40).",
                "artifact", 0.85, src)
        elif src and _ok(p5) and p5 < 40:
            add(f"{src} confirms a slow rate: {_bpm(p5)} over 5 beats.", "real", 0.85, src)
        if _ok(e5) and e5 >= 45:
            add(f"The cleaner ECG lead never drops below {_bpm(e5)} over 5 beats. The monitor is likely "
                "missing small QRS complexes.", "artifact", 0.7, la)
    elif alarm_type == "Tachycardia":
        p17, e17 = F.get("pulse_max_hr17"), F.get("ecg_min_max_hr17")
        if src and _ok(p17) and p17 <= 130:
            add(f"{src} tops out at {_bpm(p17)} over 17 beats (alarm needs 140+).", "artifact", 0.85, src)
        elif src and _ok(p17) and p17 > 140:
            add(f"{src} confirms a fast rate: {_bpm(p17)} over 17 beats.", "real", 0.85, src)
        if _ok(e17) and e17 <= 130:
            add(f"At least one ECG lead stays at or below {_bpm(e17)}. Noise is likely being counted as beats.",
                "artifact", 0.65, lb or la)
    else:  # VT / VF: does perfusion continue?
        if src and _ok(late_amp) and late_amp >= 0.7 and _ok(phr):
            add(f"{src} amplitude holds at {late_amp * 100:.0f}% of the patient's baseline with a steady "
                f"{_bpm(phr)}. Perfusion looks unchanged.", "artifact", 0.85, src)
        elif src and _ok(late_amp) and late_amp < 0.4:
            add(f"{src} amplitude collapsed to {late_amp * 100:.0f}% of baseline in the last 6 s.",
                "real", 0.95, src)
        d = F.get("hr_diff_best_pulse")
        if src and _ok(d) and d > 30 and _ok(F.get("ecg_a_hr")):
            add(f"ECG rate ({_bpm(F['ecg_a_hr'])}) and pulse rate ({_bpm(phr)}) disagree by {d:.0f} bpm.",
                "artifact", 0.6, src)
        vf = F.get("ecg_min_vf_frac_late")
        if alarm_type == "Ventricular_Flutter_Fib" and _ok(vf):
            if vf >= 0.6:
                add(f"Both leads are dominated by 2.5-7.5 Hz fibrillatory activity ({vf * 100:.0f}% of power).",
                    "real", 0.7)
            elif vf < 0.3:
                add(f"Little fibrillatory-band energy on the leads ({vf * 100:.0f}% of power).", "artifact", 0.5)

    R.sort(key=lambda r: r["weight"], reverse=True)
    return R[:5]


def template_summary(alarm_label: str, verdict: str, reasons: list[dict]) -> str:
    lead = {"likely_artifact": f"This {alarm_label} alarm looks like artifact.",
            "likely_real": f"This {alarm_label} alarm looks real. Treat it as real.",
            "needs_review": f"The evidence on this {alarm_label} alarm is mixed. Look at the strip."}[verdict]
    top = [r["text"] for r in reasons if r["toward"] != "neutral"][:2]
    return " ".join([lead] + top + ["Confirm at the strip before acting."])


async def gemini_summary(alarm_type: str, verdict: str, p_true: float, reasons: list[dict],
                         vitals: dict) -> tuple[str, str]:
    """Returns (text, source). Falls back to the template on any problem."""
    label = ALARM_LABELS.get(alarm_type, alarm_type)
    fallback = template_summary(label, verdict, reasons)
    if not config.GEMINI_API_KEY:
        return fallback, "template"
    evidence = "\n".join(f"- ({r['toward']}) {r['text']}" for r in reasons)
    prompt = (
        "You help a central monitoring unit (CMU) telemetry technician triage a bedside monitor alarm.\n"
        f"Alarm: {label}. Model verdict: {verdict.replace('_', ' ')} (probability alarm is real: {p_true:.2f}).\n"
        f"Measured vitals: {vitals}\n"
        f"Evidence from the waveforms:\n{evidence}\n\n"
        "Write at most 2 short sentences in plain language for the technician, summarizing what the "
        "waveforms show. Rules: use only the evidence above; do not invent numbers; do not give "
        "treatment advice; never tell them to silence or ignore an alarm; if the alarm may be real, "
        "say so first. End with nothing else."
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 160}}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.post(url, json=body, headers={"x-goog-api-key": config.GEMINI_API_KEY})
            r.raise_for_status()
            parts = r.json()["candidates"][0]["content"]["parts"]
            text = " ".join(p.get("text", "") for p in parts).strip()
            if text:
                return text + " (Confirm at the strip.)", f"gemini:{config.GEMINI_MODEL}"
    except Exception:
        pass
    return fallback, "template"
