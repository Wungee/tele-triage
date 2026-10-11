"""Download the PhysioNet/CinC Challenge 2015 training set (~323 MB, open access, ODC-By 1.0).

    python scripts/download_data.py            # -> <repo>/data/training/*.hea, *.mat, RECORDS

Safe to interrupt: if the connection drops (or you close the laptop), just run it again and it
resumes from where it stopped. A partial download is never treated as a finished zip.

Dataset: https://physionet.org/content/challenge-2015/1.0.0/
Cite: Clifford GD, Silva I, Moody B, et al. The PhysioNet/Computing in Cardiology Challenge 2015:
Reducing False Arrhythmia Alarms in the ICU. Computing in Cardiology 2015;42:273-276.
"""

from __future__ import annotations

import argparse
import http.client
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

URL = "https://physionet.org/files/challenge-2015/1.0.0/training.zip"
ROOT = Path(__file__).resolve().parents[2]
RETRYABLE = (urllib.error.URLError, http.client.HTTPException, TimeoutError, ConnectionError, OSError)


def fetch(url: str, part: Path) -> None:
    """Download into `part`, resuming if it already holds some bytes. Raises on incomplete."""
    have = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
    try:
        r = urllib.request.urlopen(req, timeout=60)  # a dead connection errors out instead of hanging
    except urllib.error.HTTPError as e:
        if e.code == 416:  # range not satisfiable: we already have the whole file
            return
        raise
    with r:
        if have and r.status == 200:  # server ignored the Range header: start over
            have = 0
        mode = "ab" if have else "wb"
        total = have + int(r.headers.get("Content-Length") or 0)
        done = have
        if have:
            print(f"  resuming at {have / 1e6:.1f} MB")
        with open(part, mode) as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    sys.stdout.write(f"\r  {done / 1e6:7.1f} / {total / 1e6:.1f} MB  ({100 * done / total:5.1f}%)")
                    sys.stdout.flush()
        print()
        if total and done < total:
            raise ConnectionError(f"connection closed at {done / 1e6:.1f} of {total / 1e6:.1f} MB")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data"), help="directory to extract into (default: <repo>/data)")
    ap.add_argument("--url", default=URL)
    ap.add_argument("--retries", type=int, default=20)
    ap.add_argument("--keep-zip", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "training" / "RECORDS").exists():
        n = len((out / "training" / "RECORDS").read_text().split())
        print(f"Already have {n} records in {out / 'training'} - nothing to do.")
        return

    zpath = out / "training.zip"
    part = out / "training.zip.part"
    if zpath.exists() and not zipfile.is_zipfile(zpath):
        # left behind by an older version of this script after an interrupted download
        print(f"{zpath.name} is incomplete; resuming it instead of extracting.")
        zpath.replace(part)

    if not zpath.exists():
        print(f"Downloading {args.url}\n  -> {part} (about 323 MB; safe to interrupt and re-run)")
        for attempt in range(1, args.retries + 1):
            try:
                fetch(args.url, part)
                break
            except RETRYABLE as e:
                if attempt == args.retries:
                    raise SystemExit(f"\nStill failing after {attempt} tries ({e}). "
                                     "Check your connection and run the same command again; it will resume.")
                wait = min(30, 2 * attempt)
                print(f"\n  ! {e}. Retrying in {wait}s (attempt {attempt + 1}/{args.retries}) ...")
                time.sleep(wait)
        if not zipfile.is_zipfile(part):
            part.unlink(missing_ok=True)
            raise SystemExit("Downloaded file is not a valid zip (corrupted). Deleted it - run the command again.")
        part.replace(zpath)

    print(f"Extracting {zpath} ...")
    with zipfile.ZipFile(zpath) as z:
        bad = z.testzip()
        if bad:
            raise SystemExit(f"{zpath.name} is corrupted ({bad}). Delete it and run the command again.")
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