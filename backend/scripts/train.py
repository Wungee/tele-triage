"""Train + evaluate the alarm triage model.

    python scripts/train.py                          # real data in data/training
    python scripts/train.py --data data/synthetic    # pipeline smoke test (results are meaningless)

What it does
  1. Extracts features from every alarm (parallel; cached to artifacts/features.csv).
  2. Holds out a stratified 20% TEST set the model never sees. Those alarms become the demo.
  3. 5-fold cross-validation on the other 80% picks the "likely artifact" cut-off so that at
     most --target-miss (default 1%) of TRUE alarms would ever get that label.
  4. Trains the final model on the 80%, scores the held-out 20%, writes:
       artifacts/model.joblib     model + feature list + thresholds
       artifacts/report.json/.md  honest held-out metrics, per alarm type
       artifacts/demo/*.npz       the held-out alarms (last 60 s before each alarm) for the UI
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import sklearn  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.model_selection import StratifiedKFold, train_test_split  # noqa: E402

from triage.features import analyze, feature_names  # noqa: E402
from triage.io import ALARM_LABELS, ALARM_TYPES, load_wfdb, save_npz  # noqa: E402


# ----------------------------------------------------------------- extraction
def _extract(path: str) -> dict:
    try:
        rec = load_wfdb(path)
        feats = analyze(rec).features
        return {"record": rec.record_id, "alarm_type": rec.alarm_type,
                "y": None if rec.is_true_alarm is None else int(rec.is_true_alarm), **feats}
    except Exception as e:  # keep going; report at the end
        return {"record": Path(path).name, "error": f"{type(e).__name__}: {e}"}


def list_records(data_dir: Path) -> list[Path]:
    rec_file = data_dir / "RECORDS"
    names = rec_file.read_text().split() if rec_file.exists() else sorted(p.stem for p in data_dir.glob("*.hea"))
    return [data_dir / n for n in names if (data_dir / f"{n}.hea").exists()]


def extract_all(paths: list[Path], jobs: int) -> pd.DataFrame:
    rows, errors = [], []
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        futs = [ex.submit(_extract, str(p)) for p in paths]
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            (errors if "error" in r else rows).append(r)
            if i % 50 == 0 or i == len(futs):
                print(f"  features: {i}/{len(futs)}", flush=True)
    for e in errors:
        print(f"  ! skipped {e['record']}: {e['error']}")
    return pd.DataFrame(rows)


# --------------------------------------------------------------------- model
def make_model(seed: int) -> HistGradientBoostingClassifier:
    # Shallow, regularised trees: ~600 training alarms is small. class_weight balances the
    # 60/40 false/true split so the model does not learn "say false" as a shortcut.
    return HistGradientBoostingClassifier(
        learning_rate=0.05, max_iter=300, max_leaf_nodes=12, min_samples_leaf=10,
        l2_regularization=1.0, class_weight="balanced", random_state=seed, early_stopping=False,
    )


def challenge_score(y: np.ndarray, pred_true: np.ndarray) -> float:
    """PhysioNet 2015 score: (TP+TN) / (TP+TN+FP+5*FN). Missing a true alarm costs 5x."""
    tp = int(((pred_true == 1) & (y == 1)).sum())
    tn = int(((pred_true == 0) & (y == 0)).sum())
    fp = int(((pred_true == 1) & (y == 0)).sum())
    fn = int(((pred_true == 0) & (y == 1)).sum())
    d = tp + tn + fp + 5 * fn
    return (tp + tn) / d if d else float("nan")


def summarize(y: np.ndarray, p: np.ndarray, t_low: float, t_high: float) -> dict:
    y = np.asarray(y).astype(int)
    p = np.asarray(p)
    art = p < t_low
    real = p >= t_high
    n_true, n_false = int((y == 1).sum()), int((y == 0).sum())
    out = {
        "n": int(len(y)), "n_true": n_true, "n_false": n_false,
        "auc": float(roc_auc_score(y, p)) if 0 < n_true < len(y) else None,
        # The two numbers that matter on the unit:
        "false_alarms_flagged_artifact": int((art & (y == 0)).sum()),
        "true_alarms_flagged_artifact": int((art & (y == 1)).sum()),  # dangerous - must be ~0
        "true_alarms_marked_likely_real": int((real & (y == 1)).sum()),
        "uncertain": int((~art & ~real).sum()),
    }
    out["pct_false_alarms_flagged"] = (100 * out["false_alarms_flagged_artifact"] / n_false) if n_false else None
    out["pct_true_alarms_flagged"] = (100 * out["true_alarms_flagged_artifact"] / n_true) if n_true else None
    pred = (p >= 0.5).astype(int)
    out["at_0.5"] = {
        "sensitivity_true_alarms": float(((pred == 1) & (y == 1)).sum() / n_true) if n_true else None,
        "specificity_false_alarms": float(((pred == 0) & (y == 0)).sum() / n_false) if n_false else None,
        "challenge_score": challenge_score(y, pred),
    }
    return out


def by_type(df: pd.DataFrame, p: np.ndarray, t_low: float, t_high: float) -> dict:
    res = {"ALL": summarize(df["y"].values, p, t_low, t_high)}
    for t in ALARM_TYPES:
        m = (df["alarm_type"] == t).values
        if m.any():
            res[t] = summarize(df["y"].values[m], p[m], t_low, t_high)
    return res


def strat_key(df: pd.DataFrame) -> pd.Series:
    key = df["alarm_type"] + "_" + df["y"].astype(str)
    small = key.map(key.value_counts()) < 4
    return key.where(~small, df["alarm_type"])


# ----------------------------------------------------------------- reporting
def fmt_pct(v):
    return "-" if v is None else f"{v:.1f}%"


def write_markdown(report: dict, path: Path) -> None:
    L = [f"# Alarm Triage Co-Pilot - model report", "",
         f"Dataset: **{report['dataset']}**  ", f"Trained: {report['created']}  ",
         f"Train / held-out test alarms: {report['n_train']} / {report['n_test']}  ",
         f"'Likely artifact' cut-off: p(true) < {report['t_low']:.3f} "
         f"(chosen in cross-validation so <= {100 * report['target_miss']:.1f}% of true alarms fall below it)", ""]
    if report["synthetic"]:
        L += ["> **SYNTHETIC DATA - these numbers only prove the pipeline runs. Do not present them.**", ""]
    for title, key in (("Held-out test set (never seen in training)", "test"), ("Cross-validation (training 80%)", "cv")):
        L += [f"## {title}", "",
              "| Alarm | n | true / false | AUC | false alarms flagged 'likely artifact' | TRUE alarms flagged 'likely artifact' | sens @0.5 | spec @0.5 | challenge score |",
              "|---|---|---|---|---|---|---|---|---|"]
        for t, m in report[key].items():
            name = "All alarms" if t == "ALL" else ALARM_LABELS[t]
            a = m["at_0.5"]
            L.append(
                f"| {name} | {m['n']} | {m['n_true']} / {m['n_false']} | "
                f"{'-' if m['auc'] is None else f'{m['auc']:.3f}'} | "
                f"{m['false_alarms_flagged_artifact']} ({fmt_pct(m['pct_false_alarms_flagged'])}) | "
                f"{m['true_alarms_flagged_artifact']} ({fmt_pct(m['pct_true_alarms_flagged'])}) | "
                f"{'-' if a['sensitivity_true_alarms'] is None else f'{a['sensitivity_true_alarms']:.2f}'} | "
                f"{'-' if a['specificity_false_alarms'] is None else f'{a['specificity_false_alarms']:.2f}'} | "
                f"{a['challenge_score']:.3f} |")
        L.append("")
    L += ["## What the model relies on (permutation importance, held-out set)", ""]
    for f in report["top_features"]:
        L.append(f"- `{f['feature']}`: {f['importance']:.4f}")
    L += ["", "Data: PhysioNet/CinC Challenge 2015 (ODC-By 1.0). Clifford GD et al., CinC 2015;42:273-276."]
    path.write_text("\n".join(L) + "\n")


# ----------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "training"))
    ap.add_argument("--out", default=str(ROOT / "artifacts"))
    ap.add_argument("--test-frac", type=float, default=0.2)
    ap.add_argument("--target-miss", type=float, default=0.01,
                    help="max fraction of TRUE alarms allowed under the 'likely artifact' cut-off (in CV)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--reuse-features", action="store_true")
    ap.add_argument("--max-records", type=int, default=0, help="debug: only use the first N records")
    ap.add_argument("--hold-out", default="a103l",
                    help="comma-separated record ids forced into the held-out demo set (never trained on)")
    args = ap.parse_args()

    data_dir, out = Path(args.data), Path(args.out)
    if not data_dir.exists():
        raise SystemExit(f"No data at {data_dir}. Run: python scripts/download_data.py")
    out.mkdir(parents=True, exist_ok=True)
    synthetic = "synthetic" in str(data_dir).lower()
    dataset = "SYNTHETIC test data" if synthetic else "PhysioNet/CinC Challenge 2015 training set"

    feat_csv = out / "features.csv"
    paths = list_records(data_dir)
    if args.max_records:
        paths = paths[: args.max_records]
    if args.reuse_features and feat_csv.exists():
        df = pd.read_csv(feat_csv)
        print(f"Reusing {len(df)} cached feature rows from {feat_csv}")
    else:
        print(f"Extracting features from {len(paths)} alarms with {args.jobs} workers ...")
        df = extract_all(paths, args.jobs)
        df.to_csv(feat_csv, index=False)
    df = df.dropna(subset=["y"]).sort_values("record").reset_index(drop=True)
    df["y"] = df["y"].astype(int)
    names = feature_names()
    print("\nAlarms by type (true / false):")
    for t in ALARM_TYPES:
        d = df[df.alarm_type == t]
        print(f"  {ALARM_LABELS[t]:<16} {int(d.y.sum()):>4} / {int((d.y == 0).sum()):<4}")

    tr, te = train_test_split(df, test_size=args.test_frac, random_state=args.seed, stratify=strat_key(df))
    forced = {r.strip() for r in args.hold_out.split(",") if r.strip()}
    move = tr[tr.record.isin(forced)]
    if len(move):  # e.g. the alarm you open the pitch with: guarantee the model never saw it
        tr, te = tr[~tr.record.isin(forced)], pd.concat([te, move])
        print(f"Forced into held-out set: {', '.join(move.record)}")
    tr, te = tr.reset_index(drop=True), te.reset_index(drop=True)
    Xtr, ytr = tr[names].values.astype(float), tr["y"].values
    Xte, yte = te[names].values.astype(float), te["y"].values

    # out-of-fold predictions on the training 80% -> choose the cut-off without touching test
    oof = np.zeros(len(tr))
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=args.seed)
    for k, (a, b) in enumerate(skf.split(Xtr, strat_key(tr))):
        m = make_model(args.seed + k).fit(Xtr[a], ytr[a])
        oof[b] = m.predict_proba(Xtr[b])[:, 1]
    t_low = float(np.quantile(oof[ytr == 1], args.target_miss, method="lower"))
    t_low = min(t_low, 0.5)
    t_high = 0.5

    model = make_model(args.seed).fit(Xtr, ytr)
    p_te = model.predict_proba(Xte)[:, 1]

    imp = permutation_importance(model, Xte, yte, scoring="roc_auc", n_repeats=10, random_state=args.seed)
    order = np.argsort(imp.importances_mean)[::-1][:15]
    top = [{"feature": names[i], "importance": float(imp.importances_mean[i])} for i in order]

    report = {
        "dataset": dataset, "synthetic": synthetic,
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "n_train": int(len(tr)), "n_test": int(len(te)), "t_low": t_low, "t_high": t_high,
        "target_miss": args.target_miss, "sklearn_version": sklearn.__version__,
        "test": by_type(te, p_te, t_low, t_high), "cv": by_type(tr, oof, t_low, t_high),
        "top_features": top,
        "test_predictions": [{"record": r, "alarm_type": a, "y": int(y), "p_true": float(p)}
                             for r, a, y, p in zip(te.record, te.alarm_type, te.y, p_te)],
    }
    joblib.dump({"model": model, "feature_names": names, "t_low": t_low, "t_high": t_high,
                 "sklearn_version": sklearn.__version__, "dataset": dataset, "synthetic": synthetic,
                 "created": report["created"], "test_records": list(te.record)}, out / "model.joblib")
    (out / "report.json").write_text(json.dumps(report, indent=2))
    write_markdown(report, out / "report.md")

    # demo bundle: the held-out alarms only, so every alarm in the demo is unseen by the model
    demo = out / "demo"
    demo.mkdir(exist_ok=True)
    for old in demo.glob("*.npz"):
        old.unlink()
    index = []
    for rid, a_type in zip(te.record, te.alarm_type):
        rec = load_wfdb(data_dir / rid)
        save_npz(rec, demo / f"{rid}.npz")
        index.append({"id": rid, "alarm_type": a_type})
    (demo / "index.json").write_text(json.dumps({"dataset": dataset, "synthetic": synthetic, "alarms": index}))

    s = report["test"]["ALL"]
    print("\n================ HELD-OUT TEST SET ================")
    if synthetic:
        print("  (SYNTHETIC DATA - pipeline check only, not real performance)")
    print(f"  alarms: {s['n']}  ({s['n_true']} true / {s['n_false']} false)   AUC: {s['auc']:.3f}")
    print(f"  false alarms labelled 'likely artifact': {s['false_alarms_flagged_artifact']}/{s['n_false']}"
          f"  ({fmt_pct(s['pct_false_alarms_flagged'])})")
    print(f"  TRUE alarms labelled 'likely artifact':  {s['true_alarms_flagged_artifact']}/{s['n_true']}"
          f"  ({fmt_pct(s['pct_true_alarms_flagged'])})   <- must stay near zero")
    print(f"  challenge score @0.5: {s['at_0.5']['challenge_score']:.3f}")
    print(f"\nWrote {out / 'model.joblib'}, {out / 'report.md'}, {len(index)} demo alarms in {demo}")


if __name__ == "__main__":
    main()
