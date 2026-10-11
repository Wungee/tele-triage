"""Download the PhysioNet/CinC Challenge 2015 training set (~323 MB, open access, ODC-By 1.0).

    python scripts/download_data.py            # -> data/training/*.hea, *.mat, RECORDS, ALARMS

Dataset: https://physionet.org/content/challenge-2015/1.0.0/
Cite: Clifford GD, Silva I, Moody B, et al. The PhysioNet/Computing in Cardiology Challenge 2015:
Reducing False Arrhythmia Alarms in the ICU. Computing in Cardiology 2015;42:273-276.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://physionet.org/files/challenge-2015/1.0.0/training.zip"
ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data"), help="directory to extract into (default: <repo>/data)")
    ap.add_argument("--keep-zip", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "training" / "RECORDS").exists():
        n = len((out / "training" / "RECORDS").read_text().split())
        print(f"Already have {n} records in {out / 'training'} - nothing to do.")
        return

    zpath = out / "training.zip"
    if not zpath.exists():
        print(f"Downloading {URL}\n  -> {zpath} (about 323 MB)")
        tmp = zpath.with_suffix(".part")
        with urllib.request.urlopen(URL) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = 100 * done / total
                    sys.stdout.write(f"\r  {done / 1e6:7.1f} / {total / 1e6:.1f} MB  ({pct:5.1f}%)")
                    sys.stdout.flush()
        print()
        tmp.rename(zpath)

    print(f"Extracting {zpath} ...")
    with zipfile.ZipFile(zpath) as z:
        for m in z.infolist():  # refuse path traversal
            target = (out / m.filename).resolve()
            if not str(target).startswith(str(out.resolve())):
                raise SystemExit(f"Refusing suspicious path in zip: {m.filename}")
        z.extractall(out)

    # the zip contains a top-level "training/" folder; normalise just in case
    if not (out / "training").exists():
        cands = [p.parent for p in out.rglob("RECORDS")]
        if cands:
            shutil.move(str(cands[0]), str(out / "training"))
    if not args.keep_zip:
        zpath.unlink(missing_ok=True)
    n = len((out / "training" / "RECORDS").read_text().split())
    print(f"Done: {n} records in {out / 'training'}")


if __name__ == "__main__":
    main()
