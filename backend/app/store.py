"""Audit log of every alarm review: what the AI said, what the tech decided, what the experts said.

Default: a local SQLite file (zero setup).
With DATABASE_URL=postgres://... it uses PostgreSQL and, if the TimescaleDB extension is
available (Tiger Data / Tiger Cloud, or the timescale/timescaledb Docker image), turns the table
into a hypertable and uses time_bucket() for the per-minute review stats.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import threading
from pathlib import Path

from . import config

SCHEMA_COLS = ("ts", "alarm_id", "alarm_type", "p_true", "ai_verdict", "tech_decision", "expert_label",
               "tech_agrees_expert", "ai_agrees_expert", "seconds_to_decision")


class Store:
    kind = "sqlite"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.timescale = False
        if config.DATABASE_URL.startswith(("postgres://", "postgresql://")):
            import time

            import psycopg

            self.kind = "postgres"
            for attempt in range(15):  # the database container may still be starting
                try:
                    self._pg = psycopg.connect(config.DATABASE_URL, autocommit=True, connect_timeout=5)
                    break
                except psycopg.OperationalError:
                    if attempt == 14:
                        raise
                    time.sleep(2)
            with self._pg.cursor() as cur:
                try:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
                    self.timescale = True
                except Exception:
                    self.timescale = False
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS alarm_reviews (
                        ts TIMESTAMPTZ NOT NULL DEFAULT now(),
                        alarm_id TEXT NOT NULL, alarm_type TEXT NOT NULL,
                        p_true DOUBLE PRECISION, ai_verdict TEXT, tech_decision TEXT,
                        expert_label TEXT, tech_agrees_expert BOOLEAN, ai_agrees_expert BOOLEAN,
                        seconds_to_decision DOUBLE PRECISION)""")
                if self.timescale:
                    cur.execute("SELECT create_hypertable('alarm_reviews', 'ts', if_not_exists => TRUE)")
        else:
            config.SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(str(config.SQLITE_PATH), check_same_thread=False, timeout=10)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS alarm_reviews (
                    ts TEXT NOT NULL, alarm_id TEXT NOT NULL, alarm_type TEXT NOT NULL,
                    p_true REAL, ai_verdict TEXT, tech_decision TEXT, expert_label TEXT,
                    tech_agrees_expert INTEGER, ai_agrees_expert INTEGER, seconds_to_decision REAL)""")
            self._db.commit()

    @property
    def label(self) -> str:
        if self.kind == "postgres":
            return "TimescaleDB" if self.timescale else "PostgreSQL"
        return "SQLite"

    def log(self, row: dict) -> None:
        row = {k: row.get(k) for k in SCHEMA_COLS}
        row["ts"] = row["ts"] or dt.datetime.now(dt.timezone.utc)
        with self._lock:
            if self.kind == "postgres":
                with self._pg.cursor() as cur:
                    cur.execute(f"INSERT INTO alarm_reviews ({', '.join(SCHEMA_COLS)}) "
                                f"VALUES ({', '.join(['%s'] * len(SCHEMA_COLS))})",
                                [row[k] for k in SCHEMA_COLS])
            else:
                row["ts"] = row["ts"].isoformat()
                self._db.execute(f"INSERT INTO alarm_reviews ({', '.join(SCHEMA_COLS)}) "
                                 f"VALUES ({', '.join(['?'] * len(SCHEMA_COLS))})",
                                 [row[k] for k in SCHEMA_COLS])
                self._db.commit()

    def stats(self) -> dict:
        with self._lock:
            if self.kind == "postgres":
                bucket = "time_bucket('1 minute', ts)" if self.timescale else "date_trunc('minute', ts)"
                with self._pg.cursor() as cur:
                    cur.execute("""SELECT count(*), count(*) FILTER (WHERE ai_verdict='likely_artifact'),
                                   avg(ai_agrees_expert::int), avg(tech_agrees_expert::int),
                                   avg(seconds_to_decision) FROM alarm_reviews""")
                    tot = cur.fetchone()
                    cur.execute(f"""SELECT {bucket} AS b, count(*),
                                    count(*) FILTER (WHERE ai_verdict='likely_artifact')
                                    FROM alarm_reviews WHERE ts > now() - interval '60 minutes'
                                    GROUP BY b ORDER BY b""")
                    series = [{"t": r[0].isoformat(), "reviews": r[1], "flagged_artifact": r[2]}
                              for r in cur.fetchall()]
            else:
                cur = self._db.execute("""SELECT count(*), sum(ai_verdict='likely_artifact'),
                                          avg(ai_agrees_expert), avg(tech_agrees_expert),
                                          avg(seconds_to_decision) FROM alarm_reviews""")
                tot = cur.fetchone()
                since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=60)).isoformat()
                cur = self._db.execute("""SELECT substr(ts, 1, 16) AS b, count(*), sum(ai_verdict='likely_artifact')
                                          FROM alarm_reviews WHERE ts > ? GROUP BY b ORDER BY b""", (since,))
                series = [{"t": r[0], "reviews": r[1], "flagged_artifact": r[2] or 0} for r in cur.fetchall()]
        n = tot[0] or 0
        return {
            "backend": self.label, "reviews": n, "flagged_artifact": int(tot[1] or 0),
            "ai_agreement_with_experts": None if not n or tot[2] is None else float(tot[2]),
            "tech_agreement_with_experts": None if not n or tot[3] is None else float(tot[3]),
            "avg_seconds_to_decision": None if not n or tot[4] is None else float(tot[4]),
            "per_minute": series,
        }
