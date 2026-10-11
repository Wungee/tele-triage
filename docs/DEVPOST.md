# Devpost write-up (paste into the matching fields)

Fill every `[FILL]` with something true, or delete the sentence.

## Inspiration
I work as a monitor technician in the Central Monitoring Unit at Grady, [FILL: true distance]
from this hackathon. [FILL: two sentences in your own words: what a false asystole or V-tach
alarm looks like from your chair and what you do about it]. Most of those alarms are false. In a
UCSF study, 88% of 1.1 million arrhythmia alarms were false positives. I wanted the check I do
by eye to happen on every alarm automatically.

## What it does
Alarm Triage Co-Pilot replays real ICU alarms on a central-station style bed wall. When an
arrhythmia alarm fires, it checks:
- whether each ECG lead is readable,
- whether the two leads agree,
- whether the pulse waveform is still beating.

It labels each alarm *likely real*, *needs a look* or *likely artifact*, with the evidence drawn
directly on the strip. It never silences anything. It reorders the queue so likely-real alarms
are seen first, then reveals the expert annotation after the tech decides.

## How we built it
- **Signal processing in Python** (SciPy, wfdb):
  - two independent QRS detectors per lead, whose agreement is a signal-quality index
  - pulse detection on pleth and arterial lines, anchored to the patient's own baseline
  - the monitor's own alarm math (longest pause, slowest 5 beats, fastest 17 beats)
  - 89 features in all, computed only from data *before* the alarm
- **Model:** scikit-learn gradient boosting, trained on the PhysioNet/CinC 2015 Challenge
  (750 expert-labelled ICU alarms). 20% is held out, and the "likely artifact" cut-off is chosen
  in cross-validation so at most 1% of true alarms fall below it.
- **Backend:** FastAPI.
- **Frontend:** React with canvas waveforms.
- **Audit log:** TimescaleDB hypertable.
- **Summaries:** optional Gemini rephrasing of the evidence.
- **Deployment:** Docker + Caddy on Vultr.

## Results (held-out alarms the model never saw)
[FILL: paste the "All alarms" row and the 2-3 most interesting per-type rows from artifacts/report.md]

## Challenges we ran into
[FILL: the true ones. Candidates from the build:
- the first QRS detector missed small beats next to big artifact, until it got a local adaptive threshold
- picking a cut-off that protects true alarms instead of maximising accuracy]

## Accomplishments that we're proud of
[FILL]

## What we learned
[FILL]

## What's next
- Shadow mode in a real CMU: it scores every alarm, nobody sees it, and we measure.
- Validation on telemetry-floor data and newer monitors.
- The regulatory path. This would be a medical device under FDA's CDS guidance.

## Built with
python, fastapi, scikit-learn, scipy, numpy, wfdb, react, vite, timescaledb, gemini, docker,
caddy, vultr

## Disclosure
Pre-existing: the PhysioNet 2015 dataset and open-source libraries (incl. wfdb's GQRS detector).
All application code was written during Hacklanta, with AI coding assistance (Claude).
