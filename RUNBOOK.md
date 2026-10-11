# Runbook: every command, start to finish

Commands are for macOS / Linux (zsh or bash). Windows notes are at the bottom.
Run the blocks in order. Each one says what "done" looks like.

---

## 0. One-time tools

You need **git**, **Node 20+**, and **uv**. uv installs the exact Python version for you, so a
mismatch with the Docker image can't break the model file.

```bash
# check what you have
git --version && node --version

# install uv (Python manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
# restart the terminal, then:
uv python install 3.12
```

Done when: `node --version` prints v20 or newer, and `uv python list` shows 3.12.

---

## 1. Put the project on GitHub

```bash
cd ~/Projects                       # wherever you keep code
unzip ~/Downloads/alarm-triage-copilot.zip
cd alarm-triage-copilot

git init -b main
git add .
git commit -m "Alarm Triage Co-Pilot: initial scaffold"

# create the PUBLIC repo (judges must be able to open it) and push
gh repo create alarm-triage-copilot --public --source=. --push
#   no gh CLI? create an empty public repo on github.com, then:
#   git remote add origin https://github.com/<you>/alarm-triage-copilot.git && git push -u origin main
```

Done when: the repo page shows the README.

---

## 2. Python environment

```bash
cd backend
uv venv -p 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements-dev.txt
pytest -q
```

Done when: pytest prints `passed`. Two of the tests use real PhysioNet alarms (a103l, v102s).
The API tests are skipped until a model exists. That's expected.

---

## 3. Get the real data (323 MB, open access, no login)

```bash
python scripts/download_data.py          # -> ../data/training/  (750 alarms)
```

Done when: it prints `Done: 750 records in ../data/training`.

If the download is slow on venue Wi-Fi, use your phone hotspot or run it at home. PhysioNet can be slow.

---

## 4. Train and get your real numbers

```bash
python scripts/train.py
```

This takes a few minutes, using all CPU cores but one. It prints a held-out results block and writes:

| file | what it is |
|---|---|
| `../artifacts/model.joblib` | the trained model + the "likely artifact" cut-off |
| `../artifacts/report.md` | **your pitch numbers**, per alarm type, on alarms the model never saw |
| `../artifacts/demo/*.npz` | the held-out alarms the UI replays (a103l is always forced in) |

```bash
cat ../artifacts/report.md
```

**Read these three numbers before you write a single slide:**

1. *False alarms labelled "likely artifact"*: the workload you take off a tech.
2. *TRUE alarms labelled "likely artifact"*: must be zero or close to it. If it isn't, say so.
3. *Challenge score @0.5*: for context, the 2015 real-time winner scored 81.39 (×100 scale) on the
   hidden test set. Yours is measured on a split of the public training set, so it's comparable
   in spirit, not head to head.

Re-run with a different split to check the numbers aren't luck:

```bash
python scripts/train.py --reuse-features --seed 1
python scripts/train.py --reuse-features --seed 2
python scripts/train.py --reuse-features --seed 42    # back to the default before you commit
```

If the numbers swing a lot between seeds, present a range, not the best one.

---

## 5. Run it locally (two terminals)

**Terminal A: API**
```bash
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**Terminal B: UI**
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173/?first=a103l

Done when: twelve beds sweep, and bed 01 fires *** ASYSTOLE after about 6 s while its pleth keeps pulsing.

Useful URL options:
- `?first=a103l` makes a103l the first alarm on the wall (your opener)
- `?seed=3` gives a different alarm order. Pick one you've rehearsed and use the same one on stage.

Reset the "reviewed" stats before a demo:
```bash
rm -f data/reviews.db      # from the repo root, with the API stopped
```

---

## 6. Optional: Gemini summaries (side challenge)

```bash
cp .env.example .env       # repo root
# edit .env: GEMINI_API_KEY=<key from https://aistudio.google.com/apikey>
```
Restart the API. In an alarm, click **Summarize in plain English**. The source line should say
"Gemini". With no key, or if the call fails, it falls back to the rule template, so the demo
never breaks on venue Wi-Fi.

---

## 7. Optional: TimescaleDB audit log (Tiger Data side challenge)

Every review (AI verdict, your call, expert label, time to decide) goes into a hypertable, and
`/api/stats` uses `time_bucket()`.

```bash
# from the repo root: start only the database
docker compose --profile timescale up -d timescaledb
# in .env set:  DATABASE_URL=postgresql://alarms:change-me@localhost:5432/alarms
```
For a local run outside Docker, also add `ports: ["5432:5432"]` under `timescaledb` in
docker-compose.yml. Inside compose, the host is `timescaledb`, not `localhost`.

Or use Tiger Cloud (managed): create a service, copy its connection string into `DATABASE_URL`.

Check it worked: `curl localhost:8000/api/health` shows `"database":"TimescaleDB"`.

> This path wasn't run end to end before handoff (no Postgres was available where it was built).
> Test it once before you claim the side challenge.

---

## 8. Commit the trained model + demo alarms

The model and the held-out demo clips are committed on purpose: the server deploys straight from
git, and judges can run it without downloading 323 MB. The raw dataset (`data/`) is git-ignored.

```bash
cd ..                      # repo root
git add artifacts/ backend/ frontend/
git commit -m "Train on PhysioNet 2015; held-out demo set"
git push
```

---

## 9. Production: Vultr (side challenge)

**On vultr.com:** Deploy → Cloud Compute → Ubuntu 24.04 → 1 vCPU / 2 GB is enough (inference is
light; training happens on your laptop). Add your SSH key. Copy the IP.

```bash
ssh root@<SERVER_IP>

# on the server
curl -fsSL https://get.docker.com | sh
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable

git clone https://github.com/<you>/alarm-triage-copilot.git
cd alarm-triage-copilot
cp .env.example .env
nano .env        # set GEMINI_API_KEY; DOMAIN=your.domain (or leave :80 for plain http on the IP)

docker compose --profile https up -d --build
docker compose ps
curl -s localhost:8000/api/health
```

Done when: `http://<SERVER_IP>` (or `https://your.domain`) shows the wall.

**Domain:** add an **A record** pointing your domain at the server IP, set `DOMAIN=your.domain`
in `.env`, then `docker compose --profile https up -d`. Caddy gets the HTTPS certificate
automatically. That only works once DNS has propagated, so do this early.

Redeploy after a change:
```bash
git pull && docker compose --profile https up -d --build
```

Logs: `docker compose logs -f app`

---

## 10. Before you submit to Devpost

- [ ] Repo is **public** and README renders
- [ ] Live URL works from your phone on cellular, not just venue Wi-Fi
- [ ] Demo video (2–3 min) set to **Public**
- [ ] Devpost lists: one main track (AI/ML) + at most 3 side challenges
- [ ] Disclosure: "Signal-processing building blocks (wfdb GQRS detector) and the PhysioNet 2015
      dataset existed before the event; all application code was written during Hacklanta."
      **This needs to be true.** If any of this code existed before hacking started, say so.
      The rules require it.
- [ ] Google Form submitted by one team member

---

## Windows

Use PowerShell. Differences:

```powershell
# uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# activate the venv
backend\.venv\Scripts\Activate.ps1
# delete the review db
Remove-Item data\reviews.db
```

Everything else is the same. Training uses multiprocessing, and Windows handles that fine because
`train.py` has the `if __name__ == "__main__"` guard.
