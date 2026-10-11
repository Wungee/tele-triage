# Pitch: 3 minutes + 2 minutes Q&A

**Rule for every `[FILL]`:** it has to be true. If you can't make a line true, cut it.
Use patterns you've seen many times, never a specific patient: no dates, no bed numbers, nothing
identifying. That's HIPAA, and it's also your job. Check Grady's policy on naming your employer in
a public project before you say "Grady" on stage or on Devpost.

## Show, don't tell

You never say "I have experience as a monitor tech." You *read the strip in front of the
judges* faster than they can follow, using words only a tech would use. That reading is the
proof. The three moments that do it are marked **(SHOW)** below.

---

## Setup at the judging table (before you say a word)

- App running **locally** on your laptop, not the Vultr URL, so venue Wi-Fi can't kill the demo.
  Keep the live link for Devpost.
- Browser at `http://localhost:5173/?first=a103l&seed=<the seed you rehearsed>`, full screen,
  **paused** (press *Pause replay* right after load).
- `data/reviews.db` deleted so the counters start at 0.
- A screen recording of a clean run open in another tab, as a fallback.

---

## 0:00–0:25 · Cold open

> "It's [FILL: a time of night you actually work]. I'm in the Central Monitoring Unit at Grady,
> [FILL: true distance, e.g. 'a block from this ballroom'], watching [FILL: number] patients
> across [FILL: number] screens."

*Press **Resume replay**. Bed 01 fires `*** ASYSTOLE`.*

> "Asystole. According to the monitor, this heart just stopped."

**(SHOW)** *Point at the cyan pleth, then at lead V. Say it fast, the way you would on shift:*

> "First thing I check, every time: pleth's still pulsing. Lead V's still got QRS complexes.
> That's not a dead heart. That's [FILL: the most common real cause you see, e.g. a patient
> rolling over, a loose electrode]."

## 0:25–0:50 · The problem

> "That check takes me [FILL: honest number] seconds, and I do it [FILL: something you can
> defend, e.g. 'dozens of times a shift', or cut this clause] times a shift. At UCSF,
> researchers logged 2.5 million monitor alarms in one month across five ICUs, and 88% of
> the arrhythmia alarms were false. The false ones aren't the danger. The danger is the real one
> that lands while you're clearing the false ones."

## 0:50–2:05 · Demo

> "So I built the check I do by eye into a co-pilot."

*Click bed 01.*

**(SHOW)**
> "Violet ticks are the beats it found, on the ECG and on the pulse. See how they line up? It
> says *likely artifact*, and it says why, in the words I'd use to call the nurse: the pleth kept
> pulsing at 126 through the alarm, and the longest QRS pause is 1.1 seconds when asystole needs
> four."

*Click **Artifact, ask RN to check leads**. The expert label appears.*

> "The expert annotation agrees. This is a real ICU alarm from a public dataset, and the model
> never saw it in training."

*Back to wall. Point at the queue.*

**(SHOW)**
> "Two things I designed on purpose. One: it never silences anything. Every alarm still fires.
> The co-pilot only changes the order, so likely-real alarms jump to the top of this queue.
> Two: everything the AI says is violet. On a central station, green is ECG, cyan is pleth, red
> is an alarm. Every colour already means something. The AI should never look like an alarm."

*Open the top "Likely real" alarm. Ideally pick a V-tach/V-fib where the pulse collapses;
find one while rehearsing and note its seed.*

> "Here's one it calls real: the pulse amplitude collapsed in the last six seconds. That one goes
> first."

## 2:05–2:40 · How it works and how good it is

> "Under the hood: 89 measurements from the minute *before* the alarm, so it could run live. There
> are two independent beat detectors per lead, pulse-waveform analysis, and the same rhythm math the
> monitor uses. They feed a gradient-boosted model trained on 750 expert-labeled ICU alarms from
> the PhysioNet 2015 challenge. On [FILL: n_test] alarms it never saw, it flagged
> [FILL: X%] of the false alarms as likely artifact, and [FILL: Y] of [FILL: n_true] real
> alarms. I tuned it that way on purpose: missing a real alarm is the mistake it's built to avoid."

*(Numbers from `artifacts/report.md`, "Held-out test set", "All alarms" row. If the true-alarm
miss count isn't zero, say the number out loud anyway. Judges trust the team that volunteers its
weak number.)*

## 2:40–3:00 · Close

> "I'm not asking anyone to trust an algorithm with a patient. I'm asking for the check I do by
> eye at 3 a.m. to happen on every alarm before I even look, so the real one gets to the nurse
> first. [FILL: what's next, e.g. 'Next step is shadow mode: it watches a real CMU and gets
> scored, but nobody sees it.']. Thank you."

---

## Q&A: the questions you will get

**"What if it's wrong about a real alarm?"**
It can't silence or hide it. The worst case is a true alarm sitting lower in the queue while it
still alarms at the bedside and on the wall. The artifact cut-off was chosen so at most 1% of true
alarms fall under it in cross-validation. On the held-out set it mislabelled [FILL: Y] of
[FILL: n_true].

**"Is this FDA-regulated?"**
Yes, it would be a device. FDA's Clinical Decision Support guidance excludes software that
analyses signals from a patient monitor, and ECG arrhythmia analysis is FDA's own example. This is a
research prototype. A real path means prospective validation and clearance. *(Say this before
they finish asking. It shows you know the field.)*

**"Did you use Grady data?"**
No. Only public, de-identified PhysioNet data. Nothing from work.

**"Why can't the monitor vendors just fix their algorithms?"**
They keep improving them. But a CMU watches a mixed fleet, and this sits at the central station as
a second opinion that cross-checks every channel. It also explains itself, which the bedside
algorithm doesn't.

**"How do you know it generalises?"**
Honestly, I don't yet. This is 750 alarms from ICUs in 2015. Telemetry floors, newer monitors and
other populations need their own validation. That's what shadow mode is for.

**"Where's the AI? Isn't this just rules?"**
The rules are how it *explains* itself. The decision comes from a model trained on expert labels
across 89 features. The reasons are there so a tech can verify the call in two seconds instead of
trusting it.

**"What does Gemini do?"**
It rephrases the evidence into plain English. It never makes the call. If it's down, a template
takes over.

---

## What not to say

- "It reduces alarm fatigue." You haven't measured that. Say "it's designed to cut the time spent
  on false alarms."
- "FDA-ready," "clinically validated," "accurate" without a number.
- Any Grady statistic, staffing number or patient detail.
- The synthetic-data numbers. If the yellow *Synthetic* banner is on screen, you haven't trained
  on the real data yet.

## Demo video (2–3 min, for Devpost)

Same script, recorded as a screen capture with your voiceover. Read the strip on camera. That's
the show, not tell. Upload as **Public**.
