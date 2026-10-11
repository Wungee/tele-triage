"""FastAPI app: alarm triage API + serves the built React UI.

    uvicorn app.main:app --reload --port 8000        (run from backend/)
"""

from __future__ import annotations

import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from triage.io import ALARM_TYPES, load_wfdb  # noqa: E402

from . import config  # noqa: E402
from .explain import gemini_summary  # noqa: E402
from .service import SAFE_ID, TriageService  # noqa: E402
from .store import Store  # noqa: E402

state: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        state["svc"] = TriageService(config.ARTIFACT_DIR)
    except FileNotFoundError:
        state["svc"] = None
        print(f"!! No model in {config.ARTIFACT_DIR}. Run: python scripts/train.py", file=sys.stderr)
    state["store"] = Store()
    state["summaries"] = {}
    yield


app = FastAPI(title="Alarm Triage Co-Pilot", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


def svc() -> TriageService:
    s = state.get("svc")
    if s is None:
        raise HTTPException(503, "No trained model found. Run `python scripts/train.py` first.")
    return s


def demo(alarm_id: str):
    try:
        return svc().triage_demo(alarm_id)
    except KeyError:
        raise HTTPException(404, f"Unknown alarm {alarm_id!r}")


# ------------------------------------------------------------------------ API
@app.get("/api/health")
def health():
    s = state.get("svc")
    return {"ok": True, "model_loaded": s is not None, "demo_alarms": len(s.demo_index) if s else 0,
            "synthetic": s.synthetic if s else None, "gemini": bool(config.GEMINI_API_KEY),
            "database": state["store"].label}


@app.get("/api/model")
def model_card():
    s = svc()
    return {"dataset": s.dataset, "synthetic": s.synthetic, "t_low": s.t_low, "t_high": s.t_high,
            "report": s.report}


@app.get("/api/alarms")
def list_alarms():
    """Demo queue: held-out alarms the model never trained on. No answers included."""
    return {"alarms": svc().demo_index}


@app.get("/api/alarms/{alarm_id}")
def get_alarm(alarm_id: str):
    rec, A, res = demo(alarm_id)
    return {**res, "waveform": TriageService.waveform(rec, A)}


@app.post("/api/alarms/{alarm_id}/summary")
async def summarize(alarm_id: str):
    _, _, res = demo(alarm_id)
    cache = state["summaries"]
    if alarm_id not in cache:
        text, source = await gemini_summary(res["alarm_type"], res["verdict"], res["p_true"],
                                            res["reasons"], res["vitals"])
        cache[alarm_id] = {"text": text, "source": source}
    return cache[alarm_id]


class Review(BaseModel):
    decision: str = Field(pattern="^(real|artifact)$")
    seconds_to_decision: float | None = Field(default=None, ge=0, le=3600)


@app.post("/api/alarms/{alarm_id}/review")
def review(alarm_id: str, body: Review):
    rec, _, res = demo(alarm_id)
    expert = None if rec.is_true_alarm is None else ("real" if rec.is_true_alarm else "artifact")
    ai = {"likely_artifact": "artifact", "likely_real": "real"}.get(res["verdict"])
    row = {
        "alarm_id": alarm_id, "alarm_type": rec.alarm_type, "p_true": res["p_true"], "ai_verdict": res["verdict"],
        "tech_decision": body.decision, "expert_label": expert,
        "tech_agrees_expert": None if expert is None else body.decision == expert,
        "ai_agrees_expert": None if expert is None or ai is None else ai == expert,
        "seconds_to_decision": body.seconds_to_decision,
    }
    state["store"].log(row)
    return {"expert_label": expert, "ai_verdict": res["verdict"],
            "ai_agrees_expert": row["ai_agrees_expert"], "tech_agrees_expert": row["tech_agrees_expert"]}


@app.get("/api/stats")
def stats():
    return state["store"].stats()


@app.post("/api/score")
async def score_upload(header: UploadFile = File(..., description=".hea file"),
                       signal: UploadFile = File(..., description=".mat or .dat file"),
                       alarm_type: str | None = Form(None)):
    """Score any PhysioNet-2015-format record (needs >= 1 min before the alarm at t = 300 s)."""
    if alarm_type is not None and alarm_type not in ALARM_TYPES:
        raise HTTPException(422, f"alarm_type must be one of {ALARM_TYPES}")
    hname, sname = Path(header.filename or "").name, Path(signal.filename or "").name
    stem = Path(hname).stem
    if not hname.endswith(".hea") or not SAFE_ID.match(stem) or Path(sname).suffix not in (".mat", ".dat"):
        raise HTTPException(422, "Upload a <name>.hea header and its <name>.mat/.dat signal file.")
    limit = int(config.MAX_UPLOAD_MB * 1e6)
    with tempfile.TemporaryDirectory() as td:
        for up, nm in ((header, hname), (signal, sname)):
            data = await up.read(limit + 1)
            if len(data) > limit:
                raise HTTPException(413, "File too large.")
            (Path(td) / nm).write_bytes(data)
        try:
            rec = load_wfdb(Path(td) / stem, alarm_type=alarm_type)
        except Exception as e:
            raise HTTPException(422, f"Could not read record: {e}")
    if len(rec.signals) < 30 * rec.fs:
        raise HTTPException(422, "Record must contain at least the 30 s before the alarm (t = 300 s).")
    A, res = svc().triage(rec)
    res["expert_label"] = None if rec.is_true_alarm is None else ("real" if rec.is_true_alarm else "artifact")
    return {**res, "waveform": TriageService.waveform(rec, A)}


# ------------------------------------------------------------- static UI
if config.FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(config.FRONTEND_DIST), html=True), name="ui")
